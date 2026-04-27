# Session 0' · Python 后端基建 + Preview CI/CD + Harness 第一批 — Prompt for Claude Code

> **使用说明**: 本文档是给 Claude Code 的 Session Prompt, Frank 直接复制本文件全部内容到 Claude Code 即可启动 Session 0'。
> 本 Prompt 严格遵守 `CLAUDE.md` 决策 #25 的 12 条 Prompt 编写公约 (规则 1-7 + 10/11/12)。
>
> **角色**: 你 (Claude Code) 是 GENPANO Python 后端架构师 + DevOps 工程师, 负责把 2026-04-26 完成的全 Python 架构反转 (决策 #29) 落地为可跑通的 monorepo 基建 — backend 骨架 + 前端 JSX 复用 + Preview env CI/CD + Harness Python 第一批。**本 Session 不写业务代码** (Adapter / Planner / KG / Auth 等全部留给后续 Session)。

---

## §0 前置 Grep 契约 (规则 2)

**开工第一批动作**: 必须先跑下列 grep 自证真相源仍与本 Prompt 引用一致, 任一不一致 → 停下 alignment 不写代码 (规则 7 闭环回路也复用本组命令)。

```bash
# F1: 决策 #25 (12 条公约) 仍在 CLAUDE.md
grep -n "决策 #25" CLAUDE.md | head -5
grep -n "规则 10 (MVP Scope-Cut" docs/ADMIN_CLAUDE_CODE_SESSIONS.md | head -3

# F2: 决策 #29 (Python pivot) / #30 (preview env) / #31 (branch-per-session) / #32 (repo switch) 仍在 CLAUDE.md
grep -nE "决策 #(29|30|31|32)" CLAUDE.md | head -10

# F3: REPLAN_2026_04_26.md §4 Session 0' 范围 + §6 横切要求仍存在
grep -nE "^### §4|^### §6|Session 0'" docs/REPLAN_2026_04_26.md | head -10

# F4: SESSION_PROGRESS.md 显示所有 Python Sessions 仍 ⬜ 未启动 (本 Session 是 M1 起点)
grep -nE "0' .*⬜|Phase Gate 1" docs/SESSION_PROGRESS.md | head -10

# F5: HARNESS_ENGINEERING.md §10.6 Phase Gate 1 仍是架构确认门
grep -n "§10.6" docs/HARNESS_ENGINEERING.md | head -3
grep -n "Phase Gate 1" docs/HARNESS_ENGINEERING.md | head -3

# F6: 既有 Flask 仓与 analyzer SQL 仍在原位 (Alembic 反向工程入口)
ls migrations/001_analyzer_tables.sql
ls query_tool/  # Phase 2 才迁, 本 Session 不动
```

如果任一 grep 返回 0 行或路径不存在, 立即停止并报告偏离 (规则 11 freshness check 已经被 Frank 在发 Prompt 前 30min 内执行过, 本 grep 是开工再次 self-verify)。

---

## §1 真相源索引 (规则 5 / 6)

| 文件 | 段号 | 标签 | 用途 |
|------|------|------|------|
| `CLAUDE.md` | 决策 #25 (line ~1500-1800) | [引用] | 12 条 Prompt 编写公约, 本 Prompt 自身遵守 |
| `CLAUDE.md` | 决策 #29 (line ~end of file via auto-memory) | [引用] | Python pivot 范围: FastAPI / SQLAlchemy / Alembic / Celery / Pydantic v2 / Playwright + Camoufox / passlib / slowapi / httpx, Next.js + Prisma + TypeScript 全弃 |
| `CLAUDE.md` | 决策 #30 | [引用] | 每个 Session 必须产 preview env 可点击产物 |
| `CLAUDE.md` | 决策 #31 | [引用] | branch-per-session, 从 main fork, claude/* 历史不并入 |
| `CLAUDE.md` | 决策 #32 | [引用] | 工作仓 = `C:\Users\frank.wang\genpano` (jotamotk/GenPano.git), 排除 query_tool/ Phase 2 |
| `docs/REPLAN_2026_04_26.md` | §4 Session 0' 范围 | [引用] | 做 / 不做 双列表权威源 |
| `docs/REPLAN_2026_04_26.md` | §6 横切要求 | [引用] | 3 GitHub Actions workflow + Supabase preview + 6 Celery 队列 |
| `docs/HARNESS_ENGINEERING.md` | §10.3-§10.8 (Phase Gate 1 / 三层 Agent QA / Fix Loop) | [引用] | 验收标准 + 自验脚本格式 |
| `docs/SESSION_PROGRESS.md` | 全文 | [引用] | 11 Python Sessions ⬜ 状态地图, 本 Session = M1 起点 |
| `docs/CI-CD.md` | 全文 | [引用] | 阿里云 ACR + GitHub Secrets 现状, **本 Session 仅扩 GitHub Actions, 不改 ACR 部署链** |
| `migrations/001_analyzer_tables.sql` | 全文 | [反向工程入口] | Alembic init 时 baseline 反推: `brand_mentions / sentiment_drivers / citation_sources / response_analyses` 4 表 |
| `docs/PRD.md` | 全文 | [引用, 不修改] | 产品语义真相源, 本 Session 不触碰 |
| `docs/ADMIN_PRD.md` | 全文 | [引用, 不修改] | Admin 语义, Session A0' 才用 |
| `docs/DATA_MODEL.md` | 全文 | [引用, 待 Session 1.5' 转译为 SQLAlchemy] | 本 Session 仅做 Alembic 反向工程, 不 forward-port 产品表 |
| `docs/ADAPTER_CONTRACT.md` | 全文 | [引用, 待 Session 1' 转译为 Python 接口] | 本 Session 不动 |
| `docs/DESIGN_TOKENS.md` | 全文 | [引用, JSX 不迁移] | 前端 JSX 原型保留, 本 Session 不读不改 |

**修改清单** (本 Session 完成后产生):
- 创建 `pyproject.toml` (uv-managed)
- 创建 `backend/` 目录骨架 (FastAPI + SQLAlchemy + Alembic 初始化)
- 创建 `.github/workflows/ci.yml` + `.github/workflows/preview.yml` + `.github/workflows/deploy.yml` (3 workflow)
- 创建 `scripts/python/ci-harness.py` + `scripts/python/ci-harness-selftest.py`
- 创建 `backend/.harness_fixtures/` (3 self-seeded 故意违规 fixture)
- 创建 `verify-session-0prime.sh` (Layer 1 可执行验收脚本)
- 创建 `docs/SESSION_0_PRIME_DELIVERY.md` (Session 收尾时回填 Phase Gate 通过证据)

**版本警告**: 截至本 Prompt 起草, `.github/workflows/` 目录在仓内**不存在** (经 grep 验证), 本 Session 是首次创建 GitHub Actions; `docs/CI-CD.md` 描述的 ACR 部署链是 Phase 2 才接入的产线方案, **本 Session 只做 Preview 链 (Supabase free tier + Vercel/Render preview)**, 阿里云 ACR 部署 workflow `deploy.yml` 只写骨架 + TODO 标注, 不真接, 留给生产部署 Session 单独闭环。

---

## §2 MVP 范围 — 做 / 不做 双列表 (规则 10)

### ✅ 本 Session 做 (锚点 = `docs/REPLAN_2026_04_26.md §4`)

| # | 项 | 锚点 | 验收信号 |
|---|----|------|---------|
| 1 | **Monorepo 结构**: `backend/` (Python) + `frontend/` (JSX 原样保留) + `docs/` (不动) + `scripts/` (新增 Python 子目录) | REPLAN §4.1 | `tree -L 2 -d` 输出含 `backend/{api,core,db,migrations,tests}` |
| 2 | **`pyproject.toml` (uv-managed)** with deps: fastapi 0.111+ / sqlalchemy 2.0+ / alembic / pydantic v2 / asyncpg / celery 5.4 / redis 7 / python-jose / passlib[bcrypt] / slowapi / httpx + dev: ruff / mypy / pytest / pytest-asyncio / pre-commit | REPLAN §4.2 / 决策 #29 | `uv sync` 全绿; `uv run python -c "import fastapi, sqlalchemy, celery"` 不抛 |
| 3 | **FastAPI 骨架**: `backend/api/main.py` 含 `/healthz` 返 `{"status":"ok"}` + CORS middleware + lifespan startup 打印 banner | REPLAN §4.3 | `uvicorn backend.api.main:app --reload` 起得来; `curl /healthz` 返 200 |
| 4 | **SQLAlchemy 2.0 async engine** + session factory (`backend/db/session.py`) + base declarative (`backend/db/base.py`); 不写业务模型 | REPLAN §4.4 | import 不抛; `pytest backend/tests/test_db_smoke.py` 绿 (空连接 fixture) |
| 5 | **Alembic 初始化** (`backend/migrations/`) + 反向工程 baseline 从 `migrations/001_analyzer_tables.sql` 推出第一个 revision (autogenerate 不准, 手写映射, 表名/列名/约束 1:1 复刻) | REPLAN §4.4 / `migrations/001_analyzer_tables.sql` | `alembic check` 绿; `alembic upgrade head` 在 Supabase preview 建出 4 表 (brand_mentions / sentiment_drivers / citation_sources / response_analyses); rollback `alembic downgrade base` 也绿 |
| 6 | **Celery 6 队列骨架** (不绑实际 task): `llm_chatgpt / llm_doubao / llm_deepseek / analysis / account_login / beat`; `celery -A backend.tasks worker -Q <queue>` 能起 worker (无 task 即可) | REPLAN §6 / 决策 #29 | 6 队列各跑 5s 不 crash, log 可见 worker ready |
| 7 | **环境变量三层**: `backend/.env.example` (空 placeholder) / `backend/.env.preview` (Supabase preview DSN + Redis + 假密钥占位) / `backend/.env.prod` (gitignored 仅占位); `pydantic-settings BaseSettings` 单一加载入口 | REPLAN §4.6 | `pytest backend/tests/test_settings_load.py` 绿; `.env` / `.env.prod` 在 `.gitignore` |
| 8 | **GitHub Actions 3 workflow 骨架** (新建, 非扩写): `.github/workflows/ci.yml` (push/PR 跑 ruff + mypy + pytest + harness selftest) / `.github/workflows/preview.yml` (PR 部署 backend → Render 或 Fly.io preview / frontend → Vercel preview / DB → Supabase preview branch, 评论 PR 贴 URL) / `.github/workflows/deploy.yml` (main push 触发, 仅写 TODO 注释 + skip step, 阿里云 ACR 链留给生产部署 Session) | REPLAN §6 / `docs/CI-CD.md` | PR open 后 ci.yml 全绿, preview.yml 评论一条 `Preview: https://...` 链接, 链接打得开 |
| 9 | **前端 JSX 原型保留**: `frontend/` 目录 1:1 保留, 不迁 TSX, 不动 `frontend/src/data/mock.js`; 仅在 preview.yml 中部署 `frontend/dist` (Vite build) 到静态托管, 让 Frank 浏览器看到原型可点击 | REPLAN §4.7 / 决策 #29 | preview URL 打开, JSX 原型主页加载, `/` 路由可见 |
| 10 | **Harness Python 第一批 3 条**: F1 (`no-bare-playwright-import`) / F4 (`response_source-must-be-labeled`) / D8 (`no-hardcoded-jwt-secret`); 实现于 `scripts/python/ci-harness.py`, 各扫 `backend/**/*.py` 并按 regex 黑名单 + 白名单运作; **每条规则配 1 self-seeded 故意违规 fixture** 进 `backend/.harness_fixtures/` (`F1_bare_playwright.violation.py` / `F4_response_source_unlabeled.violation.py` / `D8_jwt_hardcoded.violation.py`); 配 `scripts/python/ci-harness-selftest.py` 验证 3 fixture 各被对应 rule 抓到 (EXPECTED_POSITIVES = 3) | REPLAN §6 / 决策 #21.C self-seeded 模式 / 决策 #28.G F4 三子规则 | `python scripts/python/ci-harness.py` 在主代码全绿; `python scripts/python/ci-harness-selftest.py` 输出 `selftest: PASS  (3 / 3 fixture expectations met)` |
| 11 | **pre-commit hook**: ruff + mypy strict + pytest fast + harness selftest; `.pre-commit-config.yaml` + `pre-commit install` 写入 `Makefile` 的 `setup` target | REPLAN §4.5 | `pre-commit run --all-files` 一遍全绿 |
| 12 | **`Makefile`** with targets: `setup / dev / test / lint / typecheck / migrate / preview / harness` 各 1-3 行; `make setup && make test` 在干净 clone 上一遍跑通 | REPLAN §4.5 | 干净 clone → `make setup` → `make test` 全绿 (CI 上验证) |
| 13 | **Layer 1 可执行验收脚本** `verify-session-0prime.sh` 严格按 `docs/HARNESS_ENGINEERING.md §10.3` 例式, 含: 文件结构存在 / `uv run pytest -q` 绿 / `alembic check` 绿 / harness selftest 绿 / `/healthz` 200 / preview URL 200 / 无 hardcoded secret (`grep -rE "(JWT_SECRET|DB_PASSWORD).*=.*[\"']\\w" backend/`) | HARNESS_ENGINEERING §10.3 | `bash verify-session-0prime.sh` 退码 0 |
| 14 | **Session 收尾文档** `docs/SESSION_0_PRIME_DELIVERY.md` 回填 Phase Gate 1 通过证据 (commit hash / preview URL / pytest 行数 / coverage / harness selftest 输出) — 模板见本 Prompt §6 | HARNESS_ENGINEERING §10.6 Phase Gate 1 | Frank 打开文档能逐条 check |

### ❌ 本 Session 不做 (留给后续 Session, 锚点已注明)

| # | 项 | 推迟到 | 理由 |
|---|----|--------|------|
| N1 | JSX → TSX 迁移 | **永不** (决策 #29) | 前端原型 freeze, JSX 是最终形态 |
| N2 | Flask `query_tool/` → FastAPI 整合 | Phase 2 (决策 #32 Q2) | MVP 不动 query_tool, 通过 nginx reverse-proxy 暴露 `/preview/admin` 即可 |
| N3 | 完整 38 条 Harness grep 全数 Python 移植 | 各 Session 按需追加 (本 Session 仅 F1/F4/D8) | 范围爆炸; 每条规则要配 fixture + selftest, 一次性写 38 条 → Session 超预算 |
| N4 | Camoufox 实际 launch + 反检测真集成 | Session 1.2' (决策 #28 在 Python 重做) | 非 Phase Gate 1 范畴, Gate 1 只看架构能跑起来 |
| N5 | 知识图谱冷启动 / Planner / Adapter execute() / Citation / Auth | Sessions 1' / 1.5' / 2' / 2.1' / A0' / 4a' | 各自独立 Session, 决策 #21 转译表已映射 |
| N6 | Admin backend (Session A0' / A1') | Sessions A0' / A1' | Admin 模块独立轨道 |
| N7 | Vitest 80% 覆盖 / Playwright E2E / 视觉回归 | Session 1.2'+ Camoufox 集成 + Session 6 (决策 #18 Phase 4) | Pytest 单测在本 Session 只覆盖骨架 smoke 测试, 业务测试随 Session 落 |
| N8 | 阿里云 ACR 生产部署 workflow 真接 | 单独 "生产部署" Session (REPLAN 暂未编号) | `deploy.yml` 本 Session 只写骨架 + TODO, 不真推 ACR |
| N9 | Mock data → real data 切换 / 用户态 API | Session 4a' (Onboarding + 用户系统) | 决策 #26.C3 |
| N10 | DATA_MODEL.md SQLAlchemy 转译 + ADAPTER_CONTRACT.md Python 接口转译 | Session 1.5' / 1' 各自前置 | 真相源维护成本不在 Session 0' 范围 |

**禁用模糊措辞**: 本 Session 严禁出现 "核心功能" / "基础工作" / "necessary scaffolding" 这类无锚点说法, 所有交付物都必须可在 §2 ✅ 表的"验收信号"列被 Frank 一眼检查到。

---

## §3 STOP Triggers (规则 12)

遇到下列任一条件, 立即停下当前实施, 写一条简短报告 (≤200 字) 给 Frank, 等待人工介入。**不要尝试 workaround**, 不要静默改方案。

### Type A · 环境失败

- A1: `uv sync` 失败且重试 1 次仍失败 (网络问题 / 包源 / Python 版本不匹配)
- A2: Supabase preview branch 创建失败 (free tier quota / API key 错) — 报告给 Frank 后改用本地 docker postgres 起 fallback, 但要在 §6 Phase Gate 报告里**显式标注 "preview env: local fallback (NOT cloud)"** 让 Frank 决定是否接受
- A3: GitHub Actions 反复 fail 同一个 step 超过 2 轮 — 不要继续 push, 让 Frank 检查 secrets 配置
- A4: Docker / Camoufox 安装在 CI 环境 OOM / image not found — 不在本 Session 范围 (N4 已排除), 若不慎触发说明范围拉错, 立即停

### Type B · 真相源冲突

- B1: §0 的 6 条 grep 任一返回 0 行 / 路径不存在 / 段号偏离 — 写报告引用偏离细节, 等 Frank 决定 (a) 修真相源 (b) 修 Prompt (c) 接受当前状态
- B2: `migrations/001_analyzer_tables.sql` 的表结构与本 Prompt §1 描述的 4 表 (brand_mentions / sentiment_drivers / citation_sources / response_analyses) 不一致 — Alembic baseline 反向工程不能猜, 必须 1:1 复刻; 不一致即停
- B3: REPLAN_2026_04_26.md §4 / §6 段号在 Frank 发本 Prompt 后已改 (`git log docs/REPLAN_2026_04_26.md` 显示 30 分钟内有提交) — 规则 11 freshness check 失效, 立即停, 让 Frank 重发 Prompt

### Type C · 范围溢出

- C1: 某项实施需要触碰本 Session "❌ 不做" 列的任一条 (N1-N10) — 立即停, 不要"顺手做", 写报告让 Frank 决定是否扩 scope (规则 12 Type C 显式登记)
- C2: 实施过程发现 Phase Gate 1 验收标准 (§6) 中某条无法在不写业务代码的前提下满足 — 例如 "smoke test 必须能跑通" 但 smoke test 实际依赖 Adapter execute() — 立即停, 让 Frank 决定削 Phase Gate 还是扩 Session
- C3: 在写 Harness rule 时发现 F1/F4/D8 的 Python 形态与 TS 形态语义不可调和 (例如 Python 没有 `import * as X from`) — 写偏离登记, 不要硬套 TS 的 regex

### STOP 之后的报告模板

```markdown
## STOP 报告 — Session 0' · Type X · <一句话症状>

**触发条件**: §3 STOP Trigger Type <A/B/C> · <X编号>
**已完成步骤**: §5 第 <n> 步前全部绿
**卡点细节**:
- 现象 (1-2 句):
- 已重试: <次数 + 方式>
- 期待行为 vs 实际行为:
- 相关日志/grep 输出 (5-10 行截取):

**建议下一步** (3 选 1):
1. <方案 A>
2. <方案 B>
3. <方案 C>

等 Frank 决定后续。
```

---

## §4 验收标准 — Phase Gate 1 (架构确认门)

**Phase Gate 1 锚点**: `docs/HARNESS_ENGINEERING.md §10.6` Gate 1 要求 + `docs/REPLAN_2026_04_26.md §4` Session 0' 验收。

人工时间预算: ~30min (Frank 审核 + 浏览器开 preview URL + 复读 §6 checklist)。

### Gate 1 通过条件 (全部 ✅ 才算过)

| # | 项 | 自动验证 | 人工验证 |
|---|---|---------|---------|
| G1.1 | Monorepo 结构齐 (backend/ + frontend/ + docs/ + scripts/ + .github/workflows/) | `verify-session-0prime.sh` step 1 | 目录树看一眼 |
| G1.2 | `uv sync && uv run pytest -q` 全绿 | CI ci.yml | — |
| G1.3 | `alembic upgrade head && alembic downgrade base` 在 Supabase preview 双向都能跑 | `verify-session-0prime.sh` step 4 | — |
| G1.4 | 6 Celery 队列骨架可起 worker (worker ready log 可见) | `verify-session-0prime.sh` step 5 | — |
| G1.5 | `python scripts/python/ci-harness.py` 主代码无误判, `ci-harness-selftest.py` 输出 `selftest: PASS  (3/3)` | CI ci.yml | — |
| G1.6 | `pre-commit run --all-files` 全绿 | CI ci.yml | — |
| G1.7 | PR 上 preview.yml 评论了一条 `Preview: https://...` 链接 | GitHub PR 页 | Frank 点链接, **浏览器看到 JSX 原型主页 + `/healthz` 返 200 + `/preview/admin` 看到 Flask query_tool UI (nginx reverse-proxy)** |
| G1.8 | 无 hardcoded secret (`grep -rE "(JWT_SECRET\|DB_PASSWORD\|VOLC_API_KEY).*=.*[\"']\\w" backend/`) 输出空行 | `verify-session-0prime.sh` step 7 | — |
| G1.9 | commit chain 干净 (规则 31 branch-per-session + atomic commits, 每个 commit ≤ 5 文件 / 主题清晰) | `git log --oneline` 看 | Frank 扫一眼 |
| G1.10 | §1 真相源索引中的 9 条 [引用] 文件路径仍存在 (规则 7 闭环回路) | `verify-session-0prime.sh` step 8 | — |
| G1.11 | `docs/SESSION_0_PRIME_DELIVERY.md` 已写, 含 commit hash + preview URL + 4 行测试输出 + Phase Gate 1 通过证据 | `verify-session-0prime.sh` step 9 | Frank 读一遍 |

### Layer 2 (对抗验收) 范围 — 留给独立 Agent

按 `docs/HARNESS_ENGINEERING.md §10.4` 表中 "Docker+preview 环境" 行 + "FastAPI" 行重点审, 关注:

- secret 管理: `.env.prod` / `.env.preview` 没有真凭证 commit; GitHub Secrets 用法正确; httpx 调用不在日志泄露 Authorization header
- container 用户非 root (Dockerfile 必须 `USER nonroot`)
- `Depends` 链是否被绕过 (本 Session 只写 `/healthz`, 暂无依赖, 但要确认骨架风格)
- `pydantic-settings` 严格模式 (`extra='forbid'`)
- slowapi 限流 key 唯一性 (本 Session 暂未启用, 但 `pyproject.toml` 锁版本)
- ValidationError 不直接暴露给客户端 (FastAPI 默认行为, 别意外覆盖)

Layer 2 Agent 与本 Agent **零共享上下文**, Frank 用 `docs/HARNESS_ENGINEERING.md §10.4` 模板 spawn 新 Agent 跑 review。

### Layer 3 (规范一致性) 范围

- Session 0' 涉及 0 条 PRD §X.Y 业务规范 (本 Session 是基建, 不实现 PRD 功能)
- Session 0' 必须遵守的规范是 REPLAN_2026_04_26 §4 Session 0' 范围 + §6 横切要求 + 决策 #25 12 公约 + 决策 #29/#30/#31/#32

---

## §5 12 步交付顺序

按下列顺序执行, 每完成 1 步立即 commit (atomic, ≤5 文件), commit message 格式 `Session 0' Step N: <主题>` (中文 OK)。

**Step 0** — 创建 feature branch `session-0prime` from `main` (决策 #31). `git checkout main && git pull && git checkout -b session-0prime`.

**Step 1** — `pyproject.toml` + `uv.lock`. 用 uv 装齐 §2 ✅ 第 2 项的所有依赖, `uv sync` 全绿, `uv run python -c "import fastapi, sqlalchemy.ext.asyncio, alembic, celery, pydantic, jose, passlib, slowapi, httpx"` 不抛。Commit。

**Step 2** — `backend/` 骨架: `backend/{api/,core/,db/,migrations/,tasks/,tests/,__init__.py}`。`backend/api/main.py` 写 FastAPI app + lifespan + CORS + `/healthz` 路由。`backend/core/settings.py` 写 pydantic-settings BaseSettings 加载 `.env`。Commit。

**Step 3** — `backend/db/{base.py,session.py}` SQLAlchemy 2.0 async engine + AsyncSession factory; `backend/tests/test_db_smoke.py` 用 sqlite in-memory 验证 engine 可起 (Supabase 真连接留 step 6)。Commit。

**Step 4** — Alembic init: `alembic init backend/migrations` (注意目录) + `alembic.ini` 配置 + `env.py` 接 SQLAlchemy `Base.metadata`. Commit (空 alembic 骨架)。

**Step 5** — Alembic baseline 反向工程: 读 `migrations/001_analyzer_tables.sql`, 在 `backend/db/models/analyzer.py` 写 SQLAlchemy 模型 (BrandMention / SentimentDriver / CitationSource / ResponseAnalysis + 既有 brands / competitors / prompts / llm_responses 列扩展) **1:1 复刻表名+列名+约束+索引**, 然后 `alembic revision --autogenerate -m "baseline_analyzer_tables"` 生成第一个 revision; **手工核对**生成的 SQL 与原 .sql 一致, 不一致改模型, 不要改 revision SQL (autogenerate 不可信, 必须人眼对一遍)。Commit。

**Step 6** — 接 Supabase preview branch: 用 free tier 在 Supabase dashboard 创 preview project, 拿 DSN 写进 `.env.preview` (gitignored, 在 GitHub Secrets 配置 `SUPABASE_PREVIEW_DSN`); 本地 `alembic upgrade head` 跑通, 验证 4 张分析表建出, `alembic downgrade base` 回滚也能跑。Commit alembic revision。

**Step 7** — Celery 6 队列骨架: `backend/tasks/{__init__.py,celery_app.py}`, `celery_app.py` 配置 Redis broker + 6 routes (llm_chatgpt / llm_doubao / llm_deepseek / analysis / account_login / beat); 不写实际 task, 仅起 worker 的 ready log 能看到 6 队列名。`backend/tests/test_celery_smoke.py` 起 in-process worker 验证。Commit。

**Step 8** — `.github/workflows/ci.yml` 新建: trigger on push + PR, jobs = `lint` (ruff + mypy strict) / `test` (pytest -q + coverage) / `harness` (python scripts/python/ci-harness.py + selftest)。push 上 GitHub 验证全绿。Commit。

**Step 9** — Harness Python 第一批: `scripts/python/ci-harness.py` 实现 F1 / F4 / D8 三 rule (regex + glob + 白名单), `scripts/python/ci-harness-selftest.py` EXPECTED_POSITIVES = 3, 各 rule 验证 1 fixture 被抓; `backend/.harness_fixtures/{F1_bare_playwright.violation.py, F4_response_source_unlabeled.violation.py, D8_jwt_hardcoded.violation.py}` 写故意违规代码 (F1: `from playwright.async_api import async_playwright` 直 import / F4: 写一段 adapter execute() 返 dict 不带 `response_source` 键 / D8: `JWT_SECRET = "literally-hardcoded-32-chars-long-string-yes"`); selftest 跑 `selftest: PASS  (3 / 3 fixture expectations met)`。Commit。

**Step 10** — `.github/workflows/preview.yml` 新建: PR 触发, 构建 backend image + frontend dist, 部署 backend 到 Render preview / frontend 到 Vercel preview / DB 到 Supabase preview branch, **PR 评论一条 `Preview: https://<project>-pr-<n>.vercel.app`**; nginx reverse-proxy 把 `/preview/admin` 路径转给 Flask `query_tool/` (Phase 2 才正式整合, 本 Session 暂用 nginx)。Commit。

**Step 11** — `.github/workflows/deploy.yml` 新建: main push 触发, **仅写 TODO 注释 + skip step**, 阿里云 ACR 链留给生产部署 Session 单独闭环; 不要真接 secrets (规则 12 Type C, ACR 部署不在本 Session 范围)。Commit。

**Step 12** — `Makefile` + pre-commit + `verify-session-0prime.sh` + `docs/SESSION_0_PRIME_DELIVERY.md` 模板填充。本地 `make setup && make test` 全绿, `bash verify-session-0prime.sh` 退码 0; PR open, ci.yml 绿, preview.yml 评论出 URL, Frank 浏览器验证。Commit。

---

## §4.L3/L4 L3/L4 Phase Gate 卡控 (Hard Fail, 决策 2026-04-26)

**真相源**: `docs/REPLAN_2026_04_26.md §5` L3/L4 测试覆盖矩阵 + §5.3 Hard Fail 卡控规范.

**Hard Fail 强制**: 下列 L3/L4/Visual 任一未跑绿, GitHub Actions branch protection 拦截 merge. 不允许 soft warning, 不允许临时跳过.

**本 Session 必跑 L3 集成测试 (1 项)**:
- Alembic upgrade head + downgrade base 双向跑通; Celery worker + Redis 启动健康; FastAPI `/healthz` 在 preview env 返回 200

**本 Session 必跑 L4 E2E 测试 (1 项)**:
- Frank 浏览器打开 preview Landing → 点 "登录" → 落到 /auth → 截图比对

**本 Session Visual baseline (1 张)**:
- `/landing.png` 建立后 Playwright `to_have_screenshot()` diff < 0.1%, 后续 PR 不得破

**补救测试**: 本 Session 是 Python 新写基础设施, 无补救测试

**Phase Gate 通过条件 (在原有 G1.* 基础上追加)**:
- G_L3.1: Alembic 双向迁移 + Celery 6 队列启动 + `/healthz` 200 全部绿
- G_L4.1: Frank 浏览器 E2E 截图成功
- G_Visual.1: `/landing.png` baseline 已建立 + Playwright `to_have_screenshot()` 0 diff

---

## §6 Phase Gate 1 验收清单 (Session 收尾时回填)

收尾时, 把下列模板填进 `docs/SESSION_0_PRIME_DELIVERY.md`, Frank 一眼对照决定是否过 Gate 1。

```markdown
# Session 0' · Delivery Report

**Branch**: session-0prime
**Final commit**: <hash>
**PR**: #<n>
**Preview URL**: https://<...>
**Date**: 2026-MM-DD

## Phase Gate 1 (HARNESS_ENGINEERING §10.6)

| Gate | 标准 | 实测 | 通过 |
|------|------|------|------|
| G1.1 | Monorepo 结构齐 | `tree -L 2 -d` 输出: <粘贴 8-12 行> | ✅ / ❌ |
| G1.2 | `uv run pytest -q` 全绿 | `<n> passed in <s>s` | ✅ / ❌ |
| G1.3 | Alembic 双向跑 | `alembic upgrade head` + `downgrade base` 各 <s>s | ✅ / ❌ |
| G1.4 | 6 Celery 队列起 worker | log 截 6 行 ready | ✅ / ❌ |
| G1.5 | Harness selftest | `selftest: PASS  (3 / 3 fixture expectations met)` | ✅ / ❌ |
| G1.6 | pre-commit 全绿 | <一行输出> | ✅ / ❌ |
| G1.7 | Preview URL 可访问 | Frank 浏览器截图 / `curl -I` 200 | ✅ / ❌ |
| G1.8 | 无 hardcoded secret | grep 输出空 | ✅ / ❌ |
| G1.9 | commit chain 干净 | `git log --oneline session-0prime` <n> commits | ✅ / ❌ |
| G1.10 | 真相源索引仍成立 | `verify-session-0prime.sh` step 8 退码 0 | ✅ / ❌ |
| G1.11 | 本 DELIVERY 文档已填 | (你正在读这个文档) | ✅ |

## 偏差登记 (规则 3)

(若实施中发现与 §1 真相源不可调和冲突, 在此列 C1/C2/...)

- C1: <无 / 或描述偏离 + 同步到 CLAUDE.md 决策 #X 的 C 段>

## Layer 2 对抗 review 结果

(等独立 Agent 跑完, Frank 贴对抗 Agent 的报告链接)

## 下一步

- 进入 Session A0' (Admin auth Python 重做) 或 Session 4a' (Onboarding + 用户系统), 以 REPLAN_2026_04_26 §3 优先级为准
```

---

## §7 闭环回路 (规则 7)

收尾前 (Step 12 完成后, commit DELIVERY 文档前), 必须**再跑一次 §0 的 6 条 grep**, 确认每条仍返回非 0 行 / 路径仍存在 / 段号未漂移。

如果发现新偏离 (例如本 Session 实施中 Frank 在 CLAUDE.md 加了决策 #33), 不要静默忽略, 在 `docs/SESSION_0_PRIME_DELIVERY.md` "偏差登记" 段写 C1/C2 描述 + 同步到 CLAUDE.md 决策 #33 的 C 段 (规则 3 + 规则 4 双向同步)。

---

## §8 给 Claude Code 的最后叮嘱

1. **读 §0 grep 命令前不要写代码**。如果某条 grep 失败, 走 §3 STOP Type B。
2. **写代码时 §2 ✅ 表的"验收信号"列就是验收契约**, 不要写超出验收信号的功能 (会被规则 10 反向裁掉)。
3. **每完成 1 step 立即 commit**, 不要囤 5 step 一次性 commit (违规则 31 atomic commits 精神)。
4. **遇到 Camoufox / Adapter execute() / Planner / KG / Auth 任何业务逻辑诱惑, 走 §3 STOP Type C** — 这些都在 N1-N10 ❌ 列表。
5. **规则 11 freshness check 在你这边的复责是闭环 §0 grep 即可**, 不需要重新 grep `.auto-memory/` (Frank 在发 Prompt 前已经验过)。
6. **规则 5 §1 真相源索引在每个文件路径后都标 [引用] / [修改]**, 你写 commit message 时引用这些路径要保持原样, 不要简写。
7. **规则 6 段号最小单元**: 引用 PRD 写 `PRD §X.Y.Z`, 引用 REPLAN 写 `REPLAN §4 / §6`, 不要写"见 PRD"或"见 REPLAN"。
8. **如果 Session 收尾时 Phase Gate 1 中任一条 ❌**, 走 `docs/HARNESS_ENGINEERING.md §10.8` Fix Loop (≤3 轮); 第 4 轮失败立即升级人工 (Frank), 不要无限循环。
9. **Layer 2 对抗 review 不是你这个 Agent 的责任**, 你只负责 Layer 1 (verify-session-0prime.sh) + 内部 self-check (§7 闭环回路); Frank 会用 Cowork mode spawn 独立 Agent 跑 Layer 2。
10. **把 Frank 当智能同事**, 遇到模糊处优先选保守路径 (例如 deploy.yml 真接 ACR vs 写 TODO, 选写 TODO), 不要"顺便做了"。

---

**Prompt 结束**。Frank 复制本 Markdown 全文丢给 Claude Code 启动 Session 0'。
