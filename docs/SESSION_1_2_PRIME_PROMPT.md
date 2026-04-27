# Session 1.2' · Camoufox + 3 引擎 Adapter Live + Luban SMS Live (M2 Milestone 末)

> **Session 类型**: Python pivot 实施 Session (M2 milestone 末, milestone 切片)
> **依赖**: Session 1' (Adapter 框架就位 + parsers + queries.json + scheduler + retry/backoff/state/queue)
> **关系到 master**: 替代 master Session 1.2 (TS 双修正预先登陆作废, geo_tracker live 实现接纳)
> **预算**: 5-7 工作日 (Camoufox 启动调试 + 3 引擎实测 + Luban OTP 注入 + Golden HAR 录制)
> **分支**: `session-1.2prime` (从 main fork)

---

## §0 · 前置 Grep 契约 (Pre-Flight Grep Contract)

> **决策 #25 规则 2 强制要求**: 开工第一批动作必须跑这 8 条 grep, 把每条输出粘到 §6 交付报告 "F1-F8 grep 结果" 段。任一条 grep 输出与 §1 真相源索引描述不一致 → STOP Type B (真相源冲突), 不写代码, 找 Frank alignment。

```bash
# F1 · 验证决策 #25/#29-#32 仍是当前公约 (12 规则 + Python pivot + preview env + branch-per-session + 工作仓 genpano)
grep -nE '^(25|29|30|31|32)\.\s+' CLAUDE.md | head -20

# F2 · 验证决策 #28 §A (Platform Layer 边界) + §G C2/C3 (F4 三子规则 + 6 enum response_source)
grep -nE 'F4-1|F4-2|F4-3|response_source|web_ui|api_fallback|harness_fixture|Platform Layer 边界' CLAUDE.md | head -20

# F3 · 验证 ADAPTER_CONTRACT §5.1/§5.3a/§5.4 + §6 (9 错误码) + §7.4 (0-Node 降级) + §8 (API fallback)
grep -nE '§5\.1|§5\.3a|§5\.4|§6|§7\.4|§8|9 种 AdapterError|45s|PRE_WARMING|QUARANTINED' docs/ADAPTER_CONTRACT.md | head -30

# F4 · 验证 REPLAN §4 Session 1.2' scope + Phase Gate (M2 Milestone 末)
grep -nE 'Session 1\.2|Camoufox|Luban|guest_executor|reference-card|userToken|accounts:register|HAR replay' docs/REPLAN_2026_04_26.md | head -30

# F5 · 验证 SESSION_PROGRESS.md 当前进度 (Session 1' 应已 done, 1.2' 应是 in_progress)
grep -nE 'Session 1|Session 1\.2|done|in_progress|blocked' docs/SESSION_PROGRESS.md | head -10

# F6 · 验证 Session 1' 交付物可被本 Session 复用 (Adapter 框架 + parsers + scheduler)
ls -la backend/app/engines/adapters/ backend/app/parsers/ backend/app/scheduler/ backend/app/accounts/ 2>&1 | head -40

# F7 · 验证 geo_tracker/ 合并仓代码就位 (吸收源)
ls -la geo_tracker/agent/ geo_tracker/sms_login/ geo_tracker/pool/ 2>&1 | head -30 || echo "geo_tracker not yet present in working tree"

# F8 · 验证 pyproject.toml 依赖齐备 (camoufox-py / playwright / pytest-playwright / opencv-python / Pillow / numpy / httpx[http2] / structlog)
grep -nE 'camoufox|playwright|pytest-playwright|opencv-python|Pillow|numpy|httpx|structlog' backend/pyproject.toml | head -20
```

**STOP 条件**: F1/F2/F4/F5/F6 任一空输出或与 §1 描述不符 → 立即停; F3 ADAPTER_CONTRACT 段号漂移 → 立即停; F7 geo_tracker 缺失 → 走 Type A 环境失败处理; F8 任一依赖缺失 → Step 0 补 pyproject.toml 后再开工。

---

## §1 · 真相源索引 (Truth Source Index, 决策 #25 规则 5)

### 1.1 引用 (read-only, 不得修改)

| 真相源 | 段号 / 行号 | 用途 |
|---|---|---|
| `CLAUDE.md` 决策 #22 §A-G | 整段 | Adapter 契约对齐 / 9 错误码 / TIMEOUT sentinel 历史 |
| `CLAUDE.md` 决策 #25 | 全 12 规则 | Prompt 编写公约 |
| `CLAUDE.md` 决策 #28.A | Platform Layer 边界 | 账号管理归 Platform Layer (App/Admin 共享) |
| `CLAUDE.md` 决策 #28.G C1-C4 | 双修正最终版 | F4 三子规则 + 6 enum response_source labeling 强制 |
| `CLAUDE.md` 决策 #28.C C1 | MVP 不加密 cookie | `crypto-noop.py` 作未来 AES-GCM 替换入口, 字段保留 |
| `CLAUDE.md` 决策 #28.C C2 | Luban SMS live 拉回本 Session | scope 含 doubao + deepseek-CN 自动注册 + ChatGPT CLI 手工导入 |
| `CLAUDE.md` 决策 #29-#32 | Python pivot / preview / branch / 工作仓 | 横切公约 |
| `docs/PRD.md` §4.2.4a | ProfileGroup | profile-aware 扇出消费方 (Session 2' 才用, 本 Session 不实现 fanout, 但 humanize 必须读 profile.userAgent / locale / timezone) |
| `docs/PRD.md` §4.3 | 反检测三层 | UA + viewport + locale + timezone + WebGL fingerprint + behavior |
| `docs/ADAPTER_CONTRACT.md` §3 | 接口契约 | `Adapter.execute(ctx) -> AdapterResponse` 形状 |
| `docs/ADAPTER_CONTRACT.md` §5.1 | 账号状态机 | 6 状态 ACTIVE/COOLDOWN/FROZEN/BANNED/PRE_WARMING/QUARANTINED |
| `docs/ADAPTER_CONTRACT.md` §5.3a | Pre-Warm 7 步 | 总预算 45s + STEP_BUDGET_MS 分摊 |
| `docs/ADAPTER_CONTRACT.md` §5.4 | 自动注册 (CN 引擎) | 仅 doubao/deepseek-CN, ChatGPT 人工 |
| `docs/ADAPTER_CONTRACT.md` §6 | 9 种 AdapterError | 错误码 + 重试矩阵 |
| `docs/ADAPTER_CONTRACT.md` §7 | 代理调度 | 海外强制走代理 / CN 直连 |
| `docs/ADAPTER_CONTRACT.md` §8 | API fallback | 火山 Ark + OpenAI; citations=[] 明确返回 |
| `docs/ADAPTER_CONTRACT.md` §9 | DOM quirks | doubao `.reference-card[data-href]` / deepseek `.citation-tooltip` / chatgpt `[data-testid^="cite-"]` |
| `docs/ADAPTER_CONTRACT.md` §10 | CAPTCHA 三级 | CapSolver → 火山 vision → slider |
| `docs/ADAPTER_CONTRACT.md` §11 | 观测 HAR | 9 种 leak pattern 拦截 (F2 已落地于 Session 1') |
| `docs/DATA_MODEL.md` §2.5 | ai_responses | 5 扩字段 + `response_source CHECK IN ('web_ui','api_fallback','mock_proxy','cached_replay','admin_har_replay','harness_fixture')` |
| `docs/REPLAN_2026_04_26.md` §4 (lines 210-229) | Session 1.2' scope + Phase Gate | M2 Milestone 末 |
| `docs/REPLAN_2026_04_26.md` §6.5 | Harness 分组 Python 分布 | F4 三子规则 + 平台边界 harness |
| `docs/HARNESS_ENGINEERING.md` §10.5/§10.7 | F2 (HAR leak) + F4 (response_source) Python 重写规范 | grep 锚点 + fixture 编写 |
| `docs/SESSION_1_PRIME_PROMPT.md` §5 (12 步交付顺序) | Session 1' 已交付边界 | 本 Session 在此之上扩 execute() / Camoufox / Luban |
| `geo_tracker/agent/executor.py` (合并仓只读) | Camoufox 启动逻辑 | Step 1 直接吸收 |
| `geo_tracker/agent/guest_executor.py` (合并仓只读) | ChatGPT Cloudflare bypass | Step 3 直接吸收 |
| `geo_tracker/sms_login/luban_client.py` (合并仓只读) | Luban HTTP client | Step 5 直接吸收 |
| `geo_tracker/agent/slider_captcha.py` (合并仓只读) | OpenCV slider 解算 | Step 7 CAPTCHA Level 3 吸收 |
| `geo_tracker/agent/vision_captcha.py` (合并仓只读) | 火山 Ark vision CAPTCHA | Step 7 CAPTCHA Level 2 吸收 |

### 1.2 修改 (write, 须同步 PR 文档)

| 真相源 | 修改内容 | 责任 |
|---|---|---|
| `backend/app/engines/browser/camoufox_launch.py` | 新建 — Camoufox launch + addInitScript 反指纹 + viewport/locale/timezone 注入 | Step 1 |
| `backend/app/engines/behavior/humanize.py` | 从 Session 1' stub 升级 — Box-Muller jitter / Bezier mouse / 3 级 quill 输入策略真实化, 接 Camoufox `Page` 对象 | Step 2 |
| `backend/app/engines/adapters/doubao/index.py` | execute() TIMEOUT sentinel → real implementation: `.reference-card[data-href]` 真实 citation 抽取 + 登录态校验 + COOKIE_EXPIRED 触发 | Step 3 |
| `backend/app/engines/adapters/deepseek/index.py` | execute() 真实化: localStorage.userToken 双轨鉴权 + `.thinking-collapse` 剥离 + `.citation-tooltip` 抽取 | Step 4 |
| `backend/app/engines/adapters/chatgpt/index.py` | execute() 真实化: Cloudflare Turnstile bypass + `data-message-status` 最后 assistant 消息 + `[data-testid^="cite-"]` 脚注 + 强制走代理 | Step 4 |
| `backend/app/engines/captcha/slider.py` | 从 stub 升级 — 吸收 geo_tracker/agent/slider_captcha.py 的 OpenCV 滑块算法 | Step 7 |
| `backend/app/engines/captcha/vision.py` | 从 stub 升级 — 吸收 geo_tracker/agent/vision_captcha.py 的火山 Ark 视觉 API | Step 7 |
| `backend/app/engines/captcha/solve.py` | CapSolver → vision → slider 三级兜底真实化 (Session 1' 已有 stub 框架) | Step 7 |
| `backend/app/accounts/sms/luban.py` | stub → live HTTPS client (httpx async) + `LUBAN_API_KEY` env + retry/backoff | Step 5 |
| `backend/app/accounts/auto_register.py` | stub → live 编排器 (doubao + deepseek-CN sign-up 页面导航 + 表单 + OTP 注入 + cookie 导出 + DB 写入) | Step 6 |
| `backend/app/accounts/crypto_noop.py` | 新建 — `encode_identity_blob` / `decode_identity_blob` (UTF-8 JSON bytes 双向转换), 给未来 AES-GCM 替换无感入口 | Step 5 |
| `backend/app/accounts/cli/__init__.py` + `list.py` + `register.py` + `inject.py` | 新建 — 3 个 typer/argparse CLI 命令: `accounts:list` / `accounts:register --engine=<id>` / `accounts:inject --engine=<id> --cookies-path=<path>` | Step 8 |
| `backend/app/har/recorder.py` | Session 1' 的 sanitize 已就位; 本 Session 加 `record_session(adapter, query, output_path)` 接 Playwright `context.routeFromHAR` 录制 + post-step sanitize | Step 9 |
| `backend/tests/fixtures/adapters/doubao/golden-skincare-zh.har` + `deepseek/golden-skincare-zh.har` + `chatgpt/golden-skincare-en.har` | 3 份 golden HAR 录制 + 经 sanitize 校验无密泄漏 | Step 9 |
| `backend/tests/integration/engines/test_doubao_replay.py` + `test_deepseek_replay.py` + `test_chatgpt_replay.py` | 新建 — pytest-playwright `route_from_har` fixture 回放 golden HAR + 断言 citation/sentiment/ranking 抽取结果 | Step 10 |
| `backend/tests/unit/engines/test_camoufox_launch.py` + `test_humanize_real.py` + `test_doubao_execute.py` 等 | 扩 ≥ 8 个新测试文件, 总 case ≥ 80 (启动 / addInitScript / viewport 注入 / humanize jitter / execute 错误码穷举 / Luban OTP retry / auto_register 状态机 / CLI argparse) | Step 10 |
| `scripts/ci-check.mjs` (Group F 段) | F1/F2/F3 已落地; 本 Session 加 **F4 三子规则** Python 重写 (扫 `backend/app/**/*.py`, 三处 stamp `response_source` 必带) + **F5 platform layer boundary** (no-luban-import-outside-accounts-dir, 扫 `backend/app/api/**` + `backend/app/admin_api/**` 不得直接 import `app.accounts.sms.luban`) | Step 11 |
| `backend/app/__ci_fixtures__/` | 新建 1 份 self-seeded 故意违规: **F5** (admin api 直 import luban). F4-1/F4-2/F4-3 三枚 fixture 已在 Session 1' Step 11 中创建并计入 selftest baseline = 9, 本 Session 仅复用不重建 | Step 11 |
| `scripts/python/ci-harness-selftest.py` EXPECTED_POSITIVES | **9 → 10** (Session 1' 9 + 本 Session F5 一枚). 注: 这是 Python pivot 的本地 selftest 链, 与 master TS 的 11→15 链无关. 数值溯源: Session 0' baseline 3 (D8/D9/D10 ported from 决策 #24) → Session 1' +6 (F1/F2/F3/F4-1/F4-2/F4-3) → 9 → 本 Session +1 (F5) → 10 | Step 11 |
| `docs/SESSION_PROGRESS.md` | Session 1.2' 状态 in_progress → done, M2 Milestone 收尾标记 | Step 12 |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | Session 1.2' 摘要从 "TBD" → "已交付" | Step 12 |
| `CLAUDE.md` 决策 #38 (新增) | Session 1.2' Python 重写交付摘要 (A-H 段, 含偏差登记 C 段) | Step 12 |

### 1.3 版本警告 (锁死, 不得在本 Session 内变更)

> 任何修改下面任一锁死项 → STOP Type B (真相源冲突), 升级 PR 改真相源 + 同步决策号, 不在本 Session 内私改。

1. **9 种 AdapterError 错误码** (`backend/app/engines/adapters/errors.py`, 由 Session 1' 定义) 不得在本 Session 内增减 — 本 Session 只是把 execute() 的 TIMEOUT sentinel 替换为真实分支抛具体错误码
2. **6 enum response_source labeling** (`web_ui` / `api_fallback` / `mock_proxy` / `cached_replay` / `admin_har_replay` / `harness_fixture`) — 本 Session 落地 `web_ui` (3 引擎 execute() 真实跑) + `api_fallback` (3 引擎 api-fallback 已在 Session 1' 落); `mock_proxy` / `cached_replay` / `admin_har_replay` / `harness_fixture` 由后续 Session 用, **不能在本 Session 改 enum 集合**
3. **MVP 3 引擎口径**: `chatgpt` / `doubao` / `deepseek-CN` (literal), Gemini/Claude/Bing 不落地; deepseek 目录路径 `backend/app/engines/adapters/deepseek/` 不改 (id 是 `deepseek-CN`, 路径仍 `deepseek/`)
4. **MVP 不加密 cookie (决策 #28.C C1)**: `accounts.encrypted_cookies BYTEA?` 字段名保留 + 类型保留, **不做 schema rename**, `crypto_noop.py` 即 encode/decode 分界, AES-GCM 在 Phase 2 单点替换
5. **ChatGPT auto-register 不在本 Session**: ChatGPT 仅走 `accounts:inject` CLI 手工导入, **不实现 sign-up 自动化** (Cloudflare 拒 datacenter IP 注册 + 海外手机号方案未验证); doubao + deepseek-CN 走 Luban 自动注册
6. **Pre-Warm 7 步预算**: 总 45s + 单步 STEP_BUDGET_MS 由 ADAPTER_CONTRACT §5.3a 锁定, 本 Session 落地的 prewarm.py 不得偏离
7. **HAR 9 种 leak pattern**: F2 (Session 1' 落地) 必须继续守卫; 本 Session 录制 golden HAR 必须经 sanitize 后入库, F2 selftest 不得变红
8. **零顶层列变更 query_executions / ai_responses**: 决策 #26.C1 锁定 persona snapshot 进 `attempts[].browser_profile` JSONB; 决策 #28.G C3 锁定 `response_source` 是 ai_responses 顶层列 (Session 0' 已落地 schema), 本 Session 不加新顶层列
9. **`account_registration_logs` 已由 Session 0' 落地**: 本 Session 仅写入数据 (auto_register success/failure 行), 不改 schema

---

## §2 · MVP Scope-Cut Declaration (决策 #25 规则 10)

### ✅ 本 Session 做 (in scope, 落地代码 + 测试 + 文档)

| # | Deliverable | 锚点 |
|---|---|---|
| Y1 | **Camoufox launch** (`app/engines/browser/camoufox_launch.py`): 从 geo_tracker/agent/executor.py 吸收启动逻辑, 包 `launch_camoufox(profile: BrowserProfile) -> BrowserContext` + addInitScript 反指纹 (navigator.webdriver=undefined / chrome.runtime / hairline / WebGL vendor 等 7 注入点) | PRD §4.3 / ADAPTER_CONTRACT §3 |
| Y2 | **humanize.py 真实化** (Session 1' stub → live): Box-Muller normalSample + Bezier cubic mouse path + QUILL_ESCALATION_ORDER 三级输入 + pausePonderingMs 钳制, 接真实 Playwright `Page` 对象 (不再用 PagePort interface) | PRD §4.3 / Session 1' §C.x |
| Y3 | **Doubao execute()**: `.reference-card[data-href]` 真实 citation 抽取 + textContent 强制 + "请登录" 文案 → COOKIE_EXPIRED + 单 div captcha overlay 触发 CAPTCHA_REQUIRED + 火山 API fallback 已就位 | ADAPTER_CONTRACT §9 / 决策 #22.A |
| Y4 | **DeepSeek-CN execute()**: localStorage.userToken 双轨鉴权 + 缺失 → COOKIE_EXPIRED + `.thinking-collapse` 剥离 + `.citation-tooltip` hover race + 火山 API fallback 已就位 | ADAPTER_CONTRACT §9 / 决策 #22.A |
| Y5 | **ChatGPT execute()**: Cloudflare Turnstile bypass (从 guest_executor.py 吸收) + iframe `cloudflare.com/cdn-cgi/challenge-platform` → CF_BLOCKED + `data-message-status` 仅查最后 assistant + `[data-testid^="cite-"]` 脚注 + 强制走代理 + OpenAI API fallback 已就位 | ADAPTER_CONTRACT §9 / 决策 #22.A |
| Y6 | **Luban SMS live** (`app/accounts/sms/luban.py`): stub → httpx async HTTPS client + `LUBAN_API_KEY` env + 申请号码 / 等待 OTP / 释放号码 三个 endpoint + retry (指数退避 ± jitter, max 3 次) + 失败抛 `LubanError` 子类 | 决策 #28.C C2 / ADAPTER_CONTRACT §5.4 |
| Y7 | **auto_register.py live** (doubao + deepseek-CN): stub → 编排器, sign-up 页面导航 (Camoufox) → 填手机号 (Luban 申请) → 等 OTP (Luban 拉取) → 注入 OTP → 完成注册 → 导出 cookies + localStorage → 写 `accounts` 表 (encrypted_cookies = JSON UTF-8 bytes 明文) + 写 `account_registration_logs` 行 (success/failure + reason) | 决策 #28.C C1 / 决策 #28.C C2 |
| Y8 | **CAPTCHA Level 1 + Level 2 + Level 3 真实化**: `slider.py` (吸收 OpenCV 算法 from geo_tracker) + `vision.py` (吸收火山 Ark vision from geo_tracker) + `solve.py` 三级兜底 (CapSolver API 优先 → vision → slider, 全失败抛 CAPTCHA_REQUIRED) | ADAPTER_CONTRACT §10 |
| Y9 | **`crypto_noop.py`**: `encode_identity_blob({cookies, localStorage, userToken?}) -> bytes` + 反向, UTF-8 JSON 明文; 单一 import 入口给 `accounts/auto_register.py` 与 `accounts/cli/inject.py` 用 | 决策 #28.C C1 |
| Y10 | **3 个 CLI 命令** (`app/accounts/cli/`): `accounts:list --engine=<id>` (列水位 + state 分布) / `accounts:register --engine=doubao|deepseek-CN --count=N` (走 Luban 批量注册) / `accounts:inject --engine=chatgpt --cookies-file=<path>` (手工导入 ChatGPT) | 决策 #28.A Layer 3 |
| Y11 | **Golden HAR 录制 + routeFromHAR 回放**: 3 份 har (doubao/deepseek/chatgpt 各一, prompt 来自 `tests/fixtures/scraping/queries.json`) 经 sanitize 入库 `tests/fixtures/adapters/<engine>/golden-*.har` + pytest-playwright 用 `context.route_from_har()` 离线回放, 断言 citation 数量 + sentiment label + ranking 数 | ADAPTER_CONTRACT §11 / Session 1' F2 |
| Y12 | **F5 平台边界 harness 新增** (F4 三子规则已在 Session 1' 落地, 本 Session 只复用): Group F 加 1 条 grep (F5 = no-luban-import-outside-accounts-dir) + 1 个 self-seeded fixture (`backend/app/__ci_fixtures__/F5_admin_imports_luban.cifixture.py`) | 决策 #28.A 双轨代码检测 |
| Y13 | **Selftest 9 → 10**: `scripts/python/ci-harness-selftest.py` EXPECTED_POSITIVES + 1 (新增 F5), `uv run python scripts/python/ci-harness-selftest.py` 必须打印 `selftest: PASS  (10 / 10 fixture expectations met)`. **数值溯源**: 本 Session 起点 = Session 1' 终点 9 (Session 0' 3 + F1/F2/F3/F4-1/F4-2/F4-3 各 1 = 9), +1 = **10**. 这是 Python pivot 的本地 selftest 链, 与 master TS 11→15 链无关 | 决策 #21.C |
| Y14 | **pytest 覆盖率 ≥ 80% 全线** (branches/lines/functions/statements), 总测试数 ≥ Session 1' baseline + 80 (新增 8 个 unit + 3 个 integration) | 决策 #18 |
| Y15 | **Preview env 部署 + Frank Layer 3 验证**: `git push session-1.2prime` 触发 Vercel/Render/Fly preview, M2 Milestone 末 Frank 在 preview 跑 `accounts:register --engine=doubao` 走通 + 触发 1 条 doubao/deepseek/chatgpt query 后 Admin 后台 `ai_responses` 表 +3 行 `response_source='web_ui'` | 决策 #30 |
| Y16 | **CLAUDE.md 决策 #38** (新增): Session 1.2' 交付摘要 (A-H 段 + C 偏差登记) | Step 12 / 决策 #25 规则 3 |

### ❌ 本 Session 不做 (out of scope, 后续 Session 兜)

| # | Deferred item | 由谁兜 | 理由 |
|---|---|---|---|
| N1 | **ChatGPT auto-register 自动化** | 仍延后 (Phase 2) | Cloudflare 拒 datacenter IP + 海外手机号方案 Frank 未验证, MVP 走 `accounts:inject` 手工导入 |
| N2 | **第 4 家引擎 (Gemini/Claude/Bing)** | Phase 2 | MVP 锁 3 家 (决策 #28.G C4) |
| N3 | **Camoufox 升级到次主版本** | Phase 2 | 本 Session 锁定首个能跑通的版本, 升级走独立 Session |
| N4 | **多轮对话 Query** | Session 6+ | 决策 #26.C2 锁定 |
| N5 | **profile-aware fanout 编排** | Session 2' | 本 Session humanize 消费 profile 字段, 但 fanout 编排是 Planner 范畴 |
| N6 | **Response 采集 Celery worker** | Session 3' | 本 Session 只让 execute() 能跑, 不接 Celery 队列消费 |
| N7 | **brand_detector / sentiment / citation 真实跑** | Session 3' | parsers Session 1' 已落, 本 Session 只在 integration 测试中调用验证, 不接生产分析队列 |
| N8 | **Admin Tab 1 账号池 UI** | Admin Session A1' (M4) | 本 Session 只交付 Platform Layer + CLI, Admin UI 走 A1' |
| N9 | **AES-256-GCM cookie 加密** | Phase 2 | 决策 #28.C C1 锁定 MVP 明文, `crypto_noop.py` 是替换入口 |
| N10 | **代理订阅 fetch 自动化** | Phase 2 | 本 Session 用静态代理列表 (env `PROXY_LIST_OVERSEAS=<comma-list>`), Ninja Clash 订阅集成走独立 Session |
| N11 | **0-Node 降级实测** | Phase 2 | ADAPTER_CONTRACT §7.4 框架 Session 1' 已落, 本 Session 不实测 0-overseas-healthy 触发 |
| N12 | **Frontend 任何修改** | 各 frontend Session | 本 Session 零 frontend 改动, 不动 `frontend/**` |

---

## §3 · STOP Triggers (决策 #25 规则 12)

### Type A · 环境失败 (Environment Failure)

| Code | 触发 | 处置 |
|---|---|---|
| A1 | `geo_tracker/` 目录在工作树缺失 (F7 grep 空) | 立刻停, 找 Frank 确认合并仓 sub-tree 是否 squash 进了 main |
| A2 | `pyproject.toml` 缺 camoufox-py / playwright / pytest-playwright / opencv-python 任一 (F8 grep 空) | Step 0 内补依赖, 跑 `uv pip install -e .` 后再开工 Step 1 |
| A3 | Camoufox 首次启动 crash (任何 OSError / TimeoutError on `launch()`) | 跑 `playwright install firefox` 拉 Camoufox binary; 仍失败 → 找 Frank 验证宿主 OS 是否支持 (Linux/Mac OK, Windows WSL2 OK, 原生 Windows 不支持) |
| A4 | `LUBAN_API_KEY` env 未配 | Step 5 之前停, Frank 在 Vercel/Render preview env 配好 + 本地 `.env.local` 配好后再开工 |
| A5 | `account_registration_logs` 表 Session 0' 没建 (Alembic head 不含此表) | Type B 升级 — 找 Frank alignment, Session 0' 漏交付; 本 Session 不补救 schema, 等 0' 修补 |
| A6 | preview env 无法部署 (Vercel/Render build fail) | Step 12 之前停, 拉 build log 给 Frank, 本 Session 等部署可达后再走 Layer 3 验证 |

### Type B · 真相源冲突 (Truth-Source Conflict)

| Code | 触发 | 处置 |
|---|---|---|
| B1 | ADAPTER_CONTRACT §6 9 错误码与 Session 1' `errors.py` 实际枚举不符 | 不写代码, 升级 PR 改 ADAPTER_CONTRACT 或回 Session 1' 修 errors.py, 决策号同步 |
| B2 | DATA_MODEL §2.5 `response_source CHECK` 6 enum 与 Session 0' 实际 migration 不符 | 同 B1, 升级修真相源 |
| B3 | 决策 #28.G C2 F4 三子规则与 `HARNESS_ENGINEERING.md §10.7` Python 重写规范有歧义 | 找 Frank alignment, 选一边为准, 同步决策号 |
| B4 | PRD §4.3 反指纹要求与 Camoufox 默认 addInitScript 集合冲突 (e.g. PRD 要求隐藏 navigator.webdriver=true 但 Camoufox 默认 false) | PRD 优先, 写自定义 addInitScript 覆盖 Camoufox 默认 |
| B5 | `geo_tracker/agent/executor.py` 启动逻辑与 ADAPTER_CONTRACT §3 接口不兼容 (e.g. executor.py 直接挂 page 不返回 context) | 不直接抄, 写 thin adapter 包一层, 在 §6 偏差登记 |

### Type C · 范围溢出 (Scope Overflow)

| Code | 触发 | 处置 |
|---|---|---|
| C1 | 实施中发现 ChatGPT auto-register 也能跑通 | **不做**, 留 Phase 2 (N1); 在 §6 登记 "可行但 out of scope" |
| C2 | Camoufox 不够用要换浏览器 (e.g. undetected-chromedriver) | 不在本 Session 换栈, 走独立架构决策 PR |
| C3 | profile-aware 测试需要 Planner 跑通 | 写 mock profile fixture 在 `tests/fixtures/profiles/` 解耦, 不拉 Session 2' |
| C4 | pytest 覆盖率达不到 80% | 不降阈值, 补测试至达标; 实在补不了的模块加 `# pragma: no cover` 并在 §6 偏差登记 |
| C5 | Golden HAR 抓不到 (e.g. doubao 改了 DOM) | 不勉强录, 在 §6 登记 "DOM drift, fallback HAR-mock 替代", L3 替换为 schema-mock 测试 |
| C6 | Luban OTP 接收超 5 分钟 | 不延 timeout 边界, 抛 `LubanTimeoutError` 走 retry, max 3 次后失败入 `account_registration_logs` |

---

## §4 · Phase Gate (3 层验收)

### L3/L4 Phase Gate 卡控 (Hard Fail, 决策 2026-04-26)

**真相源**: `docs/REPLAN_2026_04_26.md §5` L3/L4 测试覆盖矩阵 + §5.3 Hard Fail 卡控规范.

**Hard Fail 强制**: 下列 L3/L4 任一未跑绿, GitHub Actions branch protection 拦截 merge. 不允许 soft warning, 不允许临时跳过.

**本 Session 必跑 L3 集成测试 (3 项)**:
- Camoufox launch + page.goto 真实 ChatGPT/Doubao/DeepSeek; Luban SMS live 1 条注册成功 (preview Luban 沙箱); Golden HAR 录制 + routeFromHAR 回放 3 引擎契约

**本 Session 必跑 L4 E2E 测试**: 本 Session 无 L4 (E2E 留给 3' Pipeline 联通后)

**补救测试**: **TS#1.2 F4 → Python F4** (response_source 三子规则 stamp/labeling 翻译)

**Phase Gate 通过条件 (在原有 Layer 1-3 基础上追加)**:
- G_L3.1: Camoufox launch + Luban SMS live + golden HAR routeFromHAR 回放 3 项全绿
- G_Remedial.1: master TS F4 三子规则翻译完成 (adapter execute stamp / api-fallback label / insert with response_source)

### Layer 1 · `verify-session-1.2prime.sh` (12 项自动验证)

```bash
#!/usr/bin/env bash
# Run from repo root
set -euo pipefail

# L1.1 · ruff strict
cd backend && uv run ruff check . --select=ALL --ignore=D,ANN,COM,FBT && cd ..

# L1.2 · mypy strict
cd backend && uv run mypy app/ tests/ --strict && cd ..

# L1.3 · pytest unit + 80% coverage
cd backend && uv run pytest tests/unit/ --cov=app --cov-report=term --cov-fail-under=80 && cd ..

# L1.4 · pytest integration (HAR replay, no live network)
cd backend && uv run pytest tests/integration/engines/ -v && cd ..

# L1.5 · Camoufox smoke launch (headless, no nav)
cd backend && uv run python -c "
import asyncio
from app.engines.browser.camoufox_launch import launch_camoufox
from app.config.browser_profiles import BROWSER_PROFILES
async def main():
    profile = BROWSER_PROFILES['cn-consumer-desktop-default']
    ctx = await launch_camoufox(profile, headless=True)
    page = await ctx.new_page()
    await page.goto('about:blank')
    title = await page.title()
    await ctx.close()
    print(f'Camoufox smoke OK: title={title!r}')
asyncio.run(main())
" && cd ..

# L1.6 · CLI help works
cd backend && uv run python -m app.accounts.cli.list --help && uv run python -m app.accounts.cli.register --help && uv run python -m app.accounts.cli.inject --help && cd ..

# L1.7 · Harness Group F (F1/F2/F3 + F4-1/F4-2/F4-3 carry-over from Session 1' + F5 new)
uv run python scripts/python/ci-check.py --group=F

# L1.8 · Harness selftest 10/10
uv run python scripts/python/ci-harness-selftest.py
# Must print: ● selftest: PASS  (10 / 10 fixture expectations met)
# 数值溯源: Session 0' baseline 3 (D8/D9/D10) → Session 1' +6 (F1/F2/F3/F4-1/F4-2/F4-3) = 9 → 本 Session +1 (F5) = 10

# L1.9 · F2 HAR leak scan green on 3 golden HARs
uv run python scripts/python/ci-check.py --rule=F2

# L1.10 · response_source enum unchanged (alembic schema diff against migration head)
cd backend && uv run alembic check && cd ..

# L1.11 · No new top-level columns on query_executions or ai_responses
grep -nE '^ALTER TABLE (query_executions|ai_responses) ADD COLUMN' backend/alembic/versions/*.py | grep -v 'response_source\|cost_usd\|cost_cny\|token_count\|latency_breakdown\|trigger_source' && echo "FAIL: new top-level cols" && exit 1 || echo "OK: no new top-level cols"

# L1.12 · Platform Layer boundary — no admin/api code imports luban directly
! grep -rn 'from app.accounts.sms.luban' backend/app/api/ backend/app/admin_api/ 2>/dev/null && echo "OK: no luban leak" || (echo "FAIL: admin/api imports luban" && exit 1)
```

### Layer 2 · Harness selftest 必通

- `uv run python scripts/python/ci-harness-selftest.py` 输出 `● selftest: PASS  (10 / 10 fixture expectations met)`
- 1 新 fixture 对应 1 条新 grep 规则 (F5); F4-1/F4-2/F4-3 已在 Session 1' 落地, 本 Session 仅消费已存在的 fixture
- ci-check Group F 完整跑通: F1 (Session 1' 已落) / F2 (HAR leak) / F3 (no inline prompt) / F4-1 (Session 1' 已落) / F4-2 (Session 1' 已落) / F4-3 (Session 1' 已落) / F5 (本 Session 新增)
- **数值溯源**: Session 0' baseline 3 (D8/D9/D10) → Session 1' +6 (F1/F2/F3/F4-1/F4-2/F4-3) = 9 → 本 Session +1 (F5) = **10** (Python pivot 链, 与 master TS 链无关)

### Layer 3 · Frank 在 preview env 静态/交互验证 (M2 Milestone 末)

| # | 验证步骤 | 预期 |
|---|---|---|
| S1 | preview env build log 显示 alembic upgrade head 成功 | CI/CD log 含 "Running upgrade -> <head_rev>" |
| S2 | preview env 跑 `accounts:register --engine=doubao --count=1` 走 Luban OTP | CLI 输出 "Registered 1 account, state=ACTIVE", DB `accounts` 表 +1 行 + `account_registration_logs` +1 success 行 |
| S3 | preview env 跑 `accounts:register --engine=deepseek-CN --count=1` 走 Luban OTP | 同 S2 |
| S4 | preview env 跑 `accounts:inject --engine=chatgpt --cookies-file=tests/fixtures/cookies/chatgpt-frank.json` (Frank 自备) | CLI 输出 "Injected 1 account, state=ACTIVE", DB `accounts` 表 +1 行 |
| S5 | preview env Admin URL `https://genpano-preview.<host>/admin/api/v1/pipeline/accounts/list?engine=doubao` (本 Session 不建 Admin UI, 但提供 read-only API stub 给 Layer 3 验证) | JSON 返回 ≥ 1 active account, `engine: 'doubao'`, `state: 'ACTIVE'` |
| S6 | preview env 触发 1 条 doubao query (走 `POST /admin/api/v1/pipeline/queries/trigger` Admin stub, body 含 prompt + engine=doubao) | DB `ai_responses` 表 +1 行, `response_source='web_ui'`, `text` 非空, `citations` 非空数组 |
| S7 | preview env 触发 1 条 deepseek-CN query | DB `ai_responses` +1 行 `response_source='web_ui'` |
| S8 | preview env 触发 1 条 chatgpt query (用 S4 注入的账号 + 海外代理) | DB `ai_responses` +1 行 `response_source='web_ui'`; 若代理 0-Node 降级则 `response_source='api_fallback'` 也接受 |
| S9 | Frank 拉 Vercel/Render preview build log + DB query 截图 | 贴回 Session 1.2' delivery thread 留档 |

**M2 Milestone 末闭环条件**: S1-S9 全部 PASS, Frank 在交付报告 §6 Layer 3 段亲自打勾确认。任一未通过 → Session 1.2' 不闭, 不进入 Session 2'。

---

## §5 · 12-Step Delivery Order

> 每步一个 atomic commit, commit 标题格式 `Session 1.2' Step <N>: <主题>` (无 emoji 无特殊 Unicode), 末尾回引 `CLAUDE.md #38 (forthcoming)`。每步交付完跑 verify-session-1.2prime.sh 该步相关检查, 绿才进下一步。

| Step | 主题 | 关键文件 | Verify 重点 |
|---|---|---|---|
| 0 | 分支 + 依赖补齐 | `git checkout -b session-1.2prime`; 改 `backend/pyproject.toml` 加 camoufox-py / playwright / pytest-playwright / opencv-python / Pillow / numpy / httpx[http2] / structlog; `uv pip install -e .[dev]`; `playwright install firefox` | F8 grep 全绿 |
| 1 | Camoufox launch | 新建 `app/engines/browser/camoufox_launch.py` 吸收 geo_tracker/agent/executor.py 启动 + addInitScript 7 注入点; 单测 `tests/unit/engines/test_camoufox_launch.py` ≥ 8 例 (启动 / context 复用 / addInitScript 注入 / viewport / locale / timezone / 关闭幂等 / 异常处理) | L1.5 Camoufox smoke 绿 |
| 2 | humanize 真实化 | `app/engines/behavior/humanize.py` Session 1' stub → live, 移除 PagePort 抽象, 直接接 Playwright `Page`; 单测 ≥ 10 例 (jitter 钳制 / Bezier 端点 / pausePondering / typing escalation / mouse path 长度 / normalSample 边界 / 节流 / 退避) | pytest unit 绿 |
| 3 | Doubao execute() 真实化 | `app/engines/adapters/doubao/index.py` execute() 真实分支; 单测 ≥ 8 例 (login redirect → COOKIE_EXPIRED / captcha overlay → CAPTCHA_REQUIRED / `.reference-card` 抽 citation / textContent 强制 / API fallback 走通 / 错误码 PARSER_FAIL coerce / response_source stamp 'web_ui') | F4-1 selftest 绿 |
| 4 | DeepSeek-CN + ChatGPT execute() 真实化 | `deepseek/index.py` + `chatgpt/index.py` 真实分支 (含 Cloudflare Turnstile 走 guest_executor 吸收的逻辑); 单测各 ≥ 8 例 | F4-1 selftest 绿 |
| 5 | Luban SMS live + crypto_noop | `app/accounts/sms/luban.py` httpx async live; `app/accounts/crypto_noop.py` UTF-8 JSON encode/decode; 单测 ≥ 12 例 (httpx mock via respx, retry / OTP 等待 / 号码释放 / 错误码 / encode-decode roundtrip / null 值容错) | LUBAN_API_KEY env 配好后跑 (live 跳过, mock 跑) |
| 6 | auto_register live (doubao + deepseek-CN) | `app/accounts/auto_register.py` stub → 编排器 (Camoufox + Luban + cookie 导出 + DB 写入); 单测 ≥ 10 例 (mock Camoufox + mock Luban, success / OTP timeout / 表单填写失败 / cookie 导出空 / DB 写入冲突 / 状态机转换) | S2/S3 Layer 3 验证条件就位 |
| 7 | CAPTCHA Level 1/2/3 真实化 | `app/engines/captcha/{slider.py, vision.py, solve.py}` 吸收 OpenCV + 火山 Ark vision; 单测 ≥ 12 例 (slider 滑块图算偏移 / vision API 调通 mock / solve 三级兜底顺序 / 全失败抛 CAPTCHA_REQUIRED / CapSolver mock) | F4-1 内含 |
| 8 | CLI 3 命令 | `app/accounts/cli/{list.py, register.py, inject.py}` (typer or argparse); 单测 ≥ 9 例 (argparse 校验 / 缺参 → exit 1 / engine literal validation / count 边界) + L1.6 CLI help works | L1.6 绿 |
| 9 | Golden HAR 录制 + sanitize | 用 Frank 配的 doubao/deepseek 实账号 (Step 6 注册的) + ChatGPT (Step 4 inject 的) 各跑 1 条 query, Camoufox `context.routeFromHAR` 录, 经 sanitize 写入 `tests/fixtures/adapters/<engine>/golden-skincare-*.har`; F2 leak scan 必须绿 | L1.9 F2 绿 |
| 10 | routeFromHAR 回放 integration tests | `tests/integration/engines/test_<engine>_replay.py` 用 pytest-playwright `route_from_har` fixture 离线回放 + 断言 citation/sentiment/ranking 数 | L1.4 integration 绿 |
| 11 | Harness F5 + selftest 10/10 | `scripts/python/ci-check.py` 加 1 条新 grep (F5) + 1 fixture (`backend/app/__ci_fixtures__/F5_admin_imports_luban.cifixture.py`); EXPECTED_POSITIVES 9 → 10 (Python pivot 链, F4-1/F4-2/F4-3 在 Session 1' 已落) | L1.7/L1.8 绿 |
| 12 | 文档同步 + 决策 #38 | `docs/SESSION_PROGRESS.md` Session 1.2' done + M2 milestone 末标记; `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 摘要更新; `CLAUDE.md` 决策 #38 (Session 1.2' 交付摘要 A-H 段); `docs/SESSION_1_2_PRIME_DELIVERY.md` 交付报告 (§6 模板) | 所有 docs 引用段号校验绿 |

---

## §6 · Delivery Report Template

> Session 收尾时, 在 `docs/SESSION_1_2_PRIME_DELIVERY.md` 按下面模板填写, 末尾粘贴 §0 F1-F8 grep 重跑结果 (决策 #25 规则 7 闭环)。

```markdown
# Session 1.2' Delivery Report (M2 Milestone 末)

## Phase Gate Evidence

### Layer 1 · 12 项自动验证
- [ ] L1.1 ruff strict 绿
- [ ] L1.2 mypy strict 绿
- [ ] L1.3 pytest unit ≥ 80% coverage 绿
- [ ] L1.4 pytest integration (HAR replay) 绿
- [ ] L1.5 Camoufox smoke launch 绿
- [ ] L1.6 CLI 3 命令 help 全绿
- [ ] L1.7 Harness Group F 全绿 (F1+F2+F3 + F4-1+F4-2+F4-3 已在 Session 1' 落地 + F5 本 Session 新增)
- [ ] L1.8 selftest 10/10 PASS (Python pivot 链)
- [ ] L1.9 F2 HAR leak scan 在 3 golden HAR 上绿
- [ ] L1.10 alembic schema diff 绿 (response_source enum 未变)
- [ ] L1.11 query_executions / ai_responses 无新顶层列
- [ ] L1.12 Platform Layer 边界 — admin/api 零 luban import

### Layer 2 · Harness selftest
- [ ] `uv run python scripts/python/ci-harness-selftest.py` 输出 `selftest: PASS  (10 / 10 fixture expectations met)`

### Layer 3 · Frank 在 preview env 验证 (M2 Milestone 末闭环)
- [ ] S1 preview alembic upgrade head 成功 (build log 截图)
- [ ] S2 `accounts:register --engine=doubao` 走 Luban 成功 (CLI output + DB row 截图)
- [ ] S3 `accounts:register --engine=deepseek-CN` 走 Luban 成功
- [ ] S4 `accounts:inject --engine=chatgpt` 手工导入成功
- [ ] S5 admin pipeline accounts list API 返回 ≥ 1 doubao active
- [ ] S6 doubao query → ai_responses +1 'web_ui' (截图 DB)
- [ ] S7 deepseek-CN query → ai_responses +1 'web_ui'
- [ ] S8 chatgpt query → ai_responses +1 'web_ui' or 'api_fallback' (代理降级时)
- [ ] S9 Frank 贴 build log + DB 截图回 thread

## 偏差登记 (决策 #25 规则 3)

### C1 (...): ...
- 现象: ...
- 根因: ...
- 处置: ...
- 真相源同步: ... (影响哪个文档段号)

### C2 (...): ...

(后续 C3/C4/...)

## 真相源同步影响

- `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 段 X 改: ...
- `docs/SESSION_PROGRESS.md` Session 1.2' 状态 → done, M2 Milestone 末闭环
- `CLAUDE.md` 决策 #38 新增 (本 Session 交付摘要)

## CLAUDE.md 决策 #38 草案

> 待 Frank merge 时正式定稿。

38. **Session 1.2' · Camoufox + 3 引擎 Adapter Live + Luban SMS Live (M2 Milestone 末) 交付 (2026-XX-XX)**: 按 `docs/REPLAN_2026_04_26.md §4` Session 1.2' scope 落地 ...

    **A. Camoufox launch + humanize 真实化**: ...
    **B. 3 引擎 execute() 真实化 (doubao + deepseek-CN + chatgpt)**: ...
    **C. Luban SMS live + auto_register live (doubao + deepseek-CN)**: ...
    **D. CAPTCHA 三级真实化 (slider OpenCV + vision Ark + CapSolver mock)**: ...
    **E. CLI 3 命令 (accounts:list / accounts:register / accounts:inject)**: ...
    **F. Golden HAR 录制 + routeFromHAR 回放 integration**: ...
    **G. Harness F5 + selftest 9→10 (F4-1/F4-2/F4-3 在 Session 1' 已落, Python pivot 本地链)**: ...
    **H. 偏差登记 (C1-Cn)**: ...

## 下一 Session 依赖确认

- Session 2' (Planner Pipeline) 可以开工: 本 Session 交付的 ai_responses 表 + 6 enum response_source + Camoufox + 3 adapter live 是 Session 2' 触发 plan.generate dry-run 的运行时基础
- Session 3' (Response 采集 + 分析) 依赖本 Session 的 execute() 真实化 + golden HAR

## §0 F1-F8 重跑结果

(粘贴每条 grep 实际输出)
```

---

## §7 · Closing Loop (决策 #25 规则 7)

Session 收尾前, 重新跑 §0 全部 8 条 grep, 把输出粘到 §6 末尾 "F1-F8 重跑结果"。任一输出与开工时的输出有差异 (e.g. CLAUDE.md 决策号变了, ADAPTER_CONTRACT 段号漂移) → 在 §6 偏差登记新增条目说明影响, 同步到 CLAUDE.md 决策 #38。

---

## §8 · 10 Final Reminders

1. **真相源不重抄**: ADAPTER_CONTRACT §5.1 / §5.3a / §5.4 / §6 / §9 / §10 是契约真相源, 本 Session 的代码注释只 `# See ADAPTER_CONTRACT.md §X.Y`, 禁重抄段内容到代码注释或 docstring 内
2. **Commit 标题格式**: `Session 1.2' Step <N>: <主题>`, 全 ASCII, 无 emoji, 无 § 符号, 无破折号 — Frank 已固化 (memory `feedback_genpano_session_commit_rule.md`); 末尾 footer 加 `Refs: CLAUDE.md #38 (forthcoming)`
3. **常量单一入口**: `STEP_BUDGET_MS` 在 `app/accounts/prewarm.py` 顶端单一定义, `BCRYPT_COST=12` (Session A0' 已落) 不重复, `LUBAN_API_BASE_URL` 在 `app/accounts/sms/luban.py` 顶端单一定义, **禁** 任何模块内 `BASE_URL = 'https://...'` 散落
4. **6 enum response_source 不重复定义**: 单一入口在 `app/models/ai_response.py` (SQLAlchemy enum); F4-1/F4-2/F4-3 三处 stamp 都从同一 enum import 取值, 禁 `response_source='web_ui'` 字符串 literal 散落 (F4 grep 会拦)
5. **httpx mock 走 respx**: Luban / 火山 Ark / OpenAI 三处 HTTP 客户端单测全部走 `respx.mock()`, 禁 monkeypatch http 全局 — pytest fixture 写在 `tests/conftest.py`
6. **golden HAR 必经 sanitize**: F2 9 种 leak pattern 是 hard gate; 录制流程在 `app/har/recorder.py::record_session()` 内置 sanitize post-step, 不能跳过 (即使是测试 fixture)
7. **Platform Layer 边界铁律**: `app/api/**` (用户态 FastAPI) + `app/admin_api/**` (Admin FastAPI) 不得直接 `import luban / from app.accounts.sms.luban`, 必须走 `from app.accounts import register_account` re-export — F5 grep 拦截
8. **零 frontend 改动**: 本 Session 不动 `frontend/**`; Layer 3 验证用 Admin curl/HTTPie API stub, 不依赖前端 UI
9. **每个 commit verify-green**: 不要堆叠到最后才跑 verify-session-1.2prime.sh; 每 step 只跑该 step 相关检查就好, Step 12 跑全套 12 项
10. **Closing Loop 必跑**: 收尾前重跑 §0 F1-F8 grep + 校对 §1 真相源段号是否仍成立 + 任何漂移登记 §6 偏差段; 这是决策 #25 规则 7 的闭环条件

---

**END OF SESSION 1.2' PRIME PROMPT**
