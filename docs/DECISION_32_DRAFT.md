# 决策 #32 · A1' Session 部分完工 + 5 step 转交后续 (DRAFT)

> **状态**: 本地草稿, 不 commit. Step 12.B (Frank Layer 3 验收 squash merge 时) 才合并到 CLAUDE.md + DECISION_LOG.md, 同 PR 内 + 删本文件。
>
> **日期**: 2026-04-29 (草稿) / TBD (Frank Layer 3 验收 squash merge 时确认)

---

## A. 实施摘要 (7/12 steps shipped, 8 commits)

7 步在 `feature/session-a1prime` 累积, Step 8 含 1 个 ruff format fixup commit (`04f63e8`), 一步两 commit.

- **Step 1** · `4c11ed3` · A1' 8 张新表 alembic baseline + `admin_password_resets.purpose server_default` DROP. 决议见 #28.G C3 (NO SCHEMA DEFAULT) + #30.F (T5 真实状态)。Closed §0.5 T5。
- **Step 3 v2** · `9e41607` · users 真实表 (DATA_MODEL §1.1 完整 schema, 10 列 + 2 索引 + 1 CHECK) + Y1-Y5 endpoints (列表/详情/冻结/解冻/软删除) + RBAC require_role + audit stub + dictConfig logger backbone (Bug 4 闭合) + Resend mock (Bug 4 闭合)。决议见 #30.H (Path B Variant 2)。Closed §0.5 T7 + T4 + T8。
- **Step 4 v2** · `3d7e3c2` · Module C KG admin 4 endpoints Y24-Y27 (alias-conflicts list/resolve + submissions list/approve+reject) + N-候选 JSONB invariant 校验。决议见 #30.J (Option Z scope) + #30.H (N-候选)。
- **Step 8** · `89acc7a` + `04f63e8` · Group J Harness 5 rules (J1 admin write→record_audit / J2 account-pool 名字限定 / J3 require_role super_admin literal / J4 cookie response→mask_secret / J5 admin 只能写 users.deletion_requested_at) + 5 .mjs scripts 决议 (4 删除 / 1 Python 重写 / 1 保留)。决议见 #30.I。Closed §0.5 T6。
- **Step 9** · `fbb996c` · frontend 17 admin pages (TSX, 命名差异见 #30.K Rule 1 偏离) + `adminFetch` 401 interceptor 闭环 T1。Closed §0.5 T1。
- **Step 10** · `af0279d` · `docker-compose.admin.yml` + `vercel.json` + `render.yaml` + `backend/.env.example` admin block。Env var 用 `ADMIN_BASE_URL` (code-correct) 而非 spec 误名 `ADMIN_FRONTEND_URL`, 决议见 #30.K (Rule 1)。
- **Step 11** · `9231a3b` · `verify-session-a1prime.sh` (Layer 1, 12 sections, 33 PASS / 0 FAIL / 1 SKIP) + `smoke_admin_a1.{sh,py}` (Layer 2, 9 步 in-process httpx ASGITransport + aiosqlite, 9/9 step + 20/20 assertion PASS) + `SESSION_A1_PRIME_LAYER3_CHECKLIST.md` (Frank S1-S6) + #30.K 登记。

**双 lane CI 验证**: commit `9231a3b` 推送后 CI lane (1m22s success) + Build & Deploy Preview lane (1m39s success), 均 GREEN。

---

## B. 偏差登记 (Rule 3, 跟 #30 同模式)

- **C1. Step 4 Y6 invite endpoint 未实施**: Step 3 v2 仅交付 Y1-Y5 (5 endpoints), Y6 (邀请新管理员) 推 Phase 2 / mini-session A1.x'。理由: Y6 需要 invitation token 流 + 邮件模板 (`AdminInvitationEmail`), Resend live 未配 (Bug 4 转交), invitation 流 + 邮件 live 一并 A1.x' 闭环更内聚。
- **C2. Step 0 独立 step 未做**: §0.5 T2 (JWT secret lifespan) + T3 (`require_admin_session` re-validate user.status) 由 Step 1+3 v2 隐式 cover (Step 1 alembic baseline 没动 admin_users.last_password_at 语义 / Step 3 v2 RBAC 走 require_role 但未在每次请求 re-validate user.status), 严格闭合留 mini-session A1.x'。
- **C3. Step 2 record_audit 真实实现转 stub**: `record_audit()` 在 Step 3 v2 已 wire 进 admin write 路径 (J1 harness 守护), 但实际写表延后 — Session 3' 落 `admin_audit_log` 表后 Step 2 真实实现在 A1.x' 接入。J1 harness 仍生效 (扫的是 token 而非真实 DB write)。
- **C4. Step 4 KG 主表 12-15 endpoints 转 Session 1.5'**: §0.5 T9, 跟 #30.J Option Z 一致, KG 主表 (kg_industries / kg_categories / kg_brands / kg_products / kg_brand_relations / kg_product_relations / kg_mined_relations) 由 Session 1.5' 拥有 alembic + L1.4 验收, A1' 仅落 admin 侧 3 表 (alias_conflicts + brand_submissions + kg_review_queue)。
- **C5. Step 5/6/7 转 mini-session A1.x'**: Step 5 (Account Pool wrapper + Module B 资源页) 依赖 Session 1.2' Account Pool live; Step 6 (Pipeline Tracker + Dashboard) 依赖 1.2'/3'; Step 7 (Cost Dashboard + Audit Log) 依赖 Session 3' `cost_paused` flag + `admin_audit_log` 表。三步在依赖 Session 落地后由 A1.x' 协调接入。
- **C6. Step 9 frontend Module B/C/D 14 子页占位**: Step 9 交付 17 pages (auth shell 3 + Module A users 1 + Module C KG aliases/submissions 2 + Module B/D placeholder 11), Module B (账号池/Pipeline) + Module D (Cost/Audit) 11 子页是 placeholder, 真实数据接入跟 Session 1.2'/3' 落地后 A1.x' 闭环。
- **C7. ADMIN_BASE_URL spec 命名偏差**: 见 #30.K, Rule 1 代码胜 (backend reads `ADMIN_BASE_URL`, spec 草稿误名 `ADMIN_FRONTEND_URL`)。docker-compose.admin.yml + render.yaml + .env.example 三处用 code 名, 不引兼容别名。

---

## C. 与 §1 修改清单的 actual delta

对照 `SESSION_A1_PRIME_PROMPT.md` §1 真相源索引 spec, 实际改动:

- **修改**: PRD §4.1 (users 派生 is_frozen) / PRD §4.1.4 / §4.3.7 / §4.4.8 (8 admin tables 字段) / ADMIN_PRD §4.2.4 (Platform Layer 边界, A1' Step 1 落地的 alembic 引用) / ADMIN_PRD §5.6.8 (admin_users baseline, A0' 已落) — Round 4-9 真相源 PR trail (#134-#140) 内完成。
- **新增**: CLAUDE.md #30 segments F (T5 真实状态) / G (T0.3 8 张表 schema alignment) / H (T0.1 users Path B Variant 2) / I (Step 8 .mjs sweep + Group J Harness) / J (T0.7 KG Option Z) / K (ADMIN_BASE_URL Rule 1) — 全部跟随 step 推进 inline 登记。
- **未做**: spec §1 列的 ADMIN_PRD §4.5 audit_log + §4.6 cost_paused 真相源更新, 跟随 Step 2/7 转交 A1.x' (Session 3' 落 `admin_audit_log` + `cost_paused` flag 后再同步)。

---

## D. 转交清单 (mini-session A1.x' / Phase 2)

- **mini-session A1.x' 范围** (Session 1.2'/3' 落地后协调启动):
  - §0.5 T2 + T3: Step 0 RBAC fine-tune (JWT secret lifespan + `require_admin_session` re-validate)
  - Step 2: `record_audit()` 真实写 `admin_audit_log` 表 (依赖 Session 3')
  - Step 5: Account Pool wrapper + Module B 资源页 (依赖 Session 1.2')
  - Step 6: Module B Pipeline Tracker + Dashboard (依赖 1.2'/3')
  - Step 7: Module D Cost Dashboard + Audit Log (依赖 Session 3')
  - Step 9 14 子页占位 → 真实数据接入 (依赖 1.2'/3')
- **Phase 2 范围**:
  - Y6 invite admin endpoint + invitation token 流 + `AdminInvitationEmail` Resend live
- **Bug 跟踪 (从 #30.E A0' 转交清单延续)**:
  - Bug 1/2/3 (A0' Step 8 known issues, A1' 未碰)
  - Bug 4 logger 可观察性 (Step 3 v2 dictConfig backbone 已建, Resend live 实际发送验证延后到 Resend live 配 API key 时)
  - Resend live actual send 验证
  - Vercel/Render preview env 接入 (Step 10 infra 已落, live deploy 待 Frank 配 API key)

---

## E. 跨 Session 影响

- **Session 1.5'**: 接 §0.5 T9 (KG 7 主表 alembic + 12-15 admin endpoints Y19-Y23 + Y28), L1.4 验收范围已含。
- **Session 1.2'**: 解锁 A1.x' Step 5 (Account Pool wrapper + Module B 资源页) + Step 6 部分 (Pipeline Tracker)。
- **Session 3'**: 解锁 A1.x' Step 2 (record_audit 真实写表) + Step 6 Dashboard 部分 + Step 7 (cost_paused flag + admin_audit_log)。
- **Session 4a'**: users 表 + admin schema 已落 (Step 3 v2 + Step 1), 4a' scope 缩为 + projects 表 + auth endpoints (注册 / 登录 / 邮件验证 / 密码重置自助流) + 30 天 grace window cron job, 不重做 users schema。

---

## F. Rule 7 反查一致性 (Session 收尾)

- ✅ ADMIN_PRD / PRD / DATA_MODEL 与代码字段名一致 (Round 4-9 + #30.F-K 已同步)
- ✅ 决策 #30 的 F-K 段落覆盖 A1' 全部 7 step 的真相源对齐与偏差
- ✅ Layer 1 verify-session-a1prime.sh 12 sections + Layer 2 smoke 9 steps + Layer 3 S1-S6 三层验证 in place
- ✅ Group J Harness 5 rules + harness selftest 12/12 + ci_check 12 rules / 0 violation
- ✅ 双 lane CI GREEN (commit 9231a3b)
- ⏳ Layer 3 Frank 浏览器实操 (Step 12.B 开始)
- ⏳ 决策 #32 落库 + DECISION_32_DRAFT.md 删除 (Step 12.B 同 squash PR 内)

---

## G. CLAUDE.md #30.L 草稿 (Layer 3 PG Smoke 触发的 baseline FK-to-stubs 移除)

> **状态**: 本节作为 #30.L 草稿在本文件就地承载, Step 12.B squash 时与 #32 一并写入 CLAUDE.md, 同 PR 删本文件。`#30.L` 是 #30 系列的延续 (跟 #30.F/G/H/I/J/K 同模式), 跟 #30.H Path B Variant 2 (users 真实表 + 3 FK ALTER materialize) 是同样的 cross-Session FK 推迟模式。

### A. 决策 (Path A-3-extended)

A0' baseline migration `2026_04_27_0231_cdfdaab4088e_baseline.py` 在 6 张表上声明了 7 个 FK-to-stubs (`brands.id` / `llm_responses.id` 两个 SQLAlchemy upstream stubs 对应的目标), 触发 PG 兼容性问题: stubs 在 `app/db/_upstream_stubs.UPSTREAM_STUB_NAMES` 仅做字符串解析注册, **从未 DDL 创建** — SQLite 的 FK 不强制 (aiosqlite 默认关闭) 让 baseline 在 SQLite 上能跑, 但 PG 在 `CREATE TABLE` 时严格校验 FK 目标表存在, 整条迁移链 (cdfdaab4088e → 55a628f2bb7d → 15500b81322a → 8a3f1d2c5e7b) 在 docker compose 起 PG admin stack 时失败, backend-admin 容器陷入 Restarting 循环。

采纳 **Path A-3-extended**: baseline 中 6 张表上的 7 条 `sa.ForeignKeyConstraint(..., ['brands.id'/'llm_responses.id'], ...)` 整体移除, 列定义保留 (`brand_id String(36)` / `response_id String(36)` 仍存在, 仅 FK 约束消失), 真实 FK 推到目标真实表所在的 Session 通过 ALTER TABLE materialize — 跟 #30.H Path B Variant 2 在 users 表上的 3 FK ALTER 是同一种 cross-Session FK 推迟模式。

### B. 移除清单 (6 张表 / 7 FK)

`backend/alembic/versions/2026_04_27_0231_cdfdaab4088e_baseline.py` 移除:

- `brand_mentions`: 2 FK
  - `brand_id → brands.id` (`fk_brand_mentions_brand_id_brands`)
  - `response_id → llm_responses.id` (`fk_brand_mentions_response_id_llm_responses`)
- `geo_score_daily`: 1 FK
  - `brand_id → brands.id` (`fk_geo_score_daily_brand_id_brands`)
- `product_score_daily`: 1 FK
  - `brand_id → brands.id` (`fk_product_score_daily_brand_id_brands`)
- `response_analyses`: 1 FK
  - `response_id → llm_responses.id` (`fk_response_analyses_response_id_llm_responses`)
- `citation_sources`: 1 FK
  - `response_id → llm_responses.id` (`fk_citation_sources_response_id_llm_responses`)
- `sentiment_drivers`: 1 FK
  - `response_id → llm_responses.id` (`fk_sentiment_drivers_response_id_llm_responses`)

仅删 FK 约束行, **列定义不动**, **不动 brand_mentions / response_analyses 内部已存在的真实表 FK**。

### C. 保留的 3 内部 FK (baseline 内部表互相引用, 真实表存在, 不受影响)

- `citation_sources.mention_id → brand_mentions.id` ✅
- `sentiment_drivers.mention_id → brand_mentions.id` ✅
- `product_feature_mentions.analysis_id → response_analyses.id` ✅

### D. Cross-Session ALTER 计划

| 真实表 | 落地 Session | 影响表 (列名 → FK 目标) | ALTER 操作 |
|---|---|---|---|
| `kg_brands` | Session 1.5' | `brand_mentions.brand_id`, `geo_score_daily.brand_id`, `product_score_daily.brand_id` | 3 张表 ALTER ADD CONSTRAINT FK |
| `ai_responses` | Session 3' | `brand_mentions.response_id`, `response_analyses.response_id`, `citation_sources.response_id`, `sentiment_drivers.response_id` | 4 张表 ALTER ADD CONSTRAINT FK |

每条 ALTER 模式参考 `2026_04_28_1700_8a3f1d2c5e7b_session_a1_step3_users_table_plus_3_fk.py` 的 `batch_alter_table(...) → batch_op.create_foreign_key(...)`, ON DELETE 策略由目标 Session 按业务语义决定 (kg_brands 引用建议 RESTRICT 或 SET NULL, ai_responses 引用建议 CASCADE — 由 Session 1.5' / 3' 实施时定稿)。

### E. 命名清理转交 (DATA_MODEL §1.5 / §2 真相源对齐)

`brands` / `llm_responses` 是 SQLAlchemy upstream stub 的临时名字, DATA_MODEL §1.5 / §2 的真相源命名是 `kg_brands` / `ai_responses`。本次仅移 FK 约束不改列定义, 列名 `brand_id` / `response_id` 是中性命名 (不带 stub 前缀), 不需要改。Session 1.5' 落 `kg_brands` 时 ALTER 直接引用真实表名, Session 3' 落 `ai_responses` 同理 — stub 命名漂移随 stub 退役自然消化。`app/db/_upstream_stubs.UPSTREAM_STUB_NAMES` 中 `brands` / `llm_responses` 两条移除时机: Session 1.5' / 3' 落地后 stub 不再需要字符串占位, 由各自 Session 同 PR 摘除 stub 注册行。

### F. Rule 3 偏离登记理由

A0' baseline 设计时假设 `brands` / `llm_responses` stub 在 SQLAlchemy schema 注册即可让 alembic 生成 FK 约束 — 这在 SQLite 测试环境成立 (FK 不强制), 但在 PG 生产/staging 环境 (Layer 3 PG smoke) 失败, 是真相源跨 DB 兼容性的隐性偏差。`#30.L` 把 baseline 与真实表所在 Session 的 schema 责任明确划分 — baseline 只声明列, FK 约束由真实表 owner Session 负责 — 跟 #30.H Path B Variant 2 (users 表 + 3 FK ALTER) 的 cross-Session FK 推迟模式同源同构。

**测试纪律守护**: 跨 DB 三次往返 (SQLite + PG) 由 `verify-session-a1prime.sh §4` 已纳入 Layer 1 验证, 但 baseline 在 A0' 时点仅在 SQLite 跑 alembic, PG 兼容性首次实际验证发生在 A1' Step 12.B Layer 3 PG smoke — Phase Gate 标准应在 Session 1' / 1.5' / 3' 推进时把 docker compose admin stack 起 PG + alembic upgrade head 纳入 mandatory smoke (避免类似 baseline-stub-FK 的隐性偏差再次仅在 Layer 3 才暴露)。

### G. 实施记录 (本次 Layer 3 PG smoke 修复)

- **T1**: `cdfdaab4088e_baseline.py` 移除 6 张表 7 FK-to-stubs 行 (Edit operations 用 PrimaryKeyConstraint 行作 anchor); 早先同次 fix 已把 Boolean defaults 从 `sa.text('0')` 改为 `sa.text('false')` (PG 兼容性, lines 50 + 135)。grep `from.*brands.*\.id|from.*llm_responses.*\.id` 验证 baseline 无残留。
- **T2**: docker compose admin profile wipe + up + healthz 200 OK + alembic head 8a3f1d2c5e7b 验证。
- **T3**: super_admin `frank@genpano.com` bootstrap (force_password_change_at=NOW(), 临时密码 `Layer3-bootstrap-2026`) + Layer 3 fixtures 3 行 (smoke-user@example.com / 苹果 alias / 花西子 brand_submission)。
- **T4.1**: SQLite 三次往返 (`alembic upgrade head` 4 migrations → `downgrade -1` 8a3f1d2c5e7b → 15500b81322a → `upgrade head` replay → final `current` 8a3f1d2c5e7b head) GREEN。
- **T4.2**: PG 三次往返 GREEN (clean DB, 因 brand_submissions 内有 `submitter_user_id IS NULL` 的 fixture 行触发 `downgrade -1` 时 NOT NULL 重新引入失败 — 通过 `clear_layer3_fixtures.py` 清理后 roundtrip 成功, 然后 `seed_layer3_fixtures.py` 重新 idempotent 入库)。**附带发现**: `2026_04_28_1700_8a3f1d2c5e7b_*.py` 的 downgrade 把 `brand_submissions.submitter_user_id` 还原为 NOT NULL — 这与 Step 1 baseline 中该列的 NOT NULL 设定一致, 是 downgrade 的正确语义, 但意味着 downgrade 不能在持有 `submitter_user_id IS NULL` (即 SET NULL FK 的合法 post-upgrade 状态) 的行的 DB 上跑。**纪律推论**: 跨 DB 三次往返必须在 clean DB 上跑, 业务数据填充与 schema 回滚测试是不同 phase, 不可混。
- **T4.3**: pytest 全跑 GREEN, coverage **84.07%** (>80% 阈值), 单测覆盖见 `tests/admin/` 下各 module。

---
