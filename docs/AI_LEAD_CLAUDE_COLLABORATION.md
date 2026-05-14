# Codex Lead And Claude Code Collaboration

This document defines how the Genpano Codex coordinator assigns work to Claude
Code. It extends `AGENTS.md` and `docs/AI_LEAD_WORKFLOW.md`; it does not replace
GitHub issues, pull requests, review comments, CI/CD runs, or PRD documents.

## Purpose

Claude Code is an implementation or verification tool assigned to a scoped
deliverable. It is not a parallel source of authority. The Codex Lead remains
responsible for requirement clarity, issue shape, PRD linkage, merge sequencing,
deployment follow-through, and live Playwright verification.

The collaboration rule is simple:

- Codex owns the system of work.
- Claude Code owns only the assigned deliverable issue or issue comment.
- GitHub is the durable state.
- Code and live behavior are the reality check.
- Human Input is user-owned intake and acceptance state; Claude Code works only
  from the scoped issue or assignment that the Lead creates from it.

## Source Of Truth Order

When sources disagree, use this order and stop for Codex Lead routing when
needed:

1. `AGENTS.md`
2. `docs/AI_LEAD_WORKFLOW.md`
3. This document
4. Current PRD docs and stable PRD requirement IDs
5. GitHub issue execution contract
6. Current code, tests, CI/CD logs, deploy logs, and live product behavior

If issue text conflicts with code reality, Claude Code must comment on the
issue or PR and wait for Codex Lead direction before changing scope.

## When To Use Claude Code

The Lead can assign Claude Code when the work has a clear deliverable, owner
hat, allowed scope, forbidden scope, verification checklist, and handoff target.

Good Claude Code assignments:

- implementing one scoped frontend integration deliverable
- implementing one backend API deliverable with targeted tests
- investigating one CI/CD or deploy failure
- running QA/E2E verification and reporting exact failures
- reviewing one PR for bugs, regressions, missing tests, and release risk
- producing a pruning report with deletion candidates and evidence, without
  changing files

Poor Claude Code assignments:

- "fix everything in this area"
- "handle this Human Input" without triage, accepted disposition, child issue,
  or assignment comment
- implementation without a linked issue or execution contract
- cross-cutting refactors mixed into a product task
- PR or merge decisions that bypass Codex Lead
- Admin work that has not confirmed the real Admin shell and route boundary
- deleting stale artifacts directly from a pruning assignment without a scoped
  cleanup issue

## Required Assignment Fields

Every Claude Code assignment must be represented by a GitHub issue or issue
comment with these fields:

- Source Human Input issue, when applicable
- Deliverable
- Owner Hat
- Assigned Tool: `Claude Code`
- Path: `fast` or `full`
- PRD Source and requirement IDs when product behavior is involved
- Goal
- Allowed Scope
- Forbidden Scope
- Contract Snapshot
- Acceptance Matrix with source for every row
- Coverage Gaps, if any
- Verification Evidence Ledger expectations
- User-Symptom Replay target when user-reported or UI-visible
- Test Integrity expectations
- Dependencies
- Branch
- PR target
- Handoff expectations

One Claude Code assignment maps to one deliverable, one branch, and one PR.

Claude Code must not make tests pass by deleting assertions, adding skips,
weakening checks, swallowing exceptions, or moving verification away from the
assigned user path. If a test appears obsolete, report it as `BLOCKER` or
`PRD-CHANGE` and wait for Codex Lead or product-owner direction.

## Branch And PR Rules

- The Lead assigns the branch in the issue before implementation starts.
- If no branch is assigned, Claude Code asks on the issue before making durable
  GitHub changes.
- Repository default branch shape is `codex/issue-123-short-slug`.
- A `claude/issue-123-short-slug` branch is allowed only when the issue says
  Claude Code owns that branch.
- Worker PRs start as draft PRs when verification is incomplete.
- Claude Code may merge PRs when the Lead has explicitly delegated that action
  (for example via a goal directive or in the linked issue). When merging,
  Claude Code must verify CI is green and the Acceptance Matrix is satisfied
  before clicking merge; if either is missing, surface the blocker instead of
  merging.
- Claude Code must not mark a PR ready unless the issue or Lead explicitly
  delegates that readiness action.
- Use `Refs #123` before final acceptance.
- Use `Closes #123` only when the issue closure type is `Completed` and the
  Lead approves merge-to-close.

## Claude Code Pre-Flight Receipt

Before editing, Claude Code should post or include this receipt in the issue or
PR. Keep it concise; it is a readiness signal, not a diary.

```md
## Claude Code Pre-Flight Receipt

- Deliverable:
- Owner Hat:
- Assigned Tool: Claude Code
- Path:
- Branch:
- Linked Issue:
- PRD Source:
- Files/docs read:
  - AGENTS.md
  - docs/AI_LEAD_WORKFLOW.md
  - docs/AI_LEAD_CLAUDE_COLLABORATION.md
  - <relevant PRD/docs>
- Current code entrypoints verified:
- Allowed Scope understood:
- Forbidden Scope understood:
- Acceptance Matrix source coverage:
- Expected Evidence Ledger rows:
- User-Symptom Replay target:
- Test Integrity risk:
- Missing context or blocker:
```

If any field is unclear, Claude Code should stop and comment instead of
guessing.

## Admin-Specific Pre-Flight

Before Claude Code changes Admin UI or Admin API behavior, it must verify and
state:

- current branch is not `main`
- the page is the orange Admin surface under `/admin`
- `backend/static/admin.html` is the Admin shell unless the issue proves
  otherwise
- Admin APIs stay under `/admin/api/*`
- no second Admin frontend is created under `frontend/src/admin/**`,
  `frontend/src/pages/admin/**`, `frontend-admin/**`, or similar
- the relevant route, request path, status, and payload are captured when the
  work starts from an incident

For Admin endpoint incidents, verify the canonical `/api/admin/...` route, the
legacy `/admin/api/...` path, and any nginx-rewritten `/api/...` path when that
distinction is relevant.

## Issue Comment Standard

Claude Code issue comments follow the repository writing standard:

- lead with conclusion
- include exact evidence
- end with next action or needed decision
- avoid status narration that does not change state, risk, decision, evidence,
  or next action

Use prefixes as appropriate: `QUESTION`, `DECISION`, `BLOCKER`, `STATUS`,
`PRD-CHANGE`, `EVIDENCE`.

When blocked, report the blocker plainly and early. Do not hide uncertainty,
invent context, or keep working outside the assigned contract.

## Implementation Handoff

Claude Code PRs must include:

- linked issue
- owner hat
- changed files
- scope kept and scope explicitly not changed
- PRD coverage table when product behavior is involved
- Acceptance Matrix status
- Verification Evidence Ledger with command/run, exit/conclusion, key output,
  scope, artifact/link, and commit SHA
- User-Symptom Replay evidence if user-reported or UI-visible
- Test Integrity Statement listing test files changed, assertions relaxed,
  skips added, exceptions swallowed, and unverified acceptance rows
- CI/CD status or blocker
- risk and rollback notes
- exact next handoff target

When the assignment comes from Human Input, the handoff target is the Lead. The
Lead owns posting the final `Ready for User Acceptance` comment on the Human
Input issue after merge, deploy, and live verification evidence are complete.

Suggested PR handoff:

```md
## Claude Code Handoff

- Linked Issue:
- Owner Hat:
- Summary:
- Changed Files:
- Not Changed:
- Acceptance Matrix:
- Verification Evidence Ledger:
- Screenshots/Traces:
- User-Symptom Replay:
- Test Integrity:
- CI/CD:
- Live Check:
- Risks:
- Rollback:
- Needs Lead Decision:
```

## Review And QA Handoff

For review-only assignments, Claude Code must not patch code. It reports:

- findings first, ordered by severity
- file and line references
- reproduction steps
- missing tests or verification gaps
- open questions

For QA/E2E assignments, Claude Code must not implement business behavior. It
reports:

- base URL
- exact scenario, including route, row, brand, query, request, payload, action,
  and expected visible result when available
- commands run
- exit codes or CI job conclusions
- screenshots, traces, or request details
- pass/fail result
- failed request URL, status, response body summary, and timestamp when
  available
- commit SHA tested

For pruning assignments, Claude Code must not delete files or change workflow
rules. It reports:

- candidate path or rule
- candidate type: debug script, legacy directory, dead code, prototype, runbook,
  template, or workflow clause
- reference evidence from search, CI/workflow usage, docs links, and open
  issue/PR dependencies
- recommendation: `Delete`, `Keep`, `Replace`, or `Needs Decision`
- risk and restore path
- proposed follow-up issue when deletion is appropriate

## Release And CI Handoff

When CI/CD, deployment, or live test-environment state is uncertain, do not
guess. Claude Code or the Release/CI hat should use GitHub Actions logs,
deploy logs, server
diagnostics, or live checks and return exact evidence.

Release/CI handoff must include:

- workflow name and run URL
- commit SHA
- failing job and step
- log excerpt summary
- suspected cause
- whether this is CI-only, deploy-only, or business-code related
- recommended next issue if business code changes are needed

## Conflict Handling

If another tool or the user changed the same files:

- do not revert those changes
- inspect the diff before editing
- keep the assignment inside the issue scope
- comment on the issue or PR when scope, branch, or ownership is no longer safe

If Claude Code finds required work outside its issue:

1. stop expanding the PR
2. comment with the discovered gap
3. recommend a new deliverable issue or PRD-change request
4. wait for Codex Lead routing

## Assignment Comment Template

```md
## Codex Lead Assignment

- Assigned Tool: Claude Code
- Deliverable:
- Owner Hat:
- Path:
- Branch:
- PR Target:
- Linked Issue:
- PRD Source:
- Allowed Scope:
- Forbidden Scope:
- Contract Snapshot:
- Required Verification:
- Handoff:

Claude Code should post the Pre-Flight Receipt before edits. Do not merge.
Escalate any scope or source-of-truth conflict back to Codex Lead.
```

## Completion Checklist

Before merge or user-facing completion, the Codex Lead verifies:

- linked issue body is current
- source Human Input issue is linked when the work started from user intake
- PRD IDs are linked when product behavior is involved
- Acceptance Matrix is source-backed and complete
- Coverage Gaps are empty or accepted
- PR stays inside one deliverable scope
- required local tests are present
- Verification Evidence Ledger is complete
- user-reported symptoms have targeted replay evidence or an explicit blocker
- Test Integrity Statement is present
- required Playwright or QA evidence matches the selected E2E tier
- CI/CD is green or the blocker is explicitly accepted
- deployment path is known
- live-facing behavior is verified on the test environment `http://116.62.36.173/`
- live Playwright E2E evidence is attached when applicable
- Human Input has a `Ready for User Acceptance` record when applicable
- issue closure type and closure record are ready; Human Input remains open for
  user closure unless closure was explicitly delegated
