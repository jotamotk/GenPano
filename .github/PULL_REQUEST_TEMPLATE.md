## Linked Work

- Issue: Refs #
- Coordination issue, if any: #
- Path: fast | full
- PRD IDs, if product behavior is involved:
  - PRD-AREA-FEATURE-001
- Parent Business Goal:
- Final Success Evidence:

## Owner Hat

<!-- lead | frontend-visualization | frontend-integration | backend-api | pipeline-data | qa-e2e | release-ci | review | pruning -->

## Summary

- 

## Scope

Changed:
- 

Not changed:
- 

## Current State Update

- [ ] Linked issue `## Current State` is current.
- [ ] Linked issue `## Decisions` is current, or no decisions changed.
- [ ] Linked issue `## Closure` is ready if this PR should close the issue.

## PRD Coverage

| PRD Criteria | Covered Here | Notes |
| --- | --- | --- |
|  |  |  |

Use `none - no product behavior change` when this is docs-only, tooling-only, or a fast-path bugfix that does not change product requirements.

## Acceptance Matrix

| AC | Source | User Path | Machine Check | Evidence Required | Status |
| --- | --- | --- | --- | --- | --- |
| AC-1 |  |  |  |  | pending |

Business Result Gate, if applicable:
- Exact business object/path:
- Required final state:
- Required artifact/readback:
- Evidence source:

Coverage gaps:
-

## Root Cause Gate

Use `not an incident - reason` when this PR is not fixing a reported failure.

- Direct trigger:
- Underlying product/system root cause:
- Evidence proving it:
- Alternatives ruled out:
- Unknowns that remain:
- Why this fix should produce the final business outcome, not only remove the current error:
- Classification: incident fix | diagnostics/instrumentation only | not an incident

## Failure Chain Review

- Current failure layer:
- Next likely failure mode:
- Guard or evidence for the next layer:
- Live retry/account/session preflight needed? yes/no:
- If yes, current row status / retry_count / account-session state / post-retry consequence:
- Expected final success evidence:

## Verification Evidence Ledger

Every checked item needs command or run URL, exit/conclusion, key output, scope, artifact/link when available, and commit SHA. No evidence means unchecked.

| Check | Command/Run | Exit/Conclusion | Key Output | Scope Covered | Artifact/Link | Commit |
| --- | --- | --- | --- | --- | --- | --- |
| Local |  |  |  |  |  |  |
| CI |  |  |  |  |  |  |

## User-Symptom Replay

Required for user-reported bugs and UI-visible changes. Use `not applicable - reason` only when there is no user-visible path.

- Exact route/row/brand/query/request/action:
- Expected visible result:
- E2E tier used: Tier 0 | Tier 1 | Tier 2 | Tier 3
- Evidence or blocker:
- Completion state: Business success proven | Diagnostic progress only | Blocked / decision needed

## Test Integrity Statement

- Test files added/modified/deleted:
- Assertions removed or relaxed:
- Skips/xfails added:
- Exceptions swallowed or converted to success:
- Acceptance rows not verified:

## Verification Summary

- [ ] Local tests:
- [ ] Screenshot/video:
- [ ] Playwright:
- [ ] CI:
- [ ] Live `http://116.62.36.173/` (test environment) check if live-facing:

## Risks

- 

## Handoff

- 

## Lead Review Checklist

- [ ] PR solves one linked issue or approved docs/process change.
- [ ] PR stays inside the issue's Allowed Scope.
- [ ] PR avoids the issue's Forbidden Scope.
- [ ] PRD Coverage matches the linked issue's Acceptance Matrix when product behavior is involved.
- [ ] Acceptance Matrix rows have sources and no unaccepted coverage gaps.
- [ ] Business Result Gate is complete for live incidents or existing-object outcomes.
- [ ] Incident fixes include Root Cause Gate and Failure Chain Review, or are explicitly diagnostics/instrumentation only.
- [ ] Verification Evidence Ledger includes command/run, exit/conclusion, key output, scope, artifact/link when available, and commit SHA.
- [ ] User-Symptom Replay is present for user-reported bugs or explicitly blocked.
- [ ] Test Integrity Statement is complete.
- [ ] Current PR head SHA has required CI passing or an accepted blocker.
- [ ] Linked issue body is current.
- [ ] Admin work preserves `backend/static/admin.html` and `/admin/api/*` boundaries.
