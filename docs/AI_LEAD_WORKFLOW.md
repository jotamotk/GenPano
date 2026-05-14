# Genpano Codex Coordination Workflow

This document defines how Codex-style agents coordinate Genpano work through
GitHub. It is a repository-level operating procedure. It does not change the
global Codex configuration.

## Core Rule

GitHub is the durable state source for Genpano work. Chat may clarify intent,
but it does not replace issues, PRs, review comments, CI logs, deploy logs, or
verification records.

The workflow optimizes for low-noise execution. An issue should let a future
Codex session understand the core problem, current judgment, decision history,
and next action without reading a long chat transcript.

## Real Topology

There is one Codex coordinator. The named agents are hats that the coordinator
wears for different responsibilities:

- `lead`: requirements, issue shaping, PRD linkage, merge sequencing, release
  planning, and live verification planning
- `frontend-visualization`: real frontend prototype or page-state visualization
- `frontend-integration`: frontend wiring to real APIs, state, and tests
- `backend-api`: FastAPI behavior, auth, aggregation, backend tests
- `pipeline-data`: scheduler, worker, adapters, migrations, repair scripts
- `qa-e2e`: verification only, including local smoke and Playwright
- `release-ci`: GitHub Actions, deploy logs, server diagnostics, CD hygiene
- `review`: review only, focused on bugs, regressions, missing tests, and risk
- `pruning`: subtraction review for stale repo artifacts, dead code, debug
  tools, obsolete prototypes, and outdated workflow rules

The hats do not imply separate people. Do not create one issue per hat. Create
issues for deliverables that can be accepted, merged, closed, or abandoned.

When Codex is wearing the `lead` hat, it does not edit business implementation
files. It may edit PRDs, GitHub issues, review comments, merge plans,
verification plans, workflow docs, and templates. Codex may switch into a worker
hat only after the issue has a clear execution contract.

## Intake And Path Selection

Every user-reported problem, incident, requirement gap, blocker, release risk,
or workflow gap must be captured in GitHub as a new issue or linked to an
existing issue before durable work continues.

At intake, choose one path.

### Fast Path

Use Fast Path for small, bounded changes:

- one affected product or engineering area
- no PRD requirement change
- no public API, schema, migration, scheduler, worker, CI/CD, or deploy
  contract change across areas
- clear reproduction or acceptance check
- one issue, one branch, one PR

Fast Path issue shape:

- Goal
- Current State
- Decisions
- Execution Contract
- Acceptance Criteria
- Verification
- Closure

Fast Path should not create an Epic, Frontend Visualization issue, or role-based
child issue unless that artifact directly improves execution.

### Full Path

Use Full Path when any condition is true:

- new user-facing workflow or material UX direction
- PRD requirement or product contract may change
- API, database, migration, scheduler, worker, CI/CD, or deployment behavior
  crosses area boundaries
- multiple deliverables must be sequenced
- production risk or rollback path needs explicit planning

Full Path issue shape:

1. Epic or coordination issue records the user goal and final merge plan.
2. User-facing work gets a Frontend Visualization deliverable first.
3. PRD changes happen only after product-owner decision.
4. Implementation is split by deliverable, not by hat.
5. Each deliverable issue has one branch and one PR.
6. After merge, production-facing behavior is verified on
   `http://116.62.36.173/` with Playwright E2E when applicable.

### Escalation From Fast To Full

Escalate a Fast Path issue to Full Path when investigation finds:

- the acceptance behavior is not product-owner-approved
- a PRD change is needed
- the fix requires contract, schema, migration, scheduler, worker, deploy, or
  CI/CD changes outside the original area
- more than one deliverable needs separate acceptance
- verification cannot be completed without production-risk planning

Escalation requires a `STATUS` comment summarizing the new fact, the reason Fast
Path is no longer safe, and the proposed Full Path shape.

## Issue Body As Current Fact Source

The issue body is the current fact source. Comments are discussion and audit
trail. When state changes materially, update the body instead of leaving the
new truth buried in comments.

Recommended issue body sections:

```md
## Goal

## Current State

## Decisions

## Execution Contract

## Acceptance Criteria

## Verification

## Closure
```

`## Current State` is not a history log. It states what is true now:

- selected path: `fast` or `full`
- known root cause or current hypothesis
- current branch or PR
- current blocker, if any
- next action

`## Decisions` records settled decisions only:

- selected product behavior
- path selection
- scope inclusion or exclusion
- accepted risk
- closure decision

## Execution Contract

Downstream issues must inline their execution contract. A link to another issue
or PRD is helpful context, but not enough by itself.

Recommended contract:

```md
## Execution Contract

- Path: fast | full
- Owner Hat:
- Branch:
- Allowed Scope:
  -
- Forbidden Scope:
  -
- Contract Snapshot:
  -
- Acceptance Criteria:
  -
- Verification:
  -
- Dependencies:
  -
- Handoff:
  -
```

`Contract Snapshot` is the frozen instruction for this issue. It should include
the relevant user-facing behavior, API shape, data rule, or PRD slice that the
worker should execute without chasing unresolved upstream comments.

## Issue Comment Writing Standard

Issue comments should be judgment-first. They should make it clear why the
reader should care.

Use these prefixes as writing guidance:

- `QUESTION`: needs product-owner, user, CI/CD, server, or GitHub input
- `DECISION`: records a settled decision
- `BLOCKER`: identifies what prevents safe progress
- `STATUS`: records a material state change
- `PRD-CHANGE`: requests product-owner decision on PRD conflict
- `EVIDENCE`: records verification proof

Default comment shape:

```md
STATUS: One-sentence conclusion.

Evidence:
- Exact fact, link, route, file, PR, run id, screenshot, or log summary.
- Exact fact.

Next:
- Next action.
- Owner or needed decision.
```

Blocker comment shape:

```md
BLOCKER: What is blocked and why.

Impact:
- What cannot safely continue.

Options:
- Option A and tradeoff.
- Option B and tradeoff.

Need:
- Specific decision, access, server help, CI/CD action, or user input.
```

Question comment shape:

```md
QUESTION: Need decision on <topic>.

Questions:
- First question.
- Second question.

Default if unanswered:
- The assumption Codex will use, or "pause until answered" if no safe default.
```

Do not post a `STATUS` comment just to narrate work performed. If the comment
does not change state, risk, decision, evidence, or next action, keep it out of
the issue.

## PRD Change Protocol

PRD is product-owner-approved fact, not an immutable artifact. Code and live
behavior can reveal that the PRD is incomplete or wrong, but Codex must not
silently rewrite product intent.

When a PRD conflict appears, post:

```md
PRD-CHANGE: <one-sentence requested decision>

PRD Text:
- File/section/requirement ID:
- Current wording:

Observed Reality:
- Code, test, product behavior, data, or operator evidence:

Conflict:
- Why both cannot be true.

Recommended Decision:
- Proposed product-owner decision.

Impact:
- Issues/PRs/tests affected:
```

Implementation waits for the decision unless there is a safe, reversible
diagnostic step that does not choose product behavior.

## Human Input Channel

The fixed Human Input issue is the product-owner inbox. It is not a task, not a
PRD, and not a status workflow item.

Rules:

- Keep it open permanently.
- Do not assign it to a branch or PR.
- Do not close it when a child task completes.
- Do not implement directly from a vague raw note.
- Do not treat it as product fact until a scoped issue or PRD decision exists.

Each raw entry needs a triage receipt:

```md
TRIAGE: <item id or short quote> classified as <bug | feature change | new requirement | question/idea | needs clarification>.

Disposition:
- Converted to: #123
- PRD decision requested in: #124
- Waiting for clarification from:
- No action because:

Receipt:
- Original note:
- Last updated:
```

The target issue or PRD-change request becomes the executable source. The Human
Input issue remains the inbox ledger.

## Workflow Improvement Notes

Codex should propose workflow improvements when it repeatedly hits friction.
Every proposal must self-classify:

- `Efficiency`: removes repeated low-value work, waiting, duplicate status, or
  template noise
- `Constraint`: relaxes a gate, forbidden scope, approval point, or authority
  boundary
- `Reliability`: reduces stale state, missed evidence, bad closure, or wrong
  routing
- `Topology Correction`: fixes a rule that assumes independent agents instead
  of one coordinator wearing hats

Recommended note:

```md
WORKFLOW-IMPROVEMENT: <one-sentence proposal>

Class:
- Efficiency | Constraint | Reliability | Topology Correction

Observed Friction:
- What happened, with issue or PR links.

Proposed Change:
- Specific rule or template change.

Risk Check:
- For Constraint proposals, what risk did the old rule prevent?
```

Efficiency and Reliability notes can accumulate in a governance/process issue.
Constraint changes need product-owner approval before becoming rules.

## Pruning Hat And Automation

The pruning hat is responsible for making subtraction visible. It does not
directly delete by automation. It periodically produces a report of candidates
that may be deleted, kept, replaced, or escalated for a decision.

Use a Codex automation for recurring pruning review when available. The
automation should run as a reporting job against the repo and post to a fixed
governance or pruning inbox issue. It must not commit, open cleanup PRs, close
issues, or delete files automatically.

Recommended cadence starts at every two weeks while the repo is changing
quickly. Once the backlog stabilizes, reduce the cadence to monthly.

### Pruning Scope

Look for:

- debug scripts and one-off diagnostics that no longer have an open incident
- legacy directories and removed product surfaces
- dead code or exports with no references
- unused prototypes and detached mockups
- stale runbooks, old verification notes, and superseded docs
- obsolete issue templates, labels, or AGENTS.md / workflow clauses
- temporary flags, debug endpoints, or repair scripts left after release

### Pruning Report

The automation output should be short and decision-oriented:

```md
## Pruning Report

| Candidate | Type | Evidence | Recommendation | Risk | Next |
| --- | --- | --- | --- | --- | --- |
| scripts/debug_x.py | debug script | no rg refs; no workflow refs | Delete | low | fast-path cleanup issue |
| admin_console/ | legacy dir | still referenced in docs | Needs Decision | medium | ask product owner |
```

Each candidate needs evidence:

- `rg` or structured search references
- workflow, CI, script, or import usage
- docs links and open issue/PR dependencies
- owner or likely owner, if known
- behavior risk and restore path

Recommendations:

- `Delete`: no known references, low risk, git history is enough restore path
- `Keep`: still referenced or intentionally retained
- `Replace`: current artifact should be folded into a better doc/script/path
- `Needs Decision`: product, incident, compliance, or runtime risk needs human
  judgment

### Deletion Rules

Pruning reports are not permission to delete.

- Low-risk docs, debug scripts, and detached prototypes can become Fast Path
  cleanup issues.
- Runtime code, CI/CD, migrations, data repair scripts, production routes,
  security-sensitive files, and product behavior removals require a scoped issue
  with explicit verification.
- Do not create archive directories as a default. If git history can recover the
  artifact, delete it. Archive only for compliance, audit, or active incident
  evidence.
- If a candidate has open issue/PR dependencies, comment on the owning issue
  instead of deleting.

## Issue Closure Protocol

Every closed issue needs a closure record. Use one closure type.

### Completed

Codex may close when required verification has passed.

Required record:

- linked PR or commit
- acceptance checklist result
- verification evidence
- live Playwright or production evidence when applicable
- final state

### Won't Do

Needs product-owner confirmation unless the issue is an obvious mistaken Codex
artifact.

Required record:

- reason
- deciding person
- accepted risk
- alternative path or "none"

### Split/Superseded

Prefer product-owner confirmation when product scope changes.

Required record:

- replacement issue links
- scope moved to each replacement
- what this issue no longer owns
- whether any PRD or acceptance criteria changed

### Duplicate

Codex may close only when the canonical issue fully covers this issue.

Required record:

- canonical issue link
- duplicate evidence
- any unique evidence copied to the canonical issue

## PR Model

Each PR implements one issue or one clearly bounded docs/process change.

Required PR sections:

- Linked Issue
- Owner Hat
- Summary
- Scope
- Verification
- Risks
- Handoff
- PRD Coverage when product behavior is involved

Use `Refs #123` while the PR is under review. Use `Closes #123` only when the
closure type is `Completed` and the PR is intended to close the issue on merge.

Draft PRs are preferred while verification is incomplete. A PR can be ready only
when the issue's verification checklist is complete or any missing verification
is explicitly blocked and accepted.

## Review Rules

Lead scope review:

- Does the PR solve exactly one issue or approved docs/process change?
- Does it stay inside Allowed Scope?
- Does it avoid Forbidden Scope?
- Does it preserve Admin boundaries when Admin is touched?
- Does it include required verification evidence?
- Is the linked issue body current?

Review hat technical review:

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

## Merge And Deployment Rules

Do not merge PRs that:

- have no linked issue or approved docs/process anchor
- are not mapped to PRD IDs when product behavior is involved
- modify unrelated scope
- have unexplained failing CI
- lack required verification
- skip needed live Playwright E2E for production-facing changes
- leave the linked issue body stale

The Lead hat produces a merge plan before merge:

- PR order
- dependencies
- CI status
- CD plan for overlapping deploys
- risks
- rollback notes
- post-merge live verification

The Lead hat may merge without waiting for a fixed phrase once the merge plan is
ready, required reviews/checks pass, release risk is understood, rollback is
documented, and post-merge live verification is planned. If the user explicitly
pauses or blocks a release, stop at the merge plan and wait.

## Status Labels

Recommended issue labels:

- `path:fast`
- `path:full`
- `hat:lead`
- `hat:frontend-visualization`
- `hat:frontend-integration`
- `hat:backend-api`
- `hat:pipeline-data`
- `hat:qa-e2e`
- `hat:release-ci`
- `hat:review`
- `hat:pruning`
- `type:epic`
- `type:deliverable`
- `type:bugfix`
- `type:e2e`
- `type:prd`
- `type:human-input`
- `type:workflow`
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

Lead reports should prioritize current facts:

```md
| Issue | Path | Owner Hat | PR | Current State | Blocker | Next |
| --- | --- | --- | --- | --- | --- | --- |
| #121 | fast | backend-api | #130 | ready for review | none | scope review |
| #122 | full | frontend-visualization | - | blocked | page direction | ask QUESTION |
```

For Admin incident merge/deploy comments, include explicit E2E coverage instead
of summarizing only the Playwright pass/skipped count:

```md
Admin E2E release-gate evidence:
- Base URL:
- Mutation mode: read-only core smoke / controlled real business-flow mutation
- Core smoke: run URL or not-run reason
- Tracker smoke: run URL or not-run reason
- Controlled retry/business flow: run URL or not-run reason
- Skipped coverage:
- Incident-specific acceptance claim: yes/no, with required coverage rows named
```
