# Session 0' Delivery Report

**Date**: 2026-04-27
**Branch**: `feature/session-0-baseline`
**Phase Gate**: 1 / 11 GREEN (G1.1 - G1.11 all PASS)

---

## §1 · Scope (REPLAN §4 Session 0')

**What this session delivered**: Python backend baseline (FastAPI / SQLAlchemy 2.0 async / Alembic / Celery 6 queues / Pydantic v2 settings), CI/CD scaffold (`ci.yml` backend-lint-test + `deploy-preview.yml` backend-preview lane), Harness Python translation (5 rules / 5 self-seeded fixtures / selftest), Phase Gate 1 verification tooling (Makefile + pre-commit + verify script + this report).

**What this session deferred**:
- FastAPI app routes beyond `/healthz` (Session 4a' onwards)
- Real adapter `execute()` (Session 1.2')
- Knowledge graph cold-start (Session 1.5')
- Planner LLM threading (Session 2' / 2.1')
- Frontend wiring (Session 4b')
- Live Supabase preview DB connection (queued for Frank, see §7)

---

## §2 · 11 Step deliverables (commit hash + 1-line summary)

- **Step 1** -- *no discrete commit* -- Branch `feature/session-0-baseline` cut from main at `c118261` (Plan J D1+D4); repo bootstrap (gitignore, dirs, REPLAN docs migration) was rolled into Step 2's first explicit work.
- **Step 2** -- `7a54fe3` -- pyproject.toml + uv sync (uv lockfile baseline; FastAPI / SQLAlchemy / Alembic / Celery / Redis / Pydantic v2 deps pinned).
- **Step 3** -- `42f0f86` -- FastAPI `/healthz` skeleton (`app/main.py` + minimal app factory).
- **Step 4** -- `9057574` -- SQLAlchemy 2.0 async engine + Base + Pydantic Settings (`app/db/`, `app/core/config.py`).
- **Step 5** -- `817d49d` -- Alembic init (`alembic/env.py` async-aware + `alembic.ini`, no baseline migration yet).
- **Step 6** -- `cad918d` -- Alembic baseline migration (G1.6 8/8 PASS) -- first revision generates schema scaffolding.
- **Step 7** -- `294191d` -- Settings `DATABASE_URL` + Celery 6 queues (G1.7 8/8 PASS) -- `app/celery_app.py` + `tasks/health.py` + `.env.example` Python era vars.
- **Step 8** -- `73f5c01` -- `.github/workflows/ci.yml` 5-step lint+test pipeline on Python 3.12 (ruff check + ruff format --check + mypy strict + alembic + pytest).
- **Step 9** -- `40dbf2a` -- Harness Python L1 (F1 + F4-1/2/3 + D8 = 5 rules) + 5 self-seeded fixtures + `ci_harness_selftest.py` 5/5.
- **Step 10** -- `38e59e3` -- `deploy-preview.yml` backend-preview sibling job (10-step preview gate; PR or feature/** push triggers; Supabase URL || sqlite fallback).
- **Step 11** -- *this commit* -- Phase Gate 1 collateral: `backend/Makefile` + `.pre-commit-config.yaml` + `scripts/verify-session-0prime.sh` + this report.

---

## §3 · Architecture summary

```
genpano/
  .github/workflows/
    ci.yml                       # backend-lint-test (Step 8)
    deploy-preview.yml           # build-and-push + deploy + backend-preview (Step 10)
    deploy.yml                   # production deploy (pre-existing)
    docker-cleanup.yml           # pre-existing
  .pre-commit-config.yaml        # Step 11 ruff + harness local hook
  scripts/
    verify-session-0prime.sh     # Step 11 one-shot verification
  backend/
    Makefile                     # Step 11 8 targets
    pyproject.toml               # Step 2 + Step 9 (excludes for fixtures)
    uv.lock                      # Step 2
    alembic.ini                  # Step 5
    alembic/
      env.py                     # Step 5 async-aware
      versions/                  # Step 6 baseline migration
    app/
      main.py                    # Step 3 FastAPI factory + /healthz
      celery_app.py              # Step 7 6 queues
      core/config.py             # Step 4 Pydantic Settings
      db/                        # Step 4 async engine + Base
      tasks/health.py            # Step 7
      __ci_fixtures__/           # Step 9 5 deliberate-violation fixtures
    scripts/
      ci_check.py                # Step 9 5 rules
      ci_harness_selftest.py     # Step 9 selftest
  docs/
    REPLAN_2026_04_26.md         # main truth source
    SESSION_0_PRIME_DELIVERY.md  # Step 11 (this file)
    ... (other Session prompts + strategic docs)
```

---

## §4 · How to run locally

One-shot verification (read-only sanity check):

```bash
bash scripts/verify-session-0prime.sh
```

Full local CI (matches `.github/workflows/ci.yml` lane):

```bash
cd backend
make install
make ci   # lint + type + harness + migrate + test
```

Targeted commands:

```bash
cd backend
make lint        # ruff check
make format      # ruff format (writes)
make type        # mypy strict on app/
make harness     # ci_check.py + ci_harness_selftest.py
make migrate     # alembic upgrade head
make test        # pytest -q (exit 5 = no tests, accepted)
make clean       # purge caches
```

Pre-commit hook setup (one-time):

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

---

## §5 · Harness Python rules (5 total)

- **F1** `no-bare-playwright-import` -- forbids `import playwright` / `from playwright...` outside the future Camoufox wrapper. Origin: CLAUDE.md #22.F. Scanner: regex line-anchored.
- **F4-1** `adapter-execute-stamps-response-source` -- adapter `execute()` return dict literals must include the `response_source` key. Origin: CLAUDE.md #28.G C2 (6-enum response_source labeling). Scanner: AST `ast.FunctionDef` named `execute` walking `ast.Return` for `ast.Dict`.
- **F4-2** `api-fallback-stamps-response-source-literal` -- functions with `api_fallback` in their name must return `response_source: "api_fallback"`. Origin: CLAUDE.md #28.G C2. Scanner: AST + value comparison.
- **F4-3** `aiResponse-constructor-explicit-kwarg` -- `AiResponse(...)` constructor calls must include explicit `response_source=` kwarg. Origin: CLAUDE.md #28.G C2. Scanner: AST `ast.Call` matching `func.id`/`func.attr == "AiResponse"`.
- **D8** `no-hardcoded-jwt-secret` -- `JWT_SECRET` / `SECRET_KEY` / `ADMIN_JWT_SECRET` must come from env/settings, not string literals. Origin: CLAUDE.md #24.F. Scanner: AST `ast.Assign` to a `Name` in the target frozenset where `node.value` is `ast.Constant(str)`.

Selftest (`scripts/ci_harness_selftest.py`) asserts each rule fires `>= EXPECTED_POSITIVES[rule_id]` violations against `backend/app/__ci_fixtures__/`. Each fixture deliberately commits exactly one violation; rule-id-tagged docstrings deliberately avoid the trigger token to prevent self-satisfying false positives (see auto-memory `feedback_fixture_naming.md`).

---

## §6 · Deviations registered (Rule 13.5 / Rule 25.3)

- **Step 1 has no discrete commit** -- Repo bootstrap (gitignore, dirs, REPLAN doc migration from `GENPANO_Claude_Lead/`) was rolled into Step 2's `7a54fe3` commit because all the bootstrap edits and the first uv-sync ran together. The branch was cut from `c118261` (Plan J D1+D4) on main, which serves as the de-facto Step 1 anchor. No regression vs REPLAN §4: REPLAN doesn't mandate per-step commit granularity, only per-step Phase Gate evidence.
- **Step 5 `alembic/env.py` was [复用]-leaning [扩写]** -- alembic's `init` template was emitted by `alembic init`, then heavily modified to wire SQLAlchemy 2.0 async + import the project's Pydantic Settings. We labeled it [扩写] in the dispatch but the body is closer to a fresh write on top of a vendored template; mark it [复用 of vendor scaffold] for future audits.
- **Step 7 default DB dialect is `sqlite+aiosqlite`** -- `app/core/config.py` defaults `GENPANO_DATABASE_URL` to `sqlite+aiosqlite:///./dev.db` for local dev ergonomics. Production / preview overrides via env (Supabase preview URL or live postgres URL). This is a deliberate dev-ergonomics choice, not a hidden default for prod.
- **Step 10 `actionlint` not run locally** -- Optional Probe 9 was SKIPPED because actionlint isn't installed on Frank's Windows host. GitHub-side workflow validation will catch syntax errors on first push; PyYAML structural probes (8/8 mandatory) cover the local check.
- **Step 11 (this) Pre-Flight Grep E -- Step 1 commit absence** -- `git log --grep="Step 1"` returned no matches except Step 10. Documented above; not a STOP because the critical anchor (HEAD = `38e59e3`) matched the dispatch §2 expectation.

---

## §7 · Manual tasks queued for Frank (NOT blocking Phase Gate 1)

The following 4-step manual task connects Supabase preview DB to the `backend-preview` workflow. **Phase Gate 1 explicitly does not require this connection** -- the preview lane currently uses sqlite fallback per Step 10 backend-preview job step 8.

### Supabase preview branch connection (~15 min)

1. **Create Supabase project** (if not done): https://supabase.com -> New project -> name `genpano-preview` -> choose region (recommend Singapore for CN+SEA users) -> save the db password to a password manager.
2. **Get connection string**: Project Settings -> Database -> Connection string -> URI tab -> copy the `postgresql://...` URI. Replace `[YOUR-PASSWORD]` placeholder with the actual db password from step 1.
3. **Add as GitHub Actions secret**:
   - Repo Settings -> Secrets and variables -> Actions -> New repository secret
   - Name: `SUPABASE_PREVIEW_DB_URL`
   - Value: paste the URI from step 2 (with real password substituted)
4. **Verify connection on next PR**:
   - Open a PR (any small change) on a `feature/*` branch.
   - The `backend-preview` job in the Actions tab should now run `alembic upgrade head` against Supabase preview DB instead of sqlite.
   - Check the "Alembic upgrade head" step log: it should print `Using Supabase preview DB` instead of `Using sqlite fallback`.
   - Optional local verify: `psql $SUPABASE_PREVIEW_DB_URL -c '\dt'` should list the tables matching local `make migrate` output.

---

## §8 · What's next (Session A0' or 4a' -- Frank's call)

Per REPLAN_2026_04_26.md §4, the 11-Session schedule is: `0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3' / A1' / 4b'`. Suggested next = **Session A0'** (Admin auth scaffold) because the App-side Sessions (1' / 1.5' / 1.2' / 2' / 2.1') depend on Admin's `requireAdminSession()` helper for the platform-data review API surface (see CLAUDE.md #23.G `Admin quality-review endpoint` deferred dependency).

Session A0' prime prompt is in `docs/SESSION_A0_PRIME_PROMPT.md` already (Plan J D4 sweep applied). Frank starts a new branch `feature/session-A0prime-admin-auth` from main after Session 0' merges.

---

## §9 · Phase Gate 1 verification snapshot

Output of `bash scripts/verify-session-0prime.sh` at Step 11 commit time:

```
(snapshot to be pasted by Frank during local verification per §8 acceptance flow,
 or auto-captured in the Step 11 commit body's probe outputs)
```

Probe results from the Step 11 commit body are the authoritative snapshot.

---

## §10 · References

- `docs/REPLAN_2026_04_26.md` §4 -- 11 Session schedule (main truth source)
- `CLAUDE.md` #29 -- Python pivot anchor decision
- `CLAUDE.md` #21 -- Review closure 8 P0 gaps (testing discipline)
- `CLAUDE.md` #25 -- Prompt convention rules 1-13 (Rule 13.4 task labels)
- `CLAUDE.md` #22.F -- F1 rule TS-era origin
- `CLAUDE.md` #24.F -- D8 rule TS-era origin
- `CLAUDE.md` #28.G C2 + C3 -- F4 rule family + 6-enum response_source
- auto-memory `feedback_genpano_session_preview_env_2026_04_26.md` -- preview env horizontal requirement
- auto-memory `feedback_genpano_branch_per_session.md` -- branch per session strategy
- auto-memory `feedback_fixture_naming.md` -- docstring trigger-token avoidance pattern

---

## §11 · Sign-off

- [ ] Frank verified `bash scripts/verify-session-0prime.sh` GREEN locally
- [ ] Frank verified `cd backend && make ci` GREEN locally
- [ ] Frank verified `ci.yml` backend-lint-test job green on this branch's last push
- [ ] Frank reviewed §7 manual Supabase task as queued (not blocking)
- [ ] Branch `feature/session-0-baseline` ready for merge to main

---

## §12 · Plan J retrospective deferred

17 dirty Plan J / K era doc files (`CLAUDE.md`, `docs/SESSION_*_PRIME_PROMPT.md`, `docs/REPLY_TO_CC_RESUME_SESSION_0.md`, `docs/CC_REPLY_SESSION_0_G2_VERIFY_AND_STEP_2_4_PUSH.md`) were carried into the working tree before Session 0' Step 1 and remain unstaged across Steps 1-11. They will be addressed in a post-Session-0' Plan J retrospective commit, intentionally not part of Session 0' commit history. The Step 10 + Step 11 dispatches both staged explicit paths (`.github/workflows/deploy-preview.yml`; Step 11 stages only its own four files) to keep this separation clean.
