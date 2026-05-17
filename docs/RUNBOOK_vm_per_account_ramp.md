# RUNBOOK — VM-per-Account 灰度 ramp (Phase 2)

> Operator-facing checklist for executing Issue #1117 (6-step ramp from `local_cookie` baseline to `vm_session` for doubao + deepseek-CN). Decision authority + GO/NO-GO criteria are in [ADR-016](./ADR/016-vm-per-account-ramp.md). Monitoring queries (Prom + SQL) are in [docs/monitoring/vm_per_account_queries.md](./monitoring/vm_per_account_queries.md).
>
> Per AGENTS.md `### Acceptance And Verification Evidence`: every checked item in the ramp Epic #1110 EVIDENCE comment needs command, exit code, key output, scope covered, artifact link, commit SHA.
>
> Per AGENTS.md `### Tiered E2E`: each step's GO uses **Tier 1 (targeted user-symptom replay)** on the next 24h's natural traffic for the new vm_session accounts — not full Playwright; Tier 3 is reserved for Step 6 → Phase 3 transition (re-run 184968/184971/184974 readback).

---

## 0. Pre-ramp checks (一次性, before Step 1)

Verify before any step. **Do not start Step 1 until all 5 of these are EVIDENCE-checked in the Epic #1110 thread.**

| Check | Command / Action | Required Outcome | Evidence |
|---|---|---|---|
| P-1 PRs merged + deployed | `git log origin/main --grep "#1119\|#1120\|#1121\|#1122" --oneline` and verify last deploy SHA in Build & Deploy run UI matches `git rev-parse origin/main` | 4 commits appear, last deploy = `main` HEAD | Build & Deploy run URL + `git log` output |
| P-2 5 VMs fleet bootstrapped | SSH into each VM, run `systemctl status chrome-doubao chrome-deepseek x11vnc websockify tailscaled` | All 5 services `active (running)` on all 5 VMs | `systemctl` output × 5 VMs |
| P-3 10 profiles manually logged in (5 doubao + 5 deepseek) via noVNC | Operator opens `https://vm-{doubao,deepseek}-0{1..5}.tail-xxx.ts.net:6080` in browser, verifies Chrome shows logged-in state (no login dialog) for each profile, then runs `cdp_check.sh <vm> <port>` from local machine | All 10 profiles return `{"loginState":"authenticated"}` from cdp-check | Screenshot of noVNC × 10 profiles + cdp_check.sh output |
| P-4 `VM_EXECUTOR_ENABLED=false` is the current default | `kubectl get configmap/backend-env -o yaml \| grep VM_EXECUTOR_ENABLED` (or equivalent: read deploy env in Build & Deploy run) | Value is `false` (or unset, which defaults to false in PR #1121's router) | configmap readback |
| P-5 Baseline `engine_health_5min` snapshot recorded | Run queries Q-BASELINE-1, Q-BASELINE-2, Q-BASELINE-3 in [monitoring/vm_per_account_queries.md](./monitoring/vm_per_account_queries.md) for the past 7 days for engine_id IN (`doubao`, `deepseek-CN`), paste output into Epic #1110 as `EVIDENCE: pre-ramp baseline` | Output captured into Epic #1110 thread with timestamp | Epic #1110 comment URL |

If any P-N fails: post `BLOCKER` on Issue #1117 with which check failed + log evidence, do not proceed.

---

## 1. Per-step procedure (template, applied 6 times)

For each Step N below, follow this template in order. The Step section that follows fills in the **bold** variable lines.

### 1.1 Plan-of-step (5 min)

1. Read the Step N row in the [§2 table](#2-the-6-ramp-steps) below for: target accounts, target traffic share, engine set, 24h observe end-time.
2. Confirm previous step (Step N-1) is in `GO` state on Epic #1110 (look for the `EVIDENCE: Step N-1 GO` comment with all three gates green).
3. Confirm operator is on-call for the next 24h (cannot start a step without someone watching the dashboard).

### 1.2 Action: create N more vm_session accounts (15 min)

Use Admin UI from PR #1122 — see `docs/ADMIN_PRD.md §4.2.4` (account management page) for the "新建 VM 账号" entry point. Per AGENTS.md Admin Surface Rule, this is the only Admin UI; do not script around it.

**Procedure:**

1. Admin UI → `/admin/accounts` page → click "新建 VM 账号" (added in PR #1122)
2. For each new account:
   - engine: `doubao` or `deepseek-CN` (per Step N spec)
   - execution_mode: `vm_session`
   - vm_id: pick from `vm-doubao-0{1..5}` / `vm-deepseek-0{1..5}` (per Step N spec)
   - cookies_json: **must be empty** (DB CHECK constraint `chk_exec_mode_cookies` will reject otherwise, see ADR-016 R2.5)
3. Save → Admin UI shows the new row in account list with `execution_mode=vm_session`.

**Verification (DB readback):**

```sql
-- Q-STEP-CREATE: confirm new vm_session accounts exist + are bound to the right VMs
SELECT id, engine, execution_mode, vm_id, cookies_json IS NULL AS cookies_cleared, status, created_at
FROM llm_accounts
WHERE execution_mode = 'vm_session'
  AND engine IN ('doubao', 'deepseek-CN')
ORDER BY created_at DESC
LIMIT 20;
```

Expected: N rows with `execution_mode='vm_session'`, `cookies_cleared=true`, `status='ACTIVE'`, vm_id matching the assigned VMs.

If `cookies_cleared` shows `false` for any row → DB CHECK should have rejected; this is a bug, post `BLOCKER` on Issue #1117 and revert via `DELETE FROM llm_accounts WHERE id IN (<new ids>)`.

### 1.3 Action: enable router flag (if not already enabled) (2 min)

For Step 1 only: set `VM_EXECUTOR_ENABLED=true` in deploy env + add `VM_EXECUTOR_ENGINES=doubao` (engines CSV, defaults empty = deny-list for vm_session even if account is marked). Step 2-3 keep `VM_EXECUTOR_ENGINES=doubao`. Step 4-6 add `deepseek-CN`: `VM_EXECUTOR_ENGINES=doubao,deepseek-CN`.

Trigger a fresh Build & Deploy run. Verify deploy completes (do not assume — read run URL conclusion = success).

**Verification:**

```sql
-- Q-STEP-ROUTE: after deploy, confirm at least one attempt has flowed through vm_session
-- (run 10-30 min after deploy completes, depending on doubao traffic level)
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

Expected for Step 1: `vm_attempts_30min ≥ 1` for `doubao`. If 0 after 30 min and there is doubao traffic in the same window (`local_attempts_30min > 0`), router is mis-wired — post `BLOCKER`, rollback via §1.6 NO-GO, do not start 24h observe.

### 1.4 24h observe (wait, watch dashboard) (~24h elapsed time)

Set a 24h timer + calendar entry from the moment §1.3 verification PASS. During the 24h window:

- Every 4-6h: run **Q-3GATE** query (in monitoring/vm_per_account_queries.md §3) and eyeball the 3 indicators per engine:
  - `error_rate_vm / error_rate_local` (target ≤ 0.5)
  - `captcha_rate_vm - captcha_rate_local` (target ≤ 0, i.e. not regressed)
  - `p95_vm_ms / p95_local_ms` (target ≤ 1.5)
- Eyeball check Prom panel `engine_health_5min` (queries P-1 through P-4 in monitoring doc) for the engine set in scope this step. Look for spikes / saturation / dead time.
- If at any time during the 24h window any of the 3 gates breaches by > 50% margin AND the sample size is ≥ 30 vm_session attempts for that engine: jump straight to §1.6 NO-GO (do not wait for the 24h mark).

What counts as PASS at the 24h mark:

- Sample size: ≥ 30 `vm_session` attempts AND ≥ 30 `local_cookie` attempts for **each** in-scope engine over the 24h window (smaller samples are inconclusive — extend by 24h up to a max of 72h, then if still under-sample, this means traffic level is too low for this step's target share and the previous step's account count should hold; re-plan).
- All 3 gates PASS (computed by Q-3GATE):
  - error rate ratio ≤ 0.5
  - captcha rate ratio ≤ 1.0 (not regressed; allows 0 baseline captchas without false-NO-GO)
  - p95 latency ratio ≤ 1.5
- No fleet-level incident in the window (login_watchdog Slack alerts on > 1 VM, Tailscale disconnects > 2 min, OOM kills) — these are infra incidents not step decisions.

### 1.5 GO command (post-PASS, 5 min)

1. Post `EVIDENCE: Step N GO` on Epic #1110 with:
   - Q-3GATE output (table form) for each in-scope engine
   - Sample counts (vm_session + local_cookie) over the 24h window
   - Build & Deploy run URL for the §1.3 deploy
   - DB account IDs added in §1.2
   - Operator name + timestamp
   - Sign-off: "GO to Step N+1, no rollback"
2. Update Issue #1117 `## Verification Evidence Ledger` to check the `Step N` box with the Epic #1110 comment URL as the link.
3. Schedule next step Plan-of-step (§1.1) for next operator on-call window (or proceed immediately if same operator + capacity).

### 1.6 NO-GO rollback (秒级, post-FAIL or BLOCKER) (5 min)

```sql
-- Q-ROLLBACK: flip the new vm_session accounts (added in this step's §1.2) back to local_cookie.
-- IMPORTANT: do NOT flip accounts from prior steps — only the ones added in this step.
-- Filter by created_at window of this step (replace timestamps accordingly).
UPDATE llm_accounts
SET execution_mode = 'local_cookie'
WHERE execution_mode = 'vm_session'
  AND engine IN ('doubao','deepseek-CN')
  AND created_at >= '<this-step-§1.2-start-ts>'
  AND created_at <  '<this-step-§1.2-end-ts>';

-- Q-ROLLBACK-VERIFY: confirm no new vm_session attempts within 5 min of rollback (router re-selects on next pool-pick).
SELECT engine_id,
       count(*) FILTER (WHERE (att->>'execution_mode') = 'vm_session') AS vm_attempts_5min,
       MAX(created_at) AS most_recent_response
FROM ai_responses,
     LATERAL jsonb_array_elements(attempts) att
WHERE engine_id IN ('doubao','deepseek-CN')
  AND created_at > NOW() - INTERVAL '5 minutes'
GROUP BY engine_id;
```

After rollback:

1. Confirm `vm_attempts_5min` count of the rolled-back accounts stops growing within ≤ 5 min (router picks new account on next query, the rolled-back ones won't be vm_session anymore).
2. **Account cleanup**: these accounts are now in mixed state — `execution_mode=local_cookie` but `cookies_json IS NULL`. They cannot serve traffic. Options:
   - (preferred) Soft-disable via Admin UI: set `status='DISABLED'`. They become inert.
   - (only if cookies are available) Re-paste cookies via Admin UI to re-activate as local_cookie account.
   - (cleanup) `DELETE FROM llm_accounts WHERE id IN (<rolled-back ids>)` if the VM profile is also being deprovisioned.
3. Re-attest baseline restored: re-run Q-BASELINE-1 from §0 P-5 for the next 1h window, compare to pre-ramp baseline; values should be within ±10%.
4. Post `EVIDENCE: Step N NO-GO + rollback complete` on Epic #1110 with:
   - Which gate failed + measured value vs threshold
   - Q-ROLLBACK and Q-ROLLBACK-VERIFY SQL output
   - Baseline-restored Q-BASELINE-1 output
   - Candidate root cause hypothesis (≤ 3 lines)
5. **Decision (operator + Lead hat)**: rollback target is one of:
   - Step N-1: if root cause is isolated to the new accounts (e.g. one specific VM is sick) — fix VM, restart Step N
   - Step 0 (full local_cookie): if root cause is architectural (e.g. router bug, schema bug, RemoteCDPConnector bug) — pause epic, file fix PR against Phase 1 PRs, re-pre-ramp
   - **Never** patch forward in-place; per AGENTS.md Hard Rule 5.

---

## 2. The 6 ramp steps

For each step: target accounts to add in §1.2, target traffic share, engine set, GO threshold table per [ADR-016](./ADR/016-vm-per-account-ramp.md).

### Step 1 — 1 doubao vm_session

- Target: add **1** new vm_session doubao account (vm_id=`vm-doubao-01`)
- Target share: ~1% of doubao traffic
- Engine set in scope for 3-gate check: `doubao`
- `VM_EXECUTOR_ENABLED=true`, `VM_EXECUTOR_ENGINES=doubao` (first time the flag flips on)
- 24h observe
- GO thresholds (against same-window doubao local_cookie baseline):
  - error rate ratio ≤ 0.5
  - captcha rate ratio ≤ 1.0 (not regressed)
  - p95 latency ratio ≤ 1.5
- NO-GO rollback: §1.6, rollback target = Step 0 (architecture-level — first vm_session attempt failing is a blocker for entire epic, not a per-account issue)

### Step 2 — 3 doubao vm_session

- Target: add **2** more new vm_session doubao accounts (vm_id=`vm-doubao-02`, `vm-doubao-03`); total now 3 doubao vm_session
- Target share: ~3-5% of doubao traffic
- Engine set: `doubao`
- 24h observe
- GO thresholds: same as Step 1
- NO-GO rollback: §1.6, rollback target = Step 1 (1 account worked, 3 didn't — likely VM-specific or pool selection imbalance)

### Step 3 — 5 doubao vm_session

- Target: add **2** more new vm_session doubao accounts (vm_id=`vm-doubao-04`, `vm-doubao-05`); total now 5 doubao vm_session (all doubao VMs in scope)
- Target share: ~10-15% of doubao traffic
- Engine set: `doubao`
- 24h observe
- GO thresholds: same as Step 1; **additionally**: R1.6 single-engine self-correlation check — query for "same VM, doubao captcha → same VM, doubao captcha within 1h" pattern, count should be ≤ 1 across the 24h window. If R1.6 self-correlation triggers, treat as NO-GO.
- NO-GO rollback: §1.6, rollback target = Step 2 (R1.6 single-engine — 1 VM is sick or doubao is collectively pushing back)

### Step 4 — 5 doubao + 5 deepseek-CN vm_session (cross-engine 双开 R1.6 gate)

- Target: add **5** new vm_session deepseek-CN accounts (vm_id=`vm-deepseek-01..05`, on the same 5 VMs that already serve doubao — confirming 双开 architecture); total now 5 doubao + 5 deepseek-CN vm_session
- Target share: ~10-15% doubao + ~100% of deepseek-CN traffic (deepseek-CN is lower volume, so 5 accounts jumps share fast)
- Engine set: `doubao` + `deepseek-CN` (3-gate check runs **per engine, not aggregate**)
- `VM_EXECUTOR_ENGINES=doubao,deepseek-CN` (deploy required)
- 24h observe
- GO thresholds: same per-engine thresholds; **additionally**: R1.6 cross-engine correlation check — query for "same VM, engine A captcha → same VM, engine B captcha within 1h" pattern, count should be ≤ 1 across the 24h window. If R1.6 cross-engine triggers, treat as NO-GO (the smoking gun for "shared IP / shared device fingerprint cross-contaminates engines").
- NO-GO rollback: §1.6, rollback target options:
  - Step 3 + lift deepseek-CN from `VM_EXECUTOR_ENGINES`: if only deepseek-CN failed
  - Step 3 + propose 1 VM 1 engine architecture change in ADR-016 follow-up: if R1.6 cross-engine triggered (the doubao + deepseek 双开 假设 is invalidated; need 10 VMs at ~¥2000/月 vs ¥1000/月)

### Step 5 — 50% of doubao + 50% of deepseek-CN vm_session

- Target: flip **half of remaining `local_cookie` doubao + deepseek-CN accounts** to vm_session (this is the **first step that affects existing local_cookie accounts**, not just newly-created vm_session accounts; requires clearing their `cookies_json` first per CHECK constraint, so Admin UI workflow is: 1) revoke cookies on selected accounts, 2) flip execution_mode + assign vm_id, 3) save). Use Q-STEP5-PICK in monitoring doc to identify candidates.
- Target share: ~50% of doubao + ~50% of deepseek-CN
- Engine set: `doubao` + `deepseek-CN`
- 24h observe
- GO thresholds: same per-engine + R1.6 cross-engine
- **Extra precaution**: pool selection may favor newer accounts; verify the 24h sample includes ≥ 30 vm_session attempts from the **newly flipped** accounts (not just the first 5 from Step 1-4). Q-STEP5-VERIFY in monitoring doc.
- NO-GO rollback: §1.6, rollback target = Step 4 (cookies-clearing was irreversible without re-paste, so flipped accounts may need cookie re-input from operator's cookie vault during rollback — this is a known cost of Step 5)

### Step 6 — 100% of doubao + 100% of deepseek-CN vm_session

- Target: flip **all remaining `local_cookie` doubao + deepseek-CN accounts** to vm_session
- Target share: ~100% of doubao + ~100% of deepseek-CN traffic
- Engine set: `doubao` + `deepseek-CN`
- **30-day observe** (vs 24h for prior steps) — this is the long-tail observation period before Phase 3 (#1118) cleanup is approved
- GO thresholds:
  - All Step 4-5 per-engine + R1.6 thresholds **continuously held over 30 days** (compute Q-3GATE weekly + on each `engine_health_5min` refresh anomaly)
  - **Business gate (per AGENTS.md `Acceptance And Verification Evidence` Business Result Gate)**: Issue #963 User-Symptom Replay — re-run the 3 historical failed queries 184968 / 184971 / 184974 against the production endpoint, verify `ai_responses` for each shows `status='SUCCESS'`, `responseSource='web_ui'`, `attempts[-1].execution_mode='vm_session'`, `rawText` ≥ 200 chars matching prompt topic. Use Q-USER-SYMPTOM-REPLAY in monitoring doc.
- NO-GO rollback at any point during 30-day window: §1.6, rollback target = Step 5 (50/50 split) — keep local_cookie path alive until incident root-caused
- GO outcome: post `EVIDENCE: Step 6 GO + 30d window started` on Epic #1110; at +30d, post `EVIDENCE: Phase 2 100% sustained 30d, ready for #1118 Phase 3 cleanup`; transfer ownership to Issue #1118.

---

## 3. Crash recovery (mid-ramp)

If a VM dies (kernel panic, hypervisor restart, disk full, OOM kill) mid-ramp:

1. **Immediate (within 5 min)**: drop the watchdog Slack alert acknowledgment ("ACK, investigating"); do NOT silence the watchdog channel (#963 lesson: silencing alerts = blind operator).
2. **Triage (within 15 min)**:
   - SSH into VM; if SSH dead, Aliyun console → Force Stop → Force Start
   - Once back, `systemctl status chrome-doubao chrome-deepseek x11vnc websockify tailscaled`
   - Check `journalctl -u chrome-doubao --since "1 hour ago"` for OOM / segfault
3. **Profile session check**: via noVNC, eyeball Chrome — is the doubao / deepseek session still logged in? Or did the crash invalidate the persistent profile?
   - If logged in → resume traffic via `UPDATE llm_accounts SET status='ACTIVE' WHERE vm_id='vm-<dead>'` (watchdog likely marked DISABLED on heartbeat miss)
   - If logged out → operator must noVNC + manual re-login + re-test before flip back to ACTIVE
4. **If re-login fails repeatedly (3+ tries within 30 min)**: treat as infrastructure incident, not step NO-GO; **but** rollback the dead VM's accounts to local_cookie via §1.6 SQL (filtered by `vm_id='<dead-vm>'`) to remove vm_session pressure while investigating.
5. **Redeploy is rarely needed** — the backend is stateless w.r.t. VMs; pool selection skips DISABLED accounts. Only redeploy if a fix lands in `vm_side/runner.py` or `RemoteCDPConnector`.
6. **Post-mortem**: open a Fast Path issue if root cause is one-shot (e.g. disk full, set up disk alarm); upgrade to Full Path issue + Epic if root cause is systemic (e.g. Chrome OOM at peak — needs VM resize from g7.large to g7.xlarge, which is a Phase 2 plan amendment).

---

## 4. Step 6 → Phase 3 transition

After Step 6 + 30-day clean-run:

1. Post `EVIDENCE: 30d sustained, ready for #1118` on Epic #1110 and on Issue #1117 `## Verification Evidence Ledger`.
2. Move ownership to Issue #1118 (Phase 3 cleanup), which will:
   - Deprecate `DOUBAO_COOKIES_JSON` env injection path code (with 30-day deprecation window inside the issue, so total deprecation window = 60 days post Step 6 GO — sufficient to preserve rollback for >1 release cycle)
   - Remove `account_pool.py` `expired_transition_count` ricochet branch for vm_session accounts (it never ran on vm_session per Phase 1 design but is dead code now)
   - Mark `ADAPTER_CONTRACT.md §5.3` (cookie 录入流程) `DEPRECATED-2026-XX-XX` for doubao + deepseek-CN, keep for chatgpt
3. **Do NOT close Issue #1117 yet** — close only after #1118 ships and the deprecation window passes; Issue #1117 closure is the business-success-proven marker for the full ramp (per AGENTS.md `Issue Closure`).
4. Update ADR-016 Status from `Proposed` to `Accepted` and add a `Date Ramp Completed: <YYYY-MM-DD>` line.

---

## 5. References

- Architecture decision: [ADR-016](./ADR/016-vm-per-account-ramp.md)
- Monitoring queries (Prom + SQL + 3-gate computation): [monitoring/vm_per_account_queries.md](./monitoring/vm_per_account_queries.md)
- Optional helper script (operator quick-check): [scripts/vm_ramp/delta_check.py](../scripts/vm_ramp/delta_check.py)
- Adapter contract for execution_mode: [ADAPTER_CONTRACT.md §10.4](./ADAPTER_CONTRACT.md) (engine_health_5min materialized view)
- Epic + child issues: #1110 (Epic), #1117 (this ramp), #1118 (cleanup), #963 (root incident)
- Phase 1 enabler PRs: #1119 (vm_side), #1120 (BrowserConnector refactor), #1121 (RemoteCDPConnector + schema + router + flag), #1122 (Admin UI)
