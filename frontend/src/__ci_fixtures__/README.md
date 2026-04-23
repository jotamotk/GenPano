# Harness Self-Seeded Violation Fixtures

**Do not import from these files. Do not render them. Do not "fix" them.**

These `*.cifixture.{js,jsx}` files intentionally violate harness rules from
`scripts/ci-check.mjs`. Their existence proves the grep rules actually catch
real violations — a dead-canary check for the harness itself.

## Policy

| Topic | Rule |
|-------|------|
| Build exclusion | `frontend/vite.config.js` → `rollupOptions.external = (id) => id.includes('__ci_fixtures__')` |
| Type-check exclusion | No `tsconfig.json` yet (all-JSX). When one arrives, `"exclude": ["src/__ci_fixtures__/**"]` |
| Main harness scan | `ci-check.mjs` scans this dir **only** when `--include-fixtures` is passed (used by `npm run ci:harness:selftest`) |
| Selftest assertion | `scripts/ci-harness-selftest.mjs` asserts every EXPECTED_POSITIVES entry has ≥1 violation hit pointing at its fixture marker |
| Lint/format | This dir has `eslint-disable` at top of each file; Prettier is fine to run |

## Fixture ↔ rule map (Session 0-rev seed)

| Fixture | Rule | Violation seeded |
|---------|------|------------------|
| `A1_cjk_leak.cifixture.jsx` | A1 | CJK in JSX text node (`<h1>总览面板</h1>`) |
| `B1_sparkline_literal.cifixture.jsx` | B1 | `<MiniSparkline width={260} height={48} />` |
| `C11_mentionrate_over1.cifixture.js` | C11-1 | `mentionRate: 1620` and `mentionRate: 3.14` |
| `C14_h1_text3xl.cifixture.jsx` | C14-1 | `<h1 className="text-3xl">` |
| `D4_missing_301.cifixture.jsx` | D4 | Legacy `/dashboard → /brand/overview` omitted |

## Adding a new fixture

1. Name the file `<RULE_ID>_<short_slug>.cifixture.jsx` (or `.js`) — the rule
   registry uses a path substring like `/<RULE>_/` to match its fixtures.
2. If the target rule currently scans a single hardcoded file
   (`MiniSparkline.jsx`, `mock.js`, `App.jsx`, etc), update the rule to also
   scan this dir when `ctx.includeFixtures` is truthy.
3. Add an entry to `EXPECTED_POSITIVES` in `scripts/ci-harness-selftest.mjs`.
4. Run `npm run ci:harness:selftest` and confirm it passes.
