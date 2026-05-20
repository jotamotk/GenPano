# Code-Level Refactoring Plan

> **Status / provenance.** Regenerated 2026-05-20 from 5 parallel evidence-based
> audits of the current checkout. The original code-level audit (referenced as
> "G4.3 workflow sprawl" inside the GitHub→GitLab migration plan) was produced in
> an earlier session but never persisted to disk, and was lost to context
> compaction. This document re-derives it from the actual code so every finding
> is anchored to a real `file:line` + metric per `AGENTS.md` "Evidence-First".
> It supersedes the lost original. **This file is committed to git so it cannot
> be lost again.**
>
> Cross-reference: the GitLab CI/CD migration plan is a *separate* artifact. Its
> "G4.3 workflow sprawl" maps to **[TOOL-1]** below.

## How to use this (for the executing session)

1. Pick findings off the **Prioritized execution sequence** (bottom). Each has a
   stable ID (e.g. `XPKG-1`, `GOD-2`) — reference it in commits/PRs.
2. **Read `AGENTS.md` first.** This repo has hard rules that gate merges:
   - *Evidence-First Shipping* — behaviour-changing refactors must trace one
     **real** value (API JSON / DB row / rendered string) before+after.
   - *Pruning Automation* — dead-code removal needs a Pruning Report +
     owner-confirm, not a silent delete. Git history is the recovery path.
   - PR bodies MUST carry **Root Cause Gate / Business Goal / Verification
     Evidence Ledger** or `.github/workflows/pr-body-lint.yml` rejects them.
     Use the `/compose-incident-pr` skill.
3. Do **behaviour-preserving** work (god-file splits, util extraction) and
   **behaviour-changing** work (contract unification, model dedup) in separate
   PRs. Never mix.

## Repo health snapshot

| Package | Files | LOC | 5 biggest files (LOC) |
|---|---|---|---|
| `backend/app/{api,admin,reports,alerts}` | 271 | 70,522 | `api/v1/projects/_charts_service.py` (3452), `_topic_analysis_service.py` (2037), `_metrics_service.py` (1792), `api/v1/industries/service.py` (1583), `admin/prompt_matrix/lib.py` (1549) |
| `backend/app/{core,db,models,tasks,kg,diagnostics,user_auth}` + `scripts` + `alembic` | 84 | 14,523 | `diagnostics/rules.py` (2259), `scripts/app_analytics_readonly_evidence.py` (1028), `scripts/inspect_products_response.py` (951), `user_auth/email.py` (651), alembic `admin_console_consolidation` (588) |
| `geo_tracker/` | 89 (+51 test) | 37,438 | `agent/guest_executor.py` (4314), `tasks/celery_tasks.py` (2513), `analyzer/cli.py` (2137), `tasks/bestcoffer_citation_geo_followup.py` (1397), `analyzer/canonical_brand_repair.py` (1294) |
| `frontend/src` | 237 | 47,120 | `pages/TopicsPage.tsx` (2156), `lib/api-types.d.ts` (1715), `data/appChartDataContract.ts` (1147), `pages/BrandDetailPage.tsx` (946), `pages/KnowledgeGraphPage.tsx` (839) |
| tooling / `.github` | — | 9,248 (workflows) | `server-diagnostics.yml` (2397) |

## Reference architectures — DO NOT "refactor" these (verified-clean counter-findings)

Touching these wastes effort and risks regressions. Use them as the **target pattern** when refactoring their messy siblings.

- `backend/app/api/v1/projects/router.py` (1057 LOC) — correct **thin aggregator**: delegates to service modules. The debt is in the *services* (`GOD-2`, `GOD-5`), not the router. This is the template for the `api/admin/*` fat routers.
- `backend/app/reports/` — clean `sections/base.py` `BaseSection` ABC + `ReportContext`.
- `geo_tracker/agent/executors/` — clean `BrowserConnector` ABC + 2 impls + `router.select_executor`, fully typed & tested. **Template** for the rest of geo_tracker.
- `frontend/src/{api,adapters,data}` — a clean 3-layer pipeline (typed HTTP via single `lib/apiClient.ts` → pure DTO reshapers → contract). **NOT** duplicated fetch logic. Error/loading plumbing (`lib/queryClient.ts` → `showApiError.ts`) is already centralized — leave it.
- `backend/app/core/` — small, typed, single-purpose (`config.py` pydantic-settings with `AliasChoices`). The config *sprawl* is raw `os.environ` reads *bypassing* it (see `DUP-8`, `GOD-8`), not `core/` itself.
- `migrations.legacy/`, `experiments/vm_per_account/`, `clash/`, `vm_side/` — **live/intentional, do NOT delete.** Each is backed by an ADR + active references (ADR-002, ADR-016, docker-compose, deploy.yml). A naive "dead-dir" sweep would wrongly target these.
- `CLAUDE.md`, `.cursorrules`, `docs/AI_LEAD_CLAUDE_COLLABORATION.md` — correctly defer to `AGENTS.md`; no drift. Leave them.

---

## Findings

### Theme A — Cross-package duplication (KEYSTONE: highest structural leverage)

**XPKG-1 · 16 shared DB tables defined twice, with diverging defaults · [correctness risk] · L / High**
`geo_tracker/db/models.py:51-905` defines its own `Base` (line 10) + 33 tables; **16 analyzer tables are re-defined** in `backend/genpano_models/analyzer.py:42-512` against a *different* `Base`. Identical `__tablename__`/constraint names on both sides (`brand_mentions` geo `:450` / backend `:43`, both `uq_mention_response_brand_product`; plus `sentiment_drivers, citation_sources, response_analyses, product_feature_mentions, analyzer_runs/batches/batch_items, response_entities, response_relation_facts, analysis_fact_links, analyzer_quality_flags, geo_score_daily, topic_score_daily, industry_benchmark_daily, product_score_daily`). **Defaults already diverged:** `is_target` is Python-side `Column(Boolean, default=False)` (geo `:457`) vs DB-side `server_default=expression.false()` (backend `:60`); same for `mention_count` (`default=1` vs `server_default="1"`). Two writers, one physical table, drifting insert semantics. `genpano_models/__init__.py:18` already names the fix: *"Future PR — move package to repo root + adapt geo_tracker imports."*
→ Make geo_tracker import the 16 analyzer models from `genpano_models` (the SSOT). Resolve the `Base`-registry split first. Gate behind migration-parity verification (compare emitted DDL before/after).

**XPKG-2 · Duplicate config + DB-session plumbing · M / Med**
`geo_tracker/config.py:9-58` hand-rolls `create_async_engine`/`async_sessionmaker`/`get_async_session` from raw `os.getenv("DATABASE_URL")`. Backend has the parallel stack: `backend/app/db/session.py:1-24` + typed `backend/app/core/config.py:7-25` (reads `AliasChoices("GENPANO_DATABASE_URL","DATABASE_URL")`). geo_tracker can't read `GENPANO_DATABASE_URL`; pool sizing/pre-ping diverge silently.
→ Extract a shared `db`/`config` module (co-located with `genpano_models`); both trees consume it. Minimum: align env-var names.

**XPKG-3 · 5+ hand-rolled Ark/Doubao/Volc LLM clients · M / Med**
`geo_tracker/analyzer/llm_analyzer.py:97-114` (`AsyncOpenAI`/`httpx` for `ARK_*`), `geo_tracker/analyzer/sentiment_analyzer.py:24-66` (`VOLC_NLP_*`), plus backend `admin/prompt_matrix/llm.py` (docstring: *"Async httpx port…"*), `admin/query_pool/llm.py`, `admin/topic_plan/llm.py`, `kg/llm_relation_extractor.py`. Retry/timeout/proxy-bypass (`trust_env=False`) set in some, not others.
→ One shared `ArkClient`/`DoubaoClient` wrapper with unified retry+proxy policy. Evidence-First: trace one real response per consumer before merge (live LLM path).

**XPKG-4 · Analyzer aggregation overlaps backend metrics services · L / Med (needs trace first)**
`geo_tracker/analyzer/aggregator.py` (1040) writes `*_score_daily`; `backend/app/api/v1/projects/_metrics_service.py` (1792), `_charts_service.py` (3452), `_mention_rollups.py` read/aggregate the same `brand_mentions`/`*_score_daily`. `backend/scripts/backfill_product_score_daily.py:114` imports `from geo_tracker.analyzer.aggregator import Aggregator` — same aggregation reached from both sides → metric-definition drift risk (writer vs reader compute `mention_rate` differently).
→ Establish one canonical metric-definition module; backend reads what geo_tracker writes rather than recomputing. **Trace before refactor** — not yet a confirmed line-for-line dup.

### Theme B — God-files & god-functions (decomposition; behaviour-preserving)

**GOD-1 · `geo_tracker/agent/guest_executor.py` — 4314 LOC, two ~1k-LOC methods · L / Med**
`_execute_once` ~937 LOC (`:759`→~1696), `_browser_query` ~1268 LOC (`:2728`→~3996); 44 defs, engine-specific branches interleaved (`_extract_chatgpt_citations:2290`, `_extract_doubao_citations:2420`, `_recover_from_doubao_unavailable_page:1780`).
→ Per-engine strategy modules (`executors/engines/{doubao,chatgpt}.py`); decompose `_browser_query` into submit/wait/extract/classify-error stages (the intent already stated in `base.py:1-25`).

**GOD-2 · `backend/.../_charts_service.py` — 3452 LOC, 11 functions >150 LOC · L / Med**
`get_mention_samples` (319), `get_sentiment_by_engine` (257), `get_sentiment_trend_by_engine` (207), `get_citation_composition` (201)… import block alone `:16-140`. Each handler inlines SQL build → fact aggregate → contract-status shape → DTO.
→ Split per chart domain into `charts/{sentiment,citation,authority,topic,pr}_service.py`; extract shared "fetch facts → aggregate → apply contract → build DTO" pipeline.

**GOD-3 · `geo_tracker/tasks/celery_tasks.py` — 2513 LOC; `execute_query` ~560 LOC · L / Med**
`execute_query` `:889`→~1449. Mixes account-handoff (`:487`), Redis session locks (`:569`), keep-alive probing (`:225`), analysis dispatch in one file.
→ Split into `tasks/{execution,keep_alive,account_handoff,session_lock}.py`.

**GOD-4 · `backend/app/diagnostics/rules.py` — 2259 LOC, 27 near-identical rule classes · L / Med**
27 `class XRule(BaseRule)`, each repeating: `if project.primary_brand_id is None:` guard (27×), `today = date.today()` (26×), `timedelta(days=29)` window math (23×), a giant `DiagnosticPayload(...)` literal (27×), `except Exception:` swallow (20×). Same skeleton: `VisibilityDeclineRule:147-199` ≅ `NegativeSentimentGrowthRule:206-258`.
→ Split into a `diagnostics/rules/` package; hoist onto `BaseRule`: `requires_primary_brand` flag, `current_and_prior_window(days=30)` helper, `make_payload(**overrides)` factory. Each rule body collapses to SQL + threshold.

**GOD-5 · `backend/.../projects/_*_service.py` monster functions · M / Med**
`_topic_analysis_service.py:1308-1698` = single **390-LOC** function (`get_query_response_detail`); also `get_citations` (305), `get_sentiment` (274). Across the 4 `_*_service.py`: **21 functions >150 LOC**.
→ Decompose each into named fetch/aggregate/shape stages; extract the shared admin-fact fallback path.

**GOD-6 · `frontend/src/pages/TopicsPage.tsx` — 2156 LOC, 19 inline components · L / Med**
Three full view screens inline — `TopicsView:762`, `PromptsView:996`, `QueriesView:1220` — + `MetricCard:237`, `ResponseAttemptsModal:1608`, 9 `useState`, 7 `useEffect`.
→ Split views into `pages/topics/*.tsx`; extract `MetricCard`/`StateBadge`/`ResponseAttemptsModal` into `components/`; move label maps to `constants.ts`. (Well covered by its 1864-LOC test.)

**GOD-7 · Other frontend god-components · M each / Med**
`pages/BrandDetailPage.tsx` (946, 10 inline comps), `pages/KnowledgeGraphPage.tsx` (839, 9), `layouts/DashboardLayout.tsx` (520, 8). Same monolith pattern as GOD-6, lower priority.
→ Extract per-tab/per-panel components into co-located folders.

**GOD-8 · `backend/app/user_auth/email.py` — 651 LOC, 4 concerns · M / Low**
One module = ~14 raw env reads (`:60-127`) + HTML layout helpers (`_button:142`…`_layout:185`) + 3 content builders (`:280,:323,:368`) + 3 provider transports (`_send_with_resend:411`, `_send_with_aliyun_dm:451`, `_send_with_preview:508`) behind `_send:558`.
→ Split into `email/templates.py`, `email/providers/{resend,aliyun_dm,preview}.py` (behind a Protocol), `email/dispatch.py`; pull env-vars into a typed `EmailSettings`.

### Theme C — Within-package duplication (extract shared helpers; mostly quick wins)

**DUP-1 · `_now()`/`_isoformat()` copy-pasted 45+× · backend · S / Low**
`datetime.now(UTC).replace(tzinfo=None)` byte-identical in **45** bodies (`api/admin/comms/router.py:33`, `cost/router.py:38`, `diagnostics/router.py:38`, `session/router.py:31`, `api/v1/reports/service.py:23`…); `_isoformat`/`_iso` ~17×. No time util in `core/` despite `errors.py`/`pagination.py`/`filters.py` living there.
→ Add `app/core/datetime.py` (`now()`, `isoformat()`); replace all local defs.

**DUP-2 · Manual `request.json()` body-parse block ×67 · backend · L / Med**
Exact 4-line `try: payload = await request.json() except: payload = {} … if not isinstance(payload, dict): payload = {}` appears **67×** across 18 files (`segments/router.py:187,240,280`, `vm_accounts/router.py:164`…); 70 total `await request.json()`. Bypasses Pydantic entirely — no schema, no OpenAPI, no type safety. Root enabler of DUP-3/DUP-5.
→ Pydantic request models per endpoint (as `api/v1/*` already does), or a shared `parse_json_body` dependency. Behaviour-changing → trace one payload per endpoint.

**DUP-3 · `emit_audit` + `ValueError→validation_error` boilerplate ×99 · backend · M / Med**
`await emit_audit(` appears **99×** across 26 routers (10 in `segments/router.py`). Each mutating handler = manual parse → `try/except ValueError` → ~10-line `emit_audit(...)` → `{"success": True}`. Business call is 1 line buried in ~30 of scaffolding.
→ `@audited(action=…, severity=…)` decorator/context-manager capturing before/after+reason; centralize `ValueError→validation_error`.

**DUP-4 · `_maybe_schema_error_response` duplicated verbatim · backend · S / Low**
Identical helper in `accounts/router.py:63` and `vm_accounts/router.py:71` (comment: *"mirrors app/api/admin/accounts/router.py"*); the `try/except RuntimeError → _maybe_schema_error_response` block repeats **13×**. Copies already differ in message text — drift in progress.
→ Move to `app/admin/db_errors.py` as one helper + a shared dependency.

**DUP-5 · camelCase/snake_case key coercion ×36 · backend · S / Low**
`payload.get("x") or payload.get("X")` **36×** (`segments/router.py:40-96` `_coerce_*` ~10 fields; `query_pool/router.py:70` brandId/brand_id). Per-field per-router; easy to miss one and silently drop data.
→ `normalize_keys(payload)` util once at the boundary, or Pydantic alias models (folds into DUP-2).

**DUP-6 · Near-identical admin-CRUD router scaffolding · backend · L / Med**
`topic_plan` (11 routes), `segments` (15), `query_pool` (10) each re-implement the same list/create/update/delete shape (`query_pool/router.py:5` docstring: *"parity with topic_plan B.1"*) + own `_now`/`_isoformat`/`_*_row` serializers.
→ Generic admin-CRUD base (router factory/mixin) parameterized by db module + audit action names. (Do after DUP-1/2/3 land the shared pieces.)

**DUP-7 · `_run_async` + Celery scaffolding duplicated · backend-core · S / Low**
Identical `_run_async(coro)` in `tasks/kg.py:28` and `tasks/reports.py:45`; every `@celery_app.task` carries `# type: ignore[untyped-decorator]` (`health.py:12`, `kg.py:33`, `reports.py:77,148,239`); `reports.py` has 11 in-function lazy imports.
→ `tasks/_base.py` with shared `_run_async`, a typed `genpano_task()` decorator (single `type: ignore`), + the DUP-8 session helper.

**DUP-8 · DB engine/sessionmaker boilerplate ~10× (shared `session.py` bypassed) · backend-core · M / Med**
`create_async_engine(settings.database_url) + async_sessionmaker(...)` at `tasks/reports.py:96,157,247` (per task body!), `tasks/kg.py:49`, + 6 scripts. `app/db/session.py`'s `AsyncSessionLocal` has **0** usages in tasks/scripts. Each task spins up & disposes its own engine per invocation — pool config never applied.
→ Add `session_scope()` async-CM + sync `run_in_session()` for Celery next to `AsyncSessionLocal`; replace per-task construction. Verify pooling under Celery's process model.

**DUP-9 · Redis client construction ×3 · backend-core · S / Low**
Identical `from_url(os.environ.get("GENPANO_REDIS_URL") or os.environ.get("REDIS_URL", "…"))` at `core/rate_limit.py:104`, `kg/llm_relation_extractor.py:83` and `:109`. `redis_url` is already a typed `Settings` field (`config.py:14`) — none use it.
→ `app/core/redis.py::get_redis_client(*, disable_env)` reading `get_settings().redis_url`.

**DUP-10 · `_env_flag`/`_env_int`/`_env_float` reimplemented 5+× with diverging defaults · geo · S / Low**
`_env_flag` in `guest_executor.py:349`, `executors/local.py:69`, `browser_lifecycle.py:41`, `sms_login/base.py:55`, `celery_tasks.py:100` — first four default `True`, `celery_tasks` defaults `False`. Truthy-parsing can drift.
→ One `geo_tracker/_env.py` (`env_flag/env_int/env_float`).

**DUP-11 · Backfill CLI `main()` identical ×7 · geo · S / Low**
`main(argv)` in `analyzer_v3_backfill.py:936`, `topics_analyzer_backfill.py:531`, `bestcoffer_analyzer_backfill.py:610` are character-identical except the caught exception type; the `build_parser`/`run_from_args`/`asyncio.run` trio repeats across 7 task files (~5295 LOC combined).
→ `tasks/_cli.py::run_backfill_cli(build_parser, run_from_args, error_types=…)`.

**DUP-12 · `tasks/_loop_utils.py` is a 27-LOC stub — the dedup seam exists but is unused · geo · S / Low**
Exposes only `safe_dispose_engine`; meanwhile every backfill rebuilds engine/session + CLI locally (DUP-10/11).
→ Promote to `tasks/_shared.py` housing engine lifecycle + CLI + env helpers (absorbs DUP-10/11).

**DUP-13 · CLI/script scaffolding ×7 (argparse+asyncio.run+engine) · backend-core scripts · M / Low**
7 scripts each carry their own argparse + `asyncio.run(main())` + DUP-8 engine build (`backfill_phase_a.py`, `promote_kg_candidates.py`…); `promote_kg_candidates.py:28` duplicates the engine setup that `tasks/kg.py:49` has for the *same* entrypoint.
→ `scripts/_common.py::async_session_for_cli()` + `run_script(main_coro)`; reuse DUP-8 helper.

**DUP-14 · SMS-login flow boilerplate + 2 parallel provider clients · geo · M / Med**
`sms_login/base.py` (1250) + `DoubaoLoginHandler` (982), `DeepseekLoginHandler` (731), `ChatGPTLoginHandler` (360) subclasses; two SMS-provider clients `herosms_client.py` (396) & `luban_client.py` (257) with parallel reserve/poll/cancel and no shared interface.
→ `SmsProvider` Protocol (reserve/mark_ready/poll/cancel) both implement; pull common login step-machine into `base.py` with engine hooks. Live money path — trace before merge.

**DUP-15 · `isLiveProjectId` defined 3× with 3 bodies · frontend · S / Low**
`lib/liveProject.ts:14` (UUID_RE), `hooks/useBrandOverview.ts:14` (re-import), `hooks/useReports.ts:20` (inline own regex). Brand pages import it from the *hook*, not the canonical lib. Divergence silently routes a project to mock vs live differently per page.
→ Keep only `lib/liveProject.ts`; re-export/redirect imports; delete duplicate bodies.

**DUP-16 · Brand-page resolution prelude duplicated across 5 pages · frontend · M / Low-Med**
Identical 4-line `useProjects()`→`resolveLiveProjectId`→`isLiveProjectId` + `isLive ? id : null` per-hook idiom in `BrandCitationsPage.tsx:77`, `BrandProductsPage.tsx:76`, `BrandSentimentPage.tsx:94`, `BrandCompetitorsPage.tsx:89`, `BrandVisibilityPage.tsx`, + same import header.
→ Extract `useLiveProjectScope()` returning `{ liveProjectId, isLive, chartFilters, brandIdOverride }`.

### Theme D — Contracts & consistency (behaviour-changing; gate with consumer traces)

**CONTRACT-1 · Two incompatible error-response contracts · backend · L / Med**
`app/core/errors.py` defines RFC-7807 `ProblemDetails` (used by 36 files), but **86 ad-hoc `{"success": False, "error":…, "message":…}`** bodies exist across 16 files. Many files mix BOTH (`segments/router.py` raises `not_found(...)` *and* returns `{"success": False}`; `accounts/router.py:57` imports `not_found` yet hand-builds 503 `{"success": False}` at `:80-110`). Frontend can't rely on one shape; the `code` field for i18n is absent from half.
→ Pick the documented `ProblemDetails`; add helpers for 503/409 cases; convert the 86 ad-hoc bodies. Trace each consumer (frontend `showApiError`) before flipping.

**CONTRACT-2 · Two i18n systems mounted simultaneously · frontend · M / Med**
`main.tsx:25-33` nests BOTH `<LocaleProvider>` (→ `i18n/messages.js`, 2275 LOC, used by **48** files, key `genpano.locale`) and `<LanguageProvider>` (→ `i18n/{en,zh}.ts`, **13** files, key `genpano_lang`). `apiClient.ts:104` reads a third raw `genpano_lang` for `Accept-Language`. Toggling one provider doesn't update the other or the API header.
→ Make `LocaleContext`/`messages.js` canonical (4× adoption); port the ~13 auth strings, swap `useLanguage`→`useLocale`, delete `LanguageContext.tsx` + `i18n/{en,zh,index}.ts`, point `apiClient` at `genpano.locale`. Verify auth-page string parity.

**CONTRACT-3 · Hardcoded CJK strings bypass i18n in 20+ files · frontend · L (volume) / Low**
Non-comment CJK JSX literals: `components/diagnostics/DiagnosticCard.tsx` (26), `pages/brand/BrandCompetitorsPage.tsx` (16, e.g. `:347` `Top 3 威胁竞品`, `:372`…), `pages/AuthPage.tsx` (11), `citation/PrTargetsPanel.tsx` (11), `BrandSimulatorPage.tsx` (10)… The en-US path renders untranslated Chinese, defeating CONTRACT-2's infra.
→ Move literals into `messages.js` namespaces, replace with `t('…')`. Add a lint rule (no raw CJK in `.tsx` JSX) to prevent regression. Prioritize high-count files.

### Theme E — Typing gaps

**TYPE-1 · `geo_tracker` entirely excluded from mypy · M / Low**
`Makefile:107` runs `mypy app/ genpano_models/` — no `geo_tracker` target; no root mypy config. Yet geo_tracker is already 67% annotated (644/965 funcs, 75/89 files use `from __future__ import annotations`) — close to mypy-ready but unchecked. ~37k LOC of the most failure-prone subsystem (browser automation, money-spending SMS) gets zero static enforcement.
→ Add `mypy geo_tracker/` (start `--ignore-missing-imports` for playwright/camoufox), fix the long tail. **Do early — it guards the rest of the geo refactors.**

**TYPE-2 · Mixed JS/TS; untyped `mock.js` wired into 23 production modules · frontend · M-L / Med**
Untyped `.js` in `src/`: `data/mock.js` (2331), `hooks/useBrandAnalysisFilters.js` (123), `lib/industry/statistics.js` (324), `i18n/messages.js` (2275). `mock.js` imported by **23** non-test files incl. `contexts/ProjectContext.tsx:29` (source-of-truth in mock mode). Type system can't catch shape drift vs real DTOs; documented "mock retirement" is stalled.
→ Convert `useBrandAnalysisFilters.js` + `statistics.js` to `.ts` first (small, high value); type `mock.js` exports against api DTOs; then drive mock-retirement to shrink the 23-file coupling. Mock underpins demo/unauth mode — verify.

**TYPE-3 · Stringly-typed diagnostics contract + `Any` SQL helpers · backend · M / Low**
`rules.py:108` `_normalize_brand_name_sql(col: Any) -> Any`, `:118` `_weighted_avg_geo_metric(col: Any) -> Any`. Severity is a bare string 41× (`"P0".."P3"`), `type` free string (`DiagnosticPayload:67`). A typo (`"P4"`) passes mypy and is silently ranked 0 in `evaluator.py:47`.
→ `Severity = Literal["P0","P1","P2","P3"]`, `DiagType = Literal[...]`; type SQL helpers as `ColumnElement[...]` (SQLAlchemy 2.0 generics). Removes the silent-rank-0 failure mode.

### Theme F — Dead code / pruning (AGENTS.md: Pruning Report → owner-confirm → delete; git recovers)

**DEAD-1 · 3 dead frontend pages (~290 LOC) · S / Low**
`pages/ProductsPage.tsx` (self-labeled `DEPRECATED`, "可以安全删除", not in `App.tsx`), `pages/RegisterPage.tsx` (171, zero importers — `/register` mounts `<AuthPage type="register"/>`), `pages/ForgotPasswordPage.tsx` (98, zero importers). All confirmed unreachable; they still import the dead `useLanguage` (inflating CONTRACT-2).

**DEAD-2 · Backend dead one-off scripts (~1072 LOC) · S / Low**
`scripts/inspect_products_response.py` (951, zero refs, docstring "Local reproduction"), `scripts/preview_user_emails.py` (121, zero refs). (Keep `app_analytics_readonly_evidence.py` — referenced by tests; keep `ci_check.py` — wired into CI.)

**DEAD-3 · geo dead scripts (~500+ LOC) · S / Low**
`geo_tracker/run_nike_test.py` (494, zero refs), `geo_tracker/add_test_accounts.py` (zero refs) — one-off manual harnesses presenting as package code.

**DEAD-4 · ~7 orphan top-level scripts · S / Low-Med**
Zero external refs: `scripts/luban_tool.py`, `reset_doubao_accounts.py`, `test_doubao_cookies.py`, `trigger_gemini_now.py`, `update_clash_sub.sh`, `update_clash_subscriptions.sh`, `test_update_vninja_subscription.sh`. Some touch live proxy — confirm operators don't run by hand (overlaps TOOL-7).

**DEAD-5 · `scripts/python` is a committed 0-byte file · S / Low**
`-rw-r--r-- … 0 … scripts/python` — almost certainly a `> scripts/python` redirect typo. Delete.

### Theme G — Tooling, infra, migrations, docs (the original "G4" area)

**TOOL-1 · Workflow sprawl: 33 of 38 workflows are ad-hoc runbooks ·  L / Med** *(= migration plan's "G4.3")*
38 files / 9248 LOC; only **5** are real CI/CD (`ci`, `pr-body-lint`, `issue-body-lint`, `deploy`, `docker-cleanup`). The rest: **16 `vm-*`** dispatch one-offs, **12** brand/incident-specific (BestCoffer×3, herosms, repair-deepseek-stale, cleanup-stuck-alembic, chatgpt-proxy-hotfix/-evidence…), the spent `.github/auto-apply-chatgpt-proxy-fix.trigger`, and `server-diagnostics.yml` (2397 LOC = 26% of all workflow LOC). **Zero `workflow_call`** reuse → all 9248 LOC is copy-paste.
→ Sunset/delete the brand/incident bucket + spent `.trigger` (git recovers); consolidate 16 `vm-*` into 1-2 parameterized dispatch workflows; split/trim `server-diagnostics.yml`. Confirm none is an active incident's only lever (chatgpt-proxy touches live UFW rules).

**TOOL-2 · Alembic: business/seed data hardcoded in schema migrations · M / Med**
24 of 39 migrations contain DML. `2026_05_18_0003_backfill_data_security_brands.py:78-162` hardcodes a 9-brand catalog + dialect-branched raw INSERT/UPDATE that duplicates `resolve_brand_industry_by_name`. Product seed frozen in immutable history.
→ Keep existing migrations (history immutable) but **stop adding new data-DML migrations**; move seed/backfill into versioned `scripts/`; document the schema-only boundary.

**TOOL-3 · Alembic head proliferation · S (CI guard) / Low**
3 merge-revisions incl. a no-op `2026_05_18_0004_merge_heads_v2.py` (`upgrade()` is `pass`); reused date-prefixes across distinct revisions (two `…0001`, two `…0003`). `alembic upgrade head` raised "Multiple heads" on every deploy until each manual merge.
→ Single-head discipline: CI check `alembic heads | wc -l == 1`; rebase concurrent branches before merge; collision-free numbering.

**TOOL-4 · Two divergent "canonical" PRDs · M (decision-gated) / Med**
root `PRD.md` (1902 lines, Chinese, login/user-flow) vs `docs/PRD.md` (7488 lines, English, "Executive Summary/Personas"). `README.md:52,54` bills both as authoritative; `docs/INDEX.md:19` calls `docs/PRD.md` canonical. AGENTS.md treats PRDs as product-owner-approved facts → drift corrupts the acceptance source.
→ **Product owner picks ONE** (needs `PRD-CHANGE` per AGENTS.md — do NOT silently rewrite); convert the other to a stub pointer or fold unique sections in.

**TOOL-5 · 13 `PRD_*` docs + multiple "Phase P" addendum forks · M / Low**
`docs/INDEX.md` "Product Requirements" lists 13 files; `*_ADDENDUM_PHASE_P` forks of PRD/ADMIN_PRD/DATA_MODEL/openapi mean base docs are stale and deltas live elsewhere.
→ After the R.x/Phase-P phase closes, merge each addendum back into its base and delete the addendum.

**TOOL-6 · Two competing doc indexes + stale INDEX · S / Low**
`docs/INDEX.md` (123) and `docs/README.md` (28) both index docs; INDEX:123 admits README "predates this INDEX". INDEX lists ADR 001-015 but `ADR/016-vm-per-account-ramp.md` exists (referenced by 5 workflows); `Makefile:73-80` ci-docs guard (`ADR count ≥15`) passes at 16 so CI never catches it.
→ Delete `docs/README.md` (root README already links INDEX); add ADR-016 line; fix the PRD size note; or generate INDEX from a script.

**TOOL-7 · 3 colliding clash-subscription scripts · M / Med**
`scripts/update_clash_sub.sh` (154, file-provider strategy) vs `scripts/update_clash_subscriptions.sh` (116, API-provider strategy) — near-identical names, different behaviour (operator foot-gun) — vs `clash/update_sub.py` (538, the live one). Plus `.env.example:41 PROXY_PROVIDER=clash` while README calls the proxy "vninja" (naming split).
→ Keep `clash/update_sub.py`; delete the two shell duplicates; standardize clash↔vninja naming. Live proxy infra — confirm with operator.

**TOOL-8 · Root `tests/` dir not collected by any pytest config · S-M / Low**
`tests/vm_side/` (3 real test files) — `backend/pyproject.toml:117 testpaths=["tests"]` is scoped to backend/; no root pytest config exists. Only `vm-poc-smoke.yml` references it, so `make test`/CI never runs it → false coverage.
→ Move `tests/vm_side/` next to `vm_side/` + add a pytest path, or add a root pytest config.

**TOOL-9 · `DEPLOY_GUIDE.md` stale · S / Low**
`:25` instructs `python3 trigger_doubao_remote.py` (not in repo); `:6` pins frozen "commit: 7392ae1"; embeds a 30-line `brand_id=999` snippet. Contradicts the modern make/docker-compose flow.
→ Rewrite to point at current `deploy.yml`/docker-compose, drop dead script + commit pin (or delete if `docs/CI-CD.md` supersedes).

**TOOL-10 · `Makefile` ci-docs guard is a placeholder · M / Low**
`Makefile:73-80` only checks file existence (comment: "placeholder until tests land") — gives a green "docs validated" while validating nothing (why TOOL-6's stale INDEX goes uncaught).
→ Implement real PRD-anchor/OpenAPI-sync checks or drop the misleading target.

---

## Prioritized execution sequence

**Tier 0 — Quick wins (S, behaviour-preserving, no contract change). Land first, build momentum:**
DUP-1, DUP-4, DUP-7, DUP-9, DUP-10, DUP-11, DUP-12, DUP-15, DEAD-1, DEAD-5, TOOL-3, TOOL-6, TOOL-9.

**Tier 1 — Guardrails (cheap, high-leverage; prevent regression of later tiers):**
TYPE-1 (mypy on geo_tracker), TOOL-3 (single-head CI), CONTRACT-3's no-raw-CJK lint rule, a "single i18n store" lint. Pruning Reports for DEAD-2/3/4.

**Tier 2 — KEYSTONE cross-package (behind migration-parity + Evidence-First traces):**
XPKG-2 → XPKG-1 → XPKG-3, then XPKG-4 (trace first). These unblock the most downstream debt; do them before the geo god-file splits.

**Tier 3 — Large mechanical decompositions (behaviour-preserving, separate PRs each):**
GOD-4, GOD-2, GOD-8 (backend) · GOD-1, GOD-3 (geo) · GOD-6, GOD-7 (frontend) · GOD-5.

**Tier 4 — Contract/consistency changes (consumer traces mandatory):**
CONTRACT-1, CONTRACT-2, CONTRACT-3 · then admin-router modernization DUP-2 → DUP-3 → DUP-5 → DUP-6 (in order) · DUP-14 · DUP-8/DUP-13 (session helper) · TYPE-2, TYPE-3.

**Tier 5 — Tooling/docs cleanup (decision-gated where noted):**
TOOL-1, TOOL-2, TOOL-7, TOOL-8, TOOL-10 · TOOL-4 (product-owner + PRD-CHANGE), TOOL-5 · DEAD-2/3/4 deletes after confirm.

## Suggested PR slicing (each independently shippable & reviewable)

1. `core/datetime.py` + replace 45 `_now`/`_isoformat` (DUP-1).
2. Dead-code sweep, frontend (DEAD-1) — separate from backend deletes.
3. `scripts/python` delete + `tests/` collection fix + alembic single-head CI (DEAD-5, TOOL-8, TOOL-3).
4. Doc hygiene: delete `docs/README.md`, add ADR-016, fix DEPLOY_GUIDE (TOOL-6, TOOL-9).
5. geo shared utils: `_env.py` + `_cli.py` + promote `_loop_utils` (DUP-10/11/12).
6. `mypy geo_tracker/` on + fix tail (TYPE-1).
7. backend `redis.py` + `tasks/_base.py` + `session_scope()` (DUP-9/7/8).
8. **Keystone:** unify `genpano_models` SSOT, geo imports analyzer models (XPKG-1/2) — migration-parity gated.
9. Shared Ark/Doubao client (XPKG-3) — LLM trace gated.
10–13. God-file splits, one per PR (GOD-4, GOD-2, GOD-1, GOD-6).
14. Single i18n store + no-CJK lint (CONTRACT-2/3).
15. Error-contract unification (CONTRACT-1) — frontend consumer trace gated.
16. Admin-router modernization (DUP-2/3/5/6) — multi-PR.
17. Workflow sprawl sunset + vm-* consolidation (TOOL-1).

## Verification requirements (apply to EVERY PR)

- **Behaviour-changing** (XPKG-1/3/4, DUP-2/3/6/8/14, CONTRACT-1/2, TYPE-2): per AGENTS.md *Evidence-First Shipping*, capture one **real** value through the changed path (API JSON / DB row / rendered string) before + after, and tie ≥1 test fixture to a real captured value (a test that seeds its own hypothesis proves nothing).
- **Behaviour-preserving** (all GOD-*, DUP-1/4/5/7/9-13/15-16): prove the public surface is unchanged — `git diff` shows no route/response-shape/exported-symbol change; full test suite green before AND after; for frontend, the existing tests (e.g. TopicsPage's 1864-LOC test) stay green.
- **Dead-code** (DEAD-*): post a Pruning Report, get owner-confirm, then delete (git history is the recovery path). No silent removal.
- **Every PR body**: include `## Root Cause Gate`, `## Business Goal`, `## Verification Evidence Ledger` or `.github/workflows/pr-body-lint.yml` blocks the merge. Use the `/compose-incident-pr` skill.
- Never mix behaviour-preserving and behaviour-changing work in one PR.
