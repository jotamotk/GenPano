"""
LLM 响应查询工具 - 带手动触发 Query
"""
import os
import re
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response

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


def get_db():
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME
    )
    return conn


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
                                <th>Retry</th>
                                <th>Query</th>
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
            document.getElementById('tab-queries').classList.toggle('active', tab === 'queries');
            document.getElementById('tab-html').classList.toggle('active', tab === 'html');
            document.getElementById('tab-queries-btn').classList.toggle('active', tab === 'queries');
            document.getElementById('tab-html-btn').classList.toggle('active', tab === 'html');
            if (tab === 'html') loadHtmlFiles();
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
                return `
                <tr>
                    <td>${q.id}</td>
                    <td><span class="llm-badge">${q.target_llm}</span></td>
                    <td><span class="status-${statusUp}">${statusUp}</span></td>
                    <td>${q.retry_count || 0}</td>
                    <td class="text-preview" title="${escapeHtml(q.query_text)}" onclick="showResponse(${q.id})">${escapeHtml(q.query_text || '')}</td>
                    <td>${q.brand_id || '-'}</td>
                    <td>${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</td>
                    <td>
                        <button class="secondary small" onclick="showResponse(${q.id})">View</button>
                        ${statusUp === 'FAILED' || statusUp === 'PENDING' ?
                            `<button class="success small" onclick="retryQuery(${q.id})">Retry</button>` : ''}
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
                ${statusUp === 'FAILED' || statusUp === 'PENDING' ? `
                <div style="margin-top: 20px;">
                    <button class="success" onclick="retryQuery(${q.id}); closeModal();">Retry This Query</button>
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
                const data = await res.json();
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
                    q.created_at,
                    q.executed_at,
                    q.retry_count,
                    r.raw_text as response,
                    r.llm_version
                FROM queries q
                LEFT JOIN llm_responses r ON q.id = r.query_id
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


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        DATABASE_URL = sys.argv[1]
    app.run(host='0.0.0.0', port=5000, debug=True)
