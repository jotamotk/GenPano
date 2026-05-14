# Agent Operating Notes

These rules are the first stop for Codex-style agents working in this repo.

## Codex Coordination Workflow

Genpano work is coordinated through GitHub. Treat GitHub issues, pull requests,
review comments, and CI/CD runs as the durable collaboration state. Chat is only
for discussion and clarification; it does not replace issue, PR, or review
state.

The purpose of this workflow is speed with recoverability. Issues should make
the core problem, current judgment, and next action obvious to the next Codex
session. Do not create process artifacts that do not improve execution.

### Real Agent Topology

- There is one Codex coordinator wearing different hats during the work. The
  named agent roles are responsibility views, not independent people.
- Do not split issues by agent role. Split by deliverable: one issue should map
  to a user-visible or engineering outcome that can be accepted or closed.
- The Lead hat does not write business code. It may maintain coordination
  artifacts: PRDs, GitHub issues, PR review comments, merge plans, verification
  plans, and workflow docs.
- Codex may switch into an implementation, QA, review, or release hat only after
  the issue has a clear execution contract. Do not pretend a handoff happened to
  a separate agent when the same coordinator is continuing the work.
- The pruning hat is the subtraction view: it regularly asks what can be deleted
  or retired, but it reports candidates instead of deleting by automation.
- In parallel or overlapping work, the Lead hat owns CD coordination: order
  production deploys intentionally, monitor overlapping Build & Deploy runs,
  cancel superseded deploy runs when safe, and verify the final live environment
  is running the intended latest `main` SHA.

### Fast Path And Full Path

Not every request needs Epic -> Frontend Visualization -> PRD -> split issues.

Use **Fast Path** when the request is a bug fix or small improvement that:

- affects one product or engineering area
- does not change PRD requirements, public contracts, schemas, migrations, or
  deployment architecture
- has a clear reproduction or acceptance check
- can be completed with one issue, one branch, and one PR

Use **Full Path** when any of these are true:

- new user-facing workflow or material UX direction
- PRD requirement or product contract may change
- API, database, migration, scheduler, worker, CI/CD, or deployment contract
  changes across areas
- multiple deliverables must be sequenced
- production risk is high or the rollback path is unclear

Full Path may use an Epic, PRD linkage, Frontend Visualization, and multiple
deliverable issues. Fast Path should not create those artifacts unless they
serve the specific fix.

### Issue Writing Standard

Issues are task control panels, not chat rooms. Comments should be short,
judgment-first, and useful three weeks later.

- Start every substantive issue comment with the conclusion, then evidence,
  then next action.
- Use prefixes as writing aids, not bureaucracy:
  `QUESTION`, `DECISION`, `BLOCKER`, `STATUS`, `PRD-CHANGE`, `EVIDENCE`.
- `QUESTION` asks all known clarifying questions at once and states the default
  assumption if the answer is not available.
- `BLOCKER` states what is blocked, impact, options, and who or what can unblock
  it.
- `STATUS` is only for material state changes. Do not post process narration
  that does not change current state, risk, decision, or next action.
- `DECISION` records only settled decisions and must be copied into
  `## Decisions` when the issue body has that section.
- `PRD-CHANGE` states the PRD text, observed code or product reality, the
  conflict, and the decision requested from the product owner.
- `EVIDENCE` records exact proof: PR, run URL, commit SHA, route, request id,
  screenshot, Playwright trace, server diagnostic, or API readback.

Before posting a comment, check that it answers: what is the core judgment, what
evidence supports it, what changed, and what happens next?

### Issue, PR, And PRD Contract

- Any problem, incident, bug, requirement gap, blocker, release risk, or workflow
  gap reported to Codex must be captured in GitHub as a new issue or linked to
  an existing issue before durable work continues.
- Issue body is the current fact source. Comments are draft discussion and audit
  trail. Keep `## Current State` and `## Decisions` current when state changes.
- Downstream issues must inline their execution contract. Do not rely on
  unresolved pointers such as "depends on #123" as the only source of scope.
- Execution contracts should include Goal, Path (`fast` or `full`), Owner Hat,
  Allowed Scope, Forbidden Scope, Contract Snapshot, Acceptance Matrix,
  Verification Evidence Ledger, Dependencies, and Handoff when relevant.
- PRDs are product-owner-approved facts. If implementation reveals a PRD problem,
  Codex must request a `PRD-CHANGE`; it must not silently rewrite PRD intent.
- PRs must include: Linked Issue, Owner Hat, Summary, Scope, Acceptance Matrix
  status, Verification Evidence Ledger, Test Integrity Statement, Risks,
  Handoff, and PRD Coverage when product behavior is involved.
- Use `Refs #123` before final acceptance. Use `Closes #123` only when the issue
  closure path is approved for completion.
- Issue text describes intent; code and live behavior describe reality. If they
  conflict, stop and raise the conflict in the issue.

### Acceptance And Verification Evidence

Testing output is evidence only when it is tied to an acceptance claim. "Tests
passed" by itself is not enough.

- Before implementation starts, the Lead hat translates PRD requirements, user
  reports, and accepted Human Input decisions into an `Acceptance Matrix`.
- Each acceptance row must cite its source: PRD ID, user-reported symptom,
  Human Input disposition, issue `DECISION`, or approved `PRD-CHANGE`.
- No source means the acceptance row is invalid. If the PRD requires behavior
  that has no row, record it as a coverage gap before coding.
- If translation is ambiguous, post one `QUESTION` with all choices and wait
  unless a safe default is explicit in the issue.
- Every checked verification item must include command, exit code, key output,
  scope covered, artifact or link, and commit SHA. No evidence means unchecked.
- User-reported bugs require a `User-Symptom Replay` check against the exact
  route, row, brand, query, request, action, or visible result when available.
  If the exact replay is impossible, mark it `BLOCKER` instead of claiming
  acceptance from adjacent tests.
- Do not make tests green by deleting assertions, skipping cases, weakening
  expectations, swallowing exceptions, or moving checks away from the user path.
  If a test is wrong or obsolete, stop with `BLOCKER` or `PRD-CHANGE` and get
  the decision before relaxing it.
- PR handoff must declare test integrity: test files changed, assertions
  removed or relaxed, skips added, and any unverified acceptance rows.

### Tiered E2E

E2E is required where it proves the acceptance claim, but it should be scoped.

- `Tier 0`: static checks, unit tests, contract tests, and focused backend or
  frontend tests for the touched layer.
- `Tier 1`: targeted user-symptom replay for the exact reported bug or changed
  user path. This is the default UI-visible Fast Path E2E.
- `Tier 2`: focused smoke across adjacent contracts when frontend, backend,
  auth, scheduler, worker, or deployment boundaries interact.
- `Tier 3`: full Playwright or release-gate E2E for high-risk changes,
  multi-PR releases, major user-facing workflows, migrations, auth, scheduler,
  worker, or production deployment gates.

Do not run full E2E as a ritual when a smaller replay proves the claim. Do not
skip targeted replay and substitute unrelated green tests.

### Issue Closure

Closed issues must say why they ended. Use one of these closure types:

- `Completed`: linked PR or commit, acceptance result, verification evidence,
  and live Playwright or production evidence when relevant. Codex may close this
  after required verification passes.
- `Won't Do`: reason, deciding person, accepted risk, and alternative path if
  any. This needs product-owner confirmation unless the issue is an obvious
  duplicate or mistaken artifact created by Codex.
- `Split/Superseded`: replacement issue links, which scope moved where, and what
  this issue no longer owns. Prefer product-owner confirmation when product
  scope changes.
- `Duplicate`: canonical issue link and why it fully covers this issue. Codex
  may close when the overlap is exact; otherwise ask first.

### Workflow Improvement Notes

Codex should surface process friction, but must classify it before proposing a
rule change:

- `Efficiency`: repeated low-value work, waiting, template noise, or duplicated
  status updates.
- `Constraint`: a gate, forbidden scope, or approval step feels restrictive.
  Treat these skeptically and explain what risk the constraint prevents.
- `Reliability`: a change that reduces missed evidence, stale state, or
  incorrect closure.
- `Topology Correction`: a rule assumes multiple independent agents when the
  real topology is one coordinator wearing hats.

Small notes can go in a governance/process issue. Do not change workflow rules
without an accepted issue or explicit user instruction.

### Pruning Automation

Codex should have a recurring pruning automation that produces a report, not a
patch. Its job is to ask what can be removed: debug scripts, legacy directories,
dead code, unused prototypes, stale runbooks, obsolete issue templates, and
outdated AGENTS.md rules.

- The automation output is a `Pruning Report` posted to a governance or pruning
  inbox issue.
- Each candidate must include evidence: reference search, workflow or CI usage,
  docs links, open issue/PR dependencies, owner if known, and rollback or
  restore path.
- Recommendations must be one of `Delete`, `Keep`, `Replace`, or
  `Needs Decision`.
- The automation must not delete files, close issues, or change workflow rules
  by itself.
- Low-risk docs/debug cleanup can become a Fast Path issue. Runtime, CI,
  migration, data repair, production path, or product behavior removal needs a
  scoped issue and explicit verification.
- Prefer real deletion over archive directories when git history is enough to
  recover the artifact. Archive only for compliance, audit, or active incident
  evidence.

### Human Input Channel

The fixed Human Input issue is an inbox, not a task and not a PRD.

- It stays open permanently and does not enter Fast Path or Full Path itself.
- It is not closed by status workflow and should not be used as a requirement
  source for implementation.
- Each raw item needs a triage receipt: item id or short quote, classification
  (`bug`, `feature change`, `new requirement`, `question/idea`, or
  `needs clarification`), disposition, target issue or PRD-change request, and
  last updated date.
- Codex must not implement a vague Human Input item directly. It must first
  convert it to a scoped issue, request a PRD decision, or ask for clarification.

See `docs/AI_LEAD_WORKFLOW.md` for the full operating procedure and templates.
For Claude Code collaboration, see `docs/AI_LEAD_CLAUDE_COLLABORATION.md`.

## Admin Surface Rule

Decision recorded on 2026-05-02:

- The product surface is called **Admin**. Do not introduce a second product called
  "Query Tool Admin" in UI copy, planning, or route ownership.
- The orange `/admin` operator console is the only Admin UI.
- Admin must remain one system under `/admin` and `/admin/*`. Do not split it into
  a separate mini-app that loses existing pages such as Topic Plan, Prompt Matrix,
  Query Pool, Segment, or Profile.
- Do not create or restore `frontend/src/admin/**`, `frontend/src/pages/admin/**`,
  `frontend-admin/**`, Next.js `app/admin/**`, or any other second Admin frontend.
- For Admin Query Pool and Segment/Profile prototype work, use branch
  `codex/admin-query-pool-prototype` or another user-approved non-main branch.

## Current Admin Boundary

- In local development, `http://127.0.0.1:5173/admin` is served through the
  Vite proxy from FastAPI on port `4000`.
- Do not infer ownership from the URL alone. Before changing any Admin UI, verify
  which file is rendering the browser page and state the exact file path.
- The Admin SPA shell now lives at `backend/static/admin.html` and is served by
  FastAPI. All Admin APIs live under `/admin/api/*` inside the FastAPI backend.
  Do not create a second Admin surface elsewhere unless the user explicitly asks
  for that architecture.
- The legacy Flask `admin_console/` package has been removed. Do not recreate a
  second Admin backend; add Admin auth/API work inside the FastAPI backend
  unless the user explicitly approves a new architecture.

## Admin Frontend Workflow

Before changing any Admin UI:

1. Confirm the branch is not `main`.
2. Inspect `frontend/vite.config.js`, the `/admin` response, and the server code
   that actually renders the orange Admin page.
3. Preserve the full Admin navigation and existing Admin pages.
4. Keep `/admin/api/*` as an API boundary; do not use it as proof that the UI
   belongs to a second Admin frontend.
5. Run the relevant frontend build or smoke check after edits.

## Admin Product Terms

- `ProfileGroup` should be displayed as `Segment`.
- A Segment detail page contains individual Profiles.
- Segment and Profile management should support create, delete, search/read,
  update, import, and LLM generation flows in the frontend prototype.
- Budget ceiling inputs should accept numbers directly instead of being a fixed
  select list.
