# App Analytics Extraction Provenance Runbook

Scope: GitHub issues #532 and #563, Pipeline/Data Agent.

This runbook covers the no-fallback analyzer and aggregate inputs for
`docs/PRD_APP_ANALYTICS_CORRECTION.md`.

## Source Tables And Columns

- `llm_responses`: `id`, `query_id`, `raw_text`, `citations_json`, `analysis_status`,
  `collected_at`.
- `queries`: `id`, `prompt_id`, `brand_id`, `target_llm`, `query_text`.
- `prompts`: `id`, `topic_id`, `intent`, `language`, `text`.
- `topics`: `id`, `brand_id`, `category`, `text`.
- `brand_mentions`: `response_id`, `brand_id`, `brand_name`, `product_name`,
  `is_target`, `position_type`, `position_rank`, `sentiment`, `sentiment_score`,
  `context_snippet`, `mention_count`.
- `sentiment_drivers`: `mention_id`, `response_id`, `brand_name`, `driver_text`,
  `polarity`, `category`, `strength`, `source_quote`.
- `citation_sources`: `response_id`, `mention_id`, `url`, `domain`, `title`,
  `citation_index`, `source_type`.
- `response_analyses.raw_analysis_json`: `brand_mention_facts`, `citation_facts`,
  `metric_input_status`.
- `geo_score_daily`: `mention_rate`, `avg_sov`, `citation_rate`,
  `avg_sentiment_score`, `avg_visibility`, `avg_sentiment`, `avg_sov_score`,
  `avg_citation_score`, `avg_geo_score`.
- `topic_score_daily`: `brand_id`, `topic_id`, `mention_count`, `total_responses`,
  `mention_rate`, `avg_position_rank`, `avg_sentiment_score`, `avg_geo_score`.
- `product_score_daily`: `brand_id`, `product_name`, `mention_count`,
  `total_queries`, `mention_rate`, `avg_sentiment_score`, `win_rate`.

## Dry-Run Counters For Estee Lauder

Use #484 production diagnostics to capture exact values. Do not infer exact
production row counts from local data.

Expected healthy counter shape for the Estee Lauder project dataset:

- collected response count by day and engine is greater than zero for the
  selected date range.
- done analyzer count matches the collected response universe selected for
  aggregation, minus explicitly failed responses.
- `brand_mentions` has one or more rows per analyzed response when brands are
  present in the response text.
- SoV is complete only when `brand_mentions` includes target rows plus at least
  one non-target configured, unconfigured, or unresolved competitive mention in
  the same eligible universe.
- Canonical alias repair must scan the same response for configured
  competitive brands. `--competitive-brand-id` rows are written with canonical
  IDs when the brand exists; configured `competitors` names are written as
  name-only `brand_mentions.brand_id IS NULL` evidence when no canonical ID is
  available.
- `citation_sources.mention_id` is populated when citation title/domain,
  citation payload text, or unambiguous response citation-marker context can be
  attributed to a persisted brand mention. Ambiguous same-response citation
  context stays unresolved.
- If citation, sentiment, position, or complete PANO/GEO component evidence is
  unavailable, `response_analyses.raw_analysis_json.metric_input_status` must
  carry explicit `partial` or `empty` states and `missing_inputs`; do not infer
  missing evidence from zeros.
- `sentiment_drivers.source_quote` is populated for brand-linked sentiment
  drivers only when raw LLM sentiment extraction supplies driver text and source
  quote. Do not synthesize drivers from snippets alone.
- topic coverage is complete only when `llm_responses -> queries -> prompts ->
  topics` linkage exists.
- daily PANO/GEO component columns remain `NULL` for missing SoV, citation, or
  sentiment evidence instead of zero-filled values.

## Read-Only Diagnostic SQL

Replace the placeholders with #484-confirmed project, brand, and date filters.

```sql
SELECT q.target_llm, DATE(lr.collected_at) AS day, COUNT(*) AS collected
FROM llm_responses lr
JOIN queries q ON q.id = lr.query_id
WHERE q.brand_id = :brand_id
  AND lr.collected_at >= :start_at
  AND lr.collected_at < :end_at
GROUP BY q.target_llm, DATE(lr.collected_at)
ORDER BY day, q.target_llm;

SELECT bm.response_id,
       COUNT(*) AS mention_rows,
       COUNT(*) FILTER (WHERE bm.brand_id = :brand_id) AS target_mentions,
       COUNT(*) FILTER (WHERE bm.brand_id IS DISTINCT FROM :brand_id) AS non_target_mentions,
       COUNT(*) FILTER (WHERE bm.brand_id IS NULL) AS unresolved_mentions
FROM brand_mentions bm
JOIN llm_responses lr ON lr.id = bm.response_id
JOIN queries q ON q.id = lr.query_id
WHERE q.brand_id = :brand_id
  AND lr.collected_at >= :start_at
  AND lr.collected_at < :end_at
GROUP BY bm.response_id
ORDER BY bm.response_id;

SELECT COUNT(*) AS citations,
       COUNT(*) FILTER (WHERE mention_id IS NOT NULL) AS attributed_citations
FROM citation_sources cs
JOIN llm_responses lr ON lr.id = cs.response_id
JOIN queries q ON q.id = lr.query_id
WHERE q.brand_id = :brand_id
  AND lr.collected_at >= :start_at
  AND lr.collected_at < :end_at;

SELECT COUNT(*) AS drivers,
       COUNT(*) FILTER (WHERE NULLIF(TRIM(source_quote), '') IS NOT NULL) AS quoted_drivers
FROM sentiment_drivers sd
JOIN llm_responses lr ON lr.id = sd.response_id
JOIN queries q ON q.id = lr.query_id
WHERE q.brand_id = :brand_id
  AND lr.collected_at >= :start_at
  AND lr.collected_at < :end_at;

SELECT COUNT(*) AS responses,
       COUNT(*) FILTER (WHERE p.topic_id IS NOT NULL) AS responses_with_topic
FROM llm_responses lr
JOIN queries q ON q.id = lr.query_id
LEFT JOIN prompts p ON p.id = q.prompt_id
WHERE q.brand_id = :brand_id
  AND lr.collected_at >= :start_at
  AND lr.collected_at < :end_at;
```

## Backfill Plan

No production writes before the AI Lead merge/deploy plan.

After deployment, re-run analyzer only for the #484-confirmed affected date
range and brand/project scope, then aggregate those dates. Verify read-only
counters before and after the run.

Suggested local command shape:

```powershell
python -m geo_tracker.analyzer.cli run-daily --date YYYY-MM-DD --brand-id BRAND_ID
```

## Stale Aggregate Cleanup Handoff

Issue #553 fixes the reaggregation behavior where no-fallback calculation could
refuse to write a replacement row but leave old aggregate rows readable by the
App. After deployment, aggregate recomputation first removes existing
`geo_score_daily`, `topic_score_daily`, and `product_score_daily` rows for the
requested brand/date scope, then writes only rows that are computable from the
current evidence.

Affected production dates to repair for Estee Lauder / brand `12`:

- `2026-04-24`
- `2026-05-06`
- `2026-05-07`

For each date, AI Lead or Release/CI should run the approved canonical repair
write path with aggregation enabled and the confirmed competitive set:

```powershell
python -m geo_tracker.analyzer.cli repair-canonical-brand `
  --brand-id 12 `
  --source-brand-id 2 `
  --competitive-brand-id 2 `
  --date YYYY-MM-DD `
  --write `
  --aggregate
```

Expected counter shape after this PR:

- `geo_score_daily_removed`, `topic_score_removed`, and `product_score_removed`
  report how many stale daily rows were cleared before recomputation.
- `mentions_inserted` or `mentions_existing` covers the canonical Estee Lauder
  target evidence for brand `12`.
- `competitive_mentions_inserted` / `competitive_mentions_existing` should
  become non-zero when source-owner brand `2` or configured competitor names are
  actually mentioned in the repaired response text. If these remain zero, SoV
  must stay `partial`; do not accept target-only 100%.
- `citations_seen`, `citations_attributed`, and `citations_unattributed`
  describe whether response `citations_json` could be converted into
  `citation_sources`. Unattributed citations are explicit partial evidence, not
  a real zero.
- `geo_score_daily=0` is acceptable when the PRD mention-rate denominator is
  missing; the important postcondition is that stale `mention_rate=1.0000` rows
  are no longer present for that brand/date.
- `topic_score=0` is acceptable when topic linkage is missing; otherwise topic
  rows must be freshly recomputed and no old one-topic or target-only rows should
  remain.
- `product_score=0` is acceptable when no product-level mentions exist; stale
  product rows for the same brand/date should be absent.

Read-only aggregate verification:

```sql
SELECT brand_id, date, target_llm, intent, language,
       total_queries, mention_count, mention_rate, avg_sov, citation_rate,
       avg_geo_score
FROM geo_score_daily
WHERE brand_id = 12
  AND date::date IN ('2026-04-24', '2026-05-06', '2026-05-07')
ORDER BY date, target_llm NULLS FIRST, intent NULLS FIRST, language NULLS FIRST;

SELECT brand_id, topic_id, date, mention_count, total_responses, mention_rate,
       avg_geo_score
FROM topic_score_daily
WHERE brand_id = 12
  AND date::date IN ('2026-04-24', '2026-05-06', '2026-05-07')
ORDER BY date, topic_id;

SELECT brand_id, product_name, date, mention_count, total_queries, mention_rate,
       avg_sentiment_score, win_rate
FROM product_score_daily
WHERE brand_id = 12
  AND date::date IN ('2026-04-24', '2026-05-06', '2026-05-07')
ORDER BY date, product_name;
```

If the rows are absent after recomputation, treat that as an explicit missing
aggregate state for Backend/API and Frontend Integration follow-up. Do not
recreate rows manually with zero, one, or target-only values.

For #489's live blocker, the root cause was target-only canonical repair
evidence: the old repair wrote brand `12` mentions from owner brand `2`
responses, but did not preserve same-response competitor denominator rows and
stored partial position/sentiment/citation/PANO inputs as neutral or zero-like
values. After this fix, rerunning the repair command above should either write
real response-level competitor/citation rows or leave machine-readable
`metric_input_status` partial/empty handoff for Backend/API #562.

## Issue #563 Attribution Rerun

Production evidence before #563:

- `2026-04-24`: 125 scanned responses, 56 target response matches, 6
  response-level competitor mentions, 170 citation rows inserted, only 2
  attributed citations, `geo_score_daily=0`.
- `2026-05-06`: 2 scanned responses, 1 target response match, no citation rows,
  `geo_score_daily=0`.
- `2026-05-07`: 3 scanned responses, 1 target response match, 7 citation rows
  inserted, 0 attributed citations, `geo_score_daily=0`.
- Readonly evidence after the approved writes: target brand `12` has 58 mention
  rows/responses, competitor brand `2` has 6 mention rows, target citations=2,
  unresolved citations=175, target sentiment rows=58, sentiment driver rows=0,
  `geo_score_daily` rows=0.

Before any write, run the dry-run form for each approved date. #563 dry-run is
idempotent: it inspects existing competitor/citation rows and reports
`citations_seen`, `citations_existing`, `citations_repairable`,
`citations_attributed_by_context`, `sentiment_drivers_seen`, and
`sentiment_drivers_inserted` without changing production data.

```powershell
$dates = @("2026-04-24", "2026-05-06", "2026-05-07")
foreach ($d in $dates) {
  python -m geo_tracker.analyzer.cli repair-canonical-brand `
    --brand-id 12 `
    --source-brand-id 2 `
    --competitive-brand-id 2 `
    --date $d
}
```

After AI Lead approval, run the write + aggregate path for the same three dates:

```powershell
$dates = @("2026-04-24", "2026-05-06", "2026-05-07")
foreach ($d in $dates) {
  python -m geo_tracker.analyzer.cli repair-canonical-brand `
    --brand-id 12 `
    --source-brand-id 2 `
    --competitive-brand-id 2 `
    --date $d `
    --write `
    --aggregate
}
```

Expected #563 counter interpretation:

- `competitive_mentions_existing` should be non-zero on reruns after the #559
  write; new competitor rows should only appear when response text contains a
  configured or name-only competitor not already stored.
- `citations_repairable` is the maximum safe citation attribution delta for a
  date. Write mode should move those existing unresolved rows to a supported
  `mention_id`; ambiguous marker contexts remain counted as
  `citations_unattributed`.
- `sentiment_mentions_updated` and `sentiment_drivers_inserted` are allowed only
  when raw `response_analyses.raw_analysis_json` contains matching brand
  sentiment and quoted driver payloads.
- `geo_score_daily` can now materialize for Admin prompt rows whose default
  denominator is evidenced by `intent` aliases such as `non_brand` or
  `informational`, or by `prompts.tags.prompt_scope` values such as
  `non_branded`, plus category dimension evidence such as `topics.category =
  '品类'` or `category`.
- If `geo_score_daily` remains absent after #563, preserve the explicit
  no-evidence state and hand the prompt/endpoint semantics to #562 instead of
  creating fallback rows.

Optional read-only prompt eligibility check:

```sql
SELECT p.intent,
       p.tags,
       t.category,
       COUNT(DISTINCT r.id) AS responses,
       COUNT(DISTINCT bm.id) FILTER (WHERE bm.brand_id = 12) AS target_mentions
FROM llm_responses r
JOIN queries q ON q.id = r.query_id
LEFT JOIN prompts p ON p.id = q.prompt_id
LEFT JOIN topics t ON t.id = p.topic_id
LEFT JOIN brand_mentions bm ON bm.response_id = r.id
WHERE q.brand_id = 2
  AND r.collected_at::date IN ('2026-04-24', '2026-05-06', '2026-05-07')
GROUP BY p.intent, p.tags, t.category
ORDER BY responses DESC;
```

## Rollback

This PR adds no schema migration.

Rollback options:

- Revert the application commit if extraction or aggregation behavior regresses.
- Re-run aggregation for the affected date range from the pre-revert code path
  if daily aggregate rows were regenerated.
- For #563 write reruns, capture repaired `citation_sources.id`,
  inserted `sentiment_drivers.id`, and any `brand_mentions` whose sentiment
  fields changed from `NULL` before committing the production audit note. Data
  rollback is:
  - set `citation_sources.mention_id = NULL` for only the captured repaired
    citation IDs;
  - delete only the captured inserted sentiment driver IDs;
  - restore captured `brand_mentions.sentiment` / `sentiment_score` values only
    for rows changed by #563;
  - rerun aggregation for the three approved dates.
- Daily aggregate cleanup only removes derived `geo_score_daily`,
  `topic_score_daily`, and `product_score_daily` rows for the recomputed scope.
  Roll forward by rerunning the repaired aggregation. Roll back by reverting the
  commit and rerunning the prior aggregation command for the affected dates.
- If a live backfill inserted analyzer rows with wrong provenance, pause further
  analyzer writes and coordinate a data repair issue before deleting rows.

Do not delete production `brand_mentions`, `citation_sources`, or
`sentiment_drivers` rows without an AI Lead-approved repair plan.
