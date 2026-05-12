# App Analytics Extraction Provenance Runbook

Scope: GitHub issue #532, Pipeline/Data Agent.

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
- `citation_sources.mention_id` is populated when citation title/domain can be
  attributed to a persisted brand mention.
- `sentiment_drivers.source_quote` is populated for brand-linked sentiment
  drivers when LLM sentiment extraction supplies drivers.
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

## Rollback

This PR adds no schema migration.

Rollback options:

- Revert the application commit if extraction or aggregation behavior regresses.
- Re-run aggregation for the affected date range from the pre-revert code path
  if daily aggregate rows were regenerated.
- If a live backfill inserted analyzer rows with wrong provenance, pause further
  analyzer writes and coordinate a data repair issue before deleting rows.

Do not delete production `brand_mentions`, `citation_sources`, or
`sentiment_drivers` rows without an AI Lead-approved repair plan.
