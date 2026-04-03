"""
LLM 响应查询工具 - 带手动触发 Query
"""
import os
import re
import sys
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response

# Add parent directory to path so we can import geo_tracker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://genpano:genpano2026@localhost:5432/genpano"
)

match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", DATABASE_URL)
if match:
    DB_USER = match.group(1)
    DB_PASS = match.group(2)
    DB_HOST = match.group(3)
    DB_PORT = match.group(4)
    DB_NAME = match.group(5)
else:
    DB_USER = "genpano"
    DB_PASS = "genpano2026"
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DB_NAME = "genpano"

# HTML debug files directory
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "/data/screenshots")

# Celery setup
HAS_CELERY = False
celery_app = None
try:
    from celery import Celery
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    celery_app = Celery(
        "geo_tracker",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        broker_connection_retry_on_startup=True,
    )
    HAS_CELERY = True
except Exception as e:
    print(f"Celery not available: {e}")


def _ensure_citations_column():
    """确保 llm_responses 表有 citations_json 和 response_html 列"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS citations_json JSONB
                """)
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS response_html TEXT
                """)
                # cookies 时间追踪字段
                cur.execute("""
                    ALTER TABLE llm_accounts
                    ADD COLUMN IF NOT EXISTS cookies_updated_at TIMESTAMP
                """)
                # query 关联的账号
                cur.execute("""
                    ALTER TABLE queries
                    ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES llm_accounts(id)
                """)
            conn.commit()
            print("DB migration: citations_json + response_html + cookies_updated_at columns ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def get_db():
    import psycopg2
    import time
    last_err = None
    for attempt in range(5):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                dbname=DB_NAME,
                connect_timeout=5,
            )
            return conn
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(2 ** attempt)  # 1, 2, 4, 8, 16 秒
    raise last_err


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>LLM Query Monitor</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1600px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }
        h2 { color: #333; margin: 20px 0 10px; font-size: 18px; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .filter-row { display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-end; }
        .form-row { display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-start; }
        .form-group { display: flex; flex-direction: column; gap: 5px; flex: 1; min-width: 200px; }
        .form-group label { font-size: 12px; color: #666; font-weight: 600; }
        .form-group select, .form-group input, .form-group textarea { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-family: inherit; font-size: 14px; }
        .form-group textarea { min-height: 80px; resize: vertical; }
        button { padding: 8px 20px; background: #4f46e5; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
        button:hover { background: #4338ca; }
        button.secondary { background: #6b7280; }
        button.secondary:hover { background: #4b5563; }
        button.success { background: #059669; }
        button.success:hover { background: #047857; }
        button.danger { background: #dc2626; }
        button.danger:hover { background: #b91c1c; }
        button.small { padding: 4px 10px; font-size: 12px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat-card { background: white; padding: 15px 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 28px; font-weight: 700; color: #4f46e5; }
        .stat-value.failed { color: #dc2626; }
        .stat-value.pending { color: #d97706; }
        .stat-value.done { color: #059669; }
        .stat-label { font-size: 12px; color: #666; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8fafc; font-weight: 600; color: #374151; font-size: 13px; }
        td { font-size: 14px; color: #4b5563; }
        tr:hover { background: #f9fafb; }
        .status-DONE { color: #059669; font-weight: 600; }
        .status-PENDING { color: #d97706; font-weight: 600; }
        .status-FAILED { color: #dc2626; font-weight: 600; }
        .status-RUNNING { color: #2563eb; font-weight: 600; }
        .llm-badge { display: inline-block; padding: 2px 8px; background: #e0e7ff; color: #4f46e5; border-radius: 999px; font-size: 12px; font-weight: 600; }
        .text-preview { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
        .html-link { color: #059669; cursor: pointer; text-decoration: underline; font-size: 12px; }
        .html-link:hover { color: #047857; }
        .html-viewer { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 4px; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6; overflow-x: auto; white-space: pre-wrap; word-break: break-all; max-height: 70vh; overflow-y: auto; }
        .html-search { display: flex; gap: 8px; margin-bottom: 10px; }
        .html-search input { flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
        .html-search span { font-size: 12px; color: #666; align-self: center; }
        mark { background: #ff0; color: #000; }
        /* Tabs */
        .tab-container { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .tab-header { padding: 0 20px; border-bottom: 2px solid #e5e7eb; }
        .tabs { display: flex; gap: 0; }
        .tab-btn { padding: 12px 24px; background: none; color: #6b7280; border: none; border-bottom: 3px solid transparent; border-radius: 0; cursor: pointer; font-weight: 600; font-size: 15px; margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; }
        .tab-btn:hover { color: #4f46e5; background: none; }
        .tab-btn.active { color: #4f46e5; border-bottom-color: #4f46e5; background: none; }
        .tab-content { padding: 20px; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }
        /* Pagination */
        .pagination { display: flex; justify-content: center; gap: 6px; margin-top: 20px; flex-wrap: wrap; }
        .pagination button { background: white; color: #4f46e5; border: 1px solid #ddd; min-width: 36px; padding: 6px 10px; font-size: 13px; }
        .pagination button:hover:not(:disabled) { background: #f0f0ff; }
        .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
        .pagination button.active { background: #4f46e5; color: white; border-color: #4f46e5; }
        /* Modal */
        .modal-backdrop { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 1000; }
        .modal-backdrop.show { display: flex; align-items: center; justify-content: center; }
        .modal { background: white; border-radius: 8px; max-width: 1200px; max-height: 90vh; width: 95%; overflow: hidden; display: flex; flex-direction: column; }
        .modal.large { max-width: 1600px; }
        .modal-header { padding: 15px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .modal-header h3 { margin: 0; }
        .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #666; padding: 0; width: 30px; height: 30px; }
        .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
        .modal-body pre { background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
        .modal-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .modal-meta-item { background: #f8fafc; padding: 10px 15px; border-radius: 4px; }
        .modal-meta-label { font-size: 12px; color: #666; margin-bottom: 4px; }
        .modal-meta-value { font-weight: 600; color: #333; }
        .refresh-btn { margin-left: 10px; }
        .auto-refresh { display: flex; align-items: center; gap: 10px; margin-left: auto; }
        .auto-refresh label { font-size: 14px; color: #666; display: flex; align-items: center; gap: 5px; }
        .alert { padding: 12px 16px; border-radius: 4px; margin-bottom: 15px; }
        .alert.success { background: #dcfce7; color: #166534; }
        .alert.error { background: #fee2e2; color: #991b1b; }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
            <h1>LLM Query Monitor</h1>
            <button class="secondary refresh-btn" onclick="loadStats(); loadQueries();">Refresh</button>
            <button class="secondary refresh-btn" onclick="backfillCitations()">Backfill Citations</button>
            <div class="auto-refresh">
                <label><input type="checkbox" id="auto-refresh" onchange="toggleAutoRefresh()"> Auto-refresh (5s)</label>
            </div>
        </div>

        <div class="stats" id="stats">
            <div class="stat-card"><div class="stat-value" id="total-queries">-</div><div class="stat-label">Total Queries</div></div>
            <div class="stat-card"><div class="stat-value done" id="done-queries">-</div><div class="stat-label">Done</div></div>
            <div class="stat-card"><div class="stat-value pending" id="pending-queries">-</div><div class="stat-label">Pending</div></div>
            <div class="stat-card"><div class="stat-value" id="running-queries">-</div><div class="stat-label">Running</div></div>
            <div class="stat-card"><div class="stat-value failed" id="failed-queries">-</div><div class="stat-label">Failed</div></div>
        </div>

        <!-- Create New Query Section -->
        <div class="card">
            <h2>Create New Query</h2>
            <div id="create-alert"></div>
            <form id="create-form" onsubmit="createQuery(event)">
                <div class="form-row">
                    <div class="form-group">
                        <label>LLM *</label>
                        <select id="new-llm" required>
                            <option value="">Select LLM</option>
                            <option value="chatgpt">ChatGPT</option>
                            <option value="gemini" selected>Gemini</option>
                            <option value="claude">Claude</option>
                            <option value="perplexity">Perplexity</option>
                            <option value="grok">Grok</option>
                            <option value="kimi">Kimi</option>
                            <option value="doubao">Doubao</option>
                            <option value="zhipu">Zhipu</option>
                            <option value="deepseek">DeepSeek</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Brand ID (optional)</label>
                        <input type="number" id="new-brand" placeholder="Brand ID">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 10px;">
                    <div class="form-group" style="flex: 3;">
                        <label>Query Text *</label>
                        <textarea id="new-query" placeholder="Enter your query here..." required></textarea>
                    </div>
                </div>
                <div style="margin-top: 15px; display: flex; gap: 10px;">
                    <button type="submit" class="success">Create &amp; Queue Query</button>
                    <button type="button" class="secondary" onclick="fillExample()">Fill Example</button>
                </div>
            </form>
        </div>

        <!-- Filters -->
        <div class="card">
            <h2>Filters</h2>
            <div class="filter-row">
                <div class="form-group">
                    <label>LLM</label>
                    <select id="filter-llm">
                        <option value="">All</option>
                        <option value="chatgpt">ChatGPT</option>
                        <option value="gemini">Gemini</option>
                        <option value="claude">Claude</option>
                        <option value="perplexity">Perplexity</option>
                        <option value="grok">Grok</option>
                        <option value="kimi">Kimi</option>
                        <option value="doubao">Doubao</option>
                        <option value="zhipu">Zhipu</option>
                        <option value="deepseek">DeepSeek</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Status</label>
                    <select id="filter-status">
                        <option value="">All</option>
                        <option value="DONE">Done</option>
                        <option value="PENDING">Pending</option>
                        <option value="RUNNING">Running</option>
                        <option value="FAILED">Failed</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Query ID</label>
                    <input type="number" id="filter-id" placeholder="Query ID">
                </div>
                <div class="form-group">
                    <label>Brand ID</label>
                    <input type="number" id="filter-brand" placeholder="Brand ID">
                </div>
                <div class="form-group">
                    <label>Limit</label>
                    <select id="filter-limit">
                        <option value="20">20</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Sort by</label>
                    <select id="filter-sort">
                        <option value="id_desc">ID (newest first)</option>
                        <option value="id_asc">ID (oldest first)</option>
                        <option value="status">Status</option>
                    </select>
                </div>
                <button onclick="currentPage=1; loadQueries();">Search</button>
            </div>
        </div>

        <!-- Tabs: Queries / Debug HTML Files -->
        <div class="tab-container">
            <div class="tab-header">
                <div class="tabs">
                    <button class="tab-btn active" id="tab-queries-btn" onclick="switchTab('queries')">Queries</button>
                    <button class="tab-btn" id="tab-accounts-btn" onclick="switchTab('accounts')">Accounts</button>
                    <button class="tab-btn" id="tab-segments-btn" onclick="switchTab('segments')">Segments</button>
                    <button class="tab-btn" id="tab-profiles-btn" onclick="switchTab('profiles')">Profiles</button>
                    <button class="tab-btn" id="tab-html-btn" onclick="switchTab('html')">Debug HTML Files</button>
                </div>
            </div>
            <div class="tab-content">
                <!-- Queries Tab -->
                <div class="tab-panel active" id="tab-queries">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>LLM</th>
                                <th>Status</th>
                                <th>Profile</th>
                                <th>Account</th>
                                <th>Retry</th>
                                <th>Query</th>
                                <th>Citations</th>
                                <th>Brand</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="results-body">
                        </tbody>
                    </table>
                    <div class="pagination" id="pagination"></div>
                </div>

                <!-- Accounts Tab -->
                <div class="tab-panel" id="tab-accounts">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">LLM Accounts</h3>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="secondary small" onclick="loadAccounts();">Refresh</button>
                            <button class="success small" onclick="showCookieUpload();">Upload Cookies</button>
                            <button class="small" style="background:#7c3aed;color:#fff;border:none;" onclick="showSmsRegister();">SMS Register</button>
                        </div>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Platform</th>
                                <th>Phone</th>
                                <th>Status</th>
                                <th>Daily Used / Limit</th>
                                <th>Fails</th>
                                <th>Cookies</th>
                                <th>Cookie Age</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="accounts-body"></tbody>
                    </table>

                    <!-- Cookie Upload Form (hidden by default) -->
                    <div id="cookie-upload-form" style="display:none; margin-top:20px; padding:20px; background:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
                        <h4 style="margin:0 0 12px; font-size:15px;">Upload Cookies</h4>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Platform</label>
                                <select id="cookie-platform">
                                    <option value="doubao">Doubao (豆包)</option>
                                    <option value="deepseek">DeepSeek</option>
                                    <option value="gemini">Gemini</option>
                                    <option value="chatgpt">ChatGPT</option>
                                    <option value="kimi">Kimi</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Account Label (optional)</label>
                                <input type="text" id="cookie-label" placeholder="e.g. phone number or email">
                            </div>
                            <div class="form-group">
                                <label>Daily Limit</label>
                                <input type="number" id="cookie-daily-limit" value="20" min="1">
                            </div>
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label>Cookies JSON (paste EditThisCookie export or Playwright format)</label>
                            <textarea id="cookie-json" style="min-height:150px; font-family:monospace; font-size:12px;" placeholder='Paste cookies JSON here...'></textarea>
                        </div>
                        <div style="margin-top:8px; display:flex; gap:8px; align-items:center;">
                            <label style="cursor:pointer; padding:8px 16px; background:#e5e7eb; border-radius:4px; font-size:13px;">
                                Or upload .json file
                                <input type="file" id="cookie-file" accept=".json" style="display:none;" onchange="loadCookieFile(this)">
                            </label>
                            <div style="flex:1;"></div>
                            <button class="secondary" onclick="hideCookieUpload();">Cancel</button>
                            <button class="success" onclick="submitCookies();">Import</button>
                        </div>
                    </div>

                    <!-- SMS Register Form (hidden by default) -->
                    <div id="sms-register-form" style="display:none; margin-top:20px; padding:20px; background:#f5f3ff; border-radius:8px; border:1px solid #ddd6fe;">
                        <h4 style="margin:0 0 12px; font-size:15px; color:#7c3aed;">SMS Auto Register / Login</h4>
                        <div class="form-row" style="align-items:flex-end;">
                            <div class="form-group">
                                <label>Platform</label>
                                <select id="sms-platform">
                                    <option value="doubao">Doubao</option>
                                    <option value="deepseek">DeepSeek</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <button style="background:#7c3aed;color:#fff;border:none;padding:8px 20px;border-radius:4px;cursor:pointer;font-size:13px;" onclick="triggerSmsRegister();">Register New Account</button>
                            </div>
                            <div class="form-group">
                                <button class="secondary" onclick="hideSmsRegister();">Cancel</button>
                            </div>
                        </div>
                        <div id="sms-task-status" style="margin-top:12px; display:none; padding:12px; background:#fff; border-radius:6px; border:1px solid #e5e7eb; font-size:13px;"></div>
                    </div>
                </div>

                <!-- Segments Tab -->
                <div class="tab-panel" id="tab-segments">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">Segment Definitions</h3>
                        <button class="secondary small" onclick="loadSegments();">Refresh</button>
                    </div>
                    <div id="segments-body">
                        <div style="color:#999; font-size:13px;">Loading...</div>
                    </div>
                </div>

                <!-- Profiles Tab -->
                <div class="tab-panel" id="tab-profiles">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">User Profiles</h3>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="secondary small" onclick="loadProfiles();">Refresh</button>
                            <button class="success small" onclick="showProfileForm();">+ New Profile</button>
                        </div>
                    </div>

                    <!-- Profile Create/Edit Form (hidden by default) -->
                    <div id="profile-form-container" style="display:none; margin-bottom:20px; padding:20px; background:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
                        <h4 style="margin:0 0 12px; font-size:15px;" id="profile-form-title">Create New Profile</h4>
                        <div id="profile-alert"></div>
                        <form id="profile-form" onsubmit="submitProfile(event)">
                            <input type="hidden" id="profile-edit-id">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Name *</label>
                                    <input type="text" id="profile-name" placeholder="e.g. 张明" required>
                                </div>
                                <div class="form-group">
                                    <label>Age Range</label>
                                    <input type="text" id="profile-age-range" placeholder="e.g. 25-34">
                                </div>
                                <div class="form-group">
                                    <label>Location</label>
                                    <input type="text" id="profile-location" placeholder="e.g. Shanghai">
                                </div>
                                <div class="form-group">
                                    <label>Country Code</label>
                                    <input type="text" id="profile-country" placeholder="e.g. CN" maxlength="8">
                                </div>
                            </div>
                            <div class="form-row" style="margin-top:10px;">
                                <div class="form-group">
                                    <label>Profession</label>
                                    <input type="text" id="profile-profession" placeholder="e.g. Software Engineer">
                                </div>
                                <div class="form-group">
                                    <label>Language</label>
                                    <select id="profile-language">
                                        <option value="zh">Chinese (zh)</option>
                                        <option value="en">English (en)</option>
                                        <option value="zh_en">Bilingual (zh_en)</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Device Type</label>
                                    <select id="profile-device">
                                        <option value="desktop">Desktop</option>
                                        <option value="mobile">Mobile</option>
                                    </select>
                                </div>
                            </div>
                            <div class="form-row" style="margin-top:10px;">
                                <div class="form-group">
                                    <label>Tone</label>
                                    <select id="profile-tone">
                                        <option value="casual">Casual</option>
                                        <option value="semi_formal">Semi-formal</option>
                                        <option value="formal">Formal</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Verbosity</label>
                                    <select id="profile-verbosity">
                                        <option value="short">Short</option>
                                        <option value="medium">Medium</option>
                                        <option value="long">Long</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Search Style</label>
                                    <select id="profile-search-style">
                                        <option value="solution_oriented">Solution Oriented</option>
                                        <option value="comparison">Comparison</option>
                                        <option value="exploratory">Exploratory</option>
                                    </select>
                                </div>
                            </div>
                            <div style="margin-top:15px; display:flex; gap:10px;">
                                <button type="submit" class="success">Save Profile</button>
                                <button type="button" class="secondary" onclick="hideProfileForm();">Cancel</button>
                            </div>
                        </form>
                    </div>

                    <!-- Profile Filters -->
                    <div style="display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; align-items:flex-end;">
                        <div class="form-group" style="min-width:150px; flex:0;">
                            <label>Segment</label>
                            <select id="profile-filter-segment" onchange="filterProfiles()">
                                <option value="">All Segments</option>
                            </select>
                        </div>
                        <div class="form-group" style="min-width:120px; flex:0;">
                            <label>Language</label>
                            <select id="profile-filter-lang" onchange="filterProfiles()">
                                <option value="">All</option>
                                <option value="zh">zh</option>
                                <option value="en">en</option>
                            </select>
                        </div>
                        <div class="form-group" style="min-width:120px; flex:0;">
                            <label>Device</label>
                            <select id="profile-filter-device" onchange="filterProfiles()">
                                <option value="">All</option>
                                <option value="desktop">Desktop</option>
                                <option value="mobile">Mobile</option>
                            </select>
                        </div>
                        <span id="profile-count-label" style="font-size:12px; color:#888; padding-bottom:8px;"></span>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Segment</th>
                                <th>Age Range</th>
                                <th>Location</th>
                                <th>Country</th>
                                <th>Profession</th>
                                <th>Language</th>
                                <th>Device</th>
                                <th>Tone / Verbosity / Style</th>
                                <th>Queries</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="profiles-body">
                        </tbody>
                    </table>
                    <div class="pagination" id="profiles-pagination"></div>
                </div>

                <!-- Debug HTML Files Tab -->
                <div class="tab-panel" id="tab-html">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
                        <span style="color:#666;font-size:14px;">HTML debug files from /data/screenshots</span>
                        <button class="secondary small" onclick="loadHtmlFiles();">Refresh</button>
                    </div>
                    <div id="html-files-body">
                        <div style="color:#999; font-size:13px;">Loading...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Query Detail Modal -->
    <div class="modal-backdrop" id="modal-backdrop" onclick="if(event.target === this) closeModal()">
        <div class="modal" id="modal">
            <div class="modal-header">
                <h3 id="modal-title">Response Details</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body"></div>
        </div>
    </div>

    <!-- HTML Source Modal -->
    <div class="modal-backdrop" id="html-modal" onclick="if(event.target === this) closeHtmlModal()">
        <div class="modal large" style="max-width:1400px;">
            <div class="modal-header">
                <h3 id="html-modal-title">HTML Source</h3>
                <button class="modal-close" onclick="closeHtmlModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="html-search">
                    <input type="text" id="html-search-input" placeholder="Search in HTML..." oninput="searchHtml(this.value)">
                    <span id="html-search-count"></span>
                    <button class="secondary small" onclick="searchHtml(document.getElementById('html-search-input').value)">Find</button>
                    <button class="secondary small" onclick="document.getElementById('html-search-input').value=''; searchHtml('')">Clear</button>
                </div>
                <div class="html-viewer" id="html-viewer-content"></div>
            </div>
        </div>
    </div>

    <script>
        let currentPage = 1;
        let totalCount = 0;
        let currentData = [];
        let autoRefreshInterval = null;
        let rawHtmlContent = '';

        // ---- Tab switcher ----
        function switchTab(tab) {
            ['queries', 'accounts', 'segments', 'profiles', 'html'].forEach(t => {
                document.getElementById('tab-' + t).classList.toggle('active', tab === t);
                document.getElementById('tab-' + t + '-btn').classList.toggle('active', tab === t);
            });
            if (tab === 'html') loadHtmlFiles();
            if (tab === 'accounts') loadAccounts();
            if (tab === 'segments') loadSegments();
            if (tab === 'profiles') loadProfiles();
        }

        // ---- Stats ----
        async function loadStats() {
            const res = await fetch('./api/stats');
            const data = await res.json();
            document.getElementById('total-queries').textContent = data.total;
            document.getElementById('done-queries').textContent = data.done;
            document.getElementById('pending-queries').textContent = data.pending;
            document.getElementById('running-queries').textContent = data.running;
            document.getElementById('failed-queries').textContent = data.failed;
        }

        // ---- Queries ----
        async function loadQueries() {
            const llm = document.getElementById('filter-llm').value;
            const status = document.getElementById('filter-status').value;
            const brand = document.getElementById('filter-brand').value;
            const queryId = document.getElementById('filter-id').value;
            const limit = parseInt(document.getElementById('filter-limit').value);
            const sort = document.getElementById('filter-sort').value;

            const params = new URLSearchParams();
            if (llm) params.append('llm', llm);
            if (status) params.append('status', status);
            if (brand) params.append('brand_id', brand);
            if (queryId) params.append('id', queryId);
            params.append('limit', limit);
            params.append('offset', (currentPage - 1) * limit);
            params.append('sort', sort);
            params.append('count', '1');

            const res = await fetch('./api/queries?' + params.toString());
            const json = await res.json();
            if (json && json.rows !== undefined) {
                currentData = json.rows;
                totalCount = json.total;
            } else {
                currentData = json;
                totalCount = json.length;
            }
            renderTable(currentData);
            renderPagination(limit);
        }

        function renderTable(data) {
            const tbody = document.getElementById('results-body');
            tbody.innerHTML = data.map(q => {
                const statusUp = (q.status || '').toUpperCase();
                const profileInfo = q.profile_name
                    ? `<span title="ID:${q.profile_id} ${q.profile_location || ''}">${q.profile_name}${q.profile_country ? ' (' + q.profile_country + ')' : ''}</span>`
                    : '<span style="color:#999;">-</span>';
                const accountInfo = q.account_id
                    ? `<span title="Account #${q.account_id}">${q.account_label || '#' + q.account_id}</span>`
                    : '<span style="color:#999;">-</span>';
                return `
                <tr>
                    <td>${q.id}</td>
                    <td><span class="llm-badge">${q.target_llm}</span></td>
                    <td><span class="status-${statusUp}">${statusUp}</span></td>
                    <td style="font-size:12px;">${profileInfo}</td>
                    <td style="font-size:12px;">${accountInfo}</td>
                    <td>${q.retry_count || 0}</td>
                    <td class="text-preview" title="${escapeHtml(q.query_text)}" onclick="showResponse(${q.id})">${escapeHtml(q.query_text || '')}</td>
                    <td>${q.citations && q.citations.length ? q.citations.length : '-'}</td>
                    <td>${q.brand_id || '-'}</td>
                    <td>${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</td>
                    <td>
                        <button class="secondary small" onclick="showResponse(${q.id})">View</button>
                        ${statusUp === 'FAILED' || statusUp === 'PENDING' ?
                            `<button class="success small" onclick="retryQuery(${q.id})">Retry</button>` : ''}
                        ${statusUp === 'DONE' ?
                            `<button class="danger small" onclick="markFailed(${q.id})">Mark Failed</button>` : ''}
                    </td>
                </tr>`;
            }).join('');
        }

        function renderPagination(limit) {
            const pag = document.getElementById('pagination');
            if (!totalCount || totalCount <= limit) {
                pag.innerHTML = '';
                return;
            }
            const totalPages = Math.ceil(totalCount / limit);
            const page = currentPage;

            let startPage = Math.max(1, page - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) {
                startPage = Math.max(1, endPage - 4);
            }

            let html = '';
            html += `<button ${page === 1 ? 'disabled' : ''} onclick="goToPage(${page - 1})">&laquo; Prev</button>`;
            for (let p = startPage; p <= endPage; p++) {
                html += `<button class="${p === page ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
            }
            html += `<button ${page === totalPages ? 'disabled' : ''} onclick="goToPage(${page + 1})">Next &raquo;</button>`;
            pag.innerHTML = html;
        }

        function goToPage(page) {
            currentPage = page;
            loadQueries();
        }

        async function showResponse(id) {
            const q = currentData.find(x => x.id === id);
            if (!q) return;

            const statusUp = (q.status || '').toUpperCase();
            document.getElementById('modal-title').textContent = `Query #${q.id} - ${q.target_llm}`;
            const statusClass = `status-${statusUp}`;
            document.getElementById('modal-body').innerHTML = `
                <div class="modal-meta">
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Status</div>
                        <div class="modal-meta-value ${statusClass}">${statusUp}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">LLM</div>
                        <div class="modal-meta-value">${q.target_llm}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Retry Count</div>
                        <div class="modal-meta-value">${q.retry_count || 0}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Brand ID</div>
                        <div class="modal-meta-value">${q.brand_id || '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Profile</div>
                        <div class="modal-meta-value">${q.profile_name ? q.profile_name + (q.profile_country ? ' (' + q.profile_country + ')' : '') : '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Account</div>
                        <div class="modal-meta-value">${q.account_id ? (q.account_label || '#' + q.account_id) : '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Created</div>
                        <div class="modal-meta-value">${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</div>
                    </div>
                    ${q.executed_at ? `
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Executed</div>
                        <div class="modal-meta-value">${new Date(q.executed_at).toLocaleString()}</div>
                    </div>
                    ` : ''}
                    ${q.llm_version ? `
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">LLM Version</div>
                        <div class="modal-meta-value">${q.llm_version}</div>
                    </div>
                    ` : ''}
                </div>
                <div class="modal-meta-item" style="margin-bottom:15px;">
                    <div class="modal-meta-label">Query</div>
                    <div class="modal-meta-value" style="font-weight: normal;"><pre>${escapeHtml(q.query_text || '')}</pre></div>
                </div>
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Response</div>
                    <pre>${escapeHtml(q.response || '(no response)')}</pre>
                </div>
                ${q.citations && q.citations.length ? `
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Citations (${q.citations.length})</div>
                    <div style="background:#1e1e2e;border:1px solid #333;border-radius:6px;padding:10px;">
                        ${q.citations.map((c, i) => `
                            <div style="margin-bottom:6px;font-size:13px;">
                                <span style="color:#888;">[${c.index || i+1}]</span>
                                <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener" style="color:#58a6ff;text-decoration:none;">${escapeHtml(c.title || c.url)}</a>
                            </div>
                        `).join('')}
                    </div>
                </div>
                ` : ''}
                ${statusUp === 'FAILED' || statusUp === 'PENDING' ? `
                <div style="margin-top: 20px;">
                    <button class="success" onclick="retryQuery(${q.id}); closeModal();">Retry This Query</button>
                </div>
                ` : ''}
                ${statusUp === 'DONE' ? `
                <div style="margin-top: 20px;">
                    <button class="danger" onclick="markFailed(${q.id}); closeModal();">Mark as Failed</button>
                </div>
                ` : ''}
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Debug HTML Files</div>
                    <div id="modal-html-files">Loading...</div>
                </div>
            `;
            document.getElementById('modal-backdrop').classList.add('show');

            // Load HTML files for this query
            fetch('./api/html_files?query_id=' + q.id).then(r => r.json()).then(files => {
                const el = document.getElementById('modal-html-files');
                if (!el) return;
                if (!files || !files.length) {
                    el.innerHTML = '<span style="color:#999;font-size:12px;">No HTML files found for this query</span>';
                    return;
                }
                el.innerHTML = files.map(f =>
                    '<div style="margin-bottom:4px;">' +
                    "<span class='html-link' onclick='showHtmlSource(" + JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")'>" + escapeHtml(f.name) + '</span>' +
                    ' <span style="color:#999;font-size:11px;">(' + (f.size / 1024).toFixed(1) + ' KB)</span>' +
                    '</div>'
                ).join('');
            }).catch(() => {
                const el = document.getElementById('modal-html-files');
                if (el) el.innerHTML = '<span style="color:#999;font-size:12px;">Failed to load HTML files</span>';
            });
        }

        function closeModal() {
            document.getElementById('modal-backdrop').classList.remove('show');
        }

        function toggleAutoRefresh() {
            const checkbox = document.getElementById('auto-refresh');
            if (checkbox.checked) {
                autoRefreshInterval = setInterval(() => {
                    loadStats();
                    loadQueries();
                }, 5000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function fillExample() {
            document.getElementById('new-llm').value = 'gemini';
            document.getElementById('new-query').value = 'Hello, please introduce yourself in one sentence.';
        }

        async function createQuery(event) {
            event.preventDefault();
            const alertDiv = document.getElementById('create-alert');
            alertDiv.innerHTML = '';

            const llm = document.getElementById('new-llm').value;
            const queryText = document.getElementById('new-query').value;
            const brandId = document.getElementById('new-brand').value;

            try {
                const res = await fetch('./api/queries', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        target_llm: llm,
                        query_text: queryText,
                        brand_id: brandId ? parseInt(brandId) : null
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alertDiv.innerHTML = `<div class="alert success">Query #${data.query_id} created successfully! It has been queued for execution.</div>`;
                    document.getElementById('create-form').reset();
                    loadStats();
                    loadQueries();
                } else {
                    alertDiv.innerHTML = `<div class="alert error">Error: ${data.error || 'Unknown error'}</div>`;
                }
            } catch (e) {
                alertDiv.innerHTML = `<div class="alert error">Error: ${e.message}</div>`;
            }
        }

        async function retryQuery(queryId) {
            try {
                const res = await fetch(`./api/queries/${queryId}/retry`, {
                    method: 'POST'
                });
                if (!res.ok) {
                    alert(`Server error: ${res.status} ${res.statusText}`);
                    return;
                }
                const text = await res.text();
                if (!text) {
                    alert('Error: Empty response from server');
                    return;
                }
                const data = JSON.parse(text);
                if (data.success) {
                    alert(`Query #${queryId} has been requeued!`);
                    loadStats();
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        async function markFailed(queryId) {
            if (!confirm(`确定将 Query #${queryId} 标记为 Failed？`)) return;
            try {
                const res = await fetch(`./api/queries/${queryId}/mark_failed`, {
                    method: 'POST'
                });
                if (!res.ok) {
                    alert(`Server error: ${res.status} ${res.statusText}`);
                    return;
                }
                const data = await res.json();
                if (data.success) {
                    alert(`Query #${queryId} 已标记为 Failed`);
                    loadStats();
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        // ---- Accounts ----
        function getCookieAgeInfo(cookiesUpdatedAt) {
            if (!cookiesUpdatedAt) return { text: 'Unknown', color: '#999', icon: '?' };
            const now = new Date();
            const updated = new Date(cookiesUpdatedAt);
            const hoursAgo = (now - updated) / (1000 * 60 * 60);
            const daysAgo = hoursAgo / 24;

            if (hoursAgo < 6) return { text: `${Math.round(hoursAgo)}h ago`, color: '#16a34a', icon: '&#9679;' };  // green
            if (hoursAgo < 24) return { text: `${Math.round(hoursAgo)}h ago`, color: '#f59e0b', icon: '&#9679;' };  // yellow
            if (daysAgo < 3) return { text: `${Math.round(daysAgo)}d ago`, color: '#f97316', icon: '&#9679;' };  // orange
            if (daysAgo < 7) return { text: `${Math.round(daysAgo)}d ago`, color: '#ef4444', icon: '&#9888;' };  // red warning
            return { text: `${Math.round(daysAgo)}d ago`, color: '#dc2626', icon: '&#9888;' };  // red expired
        }

        async function loadAccounts() {
            try {
                const res = await fetch('./api/accounts');
                const data = await res.json();
                const body = document.getElementById('accounts-body');
                if (!data.length) {
                    body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#999;">No accounts found</td></tr>';
                    return;
                }
                body.innerHTML = data.map(a => {
                    const statusCls = a.status === 'active' ? 'status-DONE' :
                                      a.status === 'banned' ? 'status-FAILED' : 'status-PENDING';
                    const cookieCount = a.cookie_count || 0;
                    const cookieAge = getCookieAgeInfo(a.cookies_updated_at);
                    const toggleLabel = a.status === 'active' ? 'Disable' : 'Enable';
                    const toggleClass = a.status === 'active' ? 'secondary' : 'success';
                    return `<tr>
                        <td>${a.id}</td>
                        <td><span class="llm-badge">${a.llm_name}</span></td>
                        <td>${a.phone_number || '-'}</td>
                        <td><span class="${statusCls}">${a.status.toUpperCase()}</span></td>
                        <td>${a.daily_used || 0} / ${a.daily_limit || 20}</td>
                        <td>${a.consecutive_fails || 0}</td>
                        <td>${cookieCount} cookies</td>
                        <td><span style="color:${cookieAge.color}; font-weight:500;" title="Last refreshed: ${a.cookies_updated_at || 'never'}">${cookieAge.icon} ${cookieAge.text}</span></td>
                        <td>
                            <button class="${toggleClass} small" onclick="toggleAccount(${a.id}, '${a.status}')">${toggleLabel}</button>
                            <button class="small" onclick="resetAccountFails(${a.id})">Reset</button>
                            <button class="small" style="background:#7c3aed;color:#fff;border:none;" onclick="triggerAutoLogin(${a.id})">Auto Login</button>
                            <button class="danger small" onclick="deleteAccount(${a.id})">Delete</button>
                        </td>
                    </tr>`;
                }).join('');
            } catch (e) {
                console.error('loadAccounts error:', e);
            }
        }

        async function toggleAccount(id, currentStatus) {
            const newStatus = currentStatus === 'active' ? 'banned' : 'active';
            try {
                const res = await fetch(`./api/accounts/${id}/status`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({status: newStatus})
                });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function resetAccountFails(id) {
            try {
                const res = await fetch(`./api/accounts/${id}/reset`, { method: 'POST' });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function deleteAccount(id) {
            if (!confirm(`确定删除账号 #${id}？此操作不可撤销。`)) return;
            try {
                const res = await fetch(`./api/accounts/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        function showCookieUpload() {
            document.getElementById('cookie-upload-form').style.display = 'block';
        }
        function hideCookieUpload() {
            document.getElementById('cookie-upload-form').style.display = 'none';
        }

        function loadCookieFile(input) {
            const file = input.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById('cookie-json').value = e.target.result;
            };
            reader.readAsText(file);
        }

        async function submitCookies() {
            const platform = document.getElementById('cookie-platform').value;
            const label = document.getElementById('cookie-label').value.trim();
            const dailyLimit = parseInt(document.getElementById('cookie-daily-limit').value) || 20;
            const jsonText = document.getElementById('cookie-json').value.trim();
            if (!jsonText) { alert('Please paste or upload cookies JSON'); return; }

            try {
                JSON.parse(jsonText);
            } catch (e) {
                alert('Invalid JSON: ' + e.message);
                return;
            }

            try {
                const res = await fetch('./api/accounts/import_cookies', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        platform: platform,
                        label: label,
                        daily_limit: dailyLimit,
                        cookies_json: jsonText,
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alert(data.message || 'Cookies imported successfully!');
                    document.getElementById('cookie-json').value = '';
                    document.getElementById('cookie-label').value = '';
                    hideCookieUpload();
                    loadAccounts();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        // ── SMS Register / Auto Login ──────────────────────────────
        function showSmsRegister() {
            document.getElementById('sms-register-form').style.display = 'block';
        }
        function hideSmsRegister() {
            document.getElementById('sms-register-form').style.display = 'none';
            document.getElementById('sms-task-status').style.display = 'none';
        }

        async function triggerSmsRegister() {
            const platform = document.getElementById('sms-platform').value;
            const statusDiv = document.getElementById('sms-task-status');
            statusDiv.style.display = 'block';
            statusDiv.innerHTML = '<span style="color:#7c3aed;">Triggering registration for ' + platform + '...</span>';
            try {
                const res = await fetch('./api/sms_register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({platform: platform})
                });
                const data = await res.json();
                if (data.success && data.task_id) {
                    pollTaskStatus(data.task_id, statusDiv);
                } else {
                    statusDiv.innerHTML = '<span style="color:#dc2626;">Error: ' + (data.error || 'Unknown') + '</span>';
                }
            } catch (e) {
                statusDiv.innerHTML = '<span style="color:#dc2626;">Error: ' + e.message + '</span>';
            }
        }

        async function triggerAutoLogin(accountId) {
            if (!confirm('Trigger auto SMS login for account #' + accountId + '?')) return;
            try {
                const res = await fetch('./api/accounts/' + accountId + '/auto_login', { method: 'POST' });
                const data = await res.json();
                if (data.success && data.task_id) {
                    alert('Auto login triggered! Task ID: ' + data.task_id + '\\nCheck task status in the SMS Register panel.');
                    // Show the status panel
                    document.getElementById('sms-register-form').style.display = 'block';
                    const statusDiv = document.getElementById('sms-task-status');
                    statusDiv.style.display = 'block';
                    statusDiv.innerHTML = '<span style="color:#7c3aed;">Auto login for account #' + accountId + ' started...</span>';
                    pollTaskStatus(data.task_id, statusDiv);
                } else {
                    alert('Error: ' + (data.error || 'Unknown'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function pollTaskStatus(taskId, statusDiv) {
            let attempts = 0;
            const maxAttempts = 60; // 3 minutes max (60 * 3s)
            const interval = setInterval(async () => {
                attempts++;
                if (attempts > maxAttempts) {
                    clearInterval(interval);
                    statusDiv.innerHTML = '<span style="color:#d97706;">Timeout: task is still running. Check worker logs.</span>';
                    return;
                }
                try {
                    const res = await fetch('./api/task_status/' + taskId);
                    const data = await res.json();
                    if (data.state === 'PENDING' || data.state === 'RECEIVED') {
                        statusDiv.innerHTML = '<span style="color:#7c3aed;">Waiting for worker to pick up task...</span>';
                    } else if (data.state === 'STARTED' || data.state === 'RETRY') {
                        statusDiv.innerHTML = '<span style="color:#2563eb;">Logging in... (SMS verification in progress)</span>';
                    } else if (data.state === 'SUCCESS') {
                        clearInterval(interval);
                        const r = data.result || {};
                        if (r.status === 'success') {
                            statusDiv.innerHTML = '<span style="color:#059669;">Login successful! Account #' + (r.account_id || '') + (r.phone ? ' (' + r.phone + ')' : '') + '</span>';
                        } else {
                            statusDiv.innerHTML = '<span style="color:#dc2626;">Task completed but login failed: ' + (r.reason || r.status || 'unknown') + '</span>';
                        }
                        loadAccounts();
                    } else if (data.state === 'FAILURE') {
                        clearInterval(interval);
                        statusDiv.innerHTML = '<span style="color:#dc2626;">Task failed: ' + (data.error || 'Unknown error') + '</span>';
                    }
                } catch (e) {
                    // Network error, keep polling
                }
            }, 3000);
        }

        async function backfillCitations() {
            try {
                const res = await fetch('./api/backfill_citations', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert(`Backfill complete: scanned ${data.scanned} responses, updated ${data.updated} with citations`);
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        // ---- HTML Files Viewer ----
        async function loadHtmlFiles(queryId) {
            const body = document.getElementById('html-files-body');
            body.innerHTML = '<div style="color:#999;font-size:13px;">Loading...</div>';
            const params = queryId ? '?query_id=' + queryId : '';
            const res = await fetch('./api/html_files' + params);
            const files = await res.json();
            if (!files.length) {
                body.innerHTML = '<div style="color:#999;font-size:13px;">No HTML debug files found in /data/screenshots</div>';
                return;
            }
            body.innerHTML = '<table style="font-size:13px;width:100%;"><thead><tr>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;">File</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;">Size</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;">Modified</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;">Action</th>' +
                '</tr></thead><tbody>' +
                files.map(f => {
                    const kb = (f.size / 1024).toFixed(1);
                    const dt = new Date(f.mtime * 1000).toLocaleString();
                    return '<tr>' +
                        '<td style="padding:6px 10px;font-family:monospace;max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(f.path) + '">' + escapeHtml(f.name) + '</td>' +
                        '<td style="padding:6px 10px;white-space:nowrap;">' + kb + ' KB</td>' +
                        '<td style="padding:6px 10px;white-space:nowrap;">' + dt + '</td>' +
                        "<td style='padding:6px 10px;'><span class='html-link' onclick='showHtmlSource(" + JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")'>View Source</span></td>" +
                        '</tr>';
                }).join('') + '</tbody></table>';
        }

        async function showHtmlSource(path, name) {
            document.getElementById('html-modal-title').textContent = name || path;
            document.getElementById('html-viewer-content').textContent = 'Loading...';
            document.getElementById('html-search-input').value = '';
            document.getElementById('html-search-count').textContent = '';
            document.getElementById('html-modal').classList.add('show');
            const res = await fetch('./api/html?path=' + encodeURIComponent(path));
            if (!res.ok) {
                rawHtmlContent = 'Error loading file: ' + res.status;
            } else {
                rawHtmlContent = await res.text();
            }
            document.getElementById('html-viewer-content').textContent = rawHtmlContent;
        }

        function searchHtml(term) {
            const viewer = document.getElementById('html-viewer-content');
            const countEl = document.getElementById('html-search-count');
            if (!term) {
                viewer.textContent = rawHtmlContent;
                countEl.textContent = '';
                return;
            }
            const escaped = term.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
            const regex = new RegExp(escaped, 'gi');
            const matches = rawHtmlContent.match(regex);
            const count = matches ? matches.length : 0;
            countEl.textContent = count + ' match' + (count !== 1 ? 'es' : '');
            if (count === 0) {
                viewer.textContent = rawHtmlContent;
                return;
            }
            const parts = rawHtmlContent.split(regex);
            const matchArr = rawHtmlContent.match(regex) || [];
            viewer.innerHTML = '';
            parts.forEach((part, i) => {
                viewer.appendChild(document.createTextNode(part));
                if (i < matchArr.length) {
                    const mark = document.createElement('mark');
                    mark.textContent = matchArr[i];
                    viewer.appendChild(mark);
                }
            });
            const firstMark = viewer.querySelector('mark');
            if (firstMark) firstMark.scrollIntoView({ block: 'center' });
        }

        function closeHtmlModal() {
            document.getElementById('html-modal').classList.remove('show');
        }

        // ---- Segments ----
        let segmentsData = [];
        let segCurrentPage = 1;
        const segPerPage = 5;

        async function loadSegments() {
            const body = document.getElementById('segments-body');
            body.innerHTML = '<div style="color:#999;font-size:13px;">Loading...</div>';
            try {
                const res = await fetch('./api/segments');
                const data = await res.json();
                if (data.error) {
                    body.innerHTML = '<div style="color:#dc2626;font-size:13px;">Error: ' + escapeHtml(data.error) + '</div>';
                    return;
                }
                if (!Array.isArray(data) || !data.length) {
                    body.innerHTML = '<div style="color:#999;font-size:13px;">No segments defined</div>';
                    return;
                }
                segmentsData = data;
                segCurrentPage = 1;
                renderSegments();
            } catch (e) {
                body.innerHTML = '<div style="color:#dc2626;font-size:13px;">Error loading segments: ' + escapeHtml(e.message) + '</div>';
            }
        }

        function renderSegments() {
            const totalPages = Math.ceil(segmentsData.length / segPerPage);
            if (segCurrentPage > totalPages) segCurrentPage = totalPages;
            if (segCurrentPage < 1) segCurrentPage = 1;
            const start = (segCurrentPage - 1) * segPerPage;
            const pageData = segmentsData.slice(start, start + segPerPage);

            const body = document.getElementById('segments-body');
            body.innerHTML = '<div style="margin-bottom:8px;font-size:12px;color:#888;">Showing ' + (start+1) + '-' + (start+pageData.length) + ' of ' + segmentsData.length + ' segments</div>' +
            pageData.map(seg => `
                    <div style="background:white; border:1px solid #e5e7eb; border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">
                            <span style="font-weight:700; font-size:16px; color:#333;">${escapeHtml(seg.name)}</span>
                            <span style="font-size:12px; color:#888; font-family:monospace;">${escapeHtml(seg.id)}</span>
                            <span class="llm-badge">${escapeHtml(seg.language)}</span>
                            ${seg.profile_count !== undefined ? '<span style="font-size:12px; color:#059669; font-weight:600;">' + seg.profile_count + ' profiles</span>' : ''}
                        </div>
                        <div style="color:#666; font-size:13px; margin-bottom:12px;">${escapeHtml(seg.description)}</div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; font-size:13px;">
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Target LLMs</div>
                                <div>${seg.target_llms.map(l => '<span class="llm-badge" style="margin:2px;">' + escapeHtml(l) + '</span>').join(' ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Tone</div>
                                <div style="color:#333;">${seg.tone_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Verbosity</div>
                                <div style="color:#333;">${seg.verbosity_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Search Style</div>
                                <div style="color:#333;">${seg.search_style_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Role Context Rate</div>
                                <div style="color:#333;">${(seg.add_role_context_rate * 100).toFixed(0)}%</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Mobile Rate</div>
                                <div style="color:#333;">${(seg.device_mobile_rate * 100).toFixed(0)}%</div>
                            </div>
                        </div>
                        <div style="margin-top:10px; display:flex; gap:16px; flex-wrap:wrap;">
                            <div style="flex:1; min-width:250px;">
                                <div style="color:#888; font-size:11px; margin-bottom:6px;">Age Ranges (${seg.age_ranges.length})</div>
                                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                                    ${seg.age_ranges.map(a => '<span style="display:inline-block;padding:2px 8px;background:#e0e7ff;color:#4f46e5;border-radius:999px;font-size:12px;">' + a.min_age + '-' + a.max_age + '</span>').join('')}
                                </div>
                            </div>
                            <div style="flex:1; min-width:250px;">
                                <div style="color:#888; font-size:11px; margin-bottom:6px;">City Tiers (${seg.city_tiers.length})</div>
                                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                                    ${seg.city_tiers.map(c => '<span style="display:inline-block;padding:2px 8px;background:#dcfce7;color:#166534;border-radius:999px;font-size:12px;">' + escapeHtml(c) + '</span>').join('')}
                                </div>
                            </div>
                        </div>
                        <div style="margin-top:10px;">
                            <div style="color:#888; font-size:11px; margin-bottom:6px;">Role Variants (${seg.role_variants.length})</div>
                            <table style="width:100%; font-size:12px; border-collapse:collapse;">
                                <thead>
                                    <tr style="background:#f8fafc;">
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Role</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Profession</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Company Size</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Income</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Pain Points</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${seg.role_variants.map(rv => '<tr style="border-top:1px solid #eee;">' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.label) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.profession) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.company_size) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.income_level) + '</td>' +
                                        '<td style="padding:4px 8px;">' + rv.pain_points.map(p => escapeHtml(p)).join(', ') + '</td>' +
                                    '</tr>').join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `).join('');

            // Segment pagination
            if (segmentsData.length > segPerPage) {
                const totalPages = Math.ceil(segmentsData.length / segPerPage);
                let pagHtml = '<div class="pagination" style="margin-top:16px;">';
                pagHtml += '<button ' + (segCurrentPage === 1 ? 'disabled' : '') + ' onclick="segCurrentPage--; renderSegments();">&laquo; Prev</button>';
                for (let p = 1; p <= totalPages; p++) {
                    pagHtml += '<button class="' + (p === segCurrentPage ? 'active' : '') + '" onclick="segCurrentPage=' + p + '; renderSegments();">' + p + '</button>';
                }
                pagHtml += '<button ' + (segCurrentPage === totalPages ? 'disabled' : '') + ' onclick="segCurrentPage++; renderSegments();">Next &raquo;</button>';
                pagHtml += '</div>';
                body.innerHTML += pagHtml;
            }
        }

        // ---- Profiles ----
        let profilesData = [];
        let profilesFiltered = [];
        let profCurrentPage = 1;
        const profPerPage = 20;

        async function loadProfiles() {
            try {
                const res = await fetch('./api/profiles');
                const data = await res.json();
                if (data.error) {
                    document.getElementById('profiles-body').innerHTML =
                        '<tr><td colspan="12" style="text-align:center;color:#dc2626;">Error: ' + escapeHtml(data.error) + '</td></tr>';
                    return;
                }
                profilesData = Array.isArray(data) ? data : [];

                // Populate segment filter dropdown
                const segFilter = document.getElementById('profile-filter-segment');
                const currentVal = segFilter.value;
                const segments = [...new Set(profilesData.map(p => (p.persona_traits || {}).segment_name).filter(Boolean))];
                segFilter.innerHTML = '<option value="">All Segments</option>' +
                    segments.map(s => '<option value="' + escapeHtml(s) + '">' + escapeHtml(s) + '</option>').join('');
                segFilter.value = currentVal;

                profCurrentPage = 1;
                filterProfiles();
            } catch (e) {
                console.error('loadProfiles error:', e);
                document.getElementById('profiles-body').innerHTML =
                    '<tr><td colspan="12" style="text-align:center;color:#dc2626;">Error loading profiles: ' + escapeHtml(e.message) + '</td></tr>';
            }
        }

        function filterProfiles() {
            const segFilter = document.getElementById('profile-filter-segment').value;
            const langFilter = document.getElementById('profile-filter-lang').value;
            const deviceFilter = document.getElementById('profile-filter-device').value;

            profilesFiltered = profilesData;
            if (segFilter) {
                profilesFiltered = profilesFiltered.filter(p => (p.persona_traits || {}).segment_name === segFilter);
            }
            if (langFilter) {
                profilesFiltered = profilesFiltered.filter(p => p.language === langFilter);
            }
            if (deviceFilter) {
                profilesFiltered = profilesFiltered.filter(p => p.device_type === deviceFilter);
            }

            profCurrentPage = 1;
            renderProfiles();
        }

        function renderProfiles() {
            const data = profilesFiltered;
            const body = document.getElementById('profiles-body');

            document.getElementById('profile-count-label').textContent =
                data.length + ' / ' + profilesData.length + ' profiles';

            if (!data.length) {
                body.innerHTML = '<tr><td colspan="12" style="text-align:center;color:#999;">No profiles found</td></tr>';
                document.getElementById('profiles-pagination').innerHTML = '';
                return;
            }

            const totalPages = Math.ceil(data.length / profPerPage);
            if (profCurrentPage > totalPages) profCurrentPage = totalPages;
            if (profCurrentPage < 1) profCurrentPage = 1;
            const start = (profCurrentPage - 1) * profPerPage;
            const pageData = data.slice(start, start + profPerPage);

            body.innerHTML = pageData.map(p => {
                const traits = p.persona_traits || {};
                const segName = traits.segment_name || '-';
                const traitStr = [traits.tone, traits.verbosity, traits.search_style].filter(Boolean).join(' / ') || '-';
                return `<tr>
                    <td>${p.id}</td>
                    <td>${escapeHtml(p.name || '-')}</td>
                    <td style="font-size:12px;"><span style="display:inline-block;padding:2px 8px;background:#fef3c7;color:#92400e;border-radius:999px;font-size:11px;">${escapeHtml(segName)}</span></td>
                    <td>${escapeHtml(p.age_range || '-')}</td>
                    <td>${escapeHtml(p.location || '-')}</td>
                    <td>${escapeHtml(p.country_code || '-')}</td>
                    <td style="font-size:12px;">${escapeHtml(p.profession || '-')}</td>
                    <td><span class="llm-badge">${escapeHtml(p.language || '-')}</span></td>
                    <td>${escapeHtml(p.device_type || '-')}</td>
                    <td style="font-size:12px;" title="${escapeHtml(JSON.stringify(traits))}">${escapeHtml(traitStr)}</td>
                    <td>${p.query_count || 0}</td>
                    <td>
                        <button class="small" onclick="editProfile(${p.id})">Edit</button>
                        <button class="danger small" onclick="deleteProfile(${p.id})">Delete</button>
                    </td>
                </tr>`;
            }).join('');

            // Pagination
            const pagEl = document.getElementById('profiles-pagination');
            if (totalPages <= 1) {
                pagEl.innerHTML = '';
                return;
            }
            let startPage = Math.max(1, profCurrentPage - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

            let html = '<button ' + (profCurrentPage === 1 ? 'disabled' : '') + ' onclick="profCurrentPage--; renderProfiles();">&laquo; Prev</button>';
            for (let p = startPage; p <= endPage; p++) {
                html += '<button class="' + (p === profCurrentPage ? 'active' : '') + '" onclick="profCurrentPage=' + p + '; renderProfiles();">' + p + '</button>';
            }
            html += '<button ' + (profCurrentPage === totalPages ? 'disabled' : '') + ' onclick="profCurrentPage++; renderProfiles();">Next &raquo;</button>';
            pagEl.innerHTML = html;
        }

        function showProfileForm(profile) {
            document.getElementById('profile-form-container').style.display = 'block';
            document.getElementById('profile-alert').innerHTML = '';
            if (profile) {
                document.getElementById('profile-form-title').textContent = 'Edit Profile #' + profile.id;
                document.getElementById('profile-edit-id').value = profile.id;
                document.getElementById('profile-name').value = profile.name || '';
                document.getElementById('profile-age-range').value = profile.age_range || '';
                document.getElementById('profile-location').value = profile.location || '';
                document.getElementById('profile-country').value = profile.country_code || '';
                document.getElementById('profile-profession').value = profile.profession || '';
                document.getElementById('profile-language').value = profile.language || 'zh';
                document.getElementById('profile-device').value = profile.device_type || 'desktop';
                const traits = profile.persona_traits || {};
                document.getElementById('profile-tone').value = traits.tone || 'casual';
                document.getElementById('profile-verbosity').value = traits.verbosity || 'medium';
                document.getElementById('profile-search-style').value = traits.search_style || 'solution_oriented';
            } else {
                document.getElementById('profile-form-title').textContent = 'Create New Profile';
                document.getElementById('profile-edit-id').value = '';
                document.getElementById('profile-form').reset();
            }
        }

        function hideProfileForm() {
            document.getElementById('profile-form-container').style.display = 'none';
        }

        function editProfile(id) {
            const profile = profilesData.find(p => p.id === id);
            if (profile) showProfileForm(profile);
        }

        async function submitProfile(event) {
            event.preventDefault();
            const alertDiv = document.getElementById('profile-alert');
            alertDiv.innerHTML = '';

            const editId = document.getElementById('profile-edit-id').value;
            const payload = {
                name: document.getElementById('profile-name').value,
                age_range: document.getElementById('profile-age-range').value,
                location: document.getElementById('profile-location').value,
                country_code: document.getElementById('profile-country').value,
                profession: document.getElementById('profile-profession').value,
                language: document.getElementById('profile-language').value,
                device_type: document.getElementById('profile-device').value,
                persona_traits: {
                    tone: document.getElementById('profile-tone').value,
                    verbosity: document.getElementById('profile-verbosity').value,
                    search_style: document.getElementById('profile-search-style').value,
                }
            };

            try {
                const url = editId ? './api/profiles/' + editId : './api/profiles';
                const method = editId ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method: method,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    alertDiv.innerHTML = '<div class="alert success">' + (editId ? 'Profile updated!' : 'Profile created!') + '</div>';
                    hideProfileForm();
                    loadProfiles();
                } else {
                    alertDiv.innerHTML = '<div class="alert error">Error: ' + (data.error || 'Unknown') + '</div>';
                }
            } catch (e) {
                alertDiv.innerHTML = '<div class="alert error">Error: ' + e.message + '</div>';
            }
        }

        async function deleteProfile(id) {
            if (!confirm('Delete profile #' + id + '? This cannot be undone.')) return;
            try {
                const res = await fetch('./api/profiles/' + id, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) loadProfiles();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        // Load on page load
        loadStats();
        loadQueries();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/stats')
def stats():
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT UPPER(status) as status, COUNT(*) as count
                FROM queries
                GROUP BY UPPER(status)
            """)
            rows = cur.fetchall()
        stats_dict = {r['status']: r['count'] for r in rows}
        total = sum(stats_dict.values())
        return jsonify({
            'total': total,
            'done': stats_dict.get('DONE', 0),
            'pending': stats_dict.get('PENDING', 0),
            'running': stats_dict.get('RUNNING', 0),
            'failed': stats_dict.get('FAILED', 0)
        })
    finally:
        conn.close()


@app.route('/api/queries')
def queries():
    from psycopg2.extras import RealDictCursor
    llm = request.args.get('llm')
    status = request.args.get('status')
    brand_id = request.args.get('brand_id')
    query_id = request.args.get('id')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    sort = request.args.get('sort', 'id_desc')
    include_count = request.args.get('count', '0') == '1'

    sort_map = {
        'id_desc': 'q.id DESC',
        'id_asc': 'q.id ASC',
        'status': 'UPPER(q.status) ASC, q.id DESC',
    }
    order_clause = sort_map.get(sort, 'q.id DESC')

    conn = get_db()
    try:
        where = []
        params = []

        if query_id:
            where.append("q.id = %s")
            params.append(int(query_id))
        if llm:
            where.append("q.target_llm = %s")
            params.append(llm)
        if status:
            where.append("UPPER(q.status) = UPPER(%s)")
            params.append(status)
        if brand_id:
            where.append("q.brand_id = %s")
            params.append(int(brand_id))

        where_clause = " AND ".join(where) if where else "1=1"

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if include_count:
                cur.execute(
                    f"SELECT COUNT(*) as cnt FROM queries q WHERE {where_clause}",
                    params
                )
                total = cur.fetchone()['cnt']
            else:
                total = None

            cur.execute(f"""
                SELECT
                    q.id,
                    q.target_llm,
                    q.status,
                    q.query_text,
                    q.brand_id,
                    q.profile_id,
                    q.account_id,
                    q.created_at,
                    q.executed_at,
                    q.retry_count,
                    r.raw_text as response,
                    r.llm_version,
                    r.citations_json as citations,
                    p.name as profile_name,
                    p.location as profile_location,
                    p.country_code as profile_country,
                    a.phone_number as account_label,
                    a.llm_name as account_llm
                FROM queries q
                LEFT JOIN llm_responses r ON q.id = r.query_id
                LEFT JOIN profiles p ON q.profile_id = p.id
                LEFT JOIN llm_accounts a ON q.account_id = a.id
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()

        result = [dict(r) for r in rows]
        if include_count:
            return jsonify({'rows': result, 'total': total})
        return jsonify(result)
    finally:
        conn.close()


@app.route('/api/queries', methods=['POST'])
def create_query():
    try:
        data = request.get_json()
        target_llm = data.get('target_llm')
        query_text = data.get('query_text')
        brand_id = data.get('brand_id')

        if not target_llm or not query_text:
            return jsonify({'success': False, 'error': 'target_llm and query_text are required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO queries (target_llm, query_text, brand_id, status, created_at)
                    VALUES (%s, %s, %s, 'pending', NOW())
                    RETURNING id
                """, (target_llm, query_text, brand_id))
                query_id = cur.fetchone()[0]
            conn.commit()

            if HAS_CELERY and celery_app is not None:
                try:
                    celery_app.send_task(
                        'geo_tracker.tasks.celery_tasks.execute_query',
                        args=[query_id],
                        queue='celery'
                    )
                except Exception as e:
                    print(f"Failed to send Celery task: {e}")

            return jsonify({'success': True, 'query_id': query_id})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/queries/<int:query_id>/retry', methods=['POST'])
def retry_query(query_id):
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, target_llm, query_text, brand_id FROM queries WHERE id = %s",
                    (query_id,)
                )
                query = cur.fetchone()
                if not query:
                    return jsonify({'success': False, 'error': 'Query not found'})

                cur.execute("""
                    UPDATE queries
                    SET status = 'pending', retry_count = COALESCE(retry_count, 0) + 1
                    WHERE id = %s
                """, (query_id,))
            conn.commit()

            if HAS_CELERY and celery_app is not None:
                try:
                    celery_app.send_task(
                        'geo_tracker.tasks.celery_tasks.execute_query',
                        args=[query_id],
                        queue='celery'
                    )
                except Exception as e:
                    print(f"Failed to send Celery task: {e}")

            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/queries/<int:query_id>/mark_failed', methods=['POST'])
def mark_failed(query_id):
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "UPDATE queries SET status = 'failed' WHERE id = %s AND status = 'done'",
                    (query_id,)
                )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Query not found or not in done status'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts')
def list_accounts():
    """列出所有 LLM 账号"""
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, llm_name, phone_number, status,
                           query_count_today AS daily_used, daily_limit,
                           consecutive_fails,
                           CASE WHEN cookies_json IS NOT NULL AND cookies_json != ''
                                THEN json_array_length(cookies_json::json)
                                ELSE 0 END AS cookie_count,
                           cookies_updated_at,
                           created_at AS updated_at
                    FROM llm_accounts
                    ORDER BY llm_name, id
                """)
                rows = cur.fetchall()
            # Convert datetime for JSON serialization
            for row in rows:
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
                if row.get('cookies_updated_at'):
                    row['cookies_updated_at'] = row['cookies_updated_at'].isoformat()
            return jsonify(rows)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/import_cookies', methods=['POST'])
def import_cookies_api():
    """通过 Web UI 导入 cookies 到 llm_accounts"""
    import json as json_mod
    try:
        data = request.get_json()
        platform = data.get('platform', '').strip()
        label = data.get('label', '').strip() or 'web_upload'
        daily_limit = data.get('daily_limit', 20)
        cookies_raw = data.get('cookies_json', '')

        if not platform:
            return jsonify({'success': False, 'error': 'Platform is required'})

        cookies = json_mod.loads(cookies_raw)

        # Auto-detect and convert EditThisCookie format
        SAME_SITE_MAP = {
            'unspecified': 'Lax', 'no_restriction': 'None',
            'lax': 'Lax', 'strict': 'Strict',
        }
        if (isinstance(cookies, list) and len(cookies) > 0
                and isinstance(cookies[0], dict)
                and ('storeId' in cookies[0] or 'hostOnly' in cookies[0])):
            import time as _time
            converted = []
            for c in cookies:
                entry = {
                    'name': c['name'], 'value': c['value'],
                    'domain': c['domain'], 'path': c.get('path', '/'),
                }
                if c.get('expirationDate'):
                    entry['expires'] = c['expirationDate']
                elif c.get('session'):
                    # Session cookie 没有过期时间，给它 30 天有效期
                    # 避免 Playwright 注入后立即过期
                    entry['expires'] = _time.time() + 30 * 86400
                if c.get('httpOnly'):
                    entry['httpOnly'] = True
                if c.get('secure'):
                    entry['secure'] = True
                ss = c.get('sameSite', 'unspecified')
                entry['sameSite'] = SAME_SITE_MAP.get(ss, 'Lax')
                converted.append(entry)
            cookies = converted

        if not isinstance(cookies, list) or len(cookies) == 0:
            return jsonify({'success': False, 'error': 'No valid cookies found'})

        cookies_json_str = json_mod.dumps(cookies)

        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if account with same platform + label exists
                cur.execute(
                    "SELECT id FROM llm_accounts WHERE llm_name = %s AND phone_number = %s",
                    (platform, label)
                )
                existing = cur.fetchone()

                if existing:
                    cur.execute(
                        """UPDATE llm_accounts
                           SET cookies_json = %s, status = 'active',
                               consecutive_fails = 0,
                               cookies_updated_at = NOW()
                           WHERE id = %s""",
                        (cookies_json_str, existing['id'])
                    )
                    msg = f'Updated account #{existing["id"]} with {len(cookies)} cookies'
                else:
                    cur.execute(
                        """INSERT INTO llm_accounts
                           (llm_name, email, password_encrypted, phone_number,
                            cookies_json, daily_limit, status, cookies_updated_at)
                           VALUES (%s, %s, '', %s, %s, %s, 'active', NOW())""",
                        (platform, f'{label}@{platform}.local', label,
                         cookies_json_str, daily_limit)
                    )
                    msg = f'Created new {platform} account with {len(cookies)} cookies'

            conn.commit()
            return jsonify({'success': True, 'message': msg})
        finally:
            conn.close()
    except json_mod.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid JSON: {e}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/status', methods=['POST'])
def update_account_status(account_id):
    """启用/禁用账号"""
    try:
        data = request.get_json()
        new_status = data.get('status', 'active')
        if new_status not in ('active', 'banned', 'cooldown'):
            return jsonify({'success': False, 'error': 'Invalid status'})
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE llm_accounts SET status = %s WHERE id = %s",
                    (new_status, account_id)
                )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/reset', methods=['POST'])
def reset_account_fails(account_id):
    """重置连续失败次数和每日用量"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE llm_accounts
                       SET consecutive_fails = 0, query_count_today = 0,
                           status = 'active', cooldown_until = NULL
                       WHERE id = %s""",
                    (account_id,)
                )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除账号"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM llm_accounts WHERE id = %s", (account_id,))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/auto_login', methods=['POST'])
def trigger_auto_login(account_id):
    """手动触发已有账号的自动重新登录"""
    if not HAS_CELERY:
        return jsonify({'success': False, 'error': 'Celery not available'})
    try:
        result = celery_app.send_task(
            'geo_tracker.tasks.celery_tasks.auto_login',
            kwargs={'account_id': account_id},
            queue='account_login',
        )
        return jsonify({'success': True, 'task_id': result.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/sms_register', methods=['POST'])
def trigger_sms_register():
    """手动触发新账号注册"""
    if not HAS_CELERY:
        return jsonify({'success': False, 'error': 'Celery not available'})
    data = request.get_json(force=True)
    platform = data.get('platform', 'doubao')
    try:
        result = celery_app.send_task(
            'geo_tracker.tasks.celery_tasks.auto_login',
            kwargs={'platform': platform, 'new_account': True},
            queue='account_login',
        )
        return jsonify({'success': True, 'task_id': result.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/task_status/<task_id>')
def task_status(task_id):
    """查询 celery task 执行状态"""
    if not HAS_CELERY:
        return jsonify({'state': 'UNKNOWN', 'error': 'Celery not available'})
    try:
        result = celery_app.AsyncResult(task_id)
        response = {
            'state': result.state,
            'task_id': task_id,
        }
        if result.state == 'SUCCESS':
            response['result'] = result.result
        elif result.state == 'FAILURE':
            response['error'] = str(result.result)
        return jsonify(response)
    except Exception as e:
        return jsonify({'state': 'ERROR', 'error': str(e)})


@app.route('/api/html_files')
def html_files():
    query_id = request.args.get('query_id')
    try:
        entries = []
        if os.path.isdir(SCREENSHOT_DIR):
            for fname in sorted(os.listdir(SCREENSHOT_DIR), reverse=True):
                if not fname.endswith('.html'):
                    continue
                if query_id and f'query_{query_id}_' not in fname and f'query_{query_id}.' not in fname:
                    continue
                fpath = os.path.join(SCREENSHOT_DIR, fname)
                stat = os.stat(fpath)
                entries.append({
                    'name': fname,
                    'path': fpath,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                })
        return jsonify(entries)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/html')
def serve_html_source():
    path = request.args.get('path')
    if not path:
        return "Path required", 400
    real_path = os.path.realpath(path)
    real_dir = os.path.realpath(SCREENSHOT_DIR)
    if not real_path.startswith(real_dir + os.sep) and real_path != real_dir:
        return "Access denied", 403
    if not os.path.isfile(real_path):
        return "File not found", 404
    with open(real_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    return Response(content, mimetype='text/plain; charset=utf-8')


@app.route('/api/backfill_citations', methods=['POST'])
def backfill_citations():
    """从历史 raw_text 和保存的 HTML 文件中提取 URL 作为 citations"""
    from psycopg2.extras import RealDictCursor
    import re
    import json as json_mod
    url_pattern = re.compile(
        r'https?://[^\s<>"\')\]},;]+',
        re.IGNORECASE,
    )
    # href 提取
    href_pattern = re.compile(
        r'<a\s[^>]*href=["\']?(https?://[^"\'>\s]+)',
        re.IGNORECASE,
    )
    skip_domains = {
        'chatgpt.com', 'gemini.google.com', 'accounts.google.com',
        'cdn.oaistatic.com', 'oaiusercontent.com', 'cdn-cgi',
        'gstatic.com', 'googleapis.com', 'google.com/gsi',
        'statsig', 'sentry', 'intercom',
    }

    def extract_urls_from_html_file(query_id):
        """从保存的 HTML debug 文件中提取链接"""
        urls = []
        if not os.path.isdir(SCREENSHOT_DIR):
            return urls
        for fname in os.listdir(SCREENSHOT_DIR):
            if not fname.endswith('.html'):
                continue
            if f'query_{query_id}_' not in fname:
                continue
            if 'extract_fail' in fname or 'content' in fname:
                # 这些是完整页面 HTML，可以从中提取
                fpath = os.path.join(SCREENSHOT_DIR, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        html = f.read()
                    urls.extend(href_pattern.findall(html))
                except Exception:
                    pass
        return urls

    try:
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT r.id, r.query_id, r.raw_text, r.response_html
                    FROM llm_responses r
                    WHERE r.citations_json IS NULL
                      AND r.raw_text IS NOT NULL
                      AND LENGTH(r.raw_text) > 20
                """)
                rows = cur.fetchall()

                updated = 0
                for row in rows:
                    # 从 raw_text 提取 URL
                    all_urls = url_pattern.findall(row['raw_text'] or '')
                    # 优先从 response_html 列提取（比文件更可靠）
                    if row.get('response_html'):
                        all_urls.extend(href_pattern.findall(row['response_html']))
                    # 再从 HTML debug 文件提取
                    all_urls.extend(extract_urls_from_html_file(row['query_id']))

                    seen = set()
                    citations = []
                    for u in all_urls:
                        u = u.rstrip('.,;:!?)]}')
                        if u in seen:
                            continue
                        if any(d in u for d in skip_domains):
                            continue
                        seen.add(u)
                        citations.append({
                            'url': u,
                            'title': '',
                            'index': len(citations) + 1,
                        })

                    if citations:
                        cur.execute(
                            "UPDATE llm_responses SET citations_json = %s WHERE id = %s",
                            (json_mod.dumps(citations), row['id'])
                        )
                        updated += 1

                conn.commit()
                return jsonify({'success': True, 'scanned': len(rows), 'updated': updated})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Segments API ─────────────────────────────────────────────────────────────

@app.route('/api/segments')
def list_segments():
    """列出所有 Segment 定义（优先从 Python 代码，失败则从 DB profiles 提取）"""
    # 尝试从 Python 定义导入
    try:
        from geo_tracker.generation.segments.definitions import SEGMENTS
        result = []
        for seg in SEGMENTS:
            result.append({
                'id': seg.id,
                'name': seg.name,
                'description': seg.description,
                'language': seg.language,
                'target_llms': seg.target_llms,
                'tone_pool': list(seg.tone_pool),
                'verbosity_pool': list(seg.verbosity_pool),
                'search_style_pool': list(seg.search_style_pool),
                'add_role_context_rate': seg.add_role_context_rate,
                'device_mobile_rate': seg.device_mobile_rate,
                'city_tiers': seg.city_tiers,
                'age_ranges': [
                    {'label': a.label, 'min_age': a.min_age, 'max_age': a.max_age}
                    for a in seg.age_ranges
                ],
                'role_variants': [
                    {
                        'label': rv.label,
                        'profession': rv.profession,
                        'company_size': rv.company_size,
                        'income_level': rv.income_level,
                        'pain_points': rv.pain_points,
                        'use_buzzwords': rv.use_buzzwords,
                    }
                    for rv in seg.role_variants
                ],
            })
        return jsonify(result)
    except ImportError:
        pass  # Fall through to DB extraction

    # 从数据库 profiles 的 persona_traits 中提取 segment 信息
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT DISTINCT
                        persona_traits->>'segment_id' AS id,
                        persona_traits->>'segment_name' AS name,
                        persona_traits->'target_llms' AS target_llms
                    FROM profiles
                    WHERE persona_traits->>'segment_id' IS NOT NULL
                    ORDER BY persona_traits->>'segment_id'
                """)
                seg_rows = cur.fetchall()

                if not seg_rows:
                    return jsonify([])

                # 对每个 segment 聚合 profile 信息
                segments = []
                for seg_row in seg_rows:
                    seg_id = seg_row['id']
                    cur.execute("""
                        SELECT
                            COUNT(*) AS profile_count,
                            array_agg(DISTINCT profession) AS professions,
                            array_agg(DISTINCT age_range) AS age_ranges,
                            array_agg(DISTINCT location) AS locations,
                            array_agg(DISTINCT country_code) AS countries,
                            array_agg(DISTINCT language) AS languages,
                            array_agg(DISTINCT device_type) AS device_types,
                            array_agg(DISTINCT persona_traits->>'tone') AS tones,
                            array_agg(DISTINCT persona_traits->>'verbosity') AS verbosities,
                            array_agg(DISTINCT persona_traits->>'search_style') AS search_styles
                        FROM profiles
                        WHERE persona_traits->>'segment_id' = %s
                    """, (seg_id,))
                    agg = cur.fetchone()

                    import json as json_mod
                    target_llms = seg_row['target_llms']
                    if isinstance(target_llms, str):
                        target_llms = json_mod.loads(target_llms)

                    segments.append({
                        'id': seg_id,
                        'name': seg_row['name'] or seg_id,
                        'description': f"从数据库提取 - {agg['profile_count']} 个 profiles",
                        'language': (agg['languages'] or ['zh'])[0] if agg['languages'] else 'zh',
                        'target_llms': target_llms or [],
                        'tone_pool': [t for t in (agg['tones'] or []) if t],
                        'verbosity_pool': [v for v in (agg['verbosities'] or []) if v],
                        'search_style_pool': [s for s in (agg['search_styles'] or []) if s],
                        'add_role_context_rate': 0,
                        'device_mobile_rate': 0,
                        'city_tiers': [],
                        'age_ranges': [
                            {'label': ar, 'min_age': int(ar.split('-')[0]) if '-' in ar else 0,
                             'max_age': int(ar.split('-')[1]) if '-' in ar else 0}
                            for ar in (agg['age_ranges'] or []) if ar and '-' in ar
                        ],
                        'role_variants': [
                            {'label': p, 'profession': p, 'company_size': '', 'income_level': '',
                             'pain_points': [], 'use_buzzwords': False}
                            for p in (agg['professions'] or []) if p
                        ],
                        'profile_count': agg['profile_count'],
                    })

                return jsonify(segments)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Profiles API ────────────────────────────────────────────────────────────

@app.route('/api/profiles')
def list_profiles():
    """列出所有 Profile"""
    try:
        import json as json_mod
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Use subquery for query_count to avoid GROUP BY issues with JSON
                cur.execute("""
                    SELECT p.id, p.name, p.age_range, p.location, p.country_code,
                           p.profession, p.language, p.device_type, p.persona_traits,
                           COALESCE(qc.cnt, 0) AS query_count
                    FROM profiles p
                    LEFT JOIN (
                        SELECT profile_id, COUNT(*) AS cnt
                        FROM queries
                        GROUP BY profile_id
                    ) qc ON p.id = qc.profile_id
                    ORDER BY p.id
                """)
                rows = cur.fetchall()

            result = []
            for r in rows:
                row = dict(r)
                # Ensure persona_traits is a proper dict for JSON serialization
                if row.get('persona_traits') and isinstance(row['persona_traits'], str):
                    try:
                        row['persona_traits'] = json_mod.loads(row['persona_traits'])
                    except (json_mod.JSONDecodeError, TypeError):
                        row['persona_traits'] = {}
                elif not row.get('persona_traits'):
                    row['persona_traits'] = {}
                result.append(row)

            return jsonify(result)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/profiles', methods=['POST'])
def create_profile():
    """创建新 Profile"""
    try:
        import json as json_mod
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO profiles (name, age_range, location, country_code,
                                         profession, language, device_type, persona_traits)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    name,
                    data.get('age_range', ''),
                    data.get('location', ''),
                    data.get('country_code', ''),
                    data.get('profession', ''),
                    data.get('language', 'zh'),
                    data.get('device_type', 'desktop'),
                    json_mod.dumps(data.get('persona_traits', {})),
                ))
                profile_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({'success': True, 'profile_id': profile_id})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profiles/<int:profile_id>', methods=['PUT'])
def update_profile(profile_id):
    """更新 Profile"""
    try:
        import json as json_mod
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE profiles
                    SET name = %s, age_range = %s, location = %s, country_code = %s,
                        profession = %s, language = %s, device_type = %s, persona_traits = %s
                    WHERE id = %s
                """, (
                    name,
                    data.get('age_range', ''),
                    data.get('location', ''),
                    data.get('country_code', ''),
                    data.get('profession', ''),
                    data.get('language', 'zh'),
                    data.get('device_type', 'desktop'),
                    json_mod.dumps(data.get('persona_traits', {})),
                    profile_id,
                ))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Profile not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profiles/<int:profile_id>', methods=['DELETE'])
def delete_profile(profile_id):
    """删除 Profile"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Check if profile has associated queries
                cur.execute("SELECT COUNT(*) FROM queries WHERE profile_id = %s", (profile_id,))
                query_count = cur.fetchone()[0]
                if query_count > 0:
                    # Nullify profile_id in queries rather than blocking delete
                    cur.execute("UPDATE queries SET profile_id = NULL WHERE profile_id = %s", (profile_id,))

                # Delete associated browser profile first
                cur.execute("DELETE FROM browser_profiles WHERE profile_id = %s", (profile_id,))

                # Nullify profile_id in llm_accounts
                cur.execute("UPDATE llm_accounts SET profile_id = NULL WHERE profile_id = %s", (profile_id,))

                cur.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Profile not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


_ensure_citations_column()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        DATABASE_URL = sys.argv[1]
    app.run(host='0.0.0.0', port=5000, debug=True)
