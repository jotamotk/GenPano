# Genpano AI Lead Multi-Agent Workflow

This document defines how Codex-style agents coordinate Genpano work through
GitHub. It is a repository-level operating procedure. It does not change the
global Codex configuration.

## Core Rule

GitHub is the state source for multi-agent work. Chat may clarify intent, but it
does not replace issues, PRs, review comments, CI logs, or verification records.

The AI Lead does not write business code. It coordinates the work, keeps the
requirement trail intact, reviews outcomes, and drives verification. Worker
Agents implement scoped issues through PRs.

## End-to-End Flow

1. User need
   - AI Lead captures the user goal, affected surface, current symptom, success
     criteria, risk, and live verification target.
   - If anything is uncertain in production, the Lead uses GitHub Actions,
     deploy logs, server diagnostics, or live checks instead of guessing.

2. Epic issue
   - One user request becomes one Epic issue.
   - The Epic links PRD requirement IDs, child Agent task issues, related
     incidents, and the final merge plan.

3. Frontend visualization
   - For user-facing experience work, the Lead first creates a
     Frontend Visualization issue.
   - Frontend is the prototype. The visualization must be a real repo page or
     real component state, not a detached mockup.
   - The Frontend Visualization Agent submits a draft PR with screenshot,
     recording, or Playwright evidence.

4. Page and PRD confirmation
   - The AI Lead reviews the visualization against the user goal.
   - After the page direction is accepted, the Lead records or updates PRD
     requirements with stable IDs.

5. Implementation issues
   - The Lead splits the confirmed work into Backend API, Frontend Integration,
     Pipeline/Data, QA/E2E, Release/CI, or Review issues.
   - Each issue has one owner Agent, a tight allowed scope, a forbidden scope,
     acceptance criteria, verification, dependencies, and handoff instructions.

6. Worker PRs
   - Each Worker opens one branch and one draft PR for one assigned issue.
   - Branch naming: `codex/issue-123-short-slug`.
   - PR title: `[#123] Short imperative title`.
   - Workers do not merge.

7. Review and verification
   - The AI Lead first checks scope.
   - The Review Agent checks bugs, regressions, missing tests, and release risk.
   - The QA/E2E Agent verifies local and live behavior when assigned.
   - The Release/CI Agent diagnoses GitHub Actions, deployment, and server
     failures when assigned.

8. Merge plan and merge
   - The AI Lead prepares a merge plan with order, dependencies, risks, rollback
     notes, and live verification.
   - Merge only after the user explicitly says `pr，merge`.
   - After deployment, verify completed functionality on
     `http://116.62.36.173/` with Playwright E2E when the feature is user
     visible or production-facing.

## Agent Roles

### AI Lead Agent

- Does not edit frontend, backend, worker, test, script, migration, or CI
  implementation files.
- May edit coordination artifacts: PRD docs, issue text, review comments,
  workflow docs, and merge plans.
- Owns requirement clarification, issue decomposition, dependency ordering,
  review orchestration, CI/CD diagnosis, and live verification planning.
- Converts user requests into Epic issues, PRD IDs, and Agent task issues.

### Frontend Visualization Agent

- Turns requirements into real frontend pages or component states.
- Uses the existing frontend and Admin surface conventions.
- May change page/component/style files and lightweight frontend-only empty
  states or mock data needed to visualize the flow.
- Must not change backend, database, scheduler, worker, migration, or CI/CD
  behavior.
- Must provide screenshot, recording, or Playwright evidence.

### Frontend Integration Agent

- Connects confirmed frontend pages to real APIs, state, errors, and tests.
- May change frontend hooks, API clients, page wiring, and frontend tests.
- Must not change backend contracts without a separate Backend API issue.
- If the API is insufficient, comments on the issue and waits for AI Lead
  routing.

### Backend API Agent

- Owns FastAPI routes, auth, aggregation, backend behavior, and backend tests.
- For Admin work, preserves `backend/static/admin.html` and `/admin/api/*`.
- Must document request/response contract changes in the PR.
- Must add targeted backend tests for behavior changes.

### Pipeline/Data Agent

- Owns scheduler, worker, adapter, data repair, and migration work.
- Must include targeted tests, production-risk notes, and rollback notes.
- Must use GitHub Actions or server diagnostics for uncertain deployment or
  runtime behavior.

### QA/E2E Agent

- Verifies only; does not implement business behavior.
- Owns Playwright, local smoke checks, screenshots, traces, and live E2E.
- Reports failures with exact route, request, response, screenshot, and
  reproduction command when possible.

### Release/CI Agent

- Owns GitHub Actions, deploy logs, server diagnostics, and release blockers.
- Uses `gh` or GitHub Actions logs when CI/CD is involved.
- Does not patch business logic unless the AI Lead creates a separate issue.

### Review Agent

- Reviews only; does not write code.
- Prioritizes correctness bugs, behavioral regressions, missing tests, and
  release risk.
- Findings must cite file and line references where possible.

## Issue Model

Issues are task contracts. They must be short enough to execute and complete
enough to prevent interpretation drift.

Required fields for every Agent task issue:

- Goal
- Owner Agent
- Epic
- PRD Source
- PRD Slice
- Allowed Scope
- Forbidden Scope
- Acceptance Criteria
- Verification
- Dependencies
- Context Links
- Handoff

Issue content should link to long-form PRD sections, docs, screenshots, code
paths, prior issues, and prior PRs. It should not copy large PRD sections.

If the issue conflicts with code reality, the Worker must stop and comment on
the issue. The AI Lead decides whether to update the issue, update the PRD,
split more work, or stop the task.

## PRD Linkage

PRD requirements are the upstream source of truth. Each actionable requirement
needs a stable ID:

```text
PRD-<AREA>-<FEATURE>-<NUMBER>
PRD-ADM-SCHED-001
PRD-APP-DASH-002
PRD-PIPELINE-DISPATCH-003
```

Agent issues must map their scope to PRD requirements:

```md
## PRD Source
- PRD: docs/PRD_ADMIN_SCHEDULER.md
- Requirement IDs:
  - PRD-ADM-SCHED-001
- Epic: #120

## PRD Slice
Included:
- Frontend display for pending / dispatched / failed
- Loading, empty, and error states

Excluded:
- Backend dispatch logic, assigned to #124
- Live E2E, assigned to #126

## Acceptance Criteria Mapping
| PRD Criteria | This Issue |
| --- | --- |
| Show pending / dispatched / failed | Yes |
| Show failed reason | Yes, frontend only |
| Brand filter | No, backend/API issue #124 |
| Live Playwright E2E | No, QA issue #126 |
```

When a PRD changes, the AI Lead must update related issues and comment with:

- changed PRD ID
- commit or PR where it changed
- impacted issues
- new or removed requirements
- whether existing PRs need updates

## PR Model

Each PR implements one issue.

Required PR sections:

- Linked Issue
- Agent Role
- Summary
- Scope
- Verification
- Risks
- Handoff
- PRD Coverage

Use `Refs #123` while the PR is under review. Use `Closes #123` only when the PR
is accepted for merge.

PRs start as draft. A Worker marks the PR ready only when the issue's
verification checklist is complete or any missing verification is clearly
explained as blocked.

## Review Rules

AI Lead scope review:

- Does the PR solve exactly one issue?
- Does it stay inside Allowed Scope?
- Does it avoid Forbidden Scope?
- Does it preserve Admin boundaries when Admin is touched?
- Does it include required verification evidence?

Review Agent technical review:

- correctness bugs
- regressions
- missing tests
- unsafe contracts
- release risks

QA/E2E review:

- local smoke evidence
- Playwright evidence
- live `http://116.62.36.173/` evidence when applicable
- exact repro for failures

Release/CI review:

- failing GitHub Actions jobs
- deploy logs
- server diagnostics
- migration/deploy blockers

Actionable feedback must live in GitHub review comments and be resolved there.

## Merge Rules

Do not merge PRs that:

- have no linked issue
- are not mapped to PRD IDs when product behavior is involved
- modify unrelated scope
- have unexplained failing CI
- lack required verification
- skip needed live Playwright E2E for production-facing changes

The AI Lead produces a merge plan before merge:

- PR order
- dependency graph
- CI status
- risks
- rollback notes
- post-merge live verification

Only merge when the user explicitly says `pr，merge`.

## Status Labels

Recommended issue labels:

- `agent:lead`
- `agent:frontend-visualization`
- `agent:frontend-integration`
- `agent:backend-api`
- `agent:pipeline-data`
- `agent:qa-e2e`
- `agent:release-ci`
- `agent:review`
- `type:epic`
- `type:visualization`
- `type:implementation`
- `type:bugfix`
- `type:e2e`
- `type:prd`
- `status:briefing`
- `status:ready`
- `status:in-progress`
- `status:blocked`
- `status:review`
- `status:verified`
- `status:merged`
- `area:admin`
- `area:app`
- `area:scheduler`
- `area:dashboard`
- `area:pipeline`

## Lead Status Report

The AI Lead should report Epic state in this shape:

```md
| Issue | Agent | PR | Status | Blocker | Next |
| --- | --- | --- | --- | --- | --- |
| #121 | frontend-visualization | #130 | review | none | Lead scope review |
| #122 | backend-api | - | blocked | waiting page confirmation | hold |
| #123 | qa-e2e | - | ready | depends on #130 | wait |
```
