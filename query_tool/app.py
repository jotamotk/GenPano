"""
简单的 LLM 响应查询工具 - 带截图查看功能
"""
import os
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://genpano:genpano2026@localhost:5432/genpano"
)

# Parse DATABASE_URL
import re
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

# Screenshot directory - from worker container
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "/data/screenshots")


def get_db():
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
        .filters { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .filter-row { display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-end; }
        .filter-group { display: flex; flex-direction: column; gap: 5px; }
        .filter-group label { font-size: 12px; color: #666; font-weight: 600; }
        .filter-group select, .filter-group input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; min-width: 150px; }
        button { padding: 8px 20px; background: #4f46e5; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
        button:hover { background: #4338ca; }
        button.secondary { background: #6b7280; }
        button.secondary:hover { background: #4b5563; }
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
        .status-done { color: #059669; font-weight: 600; }
        .status-pending { color: #d97706; font-weight: 600; }
        .status-failed { color: #dc2626; font-weight: 600; }
        .status-running { color: #2563eb; font-weight: 600; }
        .llm-badge { display: inline-block; padding: 2px 8px; background: #e0e7ff; color: #4f46e5; border-radius: 999px; font-size: 12px; font-weight: 600; }
        .text-preview { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
        .screenshot-link { color: #4f46e5; cursor: pointer; text-decoration: underline; font-size: 12px; }
        .screenshot-link:hover { color: #4338ca; }
        .pagination { display: flex; justify-content: center; gap: 10px; margin-top: 20px; }
        .pagination button { background: white; color: #4f46e5; border: 1px solid #ddd; }
        .pagination button:hover { background: #f5f5f5; }
        .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
        .pagination .active { background: #4f46e5; color: white; border-color: #4f46e5; }
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
        .screenshot-img { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; margin-top: 10px; }
        .refresh-btn { margin-left: 10px; }
        .auto-refresh { display: flex; align-items: center; gap: 10px; margin-left: auto; }
        .auto-refresh label { font-size: 14px; color: #666; display: flex; align-items: center; gap: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
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

        <div class="filters">
            <div class="filter-row">
                <div class="filter-group">
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
                <div class="filter-group">
                    <label>Status</label>
                    <select id="filter-status">
                        <option value="">All</option>
                        <option value="DONE">Done</option>
                        <option value="PENDING">Pending</option>
                        <option value="RUNNING">Running</option>
                        <option value="FAILED">Failed</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Query ID</label>
                    <input type="number" id="filter-id" placeholder="Query ID">
                </div>
                <div class="filter-group">
                    <label>Brand ID</label>
                    <input type="number" id="filter-brand" placeholder="Brand ID">
                </div>
                <div class="filter-group">
                    <label>Limit</label>
                    <select id="filter-limit">
                        <option value="20">20</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                    </select>
                </div>
                <button onclick="currentPage=1; loadQueries();">Search</button>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>LLM</th>
                    <th>Status</th>
                    <th>Retry</th>
                    <th>Query</th>
                    <th>Screenshot</th>
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

    <div class="modal-backdrop" id="modal-backdrop" onclick="if(event.target === this) closeModal()">
        <div class="modal" id="modal">
            <div class="modal-header">
                <h3 id="modal-title">Response Details</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body"></div>
        </div>
    </div>

    <div class="modal-backdrop" id="screenshot-modal" onclick="if(event.target === this) closeScreenshotModal()">
        <div class="modal large" id="screenshot-modal-content">
            <div class="modal-header">
                <h3 id="screenshot-modal-title">Screenshot</h3>
                <button class="modal-close" onclick="closeScreenshotModal()">&times;</button>
            </div>
            <div class="modal-body" id="screenshot-modal-body"></div>
        </div>
    </div>

    <script>
        let currentPage = 1;
        let currentData = [];
        let autoRefreshInterval = null;

        async function loadStats() {
            const res = await fetch('./api/stats');
            const data = await res.json();
            document.getElementById('total-queries').textContent = data.total;
            document.getElementById('done-queries').textContent = data.done;
            document.getElementById('pending-queries').textContent = data.pending;
            document.getElementById('running-queries').textContent = data.running;
            document.getElementById('failed-queries').textContent = data.failed;
        }

        async function loadQueries() {
            const llm = document.getElementById('filter-llm').value;
            const status = document.getElementById('filter-status').value;
            const brand = document.getElementById('filter-brand').value;
            const queryId = document.getElementById('filter-id').value;
            const limit = parseInt(document.getElementById('filter-limit').value);

            const params = new URLSearchParams();
            if (llm) params.append('llm', llm);
            if (status) params.append('status', status);
            if (brand) params.append('brand_id', brand);
            if (queryId) params.append('id', queryId);
            params.append('limit', limit);
            params.append('offset', (currentPage - 1) * limit);

            const res = await fetch('./api/queries?' + params.toString());
            currentData = await res.json();
            renderTable(currentData);
        }

        function renderTable(data) {
            const tbody = document.getElementById('results-body');
            tbody.innerHTML = data.map(q => `
                <tr>
                    <td>${q.id}</td>
                    <td><span class="llm-badge">${q.target_llm}</span></td>
                    <td><span class="status-${q.status.toLowerCase()}">${q.status}</span></td>
                    <td>${q.retry_count || 0}</td>
                    <td class="text-preview" title="${escapeHtml(q.query_text)}" onclick="showResponse(${q.id})">${escapeHtml(q.query_text || '')}</td>
                    <td>
                        ${q.screenshot_path ?
                            `<span class="screenshot-link" onclick="showScreenshot('${q.screenshot_path}', ${q.id})">View Screenshot</span>` :
                            (q.status === 'FAILED' ? '<span style="color:#999;font-size:12px;">No screenshot</span>' : '-')
                        }
                    </td>
                    <td>${q.brand_id || '-'}</td>
                    <td>${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</td>
                    <td>
                        <button class="secondary" style="padding:4px 10px;font-size:12px;" onclick="showResponse(${q.id})">View</button>
                    </td>
                </tr>
            `).join('');
        }

        function showResponse(id) {
            const q = currentData.find(x => x.id === id);
            if (!q) return;

            document.getElementById('modal-title').textContent = `Query #${q.id} - ${q.target_llm}`;
            const statusClass = `status-${q.status.toLowerCase()}`;
            document.getElementById('modal-body').innerHTML = `
                <div class="modal-meta">
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Status</div>
                        <div class="modal-meta-value ${statusClass}">${q.status}</div>
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
                ${q.screenshot_path ? `
                <div style="margin-bottom:15px;">
                    <div class="modal-meta-label" style="margin-bottom:8px;">Screenshot</div>
                    <span class="screenshot-link" onclick="showScreenshot('${q.screenshot_path}', ${q.id})">View Full Screenshot</span>
                    <br>
                    <img src="./api/screenshot?path=${encodeURIComponent(q.screenshot_path)}" class="screenshot-img" style="max-height:300px;cursor:pointer;" onclick="showScreenshot('${q.screenshot_path}', ${q.id})">
                </div>
                ` : ''}
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Response</div>
                    <pre>${escapeHtml(q.response || '(no response)')}</pre>
                </div>
            `;
            document.getElementById('modal-backdrop').classList.add('show');
        }

        function showScreenshot(path, queryId) {
            document.getElementById('screenshot-modal-title').textContent = `Screenshot - Query #${queryId}`;
            document.getElementById('screenshot-modal-body').innerHTML = `
                <img src="./api/screenshot?path=${encodeURIComponent(path)}" style="max-width:100%;height:auto;">
            `;
            document.getElementById('screenshot-modal').classList.add('show');
        }

        function closeModal() {
            document.getElementById('modal-backdrop').classList.remove('show');
        }

        function closeScreenshotModal() {
            document.getElementById('screenshot-modal').classList.remove('show');
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
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT status, COUNT(*) as count
                FROM queries
                GROUP BY status
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
    llm = request.args.get('llm')
    status = request.args.get('status')
    brand_id = request.args.get('brand_id')
    query_id = request.args.get('id')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_db()
    try:
        where = []
        params = []

        if query_id:
            where.append("q.id = %s")
            params.append(int(query_id))
        if llm:
            where.append("target_llm = %s")
            params.append(llm)
        if status:
            where.append("status = %s")
            params.append(status)
        if brand_id:
            where.append("brand_id = %s")
            params.append(int(brand_id))

        where_clause = " AND ".join(where) if where else "1=1"
        params.extend([limit, offset])

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
                    r.screenshot_path,
                    r.llm_version
                FROM queries q
                LEFT JOIN llm_responses r ON q.id = r.query_id
                WHERE {where_clause}
                ORDER BY q.id DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route('/api/screenshot')
def screenshot():
    path = request.args.get('path')
    if not path:
        return "Path required", 400

    import os
    filename = os.path.basename(path)
    directory = os.path.dirname(path) or SCREENSHOT_DIR

    return send_from_directory(directory, filename)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        DATABASE_URL = sys.argv[1]
    app.run(host='0.0.0.0', port=5000, debug=True)
