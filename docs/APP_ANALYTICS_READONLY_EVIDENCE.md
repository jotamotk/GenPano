# App Analytics Read-Only Evidence

Source of truth: `docs/PRD_APP_ANALYTICS_CORRECTION.md`, requirement IDs
`PRD-APP-ANALYTICS-000` through `PRD-APP-ANALYTICS-010`.

This runbook exists for issue #537. It gives Release/CI, AI Lead, and QA a
safe way to capture production formula evidence before backend, pipeline,
frontend, or E2E issues accept App analytics output as trustworthy.

## Safety Contract

- The workflow is manual only: `App Analytics Readonly Evidence`.
- The DB probe emits and runs `SELECT` statements inside
  `BEGIN TRANSACTION READ ONLY`.
- `project_id` input is still validated as UUID-shaped, but DB probes compare
  it as text so production `projects.id` columns stored as varchar/text do not
  fail before evidence collection starts.
- The API probe sends authenticated `GET` requests only.
- There is no repair, backfill, aggregation refresh, mutation, or production
  write mode.
- Secrets are never printed. `APP_ANALYTICS_BEARER_TOKEN` is masked before any
  probe runs.
- If a secret is unavailable, the workflow reports the exact missing secret and
  skips that probe family safely.

## Required Secrets

- `SERVER_HOST`: production host for the SELECT-only DB probe over SSH.
- `SERVER_USER`: SSH user.
- `SERVER_SSH_KEY`: SSH private key.
- `APP_ANALYTICS_BEARER_TOKEN`: App user Bearer token for authenticated API
  `GET` probes. If this is absent, DB probes can still run, and API probes are
  reported as blocked by this exact secret.

## Example Dispatch

Use these inputs for the current Estee Lauder App analytics target:

```text
project_id=95d43022-a5c8-5944-b6d6-34b29faa18b5
brand_id=12
competitor_brand_ids=2
date_from=2026-04-24
date_to=2026-05-11
base_url=http://116.62.36.173
```

## Evidence Captured

The SELECT probe captures:

- deployed container image/start/status snippets from `docker compose ps` and
  `docker inspect`;
- project and configured competitor context;
- response counts by engine/date;
- analyzer row counts, missing analyzer rows, and failed response statuses;
- `brand_mentions` coverage for target, configured competitors,
  unconfigured competitors, and unresolved brands;
- `citation_sources` and official-domain attribution counts;
- brand-linked sentiment rows and `sentiment_drivers` counts;
- topic to prompt to query to response linkage counts;
- daily `geo_score_daily`, `topic_score_daily`, and `product_score_daily`
  nullable aggregate averages plus per-component null/non-null counts.

The authenticated API probe captures status, request ID, response hash, short
payload snippet, and any top-level `state`, `state_reason`, `missing_inputs`,
`formula_status`, and `evidence_counts` for:

- overview;
- metrics;
- competitors metrics;
- PANO/GEO trend via competitors trend;
- topics monitoring;
- topic heatmap;
- sentiment;
- sentiment by engine;
- sentiment trend by engine;
- sentiment topic attribution;
- citations;
- citation authority trend;
- citation composition;
- metrics by engine;
- position distribution.

## Local Static Checks

Generate the SQL locally without touching production:

```powershell
py backend/scripts/app_analytics_readonly_evidence.py db-sql `
  --project-id 95d43022-a5c8-5944-b6d6-34b29faa18b5 `
  --brand-id 12 `
  --competitor-brand-ids 2 `
  --date-from 2026-04-24 `
  --date-to 2026-05-11
```

Run authenticated GET probes locally only when you already have a valid token in
the current shell:

```powershell
$env:APP_ANALYTICS_BEARER_TOKEN = "<masked token from approved secret source>"
py backend/scripts/app_analytics_readonly_evidence.py api-probes `
  --project-id 95d43022-a5c8-5944-b6d6-34b29faa18b5 `
  --brand-id 12 `
  --competitor-brand-ids 2 `
  --date-from 2026-04-24 `
  --date-to 2026-05-11 `
  --base-url http://116.62.36.173
```

## Reporting

Paste the workflow run URL plus concise findings into #537, #484, and #481.
For any blocked probe, include the exact missing secret name. Do not infer a
formula state from zeros, 100% values, or chart presence unless the numerator,
denominator, `formula_status`, and evidence counts support it.
