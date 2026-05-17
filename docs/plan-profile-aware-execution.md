# Profile-Aware 执行层改造 + 多账号 Cookie 管理

> 总体目标：让每个 Query 用对应 Profile 的浏览器指纹执行，对需要登录的 LLM（豆包、智谱等）自动从 AccountPool 注入 cookies，支持多账号轮换。

---

## 一、核心架构

### 1.1 当前问题

- `guest_executor.py` 用硬编码浏览器配置（`en-US`, `America/New_York`, `1920x1080`）执行所有查询，忽略 Profile 的 BrowserProfile 指纹
- 需要登录的 LLM（豆包、智谱）在 `celery_tasks.py:78-82` 直接被 FAILED 跳过
- 历史问题：豆包的环境变量 cookie 注入只能存**一组** cookies，无法支持
  多账号轮换。
  （历史记录：该环境变量在 Phase 3 cleanup (#1118 / Epic #1110) 中已移除，
  豆包/DeepSeek 改走 vm_session 执行模式 (ADR-016)，cookies 仅从 AccountPool
  + vm_side runner 加载，天然支持多账号轮换。）

### 1.2 设计理念 — 无需 Agent 实体

```
Agent 是运行时的临时组合，不需要维护 Agent 表：

Query(profile_id=123, target_llm="doubao")
  ↓
Profile #123 的 BrowserProfile → 浏览器指纹（UA、时区、语言、viewport）
  +
AccountPool.acquire("doubao") → Account #7 的 cookies_json → 登录态
  ↓
临时 Browser Context（指纹 + cookies）→ 强制开新对话 → 执行 → 销毁
```

### 1.3 Account 共享策略

- 理想状态 Account:Profile = 1:1（账号历史 = 人设积累）
- 现实中多 Profile 共享少量 Account，通过**每次强制开新对话**消除 Account 历史对回答的影响
- Account 按 segment 分组：20 个账号 → 20 个 segment → 每 segment 100 个 Profile 共享 1 个 Account
- 不同 segment 之间不会交叉污染记忆

### 1.4 可扩展性

- `LLMAccount.llm_name` 未来可存 `"douyin"` / `"bilibili"`（语义兼容）
- `Query` 表加 `action` 字段（默认 `"query"`，未来扩展 `"like"` / `"comment"` / `"post"`）
- 浏览器配置逻辑抽成独立函数，新 executor 可复用

---

## 二、多账号 Cookie 全链路

### 2.1 数据流

```
auto_register.py                    import_cookies.py              llm_accounts 表
(LubanSMS + Playwright)   →   ./cookies/*.json   →   (upsert)   →   每行一个账号
                                                                        ↓
celery_tasks.py  →  AccountPool.acquire(llm_name)  →  account.cookies_json
                                                                        ↓
guest_executor(account_cookies=...)  →  context.add_cookies()  →  执行查询
                                                                        ↓
                                         AccountPool.report_success/failure()
```

### 2.2 自动注册脚本 `scripts/auto_register.py` ✅ 已完成

使用 LubanSMS 接码平台 + Playwright 自动注册豆包/DeepSeek 账号并提取 cookies。

```bash
python scripts/auto_register.py --platform doubao --count 5
python scripts/auto_register.py --platform deepseek --count 3 --headless
```

- **LubanSMSClient**: 封装 getNumber/getSms/setStatus API
- **DoubaoRegistrar**: 豆包注册流程（passport.volcengine.com → 手机号 + SMS）
- **DeepSeekRegistrar**: DeepSeek 注册流程
- **CAPTCHA 处理**: 半自动，遇到 ByteDance 滑块时暂停等用户手动完成
- **输出**: `./cookies/{platform}_{phone}_{timestamp}.json`

### 2.3 Cookie 导入脚本 `scripts/import_cookies.py` 🔲 待实现

```bash
python scripts/import_cookies.py ./cookies/              # 导入目录下所有 JSON
python scripts/import_cookies.py ./cookies/doubao_*.json # 导入单个文件
python scripts/import_cookies.py ./cookies/ --dry-run    # 试运行
```

- 读取 `{"platform", "phone", "cookies"}` 格式的 JSON 文件
- Upsert 到 `llm_accounts` 表（`llm_name + phone_number` 相同时更新 `cookies_json`）
- 使用 `create_task_engine()` + `get_task_async_session()` 连接数据库

---

## 三、执行层改造步骤

### Step 1: `geo_tracker/db/models.py` — 模型改动

**LLMAccount 新增字段**:
```python
segment_group      = Column(String(64), nullable=True)    # 账号服务的 segment 分组
session_healthy    = Column(Boolean, default=True)
session_checked_at = Column(DateTime, nullable=True)
```

**Query 新增字段**:
```python
action = Column(String(32), default="query")  # "query" | 未来: "like", "comment", "post"
```

### Step 2: `geo_tracker/tasks/celery_tasks.py` — 加载 Profile + 集成 AccountPool

**改动要点**:
- Eager-load `Query → Profile → BrowserProfile`
- `requires_login=True` 时，从 AccountPool 获取账号（而非直接 FAILED）
- 无可用账号 → 设 `PENDING`（等下次重试），不是 `FAILED`
- 传 `browser_profile` + `account_cookies` 给 executor
- 执行后 `report_success()` / `report_failure()` 上报 AccountPool
- `reset_daily_counts()` 接入 `AccountPool.reset_daily_counts()`

```python
if llm_config.get("requires_login"):
    pool = AccountPool(db)
    account = await pool.acquire(query.target_llm)
    if account and account.cookies_json:
        account_cookies = account.cookies_json
    else:
        query.status = QueryStatus.PENDING.value  # 留着等下次
        return {"status": "deferred", "reason": "no_account_available"}

guest_executor = GuestQueryExecutor(proxy_url=proxy_url, account_cookies=account_cookies)
response = await guest_executor.execute(query, browser_profile=browser_profile)
```

### Step 3: `geo_tracker/agent/guest_executor.py` — 核心改造

**3a. 签名变更**:
```python
def __init__(self, proxy_url=None, account_cookies=None):
    self.account_cookies = account_cookies

async def execute(self, query, browser_profile=None):
```

**3b. 应用 BrowserProfile 指纹**（替换硬编码 `en-US`, `America/New_York`）:
```python
bp = browser_profile
locale = (bp.language if bp else None) or "zh-CN"
tz     = (bp.timezone if bp else None) or "Asia/Shanghai"
vp_w   = (bp.viewport_width if bp else None) or 1920
vp_h   = (bp.viewport_height if bp else None) or 1080
```

**3c. 强制开新对话**（多 Profile 共享 Account 时隔离上下文）:
```python
# LLM 配置中添加 new_chat_url
"doubao":  {"new_chat_url": "https://www.doubao.com/chat/new"},
"chatgpt": {"new_chat_url": "https://chatgpt.com"},
"kimi":    {"new_chat_url": "https://kimi.moonshot.cn"},

# 执行时优先用 new_chat_url
target_url = config.get("new_chat_url") or config["url"]
```

**3d. Cookie 注入**（优先 account_cookies → fallback 环境变量）:
```python
if self.account_cookies:
    cookies = json.loads(self.account_cookies)
    await context.add_cookies(cookies)
elif cookies_env:
    cookies = _load_cookies_from_env(cookies_env)
    if cookies:
        await context.add_cookies(cookies)
```

**3e. 执行后提取新 cookies**（供保存回 DB）:
```python
if resp_text and self.account_cookies:
    new_cookies = await context.cookies()
    response._new_cookies = json.dumps(new_cookies)
```

### Step 4: `geo_tracker/pool/account_pool.py` — Segment 分组

**acquire() 新增参数**:
```python
async def acquire(self, llm_name, country_code=None,
                  segment_id=None, require_healthy_session=False):
```

- 优先匹配同 segment 的账号，fallback 到无 segment 限制
- `require_healthy_session=True` 时过滤 `session_healthy=True` 且 `cookies_json IS NOT NULL`
- 排序：同 segment > 无 segment > LRU

**账号分配示例**:
```
Account #1  → segment_group="seg_enterprise_decision"  (企业决策层)
Account #2  → segment_group="seg_mid_manager"           (中层管理者)
...
Account #20 → segment_group="seg_industry_analyst"      (行业分析师)

每个 segment 100 个 Profile 共享 1 个 Account
```

### Step 5: `geo_tracker/cli/account_login.py` — 登录 & Cookie 提取

```bash
# 有 GUI：员工手动登录
python -m geo_tracker.cli.account_login --account-id 1

# 无 GUI：从文件导入
python -m geo_tracker.cli.account_login --account-id 1 --import-cookies /path/to/cookies.json
```

### Step 6: `geo_tracker/cli/account_manage.py` — 账号管理

```bash
python -m geo_tracker.cli.account_manage add --llm doubao --phone 138xxx --segment seg_mid_manager
python -m geo_tracker.cli.account_manage list [--llm doubao]
python -m geo_tracker.cli.account_manage check --account-id 1
python -m geo_tracker.cli.account_manage remove --account-id 3
python -m geo_tracker.cli.account_manage assign-segments
```

### Step 7: `geo_tracker/tasks/session_health.py` — Session 健康检查

Celery Beat 每 30 分钟：
1. 注入 cookies → headless 打开 LLM 页面
2. 检测是否跳转到登录页 / 弹出登录框
3. 失败 → `session_healthy=False`，日志告警

### Step 8: `geo_tracker/pool/proxy_pool.py` — 国内 LLM 代理支持

新增 `DOMESTIC_PROXY_URL` 环境变量，国内 LLM 可选走国内住宅代理（多账号同 IP 防风控）。

---

## 四、完整文件清单

| 状态 | 操作 | 文件 | 改动要点 |
|------|------|------|---------|
| ✅ | 新建 | `scripts/auto_register.py` | LubanSMS + Playwright 自动注册 + Cookie 提取 |
| ✅ | 新建 | `scripts/requirements-register.txt` | 注册脚本依赖 |
| 🔲 | 新建 | `scripts/import_cookies.py` | Cookie JSON 文件批量导入到 DB |
| 🔲 | 修改 | `geo_tracker/db/models.py` | LLMAccount 加 segment_group、session_healthy；Query 加 action |
| 🔲 | 修改 | `geo_tracker/tasks/celery_tasks.py` | eager-load Profile、集成 AccountPool、传 cookies |
| 🔲 | 修改 | `geo_tracker/agent/guest_executor.py` | 接受 BrowserProfile + cookies、替换硬编码配置 |
| 🔲 | 修改 | `geo_tracker/pool/account_pool.py` | acquire() 加 segment_id 分组 + session 健康过滤 |
| 🔲 | 修改 | `geo_tracker/pool/proxy_pool.py` | 国内 LLM 住宅代理 |
| 🔲 | 新建 | `geo_tracker/cli/account_login.py` | 交互式登录 + cookie 提取 |
| 🔲 | 新建 | `geo_tracker/cli/account_manage.py` | 账号增删查 + segment 分配 |
| 🔲 | 新建 | `geo_tracker/tasks/session_health.py` | 定时 session 健康检查 |

## 五、影响范围

**所有 LLM 都受益**:
- ChatGPT/Gemini/Perplexity/Kimi/DeepSeek: 用 Profile 正确的指纹（语言、时区、UA、viewport）
- Doubao/Zhipu: 从"完全无法执行"变为"cookie 注入 + 正确指纹 + 多账号轮换"
- Grok: 同理（需要 X 账号 cookies）

## 六、验证步骤

1. **注册**: `auto_register.py --platform doubao --count 2` → 生成 2 个 cookie JSON
2. **导入**: `import_cookies.py ./cookies/` → 导入到 DB，打印 2 条记录
3. **Profile 指纹验证**: CN Profile → query(kimi) → 检查 worker 日志 `zh-CN`, `Asia/Shanghai`
4. **豆包查询**: doubao query → dispatch → 日志显示 "acquired account id=X" + cookie 注入
5. **LRU 轮换**: 连续查询应使用不同 account
6. **Session 检查**: Celery Beat → 30 分钟后日志显示 session check 通过
7. **ChatGPT 对比**: US Profile → query(chatgpt) → 检查 `en-US`, `America/New_York`
