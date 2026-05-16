---
name: compose-incident-pr
description: Compose a PR body that passes `.github/workflows/pr-body-lint.yml` (the Layer 1 CI gate). Generates the required `## Linked Work`, `## Root Cause Gate`, and `## Verification Evidence Ledger` sections with grep-aligned field names so the lint validator accepts them on the first try. Use when about to create a pull request — especially for incident fixes, bug fixes, contract changes (API/schema/enum), or any PR likely to be merged into main. Do NOT use for purely-WIP draft PRs that will be rewritten before merge.
---

# Compose Incident PR

Canonical source: `AGENTS.md` → `## Enforcement` and
`.github/scripts/lint_pr_body.py`. This skill emits a PR body whose
field names and structure exactly match the lint's grep patterns, so
the gate passes without back-and-forth.

## How the lint actually decides

`lint_pr_body.py` requires three `## ` sections. For each, the rule:

| Section | Required fields | Escape hatch |
|---|---|---|
| `## Linked Work` | `Parent Business Goal:` (or `Business Goal:`), `Final Success Evidence:` — both non-placeholder | `Linked Work N/A: <reason >10 chars>` |
| `## Root Cause Gate` | `Direct trigger:`, `Underlying product/system root cause:`, `Evidence proving it:` — all non-placeholder | `Classification: not an incident - <reason>` (single value, not the `|`-separated template stub) |
| `## Verification Evidence Ledger` | At least one `- [x]` bullet **or** a table row with ≥3 non-empty cells, **AND** at least one `https://` URL | `Verification Evidence Ledger N/A: <reason >10 chars>` |

Placeholder tokens that auto-fail: `TODO`, `TBD`, `PLACEHOLDER`, `xxx`,
`...`, bare `N/A`, `<reason>`, `<route>`, `fill in`, `to be filled`,
and the Chinese template stub
`用户在 \`http://116.62.36.173/<route>\``.

## Output template — incident fix

```markdown
## Linked Work

- Issue: Refs #<n>
- Path: fast
- Parent Business Goal: <one sentence — what business outcome the user
  expects to see after this PR. Not "fix the bug"; the visible result.>
- Final Success Evidence: <the artifact that proves it — exact URL,
  query readback, screenshot path, log line. Not "tests pass".>

## Root Cause Gate

- Direct trigger: <the immediate event that produced the symptom>
- Underlying product/system root cause: <the design/code reason the
  trigger caused harm, not a restatement of the trigger>
- Evidence proving it: <commit SHA + file:line, run URL, captured log,
  or DB query result. Tie at least one item to Step 1 of
  Evidence-First Debugging.>
- Alternatives ruled out: <other hypotheses you considered and why
  they don't explain the captured evidence>
- Unknowns that remain: <or `none`>
- Why this fix produces the final business outcome:
- Classification: incident fix

## Verification Evidence Ledger

| Check | Command/Run | Exit/Conclusion | Key Output | Scope Covered | Artifact/Link | Commit |
| --- | --- | --- | --- | --- | --- | --- |
| Local | <e.g. `pytest tests/foo/`> | 0 | <last assertion or count> | <module> | <CI run URL https://...> | <sha> |
| User-symptom replay | <route + action> | <visible result observed> | <pasted output> | <user path> | <screenshot/trace https://...> | <sha> |

- [x] Captured broken-surface evidence per AGENTS.md §Evidence-First Debugging (Step 1)
- [x] Grepped all callers of the suspected handler (Step 2)
- [x] Confirmed live env code path matches the fix target (Step 3)
```

## Output template — non-incident (governance, docs, tooling, refactor)

For PRs that are not fixing a reported failure, Root Cause Gate
collapses to a single line. The lint accepts it as long as the
classification value does not contain `|`.

```markdown
## Linked Work

- Issue: Refs #<n>  (or `Linked Work N/A: docs-only change tracked in CHANGELOG`)
- Path: fast
- Parent Business Goal: <even non-incidents need this — the durable
  outcome this PR contributes to>
- Final Success Evidence: <PR merged + downstream artifact that
  confirms it lands, e.g. CI run URL, deploy SHA, doc render URL>

## Root Cause Gate

- Classification: not an incident - <one reason, no `|` separator>

## Verification Evidence Ledger

- [x] <concrete check> — <evidence with https:// URL>
- [x] <second check> — <evidence with https:// URL>
```

## Pre-submit self-lint

Before opening the PR, run the lint locally against your draft:

```bash
python3 .github/scripts/lint_pr_body.py --body-file /tmp/pr-body.md
```

Exit 0 = PASS. Exit 1 = the gate will reject this PR; fix the
listed problems before opening. Do not skip this step — the CI
comment that fires on a failed lint is noise on the PR thread.

## Anti-patterns the lint catches (and you should not try)

- Pasting the bare template line
  `Classification: incident fix | diagnostics/instrumentation only | not an incident`
  as if it were a chosen value. The `|` separator marks it as a stub.
- Filling `Final Success Evidence:` with "tests pass". Tests are a
  proxy; the lint accepts it but the AGENTS.md §Acceptance rules do
  not. Evidence is the business artifact.
- Writing `Evidence proving it: see commit` with no URL. The ledger
  requires `https://` somewhere in the section, not the gate field —
  but reviewers will reject it anyway.
- Removing assertions to make tests green and writing "tests pass" in
  the ledger. AGENTS.md §Test Integrity forbids this and the PR
  template's Test Integrity Statement will expose it.
