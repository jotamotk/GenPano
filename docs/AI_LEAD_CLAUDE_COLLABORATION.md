# AI Lead and Claude Code Collaboration

This document defines how the Genpano AI Lead coordinates work with Claude Code.
It extends `AGENTS.md` and `docs/AI_LEAD_WORKFLOW.md`; it does not replace
GitHub issues, pull requests, review comments, CI/CD runs, or PRD documents.

## Purpose

Claude Code can participate as a Worker, QA, Review, Release/CI, or
Frontend Visualization agent. The AI Lead remains responsible for requirement
clarity, issue decomposition, PRD linkage, merge sequencing, deployment
follow-through, and live Playwright verification.

The collaboration rule is simple:

- AI Lead owns the system of work.
- Claude Code owns only the assigned issue slice.
- GitHub is the durable state.
- Code and live behavior are the reality check.

## Source Of Truth Order

When sources disagree, use this order and stop for AI Lead routing when needed:

1. `AGENTS.md`
2. `docs/AI_LEAD_WORKFLOW.md`
3. This document
4. Current PRD docs and stable PRD requirement IDs
5. GitHub Epic issue and child Agent task issue
6. Current code, tests, CI/CD logs, deploy logs, and live product behavior

If issue text conflicts with code reality, Claude Code must comment on the
issue or PR and wait for AI Lead direction before changing scope.

## When To Use Claude Code

The AI Lead can assign Claude Code when the work has a clear owner role, allowed
scope, forbidden scope, verification checklist, and handoff target.

Good Claude Code assignments:

- implementing one scoped frontend integration issue
- implementing one backend API issue with targeted tests
- investigating one CI/CD or deploy failure
- running QA/E2E verification and reporting exact failures
- reviewing one PR for bugs, regressions, missing tests, and release risk

Poor Claude Code assignments:

- "fix everything in this area"
- implementation without a linked issue
- cross-cutting refactors mixed into a product task
- PR or merge decisions that bypass AI Lead
- Admin work that has not confirmed the real Admin shell and route boundary

## Required Assignment Fields

Every Claude Code assignment must be represented by a GitHub Agent task issue
or an issue comment with these fields:

- Owner Agent
- Assigned Tool: `Claude Code`
- Epic
- PRD Source and requirement IDs
- Goal
- Allowed Scope
- Forbidden Scope
- Acceptance Criteria
- Verification
- Dependencies
- Branch
- PR target
- Handoff expectations

One Claude Code task maps to one owner role, one branch, and one PR.

## Branch And PR Rules

- The AI Lead assigns the branch in the issue before implementation starts.
- If no branch is assigned, Claude Code asks on the issue before making durable
  GitHub changes.
- Repository default branch shape is `codex/issue-123-short-slug`.
- A `claude/issue-123-short-slug` branch is allowed only when the issue says
  Claude Code owns that branch.
- Worker PRs start as draft PRs.
- Claude Code must not merge PRs.
- Claude Code must not mark a PR ready unless the issue or AI Lead explicitly
  delegates that readiness action.
- Use `Refs #123` before final acceptance.
- Use `Closes #123` only when the AI Lead approves the PR for merge.

## Claude Code Pre-Flight Receipt

Before editing, Claude Code should post or include this receipt in the issue or
PR:

```md
## Claude Code Pre-Flight Receipt

- Owner Agent:
- Assigned Tool: Claude Code
- Branch:
- Linked Epic:
- Linked Agent Task:
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

## Implementation Handoff

Claude Code PRs must include:

- linked issue and Epic
- owner Agent role
- changed files
- scope kept and scope explicitly not changed
- PRD coverage table
- local verification output
- Playwright evidence if UI-visible
- CI/CD status or blocker
- risk and rollback notes
- exact next handoff target

Suggested PR handoff:

```md
## Claude Code Handoff

- Linked Issue:
- Agent Role:
- Summary:
- Changed Files:
- Not Changed:
- Verification:
- Screenshots/Traces:
- CI/CD:
- Live Check:
- Risks:
- Rollback:
- Needs AI Lead Decision:
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
Code or the Release/CI Agent should use GitHub Actions logs, deploy logs, server
diagnostics, or live checks and return exact evidence.

Release/CI handoff must include:

- workflow name and run URL
- commit SHA
- failing job and step
- log excerpt summary
- suspected cause
- whether this is CI-only, deploy-only, or business-code related
- recommended next Agent issue if business code changes are needed

## Conflict Handling

If another agent or the user changed the same files:

- do not revert those changes
- inspect the diff before editing
- keep the assignment inside the issue scope
- comment on the issue or PR when scope, branch, or ownership is no longer safe

If Claude Code finds required work outside its issue:

1. stop expanding the PR
2. comment with the discovered gap
3. recommend a new Agent task issue
4. wait for AI Lead routing

## AI Lead Assignment Comment Template

```md
## AI Lead Assignment

- Assigned Tool: Claude Code
- Owner Agent:
- Branch:
- PR Target: draft PR
- Epic:
- Agent Task:
- PRD Source:
- Allowed Scope:
- Forbidden Scope:
- Required Verification:
- Handoff:

Claude Code should post the Pre-Flight Receipt before edits. Do not merge.
Escalate any scope or source-of-truth conflict back to AI Lead.
```

## AI Lead Completion Checklist

Before merge or user-facing completion, the AI Lead verifies:

- Epic and child issue links are current
- PRD IDs are linked
- PR stays inside one issue scope
- required local tests are present
- required Playwright or QA evidence is present
- CI/CD is green or the blocker is explicitly accepted
- deployment path is known
- production-facing behavior is verified on `http://116.62.36.173/`
- live Playwright E2E evidence is attached when applicable
