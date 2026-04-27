# Session 1' · Adapter 框架 + Account/Proxy Pool (Python 重写, 吸收 geo_tracker) — Prompt for Claude Code

> **使用说明**: 本文档是给 Claude Code 的 Session Prompt, Frank 直接复制本文件全部内容到 Claude Code 即可启动 Session 1'。
> 本 Prompt 严格遵守 `CLAUDE.md` 决策 #25 的 12 条 Prompt 编写公约 (规则 1-7 + 10/11/12)。
>
> **角色**: 你 (Claude Code) 是 GENPANO 后端引擎层架构师, 负责把合并仓 `geo_tracker/` (~10000 行 Python 实战代码) 的有效部分**重组**为 `backend/app/engines/` 标准目录结构, 同时按 `docs/ADAPTER_CONTRACT.md` 真相源对齐接口契约。**本 Session 不让 Adapter 真跑** (Camoufox launch / 真实 page.goto / 鲁班 SMS live / 真实 HAR 录制全部留给 Session 1.2'), 只交付 "结构框架 + 可测试纯逻辑", 算法层 (parser / scheduler / state-machine / profile-sampler / humanize / proxy pool / HAR sanitize) 必须真实实现以满足 pytest 80% 分支覆盖。
>
> **历史依据**: 本 Session 是 master Session 1 (TS 框架, 决策 #22) + master Session 1.2 双修正预先登陆 (决策 #28.G F4 三子规则 + 6 枚举 response_source) 的 Python 重写合并版。TS 后端代码已废止 (决策 #29), `geo_tracker/` 是 Python 基线 (决策 #32 工作仓 = `C:\Users\frank.wang\genpano`)。

---

## §0 前置 Grep 契约 (规则 2)

**开工第一批动作**: 必须先跑下列 grep 自证真相源仍与本 Prompt 引用一致, 任一不一致 → 停下 alignment 不写代码 (规则 7 闭环回路也复用本组命令)。

```bash
# F1: 决策 #25 (12 条公约) / #29 (Python pivot) / #30 (preview) / #31 (branch-per-session) 仍在 CLAUDE.md
grep -nE "决策 #(25|29|30|31)" CLAUDE.md | head -10

# F2: 决策 #22 (Session 1 TS 框架) + #28.G (双修正预先登陆 F4 三子) 仍在 CLAUDE.md (作为历史参照)
grep -nE "决策 #22|#28\.G|F4-1|F4-2|F4-3|response_source|6 枚举" CLAUDE.md | head -15

# F3: ADAPTER_CONTRACT.md 真相源仍齐全 (12 章, MVP 3 引擎契约)
grep -nE "^## §[1-9]|^## §1[0-2]|EngineId|AdapterError|ExecutionContext|browser_profile" docs/ADAPTER_CONTRACT.md | head -20

# F4: REPLAN §4 Session 1' 范围 + §6.5 Group F harness 迁移仍存在
grep -nE "^### Session 1'|Group F|F1.*F2.*F3|geo_tracker" docs/REPLAN_2026_04_26.md | head -10

# F5: SESSION_PROGRESS.md Session 1' ⬜ 未启动
grep -nE "1' .*⬜|Session 1' " docs/SESSION_PROGRESS.md | head -5

# F6: Session 0' 已交付 (M1 起点 backend/ 骨架就绪 + Alembic + ci-harness.py + pyproject.toml)
ls backend/app/__init__.py backend/alembic.ini scripts/python/ci-harness.py pyproject.toml 2>&1 | head -10

# F7: 合并仓 geo_tracker/ 仍在原位 (本 Session 反向工程入口)
ls geo_tracker/agent/executor.py geo_tracker/agent/guest_executor.py geo_tracker/sms_login/ geo_tracker/agent/clash_api.py geo_tracker/agent/human_behavior.py 2>&1 | head -10

# F8: ai_responses 表已经在 Session 0' Alembic baseline 中 (response_source 列存在但 NO DEFAULT)
grep -rnE "response_source|ai_responses" backend/alembic/versions/ | head -10
```

如果任一 grep 返回 0 行或路径不存在, 立即停止并报告偏离 (规则 11 freshness check 已经被 Frank 在发 Prompt 前 30min 内执行过, 本 grep 是开工再次 self-verify)。

---

## §1 真相源索引 (规则 5 / 6)

| 文件 | 段号 | 标签 | 用途 |
|------|------|------|------|
| `CLAUDE.md` | 决策 #22 (Session 1 TS 框架) | [引用-历史参照] | TS 实现已弃, 但 §A-§G 章节描述的算法决策 (sentiment 三档 / brand-matcher 句级去重 / retry 9 错误码 / state-machine 6 状态 / proxy 黑名单 top-of-hour) 仍是 Python 重写的语义真相源 |
| `CLAUDE.md` | 决策 #28.G C1-C4 (双修正预先登陆) | [引用] | F4 三子规则 + 6 枚举 response_source labeling + MVP 3 引擎口径 (`chatgpt | doubao | deepseek-CN`) |
| `CLAUDE.md` | 决策 #25 (12 条 Prompt 公约) | [引用] | 本 Prompt 自身遵守 |
| `CLAUDE.md` | 决策 #29 (Python pivot) | [引用] | TS 后端代码已弃, 全 Python; FastAPI + SQLAlchemy + Pydantic v2 + Playwright + Camoufox |
| `CLAUDE.md` | 决策 #30 (preview env) | [引用] | 本 Session 不强制 preview 端到端 (REPLAN §4 Session 1' Phase Gate 明示), 但 CI 必须绿 + harness selftest 必须绿 |
| `CLAUDE.md` | 决策 #31 (branch-per-session) | [引用] | 本 Session 分支 = `session-1prime`, 从 main fork |
| `CLAUDE.md` | 决策 #32 (工作仓) | [引用] | `C:\Users\frank.wang\genpano`; `geo_tracker/` 在原位但被 ruff/mypy `exclude` (Phase 2 才整体迁) |
| `docs/ADAPTER_CONTRACT.md` | §1-§12 全文 | [引用-真相源] | Adapter 接口 / Profile-Aware / 三层反检测 / 账号 Cookie / 9 错误码 / 代理调度 / DOM quirks / CAPTCHA 三级 / 观测 HAR / MVP 顺序 — 不修改, 只翻译为 Python 接口 |
| `docs/PRD.md` | §4.2.2a (引擎枚举) | [引用] | `chatgpt | doubao | deepseek` 是 EngineId, MVP 仅这 3 家 |
| `docs/PRD.md` | §4.2.4.A (Sentiment 0.5 tiebreak) | [引用] | `[0, 0.45] negative / (0.45, 0.55) neutral / [0.55, 1.0] positive`, 单一入口 `classify_sentiment()` |
| `docs/PRD.md` | §4.2.6 A-H (Citation 5 Tier) | [引用] | tier_weight 1.0/0.7/0.4/0.15 + 3 级归因 (official_domain > co_occurrence > text_match) |
| `docs/REPLAN_2026_04_26.md` | §4 Session 1' 范围 | [引用-真相源] | 做 / 不做 双列表权威源 |
| `docs/REPLAN_2026_04_26.md` | §6.5 Group F harness | [引用] | F1-F4 Python 重写, 扫 `backend/app/engines/` |
| `docs/REPLAN_2026_04_26.md` | §7 不变项 | [引用] | MVP 3 引擎 + 6 枚举 response_source 战略不变 |
| `docs/HARNESS_ENGINEERING.md` | §10.3-§10.8 | [引用] | Phase Gate / 三层 Agent QA / Fix Loop |
| `docs/SESSION_PROGRESS.md` | Session 1' 行 | [修改] | 收尾时翻 ⬜ → ✅ |
| `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` | Session 1' 段 | [修改] | 收尾时回填实施摘要 |
| `geo_tracker/agent/executor.py` | 全文 | [反向工程入口] | Camoufox launch + page.goto 已跑通逻辑 (本 Session 不真跑, 只抽提 selectors / DOM 路径作为 `selectors.py` 锚点) |
| `geo_tracker/agent/guest_executor.py` | 全文 | [反向工程入口] | ChatGPT guest 模式 (Cloudflare Turnstile bypass) — 本 Session 抽 selectors, Session 1.2' 真接 |
| `geo_tracker/sms_login/luban_client.py` | 全文 | [反向工程入口] | 鲁班 HTTP client 已跑通 — 本 Session 翻译为 `accounts/sms/luban.py` stub (live 接入留 1.2') |
| `geo_tracker/agent/clash_api.py` | 全文 | [反向工程入口] | Clash 订阅链接拉节点 — 本 Session 翻译为 `proxy/clash.py` |
| `geo_tracker/agent/human_behavior.py` | 全文 | [反向工程入口] | 鼠标 Bezier / Box-Muller jitter — 本 Session 翻译为 `behavior/humanize.py` (PagePort interface, 不强耦 Playwright) |
| `geo_tracker/agent/slider_captcha.py` + `vision_captcha.py` | 全文 | [反向工程入口] | CAPTCHA 三级兜底 — 本 Session 翻译为 `captcha/{slider,vision,solve}.py` |

**修改清单** (本 Session 完成后产生):
- 新建 `backend/app/engines/__init__.py` + 子目录骨架 (`adapters/{chatgpt,doubao,deepseek}/` + `parsers/` + `scheduler/` + `accounts/{sms/}` + `proxy/` + `behavior/` + `captcha/` + `profile/`)
- 新建 `backend/app/engines/adapters/base.py` (AdapterPort interface, AdapterError 9 错误码 enum, ExecutionContext / AdapterResult dataclass)
- 新建 3 引擎 stub (`adapters/{chatgpt,doubao,deepseek-CN}/{__init__.py, selectors.py, index.py, api_fallback.py, README.md}`) — `index.py` 的 `execute()` 返回 `TIMEOUT` sentinel, 真实化留 1.2'
- 新建 5 个 parser 模块 (`parsers/{normalize,brand_matcher,sentiment_classifier,citation_extractor,ranking_extractor}.py`)
- 新建 4 个 scheduler 模块 (`scheduler/{retry,backoff,state,queue}.py`)
- 新建 5 个 accounts 模块 (`accounts/{state_machine,pool,prewarm,auto_register}.py` + `accounts/sms/luban.py` stub)
- 新建 2 个 proxy 模块 (`proxy/{pool,clash}.py`)
- 新建 1 个 humanize 模块 (`behavior/humanize.py` — PagePort 抽象接口, 不 import playwright)
- 新建 3 个 captcha 模块 (`captcha/{slider,vision,solve}.py` — 三级兜底, solve.py 全失败抛 CAPTCHA_REQUIRED)
- 新建 1 个 profile-sampler 模块 (`profile/sampler.py` — FNV-1a 确定性 hash + 8 preset)
- 新建 `backend/app/har/sanitize.py` (HAR 1.2 + 转义 JSON 双轨脱敏)
- 新建 `backend/tests/unit/engines/` 下 ≥ 13 套 pytest 单测 (覆盖 parsers / scheduler / accounts / proxy / humanize / profile-sampler / har-sanitize)
- 新建 `backend/tests/fixtures/scraping/queries.json` (4 条规范查询 — skincare-recommendation-zh/en, luxury-watch-comparison-zh, beverage-market-leaders-zh)
- 扩 `scripts/python/ci-harness.py` Group F 段 (F1/F2/F3/F4 共 6 条规则: F1 no-bare-playwright-import / F2 har-fixture-secret-leak / F3 no-inline-prompt-literal / F4-1 adapter-execute-must-stamp-response-source / F4-2 api-fallback-must-stamp-response-source / F4-3 ai-responses-insert-must-include-response-source)
- 扩 `scripts/python/ci-harness-selftest.py` EXPECTED_POSITIVES 从 Session 0' baseline +6 (F1/F2/F3/F4-1/F4-2/F4-3 各 1 fixture)
- 新建 `backend/.harness_fixtures/F1_playwright_bare_import.cifixture.py` / `F2_har_bearer_leak.cifixture.har` / `F3_inline_prompt.cifixture_test.py` / `F4_1_adapter_no_response_source.cifixture.py` / `F4_2_api_fallback_no_response_source.cifixture.py` / `F4_3_alembic_insert_no_response_source.cifixture.sql`
- 新建 `verify-session-1prime.sh` (Layer 1 可执行验收脚本)
- 新建 `docs/SESSION_1_PRIME_DELIVERY.md` (收尾时回填 Phase Gate 通过证据)
- 修改 `docs/SESSION_PROGRESS.md` (Session 1' 状态 ⬜ → ✅)
- 修改 `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` (Session 1' 段回填摘要)
- 修改 `CLAUDE.md` (新增决策 #35 · Session 1' Python Adapter 框架交付)

**版本警告**:
1. **MVP 引擎口径锁定**: 仅 `chatgpt | doubao | deepseek-CN` (决策 #28.G C4)。`deepseek-CN` 是 `EngineId` literal (区别将来可能出现的 `deepseek-overseas`), **目录路径仍为 `adapters/deepseek/`** 不改文件路径。Gemini / Claude / Bing **本 Session 不写**, 任何"为扩展性预留"的 5 引擎枚举就是范围外, 请走 §3 Type C STOP。
2. **Adapter execute() 不真跑**: 本 Session 全部 `execute()` 实现返回 `AdapterResult(error=AdapterError.TIMEOUT, response_source='harness_fixture')` sentinel。**禁** import `playwright` 真实 launch (除 `behavior/humanize.py` 的 PagePort interface 用 typing-only forward-ref + `behavior/camoufox_launch.py` 这两个白名单文件)。Camoufox 真实启动留 Session 1.2'。**Harness F1 锁定**白名单。
3. **6 枚举 response_source 全量必须 label**: `web_ui | api_fallback | mock_proxy | cached_replay | admin_har_replay | harness_fixture` — 本 Session 由于 execute() 返回 TIMEOUT sentinel, 全部用 `harness_fixture` 标; api_fallback.py 的所有返回路径必须显式 stamp `response_source='api_fallback'` (即使 stub 实现); Alembic baseline 中 `ai_responses.response_source` 列**已经在 Session 0'** 中创建为 `VARCHAR(20) NOT NULL` (NO DEFAULT) — 本 Session 不动 schema, 但所有 `INSERT INTO ai_responses` 必须显式列出 `response_source` 列。Harness F4 三子规则锁定。
4. **9 错误码不可缩**: AdapterError = `TIMEOUT | NETWORK | CF_BLOCKED | CAPTCHA_REQUIRED | COOKIE_EXPIRED | NO_ACCOUNT_AVAILABLE | RATE_LIMITED | PARSER_FAIL | UNKNOWN` — 全枚举来自 `docs/ADAPTER_CONTRACT.md §6`, 任何缩为 8 或扩为 10 都立挂 §3 Type B STOP。`retry_count` **只活在 ExecutionContext.attempt 内存中**, **绝不**做 `query_executions` 表列 (决策 #22 §A 锁死)。
5. **Sentiment 三档边界严格**: `[0, 0.45] negative / (0.45, 0.55) neutral / [0.55, 1.0] positive` (PRD §4.2.4.A), `classify_sentiment()` 是单一入口, 分数强制 clamp 到 `[0.05, 0.95]` 避免 0/1 边界崩。harness grep `(sentiment|score)\s*>\s*0\.5` 拦其他 tiebreak 写法, 已经在 Session 0' Group D 中登陆。
6. **Citation 3 级归因 + 5 Tier 权重**: `official_domain (1.0) > co_occurrence (0.7) > text_match (0.4)` (PRD §4.2.6); Tier 表 `tier 0..4 = 0.0/1.0/0.7/0.4/0.15` — 本 Session **禁硬编码** Tier 权重 (决策 #19 + Session A5'/Admin 把 tier 表升 DB seed)。本 Session 的 `citation_extractor.py` 接收 `tier_weights: dict[int, float]` 注入参数, 测试桩化, 真实参数源由 Session 3' / A5' 接 DB lookup。
7. **未来 git mv 已知**: 当 Session A1' / 3' 把 Admin Pipeline Monitor + Account 管理 UI 落地时, `app/engines/accounts/**` 会按决策 #28.A (Platform Layer 边界) 上移到 `app/platform/accounts/**` (Platform Layer)。本 Session 先放 `app/engines/accounts/` 是范围对齐 REPLAN §4 Session 1' 描述 ("吸收 sms_login/ + pool/" 之描述位置), 后续 mv 不破契约。

---

## §2 MVP 范围 — 做 / 不做 双列表 (规则 10)

### ✅ 本 Session 做 (锚点 = `docs/REPLAN_2026_04_26.md §4 Session 1'`)

| # | 项 | 锚点 | 验收信号 |
|---|----|------|---------|
| 1 | AdapterPort interface (Python Protocol) + 9 错误码 enum + ExecutionContext / AdapterResult dataclass | ADAPTER_CONTRACT §1 §6 | `mypy --strict` 通过, `pytest tests/unit/engines/test_base.py` 8 例绿 |
| 2 | 3 引擎 stub (`adapters/{chatgpt,doubao,deepseek-CN}/`): selectors.py + index.py (execute() = TIMEOUT) + api_fallback.py (火山 ARK 走 OpenAI-compatible, stub 返回固定 mock) + README.md | ADAPTER_CONTRACT §3 §4 + 决策 #22 §A | 3 引擎 import 均通过, F1 不抓本目录任何文件, F4-1/F4-2 fixture 抓本目录 fixture 后 selftest 绿 |
| 3 | 5 parser 模块 (normalize / brand_matcher / sentiment_classifier / citation_extractor / ranking_extractor) | 决策 #22 §B + PRD §4.2.4/§4.2.6 | pytest 各模块 ≥ 8 例 (含边界 + 国际化), coverage ≥ 80% |
| 4 | 4 scheduler 模块 (retry / backoff / state / queue) | 决策 #22 §C | retry exec_with_retry 9 错误码穷举 / backoff 注入 random clamp / state 6 状态 + LEGAL_TRANSITIONS / queue 每引擎独立 concurrency |
| 5 | accounts state-machine + pool (LRU + watermark) + prewarm 7 步 + auto-register stub + sms/luban stub | 决策 #22 §C + ADAPTER §5.1 §5.3a §5.4 | pool 抛 `pool:low_watermark` event / prewarm `should_quarantine` 连续 3 失败 / luban.py 是 stub 不是真实 HTTP client (留 1.2') |
| 6 | proxy/pool.py (黑名单 top-of-hour) + proxy/clash.py (订阅 URL fetch + 解析节点列表) | ADAPTER §7 + 决策 #22 §C | zero healthy 抛 `proxy:zero-healthy` / clash 不真发 HTTP (mock requests) |
| 7 | humanize.py (PagePort 抽象 interface, Box-Muller normalSample, Bezier cubic mousePathPoints) | 决策 #22 §C.x | 不 import playwright; pytest 验 jitter 钳制范围 + Bezier endpoints 严格等于起止点 |
| 8 | captcha 三级兜底 (slider → vision → CAPTCHA_REQUIRED) | ADAPTER §10 + 决策 #22 §C.xi | solve.py 全失败抛 CAPTCHA_REQUIRED |
| 9 | profile/sampler.py (FNV-1a 确定性 hash + `cn-consumer-desktop / overseas-consumer-us / overseas-consumer-sea` 8 preset) | 决策 #22 §C.xii | 同 `(profileGroupId, seed)` 必得同 preset; pytest 验确定性 + 分组隔离 |
| 10 | har/sanitize.py (HEADERS_TO_STRIP_REQUEST/RESPONSE + BODY_FIELDS_TO_STRIP 递归) — HAR 1.2 name/value 双轨 + content.text 嵌入转义 JSON | ADAPTER §9 | pytest 验 Authorization / Cookie / refresh_token 全脱敏成 `__REDACTED__`, 嵌套 + 转义 JSON 也覆盖 |
| 11 | tests/fixtures/scraping/queries.json (4 条规范查询) | 决策 #22 §D | 所有 HAR replay 测试必须从这里读 prompt, F3 拦内联 prompt literal |
| 12 | Group F harness 6 条规则 (F1-F4 三子) Python 重写 (`scripts/python/ci-harness.py`) | 决策 #28.G C2 + REPLAN §6.5 | `python scripts/python/ci-harness.py --group F` 全 6 条扫到 fixture 各 1 命中, 选 selftest +6 |
| 13 | 6 个 self-seeded fixture (各 1 故意违规) + EXPECTED_POSITIVES 从 Session 0' baseline (3) → 9 | REPLAN §6.5 + 决策 #21.C self-seeded harness 范式 | `python scripts/python/ci-harness-selftest.py` 打印 `selftest: PASS  (9 / 9 fixture expectations met)` |
| 14 | pytest backend/tests/unit/engines 全绿 + 覆盖率 ≥ 80% (branches/lines/functions/statements) | REPLAN §4 Session 1' Phase Gate + Session 0' baseline | `uv run pytest tests/unit/engines/ --cov=app/engines --cov-report=term --cov-fail-under=80` 全绿 |
| 15 | ruff + mypy strict 绿 | Session 0' Step 1 已建立 baseline | `uv run ruff check backend/app/engines/` + `uv run mypy backend/app/engines/ --strict` 0 error |
| 16 | verify-session-1prime.sh + docs/SESSION_1_PRIME_DELIVERY.md (Phase Gate 证据回填) | Session 0' 范式 | 脚本可执行, 跑通 Layer 1 全绿 |
| 17 | 分支管理: 从 main fork `session-1prime`, ≤ 12 commits, 每 commit 格式 `Session 1' Step <N>: <主题>` | 决策 #31 + Session 0' 起始范式 | `git log session-1prime --oneline` 全部符合格式 |
| 18 | 文档同步: 翻 `docs/SESSION_PROGRESS.md` Session 1' ⬜ → ✅, `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` 回填摘要, `CLAUDE.md` 加决策 #35 | 决策 #25 规则 4 双向同步 | grep `Session 1' .*✅` 在 SESSION_PROGRESS.md 命中 |

### ❌ 本 Session 不做 (留给后续 Session 的明确 scope cut)

| # | 项 | 留给 | 理由 |
|---|----|------|------|
| N1 | Camoufox launch 真实 ( `playwright_extra.firefox.launch` + stealth) | Session 1.2' | F1 锁定 playwright import 白名单, 真接入 Camoufox 才放白; M2 Milestone 末才要求 preview Camoufox 跑 |
| N2 | Adapter execute() 真实 page.goto + Cloudflare iframe handling | Session 1.2' | execute() 全返 TIMEOUT sentinel, 真实化与 Camoufox 配套 |
| N3 | 鲁班 SMS live HTTPS client + auto-register live (doubao + deepseek-CN sign-up live 化) | Session 1.2' (决策 #28.C2) | 本 Session luban.py / auto_register.py 是 stub, 不发真实 HTTP |
| N4 | golden HAR 录制 + routeFromHAR 回放契约测试 (pytest-playwright integration) | Session 1.2' | 本 Session 仅有 sanitize 单测 + queries.json fixtures, 不录制真实 HAR |
| N5 | 3 个 CLI 命令 (`accounts:list` / `accounts:register` / `accounts:inject`) | Session 1.2' | 配合 luban live + auto-register live 一起交付 |
| N6 | DB-backed account pool (Prisma → SQLAlchemy 真实 repo, accounts 表 schema) | Session 1.2' (Platform Layer 整体落) | 本 Session pool 是 in-memory `list[AccountRecord]`, repo port 留接口 (`AccountRepoPort` Protocol) |
| N7 | DB-backed proxy pool + Clash 订阅真实 fetch | Session 1.2' / Session 3' | 本 Session 都是 in-memory; Clash 订阅 URL 只 stub 解析逻辑, 不真发 HTTP |
| N8 | CAPTCHA 真接 CapSolver / 火山 vision API | Session 1.2' | solve.py 是接口三级 fallback 框架 + raise CAPTCHA_REQUIRED, 不真调外部 API |
| N9 | Response 采集 (Celery worker 消费 query_executions 写 ai_responses) | Session 3' | 本 Session 不写 worker 逻辑, 只交付被 worker 调用的 AdapterPort + Parser |
| N10 | Topic Planner / Prompt Generator / Query Assembler 三层 Pipeline | Session 2' | Planner 由 Session 2' 全责; 本 Session 的 profile-sampler 是被 Planner 复用的下游 |
| N11 | 知识图谱 LLM bootstrap (industry / brand / product discovery) | Session 1.5' | 本 Session 不接 KG; brand_matcher.py 接收 `BrandsCatalog` 注入参数, 测试桩化 |
| N12 | preview env 端到端验证 | Session 1.2' (M2 Milestone 末) | REPLAN §4 Session 1' Phase Gate 明示: "本 Session 不要求 preview 端到端验证, 因为还没接到 Pipeline 编排" |
| N13 | Citation 6 行动面 (归因诊断 / 内容策略 / PR / 竞品 / Simulator / MCP) | Session 3' | 本 Session 仅 citation_extractor.py 抽提 + tier 注入, 不做行动面 |
| N14 | 多轮对话 Query (`Query.turns[]`) | Phase 2 (决策 #26.C2) | MVP 单轮; 本 Session AdapterPort 接受单轮 prompt → response |
| N15 | Frontend 修改 | Session 4b' | 本 Session 100% 后端 |

---

## §3 STOP Triggers (规则 12)

如果遇到以下情况, 立即停止 + 写 STOP 报告 + 等 Frank 介入, **不要绕过**:

### Type A · 环境失败 (依赖工具不可用)

| ID | 触发条件 | STOP 报告内容 |
|----|---------|--------------|
| A1 | `pyproject.toml` 缺失 / `uv` 不可用 / Python 3.11+ 不可用 | 必需依赖未就位, 请先重做 Session 0' Step 1 |
| A2 | `backend/app/__init__.py` / `backend/alembic.ini` 缺失 | Session 0' 未交付完整, 请先 verify Session 0' Phase Gate |
| A3 | `geo_tracker/agent/executor.py` / `human_behavior.py` / `clash_api.py` 路径不存在 | 反向工程入口缺失, 请确认决策 #32 工作仓 = `C:\Users\frank.wang\genpano` |
| A4 | `pytest` / `ruff` / `mypy` 安装失败 (uv sync 出错) | 报错原文 + uv version + Python version |
| A5 | `scripts/python/ci-harness.py` 缺失 / 不可执行 | Session 0' 交付不完整 |
| A6 | `backend/alembic/versions/` 中 `ai_responses.response_source` 列不存在 | Session 0' Alembic baseline 不含本列, 需先补 Session 0' |

### Type B · 真相源冲突 (引用与现状不一致)

| ID | 触发条件 | STOP 报告内容 |
|----|---------|--------------|
| B1 | `docs/ADAPTER_CONTRACT.md §6` 错误码不再是 9 个 | 引用段号 + 当前枚举 + 与本 Prompt 描述差异 |
| B2 | `CLAUDE.md` 决策 #28.G C3 6 枚举 response_source 不再是 `web_ui | api_fallback | mock_proxy | cached_replay | admin_har_replay | harness_fixture` | 列出当前枚举 + 差异 |
| B3 | `docs/PRD.md §4.2.4.A` Sentiment tiebreak 边界 (0.45/0.55) 已变 | 列出当前边界 + 是否影响 classify_sentiment 三档划分 |
| B4 | `docs/PRD.md §4.2.6` Citation Tier 权重 (1.0/0.7/0.4/0.15) 已变 | 列出当前权重 + 是否影响 citation_extractor 注入接口 |
| B5 | `docs/REPLAN_2026_04_26.md §4 Session 1'` "做/不做" 与本 Prompt §2 双列表语义不一致 | 给出 diff |

### Type C · 范围溢出 (实施路径偏离 §2 双列表)

| ID | 触发条件 | STOP 报告内容 |
|----|---------|--------------|
| C1 | 发现需要真实跑 Camoufox / 真实发 HTTPS / 真实接 Luban 才能让 pytest 绿 | 一定是测试设计错了, **测试必须可在脱网环境跑**; 列出失败 case |
| C2 | 发现需要新增第 4 个引擎 (Gemini / Claude / Bing) 才能闭合接口 | 不可能, MVP 锁死 3 引擎; 列出来源压力 |
| C3 | 发现 `query_executions` 表需要 `retry_count` / `persona_snapshot` / `agent_profile_id` 任一顶层列才能让逻辑跑 | 决策 #22 §A + 决策 #26.C1 锁死 NO 顶层列, retry_count 只活在 ExecutionContext |
| C4 | pytest 覆盖率始终 < 80% 且无法通过加单测达到 | 列出哪几行未覆盖 + 为何不可达; 可能是 dead code 需删 |
| C5 | Harness selftest fixture 设计困难 (规则触发不到) | 检查 fixture 文件名是否被反白扫描 + 内容是否真有 grep target; 决策 #21.C 范式回看 |

**STOP 报告模板**:
```markdown
## STOP REPORT

**Type**: [A1-A6 / B1-B5 / C1-C5]
**触发上下文**: <精确到 step 几 + 文件路径 + 行号>
**实证证据**: <command output / 文件内容片段>
**与 Prompt §X 的偏离**: <精确引用 Prompt 哪一行>
**建议方向 (供 Frank 决策, 不自作主张)**:
1. <方案 A>
2. <方案 B>

等待 Frank 答复后再继续。
```

---

## §4 Phase Gate (规则验收闸)

### G_1.1 · Layer 1 · `verify-session-1prime.sh` (一键验收)

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "=== Layer 1.1 ruff strict ==="
uv run ruff check backend/app/engines/ --output-format=concise

echo "=== Layer 1.2 mypy strict ==="
cd backend && uv run mypy app/engines/ --strict --no-error-summary && cd ..

echo "=== Layer 1.3 pytest engines unit, coverage >= 80% ==="
cd backend && uv run pytest tests/unit/engines/ \
  --cov=app/engines --cov=app/har \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q && cd ..

echo "=== Layer 1.4 alembic upgrade head idempotent ==="
cd backend && uv run alembic upgrade head && uv run alembic current | grep -q head && cd ..

echo "=== Layer 1.5 ci-harness Group F (6 条规则) ==="
uv run python scripts/python/ci-harness.py --group F

echo "=== Layer 1.6 ci-harness selftest (9 / 9) ==="
uv run python scripts/python/ci-harness-selftest.py | grep -q "selftest: PASS  (9 / 9 fixture expectations met)"

echo "=== Layer 1.7 import smoke (3 引擎 + parsers + scheduler 全 import 不抛) ==="
cd backend && uv run python -c "
from app.engines.adapters.chatgpt import ChatGptWebAdapter
from app.engines.adapters.doubao import DoubaoWebAdapter
from app.engines.adapters.deepseek import DeepseekCNWebAdapter
from app.engines.parsers import normalize, brand_matcher, sentiment_classifier, citation_extractor, ranking_extractor
from app.engines.scheduler import retry, backoff, state, queue
from app.engines.accounts import state_machine, pool, prewarm, auto_register
from app.engines.proxy import pool as proxy_pool, clash
from app.engines.behavior import humanize
from app.engines.captcha import solve
from app.engines.profile import sampler
from app.har import sanitize
print('all imports ok')
" && cd ..

echo "=== Layer 1.8 9 错误码完整 ==="
cd backend && uv run python -c "
from app.engines.adapters.base import AdapterError
expected = {'TIMEOUT','NETWORK','CF_BLOCKED','CAPTCHA_REQUIRED','COOKIE_EXPIRED','NO_ACCOUNT_AVAILABLE','RATE_LIMITED','PARSER_FAIL','UNKNOWN'}
got = {e.name for e in AdapterError}
assert got == expected, f'mismatch: missing={expected-got}, extra={got-expected}'
print('9 error codes ok')
" && cd ..

echo "=== Layer 1.9 6 枚举 response_source 完整 ==="
cd backend && uv run python -c "
from app.engines.adapters.base import ResponseSource
expected = {'web_ui','api_fallback','mock_proxy','cached_replay','admin_har_replay','harness_fixture'}
got = {e.value for e in ResponseSource}
assert got == expected, f'mismatch: {got} vs {expected}'
print('6 response_source enum ok')
" && cd ..

echo "✅ Session 1' Phase Gate Layer 1 PASS"
```

### G_1.2 · Layer 2 · Harness selftest fixture 验证

`scripts/python/ci-harness-selftest.py` 的 EXPECTED_POSITIVES 列表必须从 Session 0' baseline 3 (D8/D9/D10 stub 占位 + Session 0' 自带) 涨到 **9** (新增 6 fixture):

| Rule | Fixture | 故意违规手段 |
|------|---------|------------|
| F1 `no-bare-playwright-import` | `backend/.harness_fixtures/F1_playwright_bare_import.cifixture.py` | `from playwright.sync_api import sync_playwright` 在非白名单文件 |
| F2 `har-fixture-secret-leak` | `backend/.harness_fixtures/F2_har_bearer_leak.cifixture.har` | HAR 1.2 含 `Authorization: Bearer xyz` + `Set-Cookie: refresh_token=abc` + content.text 嵌入转义 `\"refresh_token\":\"def\"` (双轨抓) |
| F3 `no-inline-prompt-literal` | `backend/.harness_fixtures/F3_inline_prompt.cifixture_test.py` | 引用 `routeFromHAR` 但 prompt literal 内联 ≥ 20 字符的中文 (不 import queries.json) |
| F4-1 `adapter-execute-must-stamp-response-source` | `backend/.harness_fixtures/F4_1_adapter_no_response_source.cifixture.py` | adapter execute() 返回 AdapterResult 不含 response_source 字段 |
| F4-2 `api-fallback-must-stamp-response-source` | `backend/.harness_fixtures/F4_2_api_fallback_no_response_source.cifixture.py` | api_fallback 函数返回 dict 不含 `response_source: 'api_fallback'` |
| F4-3 `ai-responses-insert-must-include-response-source` | `backend/.harness_fixtures/F4_3_alembic_insert_no_response_source.cifixture.sql` | `INSERT INTO ai_responses (id, brand_id, content) VALUES (...)` 缺 response_source 列 |

**关键陷阱**: fixture docstring **故意不 mention** rule 锁定的 token (例: F4-1 fixture 不能在注释里写 `response_source` 这个字符串, 否则 `content.includes()` 自满足导致 selftest silently pass)。这是 master 决策 #21.C / #27.D 的反直觉教训, 请在每个 fixture 第一行写: `# DO NOT mention required token in this docstring; rule must catch real code violation`。

### G_1.3 · Layer 3 · Frank 静态产物审查 (无 browser scenario)

REPLAN §4 Session 1' Phase Gate 明示 **不要求 preview 端到端**, 但 Frank 仍需通过下列 5 项静态产物完成 Layer 3 接受:

| ID | 验收对象 | Frank 检查动作 |
|----|---------|--------------|
| S1 | 4 条 fixture queries.json | 打开 `backend/tests/fixtures/scraping/queries.json`, 确认 4 条 (skincare-recommendation-zh / skincare-recommendation-en / luxury-watch-comparison-zh / beverage-market-leaders-zh) 各有 `prompt` / `engine` / `expected_brands` / `language` 字段 |
| S2 | F2 fixture HAR 抓双轨脱敏 | 打开 `backend/.harness_fixtures/F2_har_bearer_leak.cifixture.har`, 确认同时含 (a) HAR 1.2 name/value `Authorization: Bearer xyz` (b) content.text 嵌入转义 `\"refresh_token\":\"def\"` 两种 leak pattern |
| S3 | 3 引擎 README.md | 浏览 `adapters/{chatgpt,doubao,deepseek}/README.md`, 确认每份描述了引擎特征 (Cloudflare iframe / `.reference-card[data-href]` / `localStorage.userToken`) + 已知 quirks |
| S4 | sanitize 测试输出范例 | `cd backend && uv run pytest tests/unit/har/test_sanitize.py -v` 看到 6+ 条 case 名 (Authorization / Cookie / query / JSON body / nested refresh_token / 空 HAR 幂等) 各 PASS |
| S5 | profile sampler 确定性证明 | `cd backend && uv run python -c "from app.engines.profile.sampler import sample_profile; r1 = sample_profile('cn-consumer-desktop', 'seed-42'); r2 = sample_profile('cn-consumer-desktop', 'seed-42'); print('determinism:', r1 == r2)"` 输出 `determinism: True` |

---

## §5 12-Step 交付顺序 (Atomic Commits)

> **每 commit 格式**: `Session 1' Step <N>: <主题>`
> **每 commit 必须**: `uv run ruff` + `uv run mypy` + `uv run pytest` 全绿才提交; commit 不超过 12 个; 在 `session-1prime` 分支上从 main fork 起步。

| Step | 主题 | 关键交付 | Phase Gate Layer |
|------|------|---------|-----------------|
| 0 | Branch from main | `git checkout main && git pull && git checkout -b session-1prime` | (无 commit) |
| 1 | AdapterPort base + 9 错误码 + ResponseSource 6 枚举 + ExecutionContext / AdapterResult dataclass | `app/engines/adapters/base.py` + pytest test_base.py | L1.7 + L1.8 + L1.9 |
| 2 | 5 parser 模块 + pytest 单测 (≥ 8 例 / 模块) | `app/engines/parsers/{normalize,brand_matcher,sentiment_classifier,citation_extractor,ranking_extractor}.py` + tests | L1.2 + L1.3 |
| 3 | 4 scheduler 模块 + pytest | `app/engines/scheduler/{retry,backoff,state,queue}.py` + tests | L1.3 |
| 4 | accounts state-machine + pool + prewarm + auto_register stub + sms/luban stub + pytest | `app/engines/accounts/**` + tests | L1.3 |
| 5 | proxy pool + clash + pytest | `app/engines/proxy/{pool,clash}.py` + tests | L1.3 |
| 6 | humanize PagePort interface + Bezier + Box-Muller + pytest | `app/engines/behavior/humanize.py` + tests (零 playwright import 验证) | L1.3 + F1 ready |
| 7 | captcha 三级 + profile sampler + pytest | `app/engines/captcha/{slider,vision,solve}.py` + `app/engines/profile/sampler.py` + tests | L1.3 |
| 8 | har/sanitize.py + pytest (双轨脱敏 6 case) | `app/har/sanitize.py` + tests | L1.3 + S4 |
| 9 | 3 引擎 stub (selectors + index 返回 TIMEOUT + api_fallback stamp 'api_fallback' + README) | `app/engines/adapters/{chatgpt,doubao,deepseek}/**` (注: 目录名 deepseek, 但 EngineId literal = `deepseek-CN`) + queries.json | L1.7 + S1 + S3 |
| 10 | Group F 6 条 harness 规则 + 6 fixture + selftest EXPECTED_POSITIVES 3 → 9 | `scripts/python/ci-harness.py` 扩 F 段 + `backend/.harness_fixtures/F*` 6 个 fixture | L1.5 + L1.6 + S2 |
| 11 | verify-session-1prime.sh + 跑通 Layer 1 全 9 项 | `verify-session-1prime.sh` + 跑出 `✅ Session 1' Phase Gate Layer 1 PASS` | All Layer 1 |
| 12 | 文档同步 (SESSION_PROGRESS / CLAUDE_CODE_SESSIONS_PYTHON / CLAUDE.md 决策 #35 / SESSION_1_PRIME_DELIVERY.md) + git push origin session-1prime | 4 文件修改 + delivery report | (无新代码) |

---

## §6 Delivery Report (Session 收尾时写)

收尾时新建 `docs/SESSION_1_PRIME_DELIVERY.md`, 内容必须含:

```markdown
# Session 1' Delivery Report

**分支**: session-1prime
**Commit 数**: <N> (≤ 12)
**完成时间**: <YYYY-MM-DD>

## Phase Gate 通过证据

### Layer 1 (verify-session-1prime.sh 全 9 项)
- [x] L1.1 ruff strict — 0 error
- [x] L1.2 mypy strict — 0 error
- [x] L1.3 pytest engines unit + coverage — <X> tests, coverage <Y>% (≥ 80%)
- [x] L1.4 alembic upgrade head idempotent
- [x] L1.5 ci-harness Group F — 6 条规则各扫到 1 fixture
- [x] L1.6 ci-harness-selftest — `selftest: PASS  (9 / 9 fixture expectations met)`
- [x] L1.7 import smoke — 全 11 module import ok
- [x] L1.8 9 error codes complete
- [x] L1.9 6 response_source enum complete

### Layer 2 (Harness selftest)
- [x] F1 / F2 / F3 / F4-1 / F4-2 / F4-3 各扫到对应 fixture, 故意违规验证规则有效

### Layer 3 (Frank 静态审查)
- [x] S1 4 条 queries.json 字段齐
- [x] S2 F2 fixture 双轨 leak pattern 齐
- [x] S3 3 引擎 README 描述 quirks
- [x] S4 sanitize pytest 6 case 全 PASS
- [x] S5 profile sampler 确定性证明

## 偏离登记 (规则 3, 若有)

(若实施全顺利, 写 "无偏离, §1 真相源索引全部成立"; 若有偏离, 按 C1/C2/... 编号详述偏离项 + 理由 + 与真相源的差异 + 后续合并 Session 应承担的修正)

## 真相源同步 (规则 4)

- [x] `docs/SESSION_PROGRESS.md` Session 1' ⬜ → ✅
- [x] `docs/CLAUDE_CODE_SESSIONS_PYTHON.md` Session 1' 段回填实施摘要
- [x] `CLAUDE.md` 新增决策 #35 · Session 1' Python Adapter 框架交付 (含 A-G 章节: AdapterPort / Parser / Scheduler / Account+Proxy / HAR / Harness F1-F4 / 偏离登记)

## 下一 Session 依赖确认

- [x] Session 1.5' 可启动: `app/engines/parsers/brand_matcher.py` + `citation_extractor.py` 已就位 (KG cold start 需复用)
- [x] Session 2' 可启动: `app/engines/profile/sampler.py` + `app/engines/adapters/base.py::ExecutionContext` 已就位 (Planner 需 query persona snapshot)
- [x] Session 1.2' 可启动: `app/engines/adapters/base.py::AdapterPort` + 3 引擎 stub + `accounts/sms/luban.py` stub 已就位 (Camoufox 真接入 + Luban live)
```

---

## §7 Closing Loop (规则 7)

收尾前必须**重新执行** §0 F1-F8 全部 grep, 验证真相源仍然成立。任一变化 → 在 §6 Delivery Report 偏离登记段落补 C1/C2/... 条目。

---

## §8 10 条 Final Reminders

1. **真相源不复制只引用**: AdapterPort 接口语义来自 `docs/ADAPTER_CONTRACT.md §1`, 不要在 Prompt 里重抄字段定义; 字段名以源文件为准。
2. **Commit 格式严格**: `Session 1' Step <N>: <主题>`, 不用 emoji, 不用特殊 Unicode (`§ ✅ —` 等), 标题英文字符 + 中文主题 OK。
3. **常量单一入口**: `EVIDENCE_DECAY = 0.85` (本 Session 不用, 决策 #23 锁定 / 留给 Session 1.5'); BCG / Tier weights / Sentiment thresholds 全部参数注入, 不硬编码到 module-level constant; PRD §4.2.6 / §4.2.4.A 是真相源, 测试桩化即可。
4. **PagePort interface 严格抽象**: `behavior/humanize.py` 只定义 `Protocol PagePort: async def keyboard_press(...) / async def mouse_move(...)`, 不 import `playwright.async_api.Page`, F1 harness 锁定。
5. **JWT_SECRET / VOLC_API_KEY / LUBAN_API_KEY 全部 env 入**: 本 Session 不直接读环境变量 (no fallback ladder live), 但所有 stub 函数签名必须接受 `api_key: str | None = None` 参数, 测试桩化为 `None`; 真接入留 1.2'。
6. **9 错误码顺序锁定**: `TIMEOUT | NETWORK | CF_BLOCKED | CAPTCHA_REQUIRED | COOKIE_EXPIRED | NO_ACCOUNT_AVAILABLE | RATE_LIMITED | PARSER_FAIL | UNKNOWN` (来自 ADAPTER §6, 不可重排), retry 矩阵字典必须按此顺序写 (decoration order 反映重试策略矩阵 §6 表格)。
7. **6 枚举 response_source 全量必须 label**: 本 Session 因 execute() 是 stub, 全部用 `harness_fixture`; api_fallback.py 显式 stamp `api_fallback`; F4 三子 harness 规则锁定违规。**没有 schema default**, INSERT 必须显式列出 response_source 列。
8. **零 frontend 修改**: 本 Session 100% backend, 任何 `frontend/` 改动均触发 §3 Type C STOP。
9. **每 commit 跑 `uv run ruff` + `uv run mypy` + `uv run pytest`**: ci-harness 不必每 commit 跑 (Step 10 才上线 F 段), 但前 9 步每步必须 lint 和 typecheck 全绿。
10. **闭环回路 (规则 7)**: 收尾前再跑一次 §0 F1-F8, 任一不一致 → 在 §6 偏离段落记 C1/C2/...。

---

**Frank 准备好后, 复制本文件全部内容粘到 Claude Code, 启动 Session 1'。**
