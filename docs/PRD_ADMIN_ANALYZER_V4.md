# PRD: Admin Analyzer v4 Contract

Status: P0 contract stabilization for Epic #771 and task #780.
Owner: ai-lead-agent.
Date: 2026-05-13.

This document is the requirement source for the Admin Attempts analyzer trigger
work. It stabilizes the analyzer v4 output contract, persistence boundaries,
App chart consumption rules, and release verification expectations before
Worker Agents change implementation files.

The current analyzer implementation is not considered complete by default.
Implementation work must begin with an audit of existing prompt, parser,
validator, persistence, idempotency, and aggregation behavior. Workers may reuse
existing pieces only after proving they satisfy the requirements below.

## Scope

Included:

- Admin Attempts analyzer visibility and manual trigger semantics.
- Single-response and batch-response analyze/reanalyze contract.
- Analyzer v4 one-pass response analysis output package.
- First-class fact persistence, run history, evidence, quality flags, relation
  facts, and citation/fact links.
- App chart metric-readiness boundary and aggregation refresh contract.
- Operator-visible audit, errors, task/run IDs, skipped counts, caps, partial
  state, deployed SHA, and online Playwright verification expectations.

Excluded:

- Frontend implementation details beyond required state and copy contract.
- Backend route implementation details beyond request/response semantics.
- Database migration shape beyond logical persistence requirements.
- Direct KG approval. Analyzer facts may feed candidate paths, but analyzer
  output must not silently approve canonical KG relations.

## Requirement Map

| ID | Requirement | Primary owners |
| --- | --- | --- |
| `PRD-ADM-ANALYZER-001` | Admin Attempts shows analyzer status and result summary. | #779, #782, #784 |
| `PRD-ADM-ANALYZER-002` | Single and batch analyze support eligible/skipped/already_done/cap semantics. | #779, #782, #784 |
| `PRD-ADM-ANALYZER-003` | Analyzer v4 produces one response-level package for `analysis_meta`, `entities`, `mentions`, `sentiment_drivers`, `product_features`, `relations`, `citations`, and `quality_flags`. | #781 |
| `PRD-ADM-ANALYZER-004` | Analyzer persists first-class facts, run history, evidence, quality flags, relation facts, and citation/fact links. | #781 |
| `PRD-ADM-ANALYZER-005` | App charts consume metric-ready facts and aggregations; they must not chart raw analyzer JSON or raw names directly. | #781, #783 |
| `PRD-ADM-ANALYZER-006` | Analyzer success/partial states trigger aggregation refresh and expose metric-readiness state. | #782, #783 |
| `PRD-ADM-ANALYZER-007` | Admin exposes audit records, errors, task IDs, run IDs, batch caps, skipped counts, and partial visibility. | #779, #782, #784 |
| `PRD-ADM-ANALYZER-008` | CI/CD, deployed SHA, and online Playwright verification are required before Epic completion. | #786, #787 |

## PRD-ADM-ANALYZER-001: Attempts Status And Summary

Admin Attempts must show analyzer state for each row that has an analyzable
response.

Required row/detail fields:

- `response_id`
- `analysis_status`: one of `missing`, `queued`, `running`, `done`, `partial`,
  `failed`, `stale`, or `not_eligible`
- `analysis_id`
- `analyzer_run_id`
- `task_id`
- `analysis_schema_version`
- `analyzed_at`
- `analyzer_model`
- `analysis_error_code`
- `analysis_error_message`
- `analysis_summary`

`analysis_summary` is operator-facing. It may include counts and short labels
such as brand mentions, product mentions, citation count, relation count,
positive/negative/neutral driver counts, and quality flag count. It must not
display raw prompt text, raw schema dumps, or unreviewed internal JSON as UI
copy.

Rows with no response text must be `not_eligible` and must expose a reason such
as `no_response_text`. They must not show an enabled analyze action.

## PRD-ADM-ANALYZER-002: Single And Batch Analyze Semantics

Analyzer trigger semantics are response-scoped, not failed-attempt-scoped.
Failed attempts with no response must be skipped and should direct the operator
to retry collection first.

### Single response analyze/reanalyze

Single-response submit must accept a `response_id`, a `mode`, and an operator
`reason`.

Supported modes:

- `missing_or_failed_only`: default. Enqueue only when no valid current
  analysis exists, the previous run failed, or the previous run is stale.
- `reanalyze_current`: explicit operator request to replace the current
  analysis with a new current run while retaining run history.

Required submit response:

- `response_id`
- `analysis_status`
- `analyzer_run_id`
- `task_id`
- `accepted`
- `skipped_reason`

### Batch dry-run

Batch analyze must support selected response IDs and current Attempts filter
scope. Batch submit must be preceded by a dry-run preview.

Dry-run response fields:

- `dry_run_id`
- `requested_count`
- `eligible_count`
- `already_done_count`
- `skipped_no_response_count`
- `skipped_invalid_count`
- `skipped_failed_attempt_without_response_count`
- `cap_limit`
- `will_enqueue_count`
- `cap_truncated`
- `mode`
- `eligible_response_ids_preview`
- `skipped_reasons`

Default batch mode is `missing_or_failed_only`. Including already analyzed
responses requires explicit `reanalyze_current` or `reanalyze_all` semantics in
the API and UI.

### Batch cap

The server must enforce a configurable cap. Unless a different server
configuration is documented in the implementing PR, the default cap is 200
responses per batch submit.

When `eligible_count` exceeds `cap_limit`, dry-run must set
`cap_truncated=true`, `will_enqueue_count=cap_limit`, and show the operator that
only the capped deterministic selection will be submitted. The deterministic
selection must be stable for a dry-run, using the Attempts filter ordering or
explicit selected response order plus `response_id` as a tie-breaker.

Batch submit must use `dry_run_id` or an equivalent immutable selection token so
the submitted set matches the preview. It must return:

- `batch_job_id`
- `accepted_count`
- `skipped_count`
- `already_done_count`
- `cap_limit`
- `cap_truncated`
- `task_ids`
- `status_url`

## PRD-ADM-ANALYZER-003: Analyzer v4 Output Package

Analyzer v4 is a one-pass response-level analysis package. It should analyze
brand/product/entity mentions, sentiment drivers, product features, relations,
citations, and quality flags in a single LLM call followed by deterministic
validation and normalization.

The persisted raw package must use this top-level shape:

```json
{
  "analysis_meta": {},
  "entities": [],
  "mentions": [],
  "sentiment_drivers": [],
  "product_features": [],
  "relations": [],
  "citations": [],
  "quality_flags": []
}
```

### `analysis_meta`

Required fields:

- `schema_version`: must be `analyzer_v4`.
- `language`: `zh`, `en`, or `mixed`.
- `response_quality`: `ok`, `partial`, `empty`, or `invalid`.
- `model`
- `prompt_version`
- `input_response_id`
- `input_query_id`
- `created_at`
- `validator_status`: `passed`, `passed_with_flags`, or `failed`.
- `validator_errors`

### `entities`

Each entity is a response-scoped extraction, not automatically a canonical KG
entity.

Required fields:

- `entity_key`: stable within the package.
- `entity_type`: `brand`, `product`, `attribute`, `need`, `scenario`,
  `category`, `ingredient`, `channel`, `price_tier`, or `other`.
- `raw_name`
- `canonical_id`: nullable.
- `canonical_name`: nullable.
- `canonicalization_status`: `matched`, `suggested`, `unresolved`, or
  `not_applicable`.
- `evidence_quote`
- `confidence`
- `quality_flags`

### `mentions`

Mentions are observable references in the response.

Required fields:

- `mention_key`
- `entity_key`
- `response_id`
- `raw_text`
- `normalized_text`
- `mention_type`: `brand`, `product`, `attribute`, `need`, `scenario`,
  `citation`, or `other`.
- `position`: `top`, `middle`, `tail`, or `unknown`.
- `sentiment_label`: `positive`, `negative`, `neutral`, `mixed`, or `unknown`.
- `sentiment_score`: nullable numeric score in a documented range.
- `evidence_quote`
- `confidence`
- `quality_flags`

### `sentiment_drivers`

Sentiment drivers explain why a mention has a sentiment label. They must be
evidence-bound.

Required fields:

- `driver_key`
- `mention_key`
- `target_entity_key`
- `sentiment_label`: `positive`, `negative`, `neutral`, `mixed`, or `unknown`.
- `driver_type`: `benefit`, `drawback`, `comparison`, `recommendation`,
  `warning`, `uncertainty`, `price`, `availability`, `quality`, or `other`.
- `driver_summary`
- `evidence_quote`
- `confidence`
- `quality_flags`

Sentiment definitions:

- `positive`: the response expresses favorable evaluation, recommendation,
  preference, benefit, strength, suitability, or improvement tied to the target
  entity.
- `negative`: the response expresses unfavorable evaluation, warning,
  limitation, drawback, exclusion, poor fit, risk, or weakness tied to the
  target entity.
- `neutral`: the response mentions or describes the target entity without a
  directional evaluation.
- `mixed`: the response includes both positive and negative evidence for the
  same target entity or driver scope.
- `unknown`: the model cannot determine sentiment from the response evidence.

Neutral and unknown are not interchangeable. `neutral` requires descriptive
evidence. `unknown` requires a quality flag explaining why sentiment was not
determinable.

### `product_features`

Required fields:

- `feature_key`
- `product_entity_key`
- `brand_entity_key`: nullable.
- `feature_type`: `ingredient`, `function`, `benefit`, `texture`, `price`,
  `scenario`, `audience`, `packaging`, `availability`, or `other`.
- `feature_name`
- `feature_value`: nullable.
- `evidence_quote`
- `confidence`
- `quality_flags`

Products should be linked to brands when evidence supports the relationship.
Unresolved product-brand ownership is allowed only with `brand_entity_key=null`
and a quality flag such as `brand_unresolved`.

### `relations`

Relations are response-scoped facts or candidates. They are not direct approved
KG writes.

Required fields:

- `relation_key`
- `subject_entity_key`
- `relation_type`: `recommended_for`, `compared_with`, `has_attribute`,
  `addresses_need`, `avoid_for`, `belongs_to_brand`, `substitute_for`,
  `complements`, or `other`.
- `object_entity_key`
- `direction`: `directed`, `undirected`, or `unknown`.
- `evidence_quote`
- `confidence`
- `quality_flags`

Every relation must be linked to response evidence. Relations without enough
evidence must be dropped or persisted with an explicit quality flag and must not
feed approved KG tables.

### `citations`

Required fields:

- `citation_key`
- `url`: nullable when the response references a source without a URL.
- `domain`: nullable.
- `title`: nullable.
- `source_type`: `official`, `commerce`, `media`, `ugc`, `social`,
  `knowledge_base`, `unknown`, or `other`.
- `attribution_method`: `official_domain`, `co_occurrence`, `text_match`,
  `llm_inferred`, `unattributed`, or `not_applicable`.
- `mentioned_entity_keys`
- `linked_fact_keys`: mention, driver, feature, or relation keys supported by
  this citation.
- `evidence_quote`
- `confidence`
- `quality_flags`

Citation facts used in App metrics must link to specific facts through
`linked_fact_keys` or equivalent persisted citation/fact links. A standalone URL
list is not enough for citation share, authority, or provenance charts.

### `quality_flags`

Quality flags explain partial or suspect output.

Required fields:

- `flag_key`
- `severity`: `info`, `warning`, or `error`.
- `code`
- `message`
- `target_type`: `analysis`, `entity`, `mention`, `driver`, `feature`,
  `relation`, `citation`, or `aggregation`.
- `target_key`: nullable for analysis-level flags.
- `blocks_metric_readiness`: boolean.

Expected codes include:

- `empty_response`
- `invalid_json`
- `schema_validation_failed`
- `missing_evidence_quote`
- `brand_unresolved`
- `product_unresolved`
- `relation_unresolved`
- `citation_unlinked`
- `sentiment_unknown`
- `mixed_sentiment`
- `low_confidence`
- `partial_output`
- `canonicalization_conflict`

## PRD-ADM-ANALYZER-004: First-Class Persistence

The raw analyzer package is an audit artifact. Current product behavior and App
charts must read normalized first-class facts wherever first-class facts exist.

Required logical persistence:

- Analysis run history: one record per analyzer attempt with response ID,
  schema version, prompt version, model, task ID, batch job ID, status, start
  time, end time, error, validator summary, and operator trigger context.
- Current analysis pointer: one current analysis per response, retaining
  previous runs for history and audit.
- Current fact rows for mentions, sentiment drivers, product features,
  citations, and response-scoped relations.
- Response entities with canonicalization status.
- Citation/fact link rows connecting citations to mentions, drivers, features,
  and relations.
- Quality flag rows connected to the run and optional target fact.
- Full `raw_analysis_json` retention for replay/debug, not as the primary chart
  source.

If existing tables already satisfy a logical persistence requirement, Workers
should extend them rather than create duplicates. If existing tables cannot
represent a required first-class fact, the implementing issue must add or
document the necessary schema change with rollback notes.

Reanalysis must be idempotent for a response. It must not duplicate facts, leave
old current facts mixed with new current facts, or delete run history. A new
current run may replace current facts only after validation/persistence succeeds
or records a clear partial/failed state.

## PRD-ADM-ANALYZER-005: App Chart Fact Boundary

App charts must consume metric-ready facts and aggregation outputs. They must
not directly chart:

- `raw_analysis_json`
- raw LLM entity names
- unresolved raw brand/product names as canonical chart series
- prompt-only suggestions
- unlinked citations
- relation candidates that have no response evidence
- missing or partial analyzer output coerced to `0`, `100%`, or normal `ok`
  chart state

Allowed consumption layers:

1. Raw analyzer package: retained for debug, replay, and audit.
2. Normalized analyzer facts: entities, mentions, drivers, product features,
   citations, relations, quality flags, and links.
3. Metric-ready facts: canonicalized, evidence-bound facts with denominator
   context, freshness, quality state, and unresolved/missing reasons.
4. Aggregations: daily/topic/product/competitor/citation/geo rollups.
5. Chart DTOs: App API responses with `formula_status`, `missing_inputs`,
   `evidence_counts`, and `source_provenance`.

If a chart-critical input is missing, the chart state must be `partial`,
`empty`, or `error` with a visible reason. The chart must not invent an `ok`
state from available-but-insufficient facts.

## PRD-ADM-ANALYZER-006: Aggregation Refresh And Metric Readiness

Analyzer persistence must emit or record enough state for aggregation refresh.
Aggregation refresh may be synchronous, queued, or scheduled, but the contract
must expose status.

Required aggregation refresh state:

- `response_id`
- `analysis_id`
- `analyzer_run_id`
- `schema_version`
- `fact_version` or equivalent freshness token
- `aggregation_refresh_status`: `not_required`, `queued`, `running`, `done`,
  `partial`, or `failed`
- `aggregation_refresh_task_id`
- `aggregation_refreshed_at`
- `metric_readiness_status`: `ready`, `partial`, `empty`, or `blocked`
- `metric_readiness_reasons`

Metric readiness must consider:

- brand mention facts
- competitor/unresolved brand facts
- sentiment driver evidence
- citation/fact links
- product feature facts
- response-scoped relation facts
- denominator context from query/response metadata
- quality flags that block metrics

SoV and mention-rate denominators come from eligible query/response metadata,
not from LLM output alone.

## PRD-ADM-ANALYZER-007: Operator Audit And Error Visibility

Every manual analyzer action must be auditable.

Audit records must include:

- operator
- action type: single analyze, single reanalyze, batch dry-run, batch submit,
  batch cancel when supported
- response IDs or immutable filter/scope descriptor
- mode
- reason
- requested count
- eligible count
- accepted count
- skipped counts by reason
- cap limit and truncation state
- task IDs
- analyzer run IDs
- batch job ID
- result status
- error code/message

Admin-visible errors should be operator-readable. Raw stack traces may be linked
for diagnostics when authorized, but the UI must show a concise reason and task
or run ID.

Partial success must be explicit. A batch with some failed or skipped rows must
not be shown as simple success.

## PRD-ADM-ANALYZER-008: Release And Online Verification

Worker PRs must start as draft PRs and use `Refs #<issue>` until AI Lead accepts
merge readiness.

Required verification before Epic #771 completion:

- #781 analyzer v4 validator/persistence tests pass.
- #782 Admin API tests for single/batch/dry-run/status/audit paths pass.
- #783 aggregation and no-fallback chart contract tests pass.
- #784 Admin UI integration smoke/build passes.
- Review Agent confirms scope, PRD coverage, idempotency, no raw JSON charting,
  and no direct approved KG writes from analyzer output.
- Release/CI Agent identifies the final deployed `main` SHA after merge.
- QA/E2E Agent runs online Playwright against `http://116.62.36.173/`.

Minimum online Playwright evidence:

- Admin login/session reaches the Attempts page.
- Attempts row with analyzable response shows analyzer status.
- Attempt detail shows response text and analyzer summary/status.
- Single analyze or reanalyze returns task/run ID and reaches a terminal or
  observable queued/running state.
- Batch dry-run shows eligible, skipped, already_done, cap, and preview counts.
- Batch submit shows batch job ID and progress/terminal counters.
- Failed/no-response attempt cannot be submitted and shows reason.
- App chart diagnostics show metric readiness or missing inputs after analyzer
  facts/aggregations are refreshed.

If live mutation is unsafe in production, QA must use a controlled row approved
by AI Lead or document the exact not-run reason and verify every read-only state
available.

## Downstream Handoff

| Issue | Agent | Contract slice | Handoff |
| --- | --- | --- | --- |
| #779 | `frontend-visualization-agent` | `PRD-ADM-ANALYZER-001`, `PRD-ADM-ANALYZER-002`, `PRD-ADM-ANALYZER-007` | Visualize states, drawer, single trigger, batch dry-run/submit preview, skipped/cap/partial states; do not expose prompt/schema internals. |
| #781 | `pipeline-data-agent` | `PRD-ADM-ANALYZER-003`, `PRD-ADM-ANALYZER-004`, `PRD-ADM-ANALYZER-005` | Audit current analyzer first, then implement one-pass package, validator, idempotent persistence, entities, relation facts, quality flags, and citation/fact links. |
| #782 | `backend-api-agent` | `PRD-ADM-ANALYZER-001`, `PRD-ADM-ANALYZER-002`, `PRD-ADM-ANALYZER-006`, `PRD-ADM-ANALYZER-007` | Expose Attempts status fields, single/batch dry-run/submit/status APIs, caps, task/run IDs, audit, and aggregation refresh status. |
| #783 | `pipeline-data-agent` | `PRD-ADM-ANALYZER-005`, `PRD-ADM-ANALYZER-006`, `PRD-ADM-ANALYZER-008` | Turn first-class analyzer facts into metric-ready App chart facts and aggregations; no raw JSON or fake fallback values. |
| #784 | `frontend-integration-agent` | `PRD-ADM-ANALYZER-001`, `PRD-ADM-ANALYZER-002`, `PRD-ADM-ANALYZER-007` | Replace visualization state with real APIs, poll task/batch status, surface skipped/cap/partial/error states, and keep copy operator-oriented. |
