# PRD: App Analytics Truth Contract Correction

Status: P0 correction for Epic #481.
Owner: ai-lead-agent.
Date: 2026-05-12.

This PRD correction supersedes the earlier App analytics mapping in #481/#483
where it conflicts with the rules below. The prior mapping was useful as a
draft, but it was not strict enough to prevent misleading App values. The App
must prefer an explicit incomplete state over any value that is produced by
silent fallback, mock truth, proxy formulas, or target-only data.

## Problem Statement

The current App Brand Mode can show values such as 100% mention rate, 100% SoV,
0% citation share, one-topic heatmaps, empty PANO trends, and sentiment charts
that look complete while the underlying evidence is incomplete or calculated
with the wrong denominator. That is worse than an empty chart because users and
operators cannot tell where the data pipeline is broken.

The corrected goal is not just to fill charts. The goal is to expose trustworthy
metrics from Admin-collected response data, and to make missing upstream data
visible as `partial`, `empty`, or `error` with evidence counts and missing
inputs.

## Global Rule: No Metric Fallback

Requirement ID: `PRD-APP-ANALYTICS-000`.

Metric calculation must not fallback. For App analytics metrics and chart data:

- Do not use frontend mock arrays, sample data, or existing visualization data as
  live metric truth.
- Do not use one metric as a proxy for another metric. Examples: SoV cannot
  stand in for mention rate; citation rate cannot stand in for citation share;
  a GEO/PANO score cannot stand in for missing component series.
- Do not synthesize competitor rows, topic rows, trend deltas, or "Others" rows
  from a single KPI card.
- Do not turn missing denominators into `0`, `1`, `100%`, rank `#1`, or a fake
  delta.
- Do not mark a chart `ok` only because at least one cell has a value.
- Do not silently collapse multi-brand, multi-topic, or multi-engine contracts
  to a one-brand or one-topic result.
- If upstream facts are incomplete, return `partial` or `empty` and include
  `state_reason`, `missing_inputs`, `evidence_counts`, and the relevant filter
  context.

Defensive display fallbacks for labels are allowed only when they cannot change
the metric value. Value computation, denominator selection, state selection, and
trend/delta generation have no fallback path.

## Required Data State

All App analytics endpoints that feed Brand Mode KPIs or charts must expose the
same state model:

- `ok`: formula inputs and denominators are complete enough for the metric.
- `partial`: some evidence exists, but at least one required upstream input is
  missing or below the acceptance threshold.
- `empty`: no eligible evidence exists for the selected project, brand, date
  range, engine, topic, or query filters.
- `error`: computation or dependency failure.

Every non-`ok` response must say why. Required metadata:

- `state_reason`
- `missing_inputs`
- `evidence_counts`
- `formula_status`
- selected `project_id`, `brand_id`, `date_range`, `engines`, and filters
- source tables or materialized views used by the calculation

No frontend page may override a non-`ok` backend state into a normal-looking
metric card or chart.

## Metric Contracts

### PRD-APP-ANALYTICS-001: Mention Rate

Mention rate answers: "Among eligible responses where a brand mention can be
observed, what share mentions the target brand?"

Required numerator:

- Distinct eligible response IDs where the target canonical brand is confirmed
  by analyzer extraction.

Required denominator:

- Distinct eligible response IDs for the selected project, date range, engine,
  topic/query filters, and visibility scope.
- The denominator must be built from collected responses and their prompt/query
  context, not from the set of already-mentioned target-brand responses.

Invalid outputs:

- `100%` because only target-mentioned rows survived aggregation.
- `0%` because analyzer rows are missing while collected responses exist.
- Any value where the denominator is replaced with target response count.

### PRD-APP-ANALYTICS-002: Share of Voice

SoV answers: "Within responses that mention any brand in the competitive set,
what share of brand mentions belongs to the target brand?"

Required upstream:

- Analyzer/LLM extraction must persist all mentioned brands in each response,
  including target brand, configured competitors, unconfigured competitors,
  abbreviations, aliases, and industry brands.
- Each mention needs response ID, canonical brand ID or unresolved brand name,
  mention count or occurrence evidence, confidence/provenance, position/rank,
  and prompt/query/topic context.

Required numerator:

- Target canonical brand mentions, or target-mentioned response count when the
  selected SoV variant is explicitly response-share.

Required denominator:

- All competitive-set brand mentions from the same response universe.
- Configured project competitors are the display/filter set. They are not the
  extraction universe.

Invalid outputs:

- `100%` when only the target brand was extracted.
- A donut/pie made from one overview KPI plus an invented `Others` row.
- `ok` state when competitor extraction is absent, unresolved, or below
  evidence threshold.

If competitor extraction is incomplete, SoV must be `partial` with
`missing_inputs` including `brand_mentions.competitive_set` or equivalent.

### PRD-APP-ANALYTICS-003: Citation Share and Citation Rate

Citation share and citation rate are different metrics.

Citation rate:

- Numerator: target-brand responses or mentions with at least one citation.
- Denominator: target-brand responses or mentions in the same eligible universe.

Citation share:

- Numerator: citation_sources rows attributed to target-brand brand_mentions
  in the time window.
- Denominator: ALL citation_sources rows in the same time window (regardless
  of brand attribution).

Rationale (revised 2026-05-18 per #1225): the original "competitive set"
denominator degenerated to target-only when LLM responses for a project did
not cite competitor official domains, producing a misleading 100%. The
revised denominator answers "what share of LLM citations point to the
target brand" rather than "what share of competitive-set citations". This
is a window-cumulative ratio, NOT a per-day comparison.

Official-domain share:

- Numerator: citations attributed to target official domains.
- Denominator: all citation references for the target brand or selected scope.

Invalid outputs:

- Showing citation share as `0%` only because a sparkline endpoint has no
  citation series.
- Labeling citation rate as citation share.
- Treating no citation extraction as a real zero.
- Computing citation share over a denominator scoped to target-mentioning
  responses only — that recovers the pre-#1225 100% degeneracy.

If citation extraction tables are empty while responses exist, return `partial`
or `empty` based on response evidence; never silently show `0%`.

### PRD-APP-ANALYTICS-004: Rank

Rank must be based on position evidence extracted from the response, and must
carry the denominator/sample count. A rank card cannot default to `#1` when
position evidence is absent. If there is no rank evidence, state is `partial` or
`empty`.

### PRD-APP-ANALYTICS-005: Sentiment

Sentiment must derive from analyzer output tied to brand mentions and response
evidence:

- `brand_mentions.sentiment`
- `brand_mentions.sentiment_score`
- `sentiment_drivers`
- source response quote or snippet
- prompt/query/topic context

Required App surfaces:

- sentiment KPI
- sentiment distribution by engine
- sentiment trend by engine
- topic attribution
- positive/negative drivers
- sample responses

Invalid outputs:

- Sentiment calculated from unrelated response-level averages without target
  brand evidence.
- Empty driver/sample lists with `ok` chart state.
- Normal-looking sentiment charts when analyzer sentiment rows are missing.

### PRD-APP-ANALYTICS-006: PANO/GEO Trend and Components

PANO/GEO trend requires daily series for the final score and its components.
The App may show a chart only when at least two date buckets are available for
the selected range, or when the UI explicitly presents a single-point state.

Required series:

- final PANO/GEO score
- visibility/mention component
- relevance/rank component
- sentiment component
- citation/authority component
- SoV or competitive visibility component when the view requires it

Invalid outputs:

- A blank chart with no state explanation.
- A trend inferred from one current KPI value.
- A hard-coded delta or direction.

### PRD-APP-ANALYTICS-007: Topics, Prompts, Queries, and Heatmaps

Topic charts must be traceable from Topic to Prompt to Query to Response.

Required evidence for App topic views:

- topic ID/name
- prompt ID/text
- query ID/text
- response IDs
- engine/date
- target brand mentions
- competitive brand mentions
- sentiment/citation/rank evidence where applicable

Brand x Topic heatmap acceptance:

- The heatmap must include the target brand and the selected competitive set.
- Missing cells must be explicit `null`/partial cells with sample counts, not
  removed rows.
- A heatmap with only one topic or only one brand cannot be `ok` for the
  competitive Brand Mode view unless the selected filters explicitly request
  that narrow scope.
- If upstream topic links are missing, return `partial` with
  `missing_inputs` such as `prompts.topic_id`, `queries.prompt_id`, or
  `topic_score_daily`.

### PRD-APP-ANALYTICS-008: Cross-Page Consistency

Overview, Visibility, Topics, Sentiment, Citations, Competitors, and Product
App pages must share one analytics contract for the same project, primary
brand, date range, engine, and filters.

The same metric cannot show different values across navigation tabs unless the
page displays a different selected filter. The response must include the filter
context that explains the difference.

Invalid outputs:

- Overview mention rate differs from Visibility mention rate with identical
  filters.
- Overview SoV differs from Competitors SoV with identical filters.
- A tab replaces a missing endpoint with local mock data.

### PRD-APP-ANALYTICS-009: Frontend Rendering Contract

Frontend cards and charts must render the backend state honestly:

- `ok`: show value/chart and evidence metadata in tooltip/details.
- `partial`: show partial state with missing inputs and keep the chart from
  looking complete.
- `empty`: show empty state with selected filters and next diagnostic hint.
- `error`: show error state with request ID when available.

Frontend must not compute live metric values from unrelated endpoints or local
mock truth. Derived display formatting is allowed only after the backend
provides a valid metric value and formula status.

### PRD-APP-ANALYTICS-010: QA and Release Gates

QA may not accept the App analytics work with a smoke check such as
`chartCount > 0`.

Required gates:

- Verify no metric calculation path contains silent fallback for live
  App analytics values.
- Verify KPI values have plausible numerator, denominator, formula status, and
  evidence counts.
- Verify SoV uses response-level competitive extraction and is not 100% unless
  evidence proves every competitive mention is the target brand.
- Verify citation share/rate labels and denominators are distinct.
- Verify Overview and sub-navigation pages return the same metric under the
  same filters.
- Verify Topics expose topic, prompt, query, and response evidence.
- Verify Brand x Topic heatmap has a real topic and brand matrix, or an
  explicit `partial` state.
- Verify PANO/GEO trend has a real time series or an explicit non-`ok` state.
- Verify sentiment has brand-linked sentiment evidence, drivers, and samples,
  or an explicit non-`ok` state.
- Run local Playwright and live Playwright against `http://116.62.36.173/`
  after deploy.

## Required Production Diagnostics Before Fixes

Before backend/pipeline/frontend implementation PRs are marked ready, the
Release/CI Agent must capture read-only live test-environment evidence for
the affected project/brand/date range:

- collected response count by engine/date
- analyzer run count and failed analyzer count
- brand mention rows by response and canonical/unresolved brand
- competitor mention coverage
- citation source rows and official-domain attribution rows
- sentiment and sentiment driver rows
- topic -> prompt -> query -> response linkage coverage
- daily score/materialized aggregate row counts
- API payload states for overview, metrics, competitors, topics, sentiment,
  citations, and PANO/GEO trend endpoints

If any of those are missing, implementation must target the missing upstream
layer instead of hiding the gap in App rendering.

## Agent Ownership

Frontend Visualization:

- Show corrected `ok/partial/empty/error` states for the existing Brand Mode
  App experience.
- Prototype user-facing partial states for no-fallback analytics.

Release/CI:

- Gather live test-environment evidence through GitHub Actions/server diagnostics.
- Do not guess from local state when live test-environment data is uncertain.

Pipeline/Data:

- Repair analyzer persistence and aggregation inputs for brand mentions,
  competitors, citations, sentiment drivers, topics/prompts/queries, and daily
  score facts.

Backend API:

- Enforce formula contracts, denominator correctness, evidence counts, and
  cross-page consistency.
- Remove calculation fallback paths for live App analytics metrics.

Frontend Integration:

- Remove mock/proxy truth from live App cards/charts.
- Render backend states honestly across overview and sub-navigation pages.

QA/E2E:

- Verify formulas, evidence counts, consistency, and live user-visible behavior.

Review:

- Block PRs that reintroduce silent fallback, fake zeros/100s, or chart smoke
  acceptance without formula evidence.
