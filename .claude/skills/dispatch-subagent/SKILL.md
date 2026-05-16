---
name: dispatch-subagent
description: Compose a safe subagent prompt that complies with AGENTS.md `### Orchestrator And Subagent Discipline`. Auto-injects the AGENTS.md rule reference, restricts tools to investigate-only for first dispatch on a bug-fix task, and refuses to pre-bake hypotheses. Use BEFORE every Agent tool call for bug-fix, incident, contract-change, or any task that will end in a PR. Skip only for pure file-finding / lookup tasks where Explore subagent without context is fine.
---

# Dispatch Subagent (safely)

Canonical source: `AGENTS.md` → `### Orchestrator And Subagent
Discipline`. The orchestrator is the only enforcement point — CI
cannot detect a hypothesis-driven subagent dispatch.

## The failure mode this prevents

Orchestrator reads AGENTS.md, knows the rules, writes a prompt like:

> "The bug is at `scraper.py:88` where the timeout is too short. Fix
> it by raising the timeout to 60s and adding a retry."

Subagent dutifully edits `scraper.py:88`, opens a PR with a ledger
filled from the orchestrator's hypothesis, CI passes (the body has
all required fields), merge happens, user reports the same bug.
This is #905-class compounding error: each layer trusts the layer
above, no one captured Step 1 evidence.

## Decision: which prompt template

| Task type | Template | Tools allowed |
|---|---|---|
| User-reported bug, first dispatch | **Investigate-only** | Read, Grep, Bash (no Edit/Write/NotebookEdit) |
| Bug fix after evidence is captured | **Fix-with-ledger** | Read, Edit, Write, Bash |
| Open-ended research / "where is X" | **Explore** | Use `subagent_type: Explore` directly |
| Contract change (API/schema/enum) | **Fix-with-ledger** + trace requirement | Read, Edit, Write, Bash |
| Refactor / cleanup | **Fix-with-ledger** without Root Cause Gate | Read, Edit, Write, Bash |

## Template — Investigate-only (first dispatch for any bug-fix)

```
Read AGENTS.md `### Evidence-First Debugging` and `### Orchestrator
And Subagent Discipline` before proceeding.

CONTEXT: <one sentence — what the user reported, verbatim where
possible. Do NOT include your hypothesis about the cause.>

UNKNOWN: <what we need to find out, framed as a question. NOT a
directive. Good: "Which handler serves the /admin/foo response
the user screenshot shows?" Bad: "Fix the bug in foo.py:42".>

INVESTIGATE-ONLY — DO NOT WRITE OR EDIT CODE. Your job is to fill
in the Evidence Capture block from
`.claude/skills/evidence-first-debug/SKILL.md`. Specifically:

1. Capture the broken-surface output (curl the endpoint, query the
   DB, read the log, paste a screenshot OCR — whichever applies).
2. Grep all callers of every function/handler/SQL you think is
   involved. List every hit, do not collapse to "one match" without
   verifying.
3. Read the SQL or handler the live test environment actually runs
   for this surface — not the one you think it runs.
4. State the cause-and-effect chain with evidence per link.

If you cannot complete a step, report `BLOCKED: need <X>` for that
step and stop. Do not guess.

REPORT BACK: paste the filled Evidence Capture block. Do not
recommend a fix. Do not edit files.
```

## Template — Fix-with-ledger (only after investigate-only returned evidence)

```
Read AGENTS.md `### Evidence-First Debugging`, `### Evidence-First
Shipping`, and `### Orchestrator And Subagent Discipline` before
proceeding.

CONTEXT: <user-reported symptom verbatim>

EVIDENCE ALREADY CAPTURED (from prior investigate-only dispatch):
<paste the Evidence Capture block here — Steps 1-4 filled. If any
step is `BLOCKED:`, STOP and ask the user instead of dispatching
this template.>

ROOT CAUSE (confirmed by evidence above):
<one or two sentences naming the design/code reason. Must trace to
specific lines in the Evidence Capture block.>

CHANGE SCOPE: <files to touch + the reason each is in scope. List
forbidden scope explicitly: "do not modify <X> because <Y>".>

ACCEPTANCE: <the user-visible result that proves success. Same
content as `Parent Business Goal` and `Final Success Evidence`
will go in the PR body.>

DELIVERABLE:
1. Code change scoped to CHANGE SCOPE only.
2. PR body composed via `.claude/skills/compose-incident-pr/SKILL.md`.
3. Run `python3 .github/scripts/lint_pr_body.py --body-file <draft>`
   and report PASS before opening the PR.
4. For contract changes (API field, enum, schema): also paste one
   real new value from the producer + the consumer's return for that
   input, per AGENTS.md §Evidence-First Shipping.
```

## Anti-patterns (never put these in a subagent prompt)

- "The bug is at `foo.py:42` — fix it." → No. State the symptom and
  unknown; let the subagent confirm the location with evidence.
- "Run pytest and make sure it passes." → No. Tests passing is not
  acceptance. State the user-visible result that must hold.
- "Use your best judgment." → No. Specify forbidden scope explicitly.
  Bug fixes do not get to refactor surrounding code.
- "Based on your investigation, implement the fix." → No. Two-phase:
  investigate-only first, then a separate dispatch with the captured
  evidence pasted into the prompt.
- Omitting the AGENTS.md reference string. The rule literally requires
  it. A prompt without "AGENTS.md" is non-compliant regardless of
  outcome.

## Orchestrator self-check (before sending the Agent tool call)

- [ ] Prompt contains the literal string "AGENTS.md".
- [ ] Prompt names the relevant `###` section(s) by exact heading.
- [ ] For investigate-only: tools restricted, no Edit/Write.
- [ ] For fix-with-ledger: Evidence Capture block pasted, not summarized.
- [ ] No `file:line` directive that pre-bakes the cause.
- [ ] Forbidden scope is explicit.
- [ ] Deliverable names a verifiable artifact (lint PASS, ledger row,
      consumer trace), not "make it work".
