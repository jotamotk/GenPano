---
name: evidence-first-debug
description: Walk through the 4-step Evidence-First Debugging checklist from AGENTS.md before writing any bug-fix code. Captures broken-surface output, greps callers, identifies live code path, and states the cause-and-effect chain with evidence. Use when the user reports a bug, error, regression, broken endpoint, broken UI, failing test in production, or any "X is wrong / X doesn't work" symptom. Use BEFORE editing code, not after. If the 4 steps cannot be completed, the skill outputs `BLOCKED: need <X>` instead of guessing.
---

# Evidence-First Debugging

Canonical source: `AGENTS.md` → `### Evidence-First Debugging`.
This skill is a structured walkthrough of those 4 steps. Do not skip
steps because "the bug is obvious" — that's exactly the failure mode
the rule exists to prevent (see #905: 4 wrong PRs from skipping it).

## Mandatory output template

Produce this block in the issue comment, PR body, or chat reply before
proposing or writing any fix. Each step has a hard requirement; if you
cannot satisfy it, write `BLOCKED: <what is needed>` for that step and
stop.

```
## Evidence Capture (AGENTS.md §Evidence-First Debugging)

Step 1 — Broken-surface output:
  Source:        <API endpoint / log file / DB query / screenshot path>
  Captured at:   <ISO timestamp or commit/run URL>
  Raw value:     <paste the actual JSON / row / log line / OCR'd text>

Step 2 — Caller grep:
  Command:       <e.g. `grep -rn "format_attempt_analysis_fields" backend/`>
  Hits:          <list every caller; do NOT collapse to "one match" unless verified>
  Surface served by: <function/handler/file:line confirmed to serve the broken surface>

Step 3 — Live code path:
  Environment:   <test env URL / prod / staging>
  SQL/handler actually executed: <paste, or cite the run-time log proving it>
  Differs from suspected path? <yes/no — if yes, name the suspected path you ruled out>

Step 4 — Cause-and-effect chain:
  Trigger:       <what input/state activates the bug>
  Mechanism:     <step-by-step from trigger to broken output, each link citing Step 1-3>
  Evidence per link:
    - <link 1> — proved by <Step N output / file:line>
    - <link 2> — proved by ...
```

## Rules while filling this in

- **No `file:line` substitutes for Step 1.** Code references describe
  what code might do, not what happened. They are not evidence.
- **Do not assume one caller.** Step 2's grep must enumerate every
  hit. The #905 root cause was a sibling caller no one looked at.
- **The live env may differ from the path you suspect.** Step 3 must
  cite run-time evidence (log line, SQL EXPLAIN, request trace), not
  static reading.
- **Correlation is not causation.** A diagnostic label or error code
  matching the symptom is not Step 4 — you still must trace the
  mechanism.

## When DB access seems unavailable

Per AGENTS.md digest Hard Rule 2: DB access IS available via CI/CD.
Look for `app-analytics-readonly-evidence.yml` or similar
`workflow_dispatch` workflows. Do not write "I cannot access the DB"
as a Step 1 blocker without first checking `.github/workflows/` for
a readonly evidence workflow.

## Orchestrator usage

If you are dispatching a subagent to do this capture (the
**recommended first dispatch** per AGENTS.md §Orchestrator And
Subagent Discipline), the subagent prompt must:

1. Include the literal string "Read AGENTS.md Evidence-First Debugging
   before proceeding."
2. Be marked investigate-only — restrict `tools:` to Read, Grep, Bash
   (no Edit/Write).
3. Not contain a pre-baked hypothesis. State the symptom and the
   unknown, not the suspected cause.

See `.claude/skills/dispatch-subagent/SKILL.md` for the prompt template.
