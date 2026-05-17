# Monitoring queries — VM-per-account ramp (#1117)

> Vendor-neutral monitoring queries (Prom + SQL) to validate the 3-gate indicator per ramp step. Used by [RUNBOOK_vm_per_account_ramp.md](../RUNBOOK_vm_per_account_ramp.md). Decision context: [ADR-016](../ADR/016-vm-per-account-ramp.md).
>
> All queries assume the `ai_responses` table + `engine_health_5min` materialized view per ADAPTER_CONTRACT.md §10.1 / §10.4, with `attempts` JSONB column containing per-attempt records including the new `execution_mode` field (`'local_cookie' | 'vm_session'`) and `vm_id` field added by PR #1121.
>
> All queries are AS-IS runnable against production read replica; no additional glue.

---

## 1. Indices required (one-time, applied by PR #1121 migration)

Phase 1 (#1121) migration must add expression indices for the slice queries below to stay sub-second on a 7-day window:

```sql
-- Already created by PR #1121 migration <ts>_llm_accounts_execution_mode.py:
-- CREATE INDEX idx_ai_responses_engine_created ON ai_responses (engine_id, created_at DESC);
-- CREATE INDEX idx_ai_responses_attempts_mode ON ai_responses USING GIN ((attempts) jsonb_path_ops);

-- If the GIN index above is not in PR #1121 (verify before Step 1), add it:
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_responses_attempts_mode
  ON ai_responses USING GIN ((attempts) jsonb_path_ops);
```

If neither index is present, the queries below still run but may take 30s+ on production scale; acceptable for ad-hoc ramp validation but unacceptable for any future dashboard refresh.

---

## 2. Baseline snapshot (pre-ramp, ramp §0 P-5)

### Q-BASELINE-1 — 7-day baseline error rate / sample count per engine

```sql
-- Run BEFORE any vm_session account exists. Captures the local_cookie-only baseline.
-- Save output to Epic #1110 as evidence; future comparison anchor.
SELECT
  engine_id,
  COUNT(*) AS sample_count_7d,
  COUNT(*) FILTER (WHERE status = 'SUCCESS') * 1.0
    / NULLIF(COUNT(*) FILTER (WHERE error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')), 0) AS success_rate,
  COUNT(*) FILTER (WHERE status <> 'SUCCESS') * 1.0
    / NULLIF(COUNT(*) FILTER (WHERE error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')), 0) AS error_rate,
  COUNT(*) FILTER (WHERE error_code = 'CAPTCHA_REQUIRED') * 1.0 / NULLIF(COUNT(*), 0) AS captcha_rate,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status = 'SUCCESS') AS p50_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status = 'SUCCESS') AS p95_latency_ms
FROM ai_responses
WHERE engine_id IN ('doubao', 'deepseek-CN')
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY engine_id
ORDER BY engine_id;
```

### Q-BASELINE-2 — error breakdown per engine

```sql
SELECT
  engine_id,
  error_code,
  COUNT(*) AS cnt,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY engine_id) AS pct
FROM ai_responses
WHERE engine_id IN ('doubao', 'deepseek-CN')
  AND created_at > NOW() - INTERVAL '7 days'
  AND error_code IS NOT NULL
GROUP BY engine_id, error_code
ORDER BY engine_id, cnt DESC;
```

### Q-BASELINE-3 — current `engine_health_5min` last-window per engine

```sql
SELECT *
FROM engine_health_5min
WHERE engine_id IN ('doubao', 'deepseek-CN')
ORDER BY engine_id, window_start DESC
LIMIT 4;  -- last 2 windows per engine
```

---

## 3. The 3-gate indicator computation (Q-3GATE, called every 4-6h during 24h observe + at 24h mark)

This is the core query the ramp runs at each step to decide GO / NO-GO. Computes 3 ratios per in-scope engine over the last 24h window, comparing `attempts[].execution_mode='vm_session'` slice vs `attempts[].execution_mode='local_cookie'` slice for the **same engine_id** at the **same time window**, eliminating time-of-day / brand-mix / pool-imbalance confounds.

```sql
-- Q-3GATE: 3-gate computation per engine over the last 24h window.
-- Outputs one row per engine_id with vm/local samples + 3 ratio columns + PASS/NO-GO verdict.
WITH attempt_unfold AS (
  SELECT
    r.engine_id,
    r.created_at,
    r.status,
    r.error_code,
    r.latency_ms,
    (att->>'execution_mode') AS exec_mode,
    (att->>'vm_id') AS vm_id
  FROM ai_responses r,
       LATERAL jsonb_array_elements(r.attempts) att
  WHERE r.engine_id IN ('doubao', 'deepseek-CN')
    AND r.created_at > NOW() - INTERVAL '24 hours'
    AND (att->>'execution_mode') IN ('local_cookie', 'vm_session')
),
slice_metrics AS (
  SELECT
    engine_id,
    exec_mode,
    COUNT(*) AS sample_count,
    COUNT(*) FILTER (WHERE status <> 'SUCCESS' AND error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')) * 1.0
      / NULLIF(COUNT(*) FILTER (WHERE error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')), 0) AS error_rate,
    COUNT(*) FILTER (WHERE error_code = 'CAPTCHA_REQUIRED') * 1.0 / NULLIF(COUNT(*), 0) AS captcha_rate,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status = 'SUCCESS') AS p95_latency_ms
  FROM attempt_unfold
  GROUP BY engine_id, exec_mode
),
pivoted AS (
  SELECT
    engine_id,
    MAX(sample_count) FILTER (WHERE exec_mode = 'local_cookie') AS local_n,
    MAX(sample_count) FILTER (WHERE exec_mode = 'vm_session')   AS vm_n,
    MAX(error_rate)   FILTER (WHERE exec_mode = 'local_cookie') AS local_err,
    MAX(error_rate)   FILTER (WHERE exec_mode = 'vm_session')   AS vm_err,
    MAX(captcha_rate) FILTER (WHERE exec_mode = 'local_cookie') AS local_cap,
    MAX(captcha_rate) FILTER (WHERE exec_mode = 'vm_session')   AS vm_cap,
    MAX(p95_latency_ms) FILTER (WHERE exec_mode = 'local_cookie') AS local_p95,
    MAX(p95_latency_ms) FILTER (WHERE exec_mode = 'vm_session')   AS vm_p95
  FROM slice_metrics
  GROUP BY engine_id
)
SELECT
  engine_id,
  local_n, vm_n,
  ROUND(local_err::numeric, 4) AS local_err_rate,
  ROUND(vm_err::numeric, 4)    AS vm_err_rate,
  ROUND((vm_err / NULLIF(local_err, 0))::numeric, 3) AS err_ratio_vm_over_local,
  ROUND(local_cap::numeric, 4) AS local_captcha_rate,
  ROUND(vm_cap::numeric, 4)    AS vm_captcha_rate,
  ROUND((vm_cap / NULLIF(local_cap, 0.0001))::numeric, 3) AS captcha_ratio_vm_over_local,
  local_p95, vm_p95,
  ROUND((vm_p95::numeric / NULLIF(local_p95::numeric, 0)), 3) AS p95_ratio_vm_over_local,
  CASE
    WHEN vm_n < 30 OR local_n < 30 THEN 'UNDER-SAMPLE'
    WHEN (vm_err / NULLIF(local_err, 0)) > 0.5 THEN 'NO-GO err'
    WHEN vm_cap > local_cap THEN 'NO-GO captcha'
    WHEN (vm_p95::numeric / NULLIF(local_p95::numeric, 0)) > 1.5 THEN 'NO-GO latency'
    ELSE 'PASS'
  END AS verdict
FROM pivoted
ORDER BY engine_id;
```

**Reading the verdict:**

- `PASS` → all 3 gates green AND sample size ≥ 30/30 → eligible for §1.5 GO
- `NO-GO err` / `NO-GO captcha` / `NO-GO latency` → §1.6 rollback, gate name identifies the failing dimension
- `UNDER-SAMPLE` → extend window 24h, re-run; if still under-sample after 72h, traffic level too low for this step's target share, hold at previous step

**Note on `captcha_ratio_vm_over_local`**: the ratio uses `NULLIF(local_cap, 0.0001)` to avoid div-by-zero when baseline has 0 captchas; the verdict column uses absolute comparison `vm_cap > local_cap` which correctly handles the 0-baseline case (any vm captcha is regression).

---

## 4. R1.6 cross-engine correlation gate (Step 4+ only)

Two queries: single-engine self-correlation (Step 3+) and cross-engine (Step 4+).

### Q-R16-SINGLE — same VM same engine captcha-chain within 1h (Step 3 GO requires count ≤ 1)

```sql
WITH vm_captcha_events AS (
  SELECT
    (att->>'vm_id') AS vm_id,
    r.engine_id,
    r.created_at
  FROM ai_responses r,
       LATERAL jsonb_array_elements(r.attempts) att
  WHERE r.error_code = 'CAPTCHA_REQUIRED'
    AND (att->>'execution_mode') = 'vm_session'
    AND r.created_at > NOW() - INTERVAL '24 hours'
)
SELECT
  vm_id, engine_id, COUNT(*) AS chain_pair_count
FROM vm_captcha_events a
JOIN vm_captcha_events b USING (vm_id, engine_id)
WHERE b.created_at > a.created_at
  AND b.created_at < a.created_at + INTERVAL '1 hour'
GROUP BY vm_id, engine_id
HAVING COUNT(*) > 0
ORDER BY chain_pair_count DESC;
```

Expected at Step 3 GO: ≤ 1 row across all (vm_id, engine_id) pairs.

### Q-R16-CROSS — same VM, captcha on engine A then captcha on engine B within 1h (Step 4+ GO requires count ≤ 1)

```sql
WITH vm_captcha_events AS (
  SELECT
    (att->>'vm_id') AS vm_id,
    r.engine_id,
    r.created_at
  FROM ai_responses r,
       LATERAL jsonb_array_elements(r.attempts) att
  WHERE r.error_code = 'CAPTCHA_REQUIRED'
    AND (att->>'execution_mode') = 'vm_session'
    AND r.created_at > NOW() - INTERVAL '24 hours'
)
SELECT
  a.vm_id,
  a.engine_id AS first_engine,
  b.engine_id AS second_engine,
  a.created_at AS first_event,
  b.created_at AS second_event,
  EXTRACT(EPOCH FROM (b.created_at - a.created_at)) AS gap_seconds
FROM vm_captcha_events a
JOIN vm_captcha_events b USING (vm_id)
WHERE a.engine_id <> b.engine_id
  AND b.created_at > a.created_at
  AND b.created_at < a.created_at + INTERVAL '1 hour'
ORDER BY a.vm_id, a.created_at;
```

Expected at Step 4 GO: ≤ 1 row total across the 24h window. > 1 = "shared IP / shared fingerprint cross-contaminates engines" smoking gun (#1117 ADR-016 Step 4 rollback path).

---

## 5. Per-step verification queries (called from RUNBOOK §1.3)

### Q-STEP-ROUTE — confirm flag-on routed traffic to vm_session (post-deploy)

See RUNBOOK §1.3 (already inlined there; re-stated here for monitoring doc completeness):

```sql
SELECT engine_id,
       count(*) FILTER (WHERE (att->>'execution_mode') = 'vm_session') AS vm_attempts_30min,
       count(*) FILTER (WHERE (att->>'execution_mode') = 'local_cookie') AS local_attempts_30min
FROM ai_responses,
     LATERAL jsonb_array_elements(attempts) att
WHERE engine_id IN ('doubao','deepseek-CN')
  AND created_at > NOW() - INTERVAL '30 minutes'
GROUP BY engine_id
ORDER BY engine_id;
```

### Q-STEP5-PICK — identify candidate local_cookie accounts to flip in Step 5 (50% target)

```sql
-- Pick the older half of currently local_cookie accounts for the engine, leaving the newer half alone.
-- "Older" tends to mean "already in pool rotation longer" — flipping them keeps newer cookies as backup.
WITH per_engine_count AS (
  SELECT engine, COUNT(*) AS total
  FROM llm_accounts
  WHERE execution_mode = 'local_cookie'
    AND engine IN ('doubao', 'deepseek-CN')
    AND status = 'ACTIVE'
  GROUP BY engine
)
SELECT a.id, a.engine, a.created_at, a.status
FROM llm_accounts a
JOIN per_engine_count pec USING (engine)
WHERE a.execution_mode = 'local_cookie'
  AND a.engine IN ('doubao', 'deepseek-CN')
  AND a.status = 'ACTIVE'
ORDER BY a.engine, a.created_at ASC
LIMIT (SELECT SUM(total / 2) FROM per_engine_count);
```

Operator reviews the list, then via Admin UI clears cookies + flips execution_mode + assigns vm_id per account.

### Q-STEP5-VERIFY — confirm newly-flipped accounts are actively serving traffic (not starved)

```sql
-- After Step 5 §1.3, run after 6h+ to verify the freshly-flipped accounts have served queries
-- (pool selection may favor newer / less-used accounts; if flipped accounts are starved, sample is biased).
SELECT
  a.id AS account_id,
  a.engine,
  a.vm_id,
  COUNT(r.id) AS attempts_6h_after_flip
FROM llm_accounts a
LEFT JOIN ai_responses r ON r.account_id_used = a.id
  AND r.created_at > NOW() - INTERVAL '6 hours'
WHERE a.execution_mode = 'vm_session'
  AND a.engine IN ('doubao', 'deepseek-CN')
GROUP BY a.id, a.engine, a.vm_id
ORDER BY a.engine, attempts_6h_after_flip DESC;
```

Each flipped account should show ≥ 5 attempts within 6h; accounts with 0 are starved and the §1.5 GO sample is incomplete.

### Q-USER-SYMPTOM-REPLAY — Step 6 30-day Business Result Gate

Per AGENTS.md `Acceptance And Verification Evidence` Business Result Gate: the original failed queries (184968, 184971, 184974 from Issue #963) must succeed via vm_session.

```sql
SELECT
  r.id AS response_id,
  r.engine_id,
  r.query_id,
  r.status,
  r."responseSource" AS response_source,
  (r.attempts->-1->>'execution_mode') AS last_attempt_mode,
  (r.attempts->-1->>'vm_id') AS last_attempt_vm,
  LENGTH(r.raw_text) AS raw_text_len,
  r.created_at
FROM ai_responses r
WHERE r.query_id IN ('184968', '184971', '184974')
  AND r.created_at > '<step-6-go-ts>'  -- replace with actual Step 6 GO timestamp
ORDER BY r.query_id, r.created_at DESC;
```

Expected per query: `status='SUCCESS'`, `responseSource='web_ui'`, `last_attempt_mode='vm_session'`, `raw_text_len ≥ 200`. Paste output into Issue #963 + Issue #1117 as the closing User-Symptom Replay evidence.

---

## 6. Prometheus / generic time-series queries

These assume the existing metrics pipeline exposes `engine_health_5min` columns as gauges with label `engine` (per ADAPTER_CONTRACT.md §10.4 + ADMIN_PRD §4.2.2) and that PR #1121 / #1122 add an additional label `execution_mode` (sliced gauges). If your monitoring stack uses different metric names, adapt accordingly — the SQL queries above are the canonical SSOT.

### P-1 — error rate ratio (vm vs local), per engine

```promql
# Numerator: vm_session error rate
(1 - engine_health_5min_success_rate{engine=~"doubao|deepseek-CN", execution_mode="vm_session"})
/
# Denominator: local_cookie error rate
(1 - engine_health_5min_success_rate{engine=~"doubao|deepseek-CN", execution_mode="local_cookie"})
# Alert: > 0.5 for 24h sustained → NO-GO
```

### P-2 — captcha rate delta (vm minus local), per engine

```promql
# Captcha rate as error_breakdown:CAPTCHA_REQUIRED / sample_count
(engine_health_5min_error_breakdown{engine=~"doubao|deepseek-CN", execution_mode="vm_session", error="CAPTCHA_REQUIRED"}
 / engine_health_5min_sample_count{engine=~"doubao|deepseek-CN", execution_mode="vm_session"})
-
(engine_health_5min_error_breakdown{engine=~"doubao|deepseek-CN", execution_mode="local_cookie", error="CAPTCHA_REQUIRED"}
 / engine_health_5min_sample_count{engine=~"doubao|deepseek-CN", execution_mode="local_cookie"})
# Alert: > 0 for 24h sustained → NO-GO captcha regressed
```

### P-3 — p95 latency ratio (vm vs local), per engine

```promql
engine_health_5min_p95_latency_ms{engine=~"doubao|deepseek-CN", execution_mode="vm_session"}
/
engine_health_5min_p95_latency_ms{engine=~"doubao|deepseek-CN", execution_mode="local_cookie"}
# Alert: > 1.5 for 24h sustained → NO-GO latency
```

### P-4 — fleet health (VM session alive gauge, from login_watchdog)

```promql
# Both labels expected from PR #1119 vm_side login_watchdog Prom exporter
sum by (engine) (doubao_session_alive{vm_id=~"vm-doubao-0[1-5]"})  # expect = 5 at fleet-healthy
sum by (engine) (deepseek_session_alive{vm_id=~"vm-deepseek-0[1-5]"})  # expect = 5 at fleet-healthy
# Alert: < 4 → fleet degraded, see RUNBOOK §3 crash recovery
```

---

## 7. Cost & sample-size reference

| Step | Expected vm_session attempts / 24h (per engine in scope) | Notes |
|---|---|---|
| Step 1 | ~50-150 doubao | 1 account; low-traffic engine pool spread |
| Step 2 | ~150-450 doubao | 3 accounts |
| Step 3 | ~250-750 doubao | 5 accounts |
| Step 4 | ~250-750 doubao + ~50-200 deepseek-CN | deepseek-CN low total volume |
| Step 5 | ~3000-8000 each | 50% traffic |
| Step 6 | ~6000-16000 each | 100% traffic |

If actual attempts at Step N are < 50% of the lower bound, traffic level dropped (e.g. brand pause) and the 3-gate Q-3GATE will return `UNDER-SAMPLE`. Re-plan timing.
