# METRIC_CONTRACT.md — Unified Metric Calculation Audit & Contract

Branch: `claude/unify-metrics-analysis-fEY07`

This document is the deliverable for the AI Lead's request:

> 现在因为分了topics、prompt、query、attemps 几个层级，每个层级上又有一些很类似的指标，目前看很多指标都很奇怪。请统一调度排查和分析

It contains:

1. **Phase A — Audit** (complete): a cross-layer inventory of how each metric is currently computed at the `topics` / `prompt` / `query` / `attempts` layers, plus the design defects this audit identifies.
2. **Phase B — Evidence** (pending workflow run): SQL/API probes ready to dispatch through `.github/workflows/app-analytics-readonly-evidence.yml`. Live readback will be appended below before the contract in §3 is treated as final.
3. **Phase C — Draft contract** (conditional on Phase B): proposed canonical definitions and cross-layer rollup rules, with a divergence list pointing back at the current implementations that must be reconciled.

**Implementation (Phase D) is out of scope for this branch.** After the contract is signed off, each divergence becomes its own Fast-Path or Full-Path issue per `AGENTS.md ### Fast Path And Full Path`.

This document follows `AGENTS.md ### Evidence-First Debugging` and `AGENTS.md ### Evidence-First Shipping`: no canonical definition becomes final until at least one (DB row + API JSON) pair captured from the live test environment confirms the divergence.

---

## 执行摘要（中文）

**核心结论：用户判断正确——问题在指标计算层有系统性的设计缺陷，不是某一个数字算错。**

审计共识别 13 个设计缺陷（D1–D13），其中 5 个属于"同一页面/同名指标按构造方式就对不上"的关键级别（D7、D8、D9、D11、D13）。最严重的发现：

- **D13（新发现，关键级）：契约层声明所有 ratio 类指标的数据源是 `geo_score_daily` 表（见 `contracts/definitions.py:24`），但全仓库 `grep` 显示**没有任何代码向 `geo_score_daily` 写入数据**。该表只有读操作。这解释了：
  - 为什么 #1236 加入 9 个数据安全品牌后没有聚合行（没有 writer 给它们建行）
  - 为什么 citation_share 在两周内反复改公式（#1234 / #1235 / #1237）——每次都是改"怎么读"，从未改"怎么写"
  - 为什么 `contracts/definitions.py:148-157` 自己承认 "Treat geo_score_daily ratio values as formula-pending until analyzer/data PRs are patched"

- **D1（强化）：`mention_rate` 实际是三路分歧**。契约 (`definitions.py:36`) 说分母是 "eligible non-brand/category responses"；`queries/analytics.py:217` 用的是 `COUNT(DISTINCT q.id)`（所有 query）；`_topic_analysis_dto.py:100` 用的是过滤后的 `mention_denominator`。三种实现对应三种数字。

- **D7（关键）：同一接口 `/admin/queries/analytics` 上 `by_topic` 用 INNER JOIN（丢弃 NULL prompt_id 的 query），`by_engine` 用 LEFT JOIN（保留）**。前端把这两块画在同一页，按构造方式 `sum(queries by engine) ≠ sum(queries by topic)`。

- **D9（关键）：`by_status` 字典只列 {done, failed, pending, running} 四桶；DB 里实际还有 `queued`、`unqueued`** —— 这两种状态的 query 在前端总数中**静默消失**。

下一步建议：用户在 GitHub Actions 上手动跑 `App Analytics Readonly Evidence` 工作流，参数见 §2.2，把回读结果贴回本文档 §2.3。证据齐了再固化 §3 的契约，按缺陷拆 issue 落地修复。

---

## 1. Phase A — Cross-Layer Audit

### 1.1 Layer entities and cardinality (confirmed)

| Layer | Primary tables | Definition | Reference |
| --- | --- | --- | --- |
| topics | `topics`, `topic_candidates`, `topic_score_daily` | Research subject (5–20 char noun phrase) | `genpano_models/admin_console.py:311` |
| prompts | `prompts`, `prompt_candidates` | User input phrase (8–60 char) | `genpano_models/admin_console.py:387` |
| queries | `queries`, `query_generation_*` | Prompt instantiated per profile (20–200 char) | `genpano_models/admin_console.py:432` |
| attempts | `llm_responses`, `analyzer_runs`, `analyzer_batch_items`, `query_attempts` | One LLM execution / analysis attempt | `genpano_models/analyzer.py:190+` |

Cardinality (proved by FK columns and observed grouping SQL):

- topic → prompt: **1:M** via `prompts.topic_id`
- prompt → query: **1:M** via `queries.prompt_id`
- query → `llm_responses`: **1:M** via `llm_responses.query_id`
- query → `query_attempts`: **1:M** via `query_attempts.query_id`

Implication for any cross-layer rate: naive `AVG(child.rate)` is wrong unless children are equal-weighted. The contract (§3.2) must pick `sum-of-num / sum-of-denom` (default) or explicit weighting.

### 1.2 Cross-layer metric definitions — observed

This is the inventory of *current* implementations. The denominator/JOIN-type columns are the field that diverges across layers; this is where every defect in §1.3 surfaces.

| Metric name | Layer / surface | Numerator | Denominator | JOIN policy on `queries → prompts/topics` | File:line |
| --- | --- | --- | --- | --- | --- |
| `mention_rate` | TOPICS contract spec | "target brand mentioned eligible responses" | **"eligible non-brand/category responses"** | (spec only) | `contracts/definitions.py:30-39` |
| `mention_rate` | `/admin/queries/analytics` `by_engine` | `COUNT(DISTINCT bm.id)` | **`COUNT(DISTINCT q.id)`** (all queries) | LEFT (responses/analyses/mentions) | `queries/analytics.py:212-226` |
| `mention_rate` | `/admin/queries/analytics` `by_topic` | `COUNT(DISTINCT bm.id)` | `COUNT(DISTINCT q.id)` (queries with valid prompt+topic) | **INNER (prompts→topics)** + LEFT downstream | `queries/analytics.py:341-379` |
| `mention_rate` | `/admin/queries/analytics` `daily_trend` | `COUNT(DISTINCT bm.id)` | `COUNT(DISTINCT q.id)` (all queries) | LEFT | `queries/analytics.py:278-339` |
| `mention_rate` | PROMPTS DTO `TopicPromptRow` | `target_mention_responses` | **`mention_denominator`** (filtered non-brand) | (in-Python aggregation) | `_topic_analysis_dto.py:100` |
| `mention_rate` | BRAND OVERVIEW `_charts_service.py` | `func.avg(GeoScoreDaily.mention_rate)` | (reads precomputed) | (reads `geo_score_daily`) | `_charts_service.py:732` |
| `success_rate` | PROMPTS DTO `TopicPromptRow` | queries with `status IN ('done','success','completed')` | `query_count` | n/a (per-prompt rollup) | `_topic_analysis_dto.py:98` |
| `success_rate` | TOPICS layer | — | — | **NOT DEFINED** | — |
| `success_rate` | QUERIES layer | — | — | **NOT DEFINED** (status is per-row, not a rate) | — |
| `success_rate` | ATTEMPTS layer | `query_attempts.outcome IN ('success','completed')` per account | per-account attempts | n/a | `vm_accounts/db.py:291-294` |
| `citation_rate` | CONTRACT spec | "citation-backed brand mentions/responses" | **"eligible brand mentions/responses"** (ambiguous: mentions OR responses?) | (spec only) | `contracts/definitions.py:54-64` |
| `citation_rate` | PROMPTS DTO `TopicPromptRow` | `cited_response_ids` | `response_count` | (in-Python) | `_topic_analysis_dto.py:108` |
| `citation_share` | BRAND OVERVIEW KPI | **redefined twice in May 2026**; current = window-total citation count | (post-#1237: ALL citation_sources in window) | (reads `geo_score_daily` + raw) | PRs #1234 / #1235 / #1237 |
| `avg_geo_score` | TOPICS, PROMPTS, QUERIES, BRAND | `AVG(response_analyses.geo_score)` | n/a (average) | varies | multiple |
| `avg_position_rank` | TOPICS, PROMPTS, BRAND | `AVG(brand_mentions.position_rank)` | n/a (average) | **INNER, drops NULL ranks** | `queries/analytics.py:421-436` |
| `attempt_count` | QUERIES DTO | `COUNT(llm_responses.id)` per query | n/a | n/a | `_topic_analysis_dto.py:155` |
| `attempt_count` | TOPICS / PROMPTS layer | — | — | **NOT DEFINED (no rollup rule)** | — |
| `coverage_rate` | TOPICS admin | `len(brand_topics)` | **`max_per_brand`** (configured cap, not actual) | n/a | `topic_plan/db.py:352` |
| `coverage` (status) | PROMPTS admin | derived bucket from `prompt_count` per topic | n/a (bucket label `covered/gap/partial/risk`) | LEFT JOIN prompts | `prompt_matrix/db.py:360-368` |
| `analyzed_rate` (implicit) | `/admin/queries/analytics` `total_analyzed` | `COUNT(*)` after **two-level INNER JOIN** | (no explicit denominator; total_queries shown separately) | INNER+INNER | `queries/analytics.py:149-159` |
| `position_distribution` (bucket counts) | `/admin/queries/analytics` | `CASE` on `position_rank` | n/a | **INNER JOIN brand_mentions; NULL rank dropped** | `queries/analytics.py:421-436` |
| `by_status` (bucket counts) | `/admin/queries/analytics` | `COUNT(*)` per `LOWER(status)` | n/a | n/a | `queries/analytics.py:187-203` |

### 1.3 Identified design defects

Severity: **CRITICAL** = same surface contains two values that cannot reconcile by construction; **MAJOR** = same metric name has different math at different layers; **STRUCTURAL** = no writer / no rollup rule / contract spec is ambiguous.

| # | Severity | Defect | Evidence |
| --- | --- | --- | --- |
| D1 | MAJOR | `mention_rate` has 3 divergent denominators: (a) contract spec = filtered non-brand responses; (b) admin by_engine = all queries; (c) prompts DTO = `mention_denominator`. | `contracts/definitions.py:36` vs `queries/analytics.py:217` vs `_topic_analysis_dto.py:100` |
| D2 | STRUCTURAL | `success_rate` defined only at PROMPTS layer; no rollup to TOPICS, no definition at QUERIES (status-per-row), inconsistent at ATTEMPTS (per-account outcome). | `_topic_analysis_dto.py:98`; absence elsewhere |
| D3 | MAJOR | `citation_share` denominator redefined twice in May 2026; consumer values jumped 100% → 23.9% post-#1237. Contract still uses ambiguous "eligible brand mentions/responses" wording. | PRs #1234, #1235, #1237; `contracts/definitions.py:60-61` |
| D4 | STRUCTURAL | #1236 inserted 9 数据安全 brands; no aggregation rows exist for them; UI renders nulls/zeros indistinguishably from "actually zero". | `2026_05_18_0003_backfill_data_security_brands.py:54` |
| D5 | STRUCTURAL | `attempt_count` exists only at QUERIES layer; no rollup rule to PROMPTS or TOPICS. Any parent-level "avg attempts" is ad-hoc. | `_topic_analysis_dto.py:155` |
| D6 | STRUCTURAL | `citation_rate` denominator in contract spec = "eligible brand mentions/responses" (mentions OR responses?). Implementations interpret inconsistently. | `contracts/definitions.py:60-61` |
| **D7** | **CRITICAL** | Same handler mixes INNER and LEFT joins. `by_topic` uses INNER JOIN `queries → prompts → topics` (silently drops queries with NULL `prompt_id` or `topic_id`); `by_engine`, `daily_trend` use LEFT JOIN. Sum over engines ≠ sum over topics by construction. | `queries/analytics.py:356-363` (INNER) vs `queries/analytics.py:222-225` (LEFT) |
| **D8** | **CRITICAL** | Status enum incoherent across layers: topics `{draft, active, expired, rejected}`; prompts (no CHECK, ALTER-added); queries `{queued, running, done, failed, pending, unqueued}` (lowered at read); query_attempts `{success, completed (synonym), failed}`. No single source of truth. | `2026_05_04_0001_legacy_sql_into_alembic.py:223-224`; `2026_05_06_0002_admin_console_consolidation.py:498`; `queries/analytics.py:188`; `vm-backfill-query-attempts.yml:85` |
| **D9** | **CRITICAL** | `by_status` aggregator enumerates only `{done, failed, pending, running}`. Queries with `queued` or `unqueued` are silently dropped from the bucket. Page totals will not match `COUNT(*)`. | `queries/analytics.py:199-203` |
| D10 | STRUCTURAL | Alembic 2026_05_06_0002 §D cascade-deletes queries outside `{chatgpt, doubao, deepseek, gemini}` plus their downstream rows. Historical comparison is irreversible. | `2026_05_06_0002_admin_console_consolidation.py:556-578` |
| **D11** | **CRITICAL** | `total_analyzed` uses two-level INNER JOIN `queries → llm_responses → response_analyses`, dropping queries with missing response or analysis. If a UI computes `analyzed_rate = total_analyzed / total_queries`, the rate is biased high. | `queries/analytics.py:149-159` |
| D12 | MAJOR | `position_distribution` INNER-joins `brand_mentions` and groups by `CASE position_rank`; rows with NULL `position_rank` silently excluded (not labelled `unranked`). | `queries/analytics.py:421-436` |
| **D13** | **CRITICAL** | The canonical aggregate `geo_score_daily` has **zero writers in the entire repository** (`grep -rn "INSERT INTO geo_score_daily"` → no hits; ORM `session.add(GeoScoreDaily(...))` → no hits). All 30+ read sites depend on a table whose writer must live outside this codebase (or was removed with `admin_console/`). `definitions.py:148-157` self-admits "Treat geo_score_daily ratio values as formula-pending until analyzer/data PRs are patched." | `definitions.py:24`, `_charts_service.py:732`, `_metrics_service.py:230`; absence of any writer |

---

## 2. Phase B — Live Evidence (PENDING WORKFLOW DISPATCH)

Per `AGENTS.md ### Evidence-First Debugging` Hard Rule 1: every defect above must have at least one (DB row + API JSON) pair before the corresponding contract entry in §3 is treated as final.

### 2.1 Required probes per defect

| Defect | Surface to probe | What to compare |
| --- | --- | --- |
| D1 | `GET /admin/queries/analytics?brand_id=<B>` + `GET /api/v1/projects/<P>/analysis/topics/<T>/prompts` for the same date window | The two `mention_rate` values for the same brand×topic — they should differ if D1 is real |
| D7 | Same `GET /admin/queries/analytics?brand_id=<B>` response | `sum(by_engine[*].queries)` vs `sum(by_topic[*].queries)` — divergence proves INNER-JOIN drop |
| D8 | `SELECT DISTINCT status FROM queries WHERE brand_id=<B>`; same for `topics`, `prompts`, `query_attempts.outcome` | Set difference across the four enum lists |
| D9 | `SELECT LOWER(status), COUNT(*) FROM queries WHERE brand_id=<B> GROUP BY LOWER(status)` vs same endpoint's `by_status` dict | Any status the DB returns but the dict doesn't show proves D9 |
| D11 | `SELECT COUNT(*) FROM queries WHERE brand_id=<B>` vs same endpoint's `total_analyzed` divided by `total_queries` | If `total_analyzed < total_queries` substantially, D11 is real |
| D13 | `SELECT COUNT(*), MAX(date), MAX(updated_at) FROM geo_score_daily WHERE brand_id=<B>` for the 9 new 数据安全 brands and for one well-aggregated brand | Empty / stale rows for the new brands prove D13 |

### 2.2 Dispatch command

This branch cannot trigger workflows from chat (no `gh` CLI, no MCP workflow_dispatch tool). The AI Lead or a CI operator should dispatch the existing `App Analytics Readonly Evidence` workflow manually with these inputs:

```text
project_id           = 95d43022-a5c8-5944-b6d6-34b29faa18b5   # bestCoffer (workflow default)
brand_id             = 12
competitor_brand_ids = 2
date_from            = 2026-04-24
date_to              = 2026-05-18                              # extend to today
base_url             = http://116.62.36.173
```

Existing probes in `backend/scripts/app_analytics_readonly_evidence.py` already cover most of §2.1 (in particular the `geo_score_daily` cross-project sanity at line 338 and the response_analyses geo_score distribution at line 306 — both added by #1235). If §2.1 reveals a gap, add probes to that script in a separate PR.

Workflow artifacts land in `$RUNNER_TEMP`:

- `app_analytics_readonly_evidence_db.log` — DB SELECT output
- `app_analytics_readonly_evidence_api.jsonl` — authenticated API readback

### 2.3 Evidence ledger (TO BE FILLED AFTER DISPATCH)

After the workflow run, paste the relevant snippets here. One row per defect. **A defect without an evidence row cannot graduate to §3.**

| Defect | DB readback (paste row) | API readback (paste JSON) | Divergence observed |
| --- | --- | --- | --- |
| D1 | _pending_ | _pending_ | _pending_ |
| D7 | _pending_ | _pending_ | _pending_ |
| D8 | _pending_ | _pending_ | _pending_ |
| D9 | _pending_ | _pending_ | _pending_ |
| D11 | _pending_ | _pending_ | _pending_ |
| D13 | _pending_ | _pending_ | _pending_ |

Defects D2/D5/D6/D10/D12 are structural / archival — their evidence is in the migration history and the absence of code (see §1.3). They will be cited by file:line in the issues without a fresh DB probe.

---

## 3. Phase C — Draft Unified Contract (CONDITIONAL ON §2.3)

This section is a **draft**. Each entry below carries an `evidence-needed: <defect>` note when its finalization depends on a §2.3 row.

### 3.1 Canonical metric definitions

Each metric has exactly one definition. Surfaces compute the metric the same way or relabel it.

**`mention_rate`** (evidence-needed: D1)

- Numerator: number of `llm_responses` where the target brand is mentioned (`EXISTS (SELECT 1 FROM brand_mentions bm WHERE bm.response_id = r.id AND bm.brand_id = q.brand_id)`).
- Denominator: number of `llm_responses` that are *eligible* — i.e., the response is `analysis_status='done'` and the response's response_analyses row indicates the query was not classified as the brand's own promotional response. (Concrete eligibility predicate to be finalized after §2.3 confirms the contract spec's intent.)
- Time grain: `llm_responses.collected_at::date`.
- NULL handling: a query with no response is **excluded from both numerator and denominator** (it cannot be mentioned in a response that does not exist).
- Allowed surfaces: TopicsPage `by_topic` panel; PromptMatrix per-prompt row; Brand overview KPI card.
- Forbidden: surfaces that compute `mention_rate` by dividing by `COUNT(DISTINCT queries.id)` directly — those compute a different quantity ("mentions per query attempted") and must be relabelled `mention_rate_per_query` or removed.

**`success_rate`** (evidence-needed: D2)

- Defined at: QUERIES layer only.
  - Numerator: `COUNT(DISTINCT q.id)` where `LOWER(q.status) IN ('done','success','completed')`.
  - Denominator: `COUNT(DISTINCT q.id)` where `LOWER(q.status) NOT IN ('queued','unqueued','running')` — i.e., terminal queries only.
- Rollup to PROMPTS: `sum(query_success_num) / sum(query_terminal_denom)` (sum-of-num / sum-of-denom).
- Rollup to TOPICS: same rule, one further hop.
- ATTEMPTS-layer `outcome` is **renamed** to `attempt_success_rate` to avoid collision with QUERIES `success_rate`.

**`citation_rate`** (evidence-needed: D3, D6)

- Numerator: distinct `llm_responses.id` that have at least one row in `citation_sources` whose attributed brand is the target brand.
- Denominator: distinct `llm_responses.id` that are eligible (same eligibility predicate as `mention_rate`).
- The brand-overview `citation_share` is a **different metric** that uses window-total `COUNT(citation_sources.id)` as numerator; it must be renamed `citation_share` everywhere (never displayed as `citation_rate`) and the contract spec at `contracts/definitions.py:60-61` updated to remove the ambiguous "mentions/responses" slash.

**`attempt_count`** (evidence-needed: D5)

- Defined at: QUERIES layer.
  - Value: `COUNT(*) FROM query_attempts WHERE query_id = q.id`.
- Rollup to PROMPTS: `SUM(attempt_count)` (NOT average) per prompt; expose as `total_attempts_per_prompt`.
- Rollup to TOPICS: `SUM(attempt_count)` per topic; expose as `total_attempts_per_topic`.
- No parent layer exposes `attempt_count` as an unqualified field; the renamed forms above are mandatory.

**`coverage_rate`** (evidence-needed: D4, D10)

- TOPICS layer: defined as `min(1.0, len(active_topics_for_brand) / target_topic_count_per_brand)` where `target_topic_count_per_brand` is the configured PRD value (currently `max_per_brand`). This is acceptable.
- PROMPTS layer: defined as `prompt_count_per_topic`-bucketed status (`covered / gap / partial / risk`). Status thresholds must be moved out of `prompt_matrix/db.py` into a config and reused by any other surface that wants the same buckets.
- "No data" must be distinguishable from "0": if `geo_score_daily` has no row for a (brand, date), the API must return `formula_status: no_evidence` instead of `value: 0`.

**`status` enum (D8)** — see §3.3.

### 3.2 Rollup rules

Only two patterns are allowed. Anything else must be approved via PRD-CHANGE.

1. **Default: `sum-of-num / sum-of-denom`.** A parent-level rate is the sum of all child numerators divided by the sum of all child denominators. This is correct under any 1:M cardinality and matches what `_charts_service.py` does when grouping by date.
2. **Explicit weighted average.** When the metric is inherently per-row (e.g., `avg_geo_score`, `avg_position_rank`, `avg_sentiment`), the parent layer averages with explicit weights (default weight = 1; per-response weight permitted if documented).

Anti-patterns (forbidden):

- `AVG(child_rate)` over a 1:M relation without weights (gives equal weight to small and large children — wrong by construction).
- `COUNT(DISTINCT q.id)` as a denominator for a "response-level" rate (gives a different quantity than the response-level denominator).

### 3.3 Status enum unification (D8)

The four current enums are reduced to two:

**Production lifecycle (`topics`, `prompts`):** `{draft, active, archived}`. `expired` becomes `archived`; `rejected` becomes `archived` with a `rejection_reason`.

**Execution state (`queries`, attempts):** `{queued, running, done, failed}`. `pending` → `queued`. `unqueued` → `draft` (production state, not execution). `success` and `completed` (at `query_attempts.outcome`) → `done`.

All enums become DB-level CHECK constraints in a forward-only migration with a backfill. The `by_status` aggregator must be replaced with `unnest` of the canonical enum so unknown values cause a CI failure rather than a silent drop (D9).

### 3.4 Divergence list (drives Phase D issues)

These are the implementations that must change once the contract is signed off. Each becomes one issue.

| Defect | File:line to change | Direction |
| --- | --- | --- |
| D1 | `queries/analytics.py:215-217`, `:280-281` | Replace `COUNT(DISTINCT q.id)` denominator with eligibility predicate matching `definitions.py:36`. Or rename the output field `mention_rate_per_query` and add a separate `mention_rate` that uses the contract denominator. |
| D7 | `queries/analytics.py:357-358` | Convert `JOIN prompts ... JOIN topics` to `LEFT JOIN`, group queries with NULL prompt/topic under a synthetic bucket `"(unassigned)"`. |
| D8 | `2026_05_*` migrations + new alembic | Add CHECK constraints per §3.3; backfill normalization. |
| D9 | `queries/analytics.py:199-203` | Initialize `by_status` from the canonical enum; raise / log when DB returns a value outside it. |
| D11 | `queries/analytics.py:149-160` | Change to LEFT JOIN; expose `analyzed_rate = total_analyzed / total_queries` as a labelled rate, not just a raw count. |
| D12 | `queries/analytics.py:421-436` | Add `unranked` bucket for NULL `position_rank`. |
| D13 | New module under `backend/app/admin/analyzer/` | Write the canonical `geo_score_daily` writer (probably a periodic Celery task) so the table is no longer a read-only ghost. **Highest priority.** |
| D3, D6 | `contracts/definitions.py:54-64` | Disambiguate denominators per §3.1 `citation_rate` and `citation_share`. |
| D4 | New issue for backfill of historical aggregations for the 9 数据安全 brands | Until D13's writer is in place, these brands' aggregations must come from a one-off backfill. |
| D10 | Documentation only | Document the cascade-delete in `docs/DATA_MODEL.md` so historical analysis tools know the cutoff. |
| D2, D5 | DTOs in `_topic_analysis_dto.py` + service layer | Add the rollup helpers per §3.1 + §3.2. |

### 3.5 Surface allowlist (after Phase D)

A surface is **not allowed** to invent its own formula. The allowed mapping after Phase D:

| Surface | Allowed metrics |
| --- | --- |
| TopicsPage `QueryActivityCard` | `mention_rate`, `avg_sentiment`, `avg_geo_score`, `avg_position_rank`, plus the labelled bucket counts (`by_status`, `position_distribution` with `unranked`, `by_engine`, `by_topic`) |
| PromptMatrix rows | `prompt_count`, `coverage_status` (bucket) |
| QueryPool admin | `attempt_count`, query-row `status`, response-row `analysis_status` |
| DashboardPage brand-overview KPIs | `citation_share` (contract spec), `sov`, `mention_rate`, `avg_sentiment`, `avg_geo_score` — all sourced from `geo_score_daily` post-D13 |
| Brand competitor panel | Same as Brand-overview, restricted to the competitor set |
| DiagnosticsPage | `formula_status`, `missing_inputs` (already correct) |

---

## 4. Open questions for the AI Lead

These are questions the audit could not answer without a decision; they block §3 finalization.

1. **D13 fix path.** The simplest fix is to write a Celery task that periodically aggregates `geo_score_daily` from `brand_mentions` / `response_analyses`. Alternative: declare `geo_score_daily` deprecated and route all aggregate reads through a live SQL view over raw tables. Which path?
2. **D1 disambiguation.** Three implementations of `mention_rate` exist. The contract spec at `definitions.py:36` is one — but is the PRD intent "rate per response" (current spec) or "rate per query attempt"? They are different business measures.
3. **`citation_share` vs `citation_rate` naming.** Frontend may currently display "引用份额" pointing at either of the two formulas after #1237. Confirm which one is the user-facing 引用份额; the other gets a new label.
4. **Time grain for terminal-query denominator (D8 / `success_rate`).** Currently the denominator depends on whether `queued`/`unqueued` queries exist at the time of read. Should the denominator be fixed at the time the query was created (so old reads are reproducible) or be the live value? Reproducibility means `success_rate` for a past date stops changing.

---

## 5. References

- `AGENTS.md` — primary contract for this work, especially `### Evidence-First Debugging`, `### Evidence-First Shipping`, `### Orchestrator And Subagent Discipline`, and `## Enforcement`.
- `docs/APP_ANALYTICS_READONLY_EVIDENCE.md` — runbook for the workflow used in §2.2.
- `docs/PRD_APP_ANALYTICS_CORRECTION.md` (cited by the read-only evidence runbook as source of truth).
- PRs referenced: #1207, #1214, #1217, #1225, #1230, #1233, #1234, #1235, #1236, #1237.
