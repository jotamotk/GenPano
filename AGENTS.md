# AGENTS.md — canonical contract for ALL agents in this repository

**This file is the canonical contract for ALL agents working in this repository, including Claude (Code/Anthropic API), Codex (OpenAI), Cursor, Aider, Devin, and any future agent — as well as human contributors.**

Agent-specific config files (`CLAUDE.md`, `.cursorrules`, `.codex/`, `.devin/`, etc.) MUST point here and not duplicate rules. If a rule appears only in an agent-specific config, that is a bug — file an issue.

**Enforcement layers** (Section "Enforcement" below has the details):

1. **GitHub CI (primary, agent-agnostic)**: `.github/workflows/pr-body-lint.yml` rejects PRs whose body omits Root Cause Gate / Verification Evidence / Business Goal. Branch protection requires this check to pass. No agent can bypass.
2. **GitHub issue templates**: `validations.required: true` enforces fields when issues are opened via the web UI. `issue-body-lint.yml` provides feedback on issues opened via the API.
3. **Agent-specific automation** (best-effort): each agent's config layer (Claude SessionStart hook, etc.) injects this file's rules into the agent's context. If this layer fails for a given agent, Layer 1 still catches.

If you are an agent reading this for the first time in a session: **before you write any code for a bug fix**, follow the four-step Evidence-First Debugging checklist below. Code-reading is not evidence.

---

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
  live test-environment deploys intentionally, monitor overlapping Build & Deploy runs,
  cancel superseded deploy runs when safe, and verify the final live environment
  is running the intended latest `main` SHA.

### Evidence-First Debugging

任何根因排查的第一步必须是从坏掉的 surface 直接抓真实响应/输出作为硬证据，并
`grep` 全部调用者验证 live test 环境实际走的代码路径——禁止以"读代码推断行为"或
"假设端点走某段 SQL/handler"替代直接观察。

Why this rule exists:

- #905 took 5 PR rounds (#913 → #934 → #935 → #942 → #943) to land the actual
  root cause because the first 4 PRs were built on code-path assumptions
  ("Admin Tracker uses `list_queries` SQL", "the formatter is the bug surface",
  "`profile_id IS NULL` is the blocking gate") that were never validated
  against the broken endpoint's real response. PR #943 — the actual fix —
  took 30 seconds of SQL reading once `grep "format_attempt_analysis_fields"`
  revealed the surface was served by `fetch_response_analyzer_status`, a
  different SQL with a stripped-down `SELECT`.
- Diagnostic labels (e.g. `_profile_state="query_profile_id_null"`) are not
  code gates; correlation is not causation. Verify the actual control flow.

Minimum evidence checklist before opening a fix PR for a user-reported bug:

1. Capture (or request from the user) the actual response/output of the
   broken surface — API JSON, log line, screenshot of rendered text, DB row,
   whichever applies. Paste it into the issue or PR body.
2. `grep` every caller of the function/handler/formatter you suspect; do not
   assume a single endpoint serves the surface.
3. Read the SQL/code path that the *live test environment* actually executes
   for that surface, not the one you think it executes.
4. State the assumed cause-and-effect chain explicitly, then point at the
   evidence that confirms each link.

Inferred behaviour without these four steps is a hypothesis, not a diagnosis.
Do not ship a fix on a hypothesis.

### Business Goal And Root Cause Gates

The first target is the issue's business goal. A fix that only changes the
visible error state is not complete.

- Human Input and Epic issues must state `Business Goal`, `Final Success
  Evidence`, and `What Does NOT Count As Done` before child work is split.
- Incident PRs must pass a `Root Cause Gate`: direct trigger, underlying
  product/system root cause, evidence, alternatives ruled out, remaining
  unknowns, and why the fix should produce the final business outcome.
- If root cause is still unknown, the PR can be marked only as
  `diagnostics/instrumentation only`; do not present it as the incident fix.
- Review work must include a failure-chain review: why did this happen, why did
  the previous guard fail, why does this fix reach the business goal, what is
  the next likely failure, and what live evidence proves success?
- Live retries or other live budget spend require preflight: current row/object
  state, retry count or equivalent budget, account/session state when relevant,
  post-action consequence, expected final evidence, and fallback if the next
  layer fails.
- Completion language has only three allowed states: `Business success proven`,
  `Diagnostic progress only`, or `Blocked / decision needed`.

### Evidence-First Shipping

When you change a value that crosses a boundary (API field, enum, schema,
URL param, contract status), don't merge until you've traced one real value
through the consumer.

Why this rule exists:

- #948 needed a follow-up PR #960 because the original #953 changed the
  backend to emit `formula_status: partial` for trustworthy values without
  verifying the frontend gate `canUseContractMetricValue` accepted that new
  value. Backend + frontend test suites both passed; the bug surfaced only
  when the user hand-traced a live API response into the consumer function.
  Symmetric failure to Evidence-First Debugging — "tests green" is not
  enough when a contract value set changes.

Minimum evidence in the PR body before merge: one new value the producer
emits, plus the consumer's return for that input, pasted not assumed. If
multiple consumers exist, repeat or cite a grep proving one consumer
covers all values in the new set.

If you can't paste that trace, the PR isn't ready.

### Orchestrator And Subagent Discipline

Subagents (anything dispatched via the Agent tool — Claude Code subagents,
Codex sub-tasks, Aider sub-runs, etc.) do **not** inherit this file. They
see only the prompt the orchestrator writes. That gap is where prior bugs
slipped past every rule above: the orchestrator wrote a hypothesis-laden
prompt, the subagent acted on it as fact, and the chain produced a fix
with no evidence ledger.

The rules below are canonical. The Claude Code SessionStart digest
(`.claude/hooks/session-start.sh`) and any other agent-specific reminder
must reference this section by name rather than redefining it — drift
between digest and source is itself a violation.

1. **First dispatch is investigate-only.** When a bug-fix task starts,
   the first subagent call must produce evidence (broken-surface output,
   live-env code path, grep of callers), not code. Edit/Write tool access
   should be withheld on the first call. Use the `Explore` subagent or
   restrict `tools:` in the subagent definition.

2. **Prompts must reference this file.** Every subagent prompt for a
   bug-fix, incident, or contract-changing task MUST contain the literal
   string "AGENTS.md" plus the relevant section name (e.g. "Read AGENTS.md
   `### Evidence-First Debugging` before proceeding"). A prompt that omits
   it is non-compliant regardless of outcome. CI cannot catch this; the
   orchestrator owns it.

3. **No pre-baked hypotheses.** Anti-pattern: "The bug is at
   `foo.py:42`; fix it." This collapses investigation into a directive
   and is how #905 produced 4 wrong PRs. Acceptable: "User reports
   <symptom>. Capture broken-surface evidence, grep callers, identify
   live code path. Do not edit code." State the symptom and the unknown,
   not the cause.

4. **Second-iteration revert applies recursively.** If a subagent's
   output produced a PR that the user rejected, the orchestrator must
   revert that subagent's changes before dispatching a follow-up — not
   patch forward with another subagent. Same rule as Hard Rule 5 in the
   digest, applied at the orchestration layer.

5. **Skills are the preferred carrier.** When the same prompt pattern
   recurs (evidence capture, PR body composition, safe subagent
   dispatch), package it as a skill in `.claude/skills/` so the rule
   travels with the invocation instead of relying on the orchestrator's
   memory. Skills do not replace CI — they raise compliance rate
   without claiming to be a gate.

Failure mode this prevents: orchestrator skims AGENTS.md, dispatches a
subagent with "fix the timeout bug at scraper.py:88", subagent edits the
line, PR opens, lint passes because the orchestrator hand-fills the
ledger from the same hypothesis. CI cannot detect a hypothesis-grounded
ledger. Only the orchestrator can.

### Coding Discipline (General)

These four principles cover the *generic* coding-quality failure modes for LLM
agents. They are adapted from
[Andrej Karpathy's observations on LLM coding pitfalls](https://x.com/karpathy/status/2015883857489522876)
(packaged at `forrestchang/andrej-karpathy-skills`, MIT-licensed) and rewritten
to fit this repo's rule precedence.

**Precedence note.** For bug-fix, incident, or contract-change tasks, the
project-specific rules above (`Evidence-First Debugging`, `Evidence-First
Shipping`, `Acceptance And Verification Evidence`) are stricter and take
precedence. The four points below apply to feature work, refactors, and any
task not gated by an Evidence-First section.

1. **Think before coding.** State assumptions explicitly. If multiple
   interpretations exist, surface them — do not pick silently. If a simpler
   approach exists, say so before implementing. If something is unclear,
   stop and ask. (For bug-fix tasks, "thinking" means executing the
   Evidence-First Debugging checklist, not free-form reasoning.)

2. **Simplicity first.** Minimum code that solves the stated problem.
   No features beyond what was asked, no abstractions for single-use code,
   no "flexibility" or "configurability" that was not requested,
   no error handling for impossible scenarios. If 200 lines could be 50,
   rewrite.

3. **Surgical changes.** Touch only what the request requires. Do not
   "improve" adjacent code, comments, or formatting. Do not refactor things
   that are not broken. Match existing style even if you would do it
   differently. If you notice unrelated dead code, mention it — do not
   delete it. Test: every changed line should trace directly to the
   request.

4. **Goal-driven execution.** Translate every task into a verifiable goal
   before starting. "Fix the bug" → "Write a test that reproduces it, then
   make it pass." "Refactor X" → "Ensure tests pass before and after."
   For multi-step tasks, state a brief plan with a verification check per
   step. (For incidents, the `Acceptance Matrix` / `Verification Evidence
   Ledger` is the canonical form of this; this principle covers the
   non-incident equivalent.)

**Attribution.** Source: <https://github.com/forrestchang/andrej-karpathy-skills>
(MIT). Reworded to align with this repo's evidence-first stance and rule
precedence.

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
- release risk is high or the rollback path is unclear

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

Use `Business success proven` only when the final business artifact/readback is
present. Use `Diagnostic progress only` when observability improved but the
business result is not proven. Use `Blocked / decision needed` when root cause,
acceptance, or safe next action is uncertain.

Before posting a comment, check that it answers: what is the core judgment, what
evidence supports it, what changed, and what happens next?

### Issue, PR, And PRD Contract

- Any problem, incident, bug, requirement gap, blocker, release risk, or workflow
  gap reported to Codex must be captured in GitHub as a new issue or linked to
  an existing issue before durable work continues.
- Every issue must use the shared priority taxonomy: one required `Priority`,
  one required `Priority Rationale`, and exactly one matching label from
  `priority:p0`, `priority:p1`, `priority:p2`, or `priority:p3`.
- Issue body is the current fact source. Comments are draft discussion and audit
  trail. Keep `## Current State` and `## Decisions` current when state changes.
- Downstream issues must inline their execution contract. Do not rely on
  unresolved pointers such as "depends on #123" as the only source of scope.
- Execution contracts should include Goal, Path (`fast` or `full`), Owner Hat,
  Parent Business Goal, Allowed Scope, Forbidden Scope, Contract Snapshot,
  Acceptance Matrix, Root Cause Gate, Failure Chain Review, Verification
  Evidence Ledger, Dependencies, and Handoff when relevant.
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
- Before implementation starts, the Lead hat also confirms the Business Goal and
  Final Success Evidence. If unclear, post `HUMAN DECISION NEEDED` instead of
  splitting work.
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
- Live incidents require a `Business Result Gate` row that names the exact
  business object and final state required. CI green, deploy green, or a
  better error code is not acceptance unless that row also passes. For scraper
  recovery, this means exact query readback such as `done + response evidence`
  when the user asked for capture success.
- Observability-only improvements are useful but cannot close a business
  incident unless the Business Result Gate passes. Better diagnostics, a more
  specific error code, or a clean deploy is `Diagnostic progress only`.
- Any Playwright test that mutates a live object, such as retrying a production
  query or submitting analyzer work, must run with Playwright retries disabled.
  A workflow must not repeat a live mutation because the first assertion failed.
- The poll window for a live mutation gate must cover the full expected
  recovery loop, including account reauth and the post-reauth query attempt.
  If the window expires while the object is still running, report the evidence
  as inconclusive instead of treating the workflow status as acceptance.
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
  worker, or live test-environment deployment gates.

Do not run full E2E as a ritual when a smaller replay proves the claim. Do not
skip targeted replay and substitute unrelated green tests.

### Issue Closure

Closed issues must say why they ended. Use one of these closure types:

- `Human Input Accepted`: user accepted the online result and closed, or
  explicitly delegated closure after reviewing the live test-environment
  evidence. Agents should not close Human Input issues just because child
  tasks or PRs completed.
- `Completed`: linked PR or commit, acceptance result, verification evidence,
  and live Playwright or live test-environment evidence when relevant. Codex
  may close this after required verification passes.
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
  migration, data repair, live runtime path, or product behavior removal
  needs a scoped issue and explicit verification.
- Prefer real deletion over archive directories when git history is enough to
  recover the artifact. Archive only for compliance, audit, or active incident
  evidence.

### Human Input Channel

Human Input is the user's durable intake and final acceptance issue. It is not a
worker task, branch, PR, or PRD by itself.

- The Lead hat owns triage: classify each raw item as `bug`, `feature change`,
  `new requirement`, `question/idea`, or `needs clarification`.
- The Lead hat must confirm the Human Input `Business Goal`, `Final Success
  Evidence`, and `What Does NOT Count As Done`. If any are unclear, post
  `HUMAN DECISION NEEDED` before routing implementation.
- The Lead hat must split actionable Human Input into one or more executable
  issues: Fast Path issue, Full Path coordination issue, PRD-change request, or
  scoped deliverable issue. Each child issue links back with `Refs #<human>`.
- Human Input can become an acceptance source only after a triage disposition or
  issue `DECISION` records the accepted user intent.
- Codex must not implement directly from a vague Human Input note.
- The Lead hat schedules and coordinates the needed hats until the child work is
  merged, deployed, and verified on the relevant live route.
- Final delivery is a `Ready for User Acceptance` comment on the Human Input
  issue with live URL, user-visible result, PRs, deploy SHA, Playwright or
  live test-environment evidence, and known caveats.
- The Human Input issue stays open until the user can verify the online result.
  The user closes it if the result is acceptable; Agents close it only when the
  user explicitly delegates closure.

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

## Enforcement

The rules above are enforced in CI so that no agent — Claude, Codex, Cursor,
Aider, Devin, or human — can ship a PR that skips Root Cause Gate, Business
Goal, or Verification Evidence. Enforcement lives in the GitHub layer because
that is the only point every agent must pass through.

**Layer 1: `.github/workflows/pr-body-lint.yml`** (gate)

- Triggers on `pull_request: [opened, edited, synchronize, reopened]`.
- Validator: `.github/scripts/lint_pr_body.py` (Python 3.12 stdlib, no deps).
- The PR body must contain three `## ` sections:
  - `## Linked Work` with `Business Goal:` and `Final Success Evidence:`
  - `## Root Cause Gate` with `Direct trigger:`, `Underlying product/system root cause:`, `Evidence proving it:` — OR `Classification: not an incident - <reason>` (single value, not the template's `|`-separated stub).
  - `## Verification Evidence Ledger` with at least one `- [x]` item and one `https://` URL.
- Placeholder text (TODO, TBD, PLACEHOLDER, xxx, ..., bare N/A, and the issue
  template's literal Chinese stubs like `用户在 \`http://116.62.36.173/<route>\``)
  is rejected as if the field were empty.
- Failure: the workflow posts a comment on the PR listing each missing/empty
  field and fails the check. Branch protection on `main` (set in repo Settings →
  Branches) must list `Lint PR Body` as a required status check; without that,
  the lint runs but does not block merge.

**Layer 2: `.github/workflows/issue-body-lint.yml`** (feedback)

- Triggers on `issues: [opened, edited]`.
- Validator: `.github/scripts/lint_issue_body.py`.
- Detects issue type from labels (`type:human`, `type:epic`, `type:task`) and
  body markers. Validates required fields per template.
- Comments on the issue with gaps but **never fails the workflow** — this layer
  is feedback only, because failing on human-authored issues is too aggressive.

**Adding a new required field**

1. Add the field to the relevant issue template under `.github/ISSUE_TEMPLATE/`
   with `validations.required: true` (web UI enforcement).
2. Add the field name to `REQUIRED_FIELDS_BY_TYPE` in
   `.github/scripts/lint_issue_body.py` (or to `REQUIRED_FIELDS` /
   `REQUIRED_SECTIONS` in `lint_pr_body.py` for PR fields).
3. Update `.github/PULL_REQUEST_TEMPLATE.md` if it's a PR field.
4. Smoke-test locally: `python3 .github/scripts/lint_pr_body.py --help` and run
   against `.github/PULL_REQUEST_TEMPLATE.md` (must fail) and a known-good body
   (must pass).
