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

Poor Claude Code assignments:

- "fix everything in this area"
- implementation without a linked issue or execution contract
- cross-cutting refactors mixed into a product task
- PR or merge decisions that bypass Codex Lead
- Admin work that has not confirmed the real Admin shell and route boundary

## Required Assignment Fields

Every Claude Code assignment must be represented by a GitHub issue or issue
comment with these fields:

- Deliverable
- Owner Hat
- Assigned Tool: `Claude Code`
- Path: `fast` or `full`
- PRD Source and requirement IDs when product behavior is involved
- Goal
- Allowed Scope
- Forbidden Scope
- Contract Snapshot
- Acceptance Criteria
- Verification
- Dependencies
- Branch
- PR target
- Handoff expectations

One Claude Code assignment maps to one deliverable, one branch, and one PR.

## Branch And PR Rules

- The Lead assigns the branch in the issue before implementation starts.
- If no branch is assigned, Claude Code asks on the issue before making durable
  GitHub changes.
- Repository default branch shape is `codex/issue-123-short-slug`.
- A `claude/issue-123-short-slug` branch is allowed only when the issue says
  Claude Code owns that branch.
- Worker PRs start as draft PRs when verification is incomplete.
- Claude Code must not merge PRs.
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
- Expected verification:
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
- local verification output
- Playwright evidence if UI-visible
- CI/CD status or blocker
- risk and rollback notes
- exact next handoff target

Suggested PR handoff:

```md
## Claude Code Handoff

- Linked Issue:
- Owner Hat:
- Summary:
- Changed Files:
- Not Changed:
- Verification:
- Screenshots/Traces:
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
- exact scenario
- commands run
- screenshots, traces, or request details
- pass/fail result
- failed request URL, status, response body summary, and timestamp when
  available

## Release And CI Handoff

When CI/CD, deployment, or production state is uncertain, do not guess. Claude
Code or the Release/CI hat should use GitHub Actions logs, deploy logs, server
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
- PRD IDs are linked when product behavior is involved
- PR stays inside one deliverable scope
- required local tests are present
- required Playwright or QA evidence is present
- CI/CD is green or the blocker is explicitly accepted
- deployment path is known
- production-facing behavior is verified on `http://116.62.36.173/`
- live Playwright E2E evidence is attached when applicable
- issue closure type and closure record are ready
