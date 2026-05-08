# Generation Quality Feedback Implementation Plan

> **2026-05-08 update (PR #386):** This plan was written before the Flask
> `admin_console/` migration. The Flask service has been deleted; references
> below to `admin_console/app.py`, `admin_console/topic_plan.py`,
> `admin_console/prompt_matrix.py`, `admin_console/templates/admin.html`, and
> `admin_console/tests/*` should be re-mapped to:
> - `backend/app/api/admin/topic_plan/`, `backend/app/api/admin/prompt_matrix/`
> - `backend/app/services/topic_plan.py`, `backend/app/services/prompt_matrix.py`
> - `backend/static/admin.html`
> - `backend/tests/`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Topic Plan, Prompt Matrix, and Query Pool generation stop cleanly and explain quality-gate rejections instead of appearing stuck or empty.

**Architecture:** Keep existing Admin Console modules and tables. Add a shared generation metrics shape, mark zero-accepted quality-gated runs as terminal `failed` with `quality_gate_blocked`, and update the single orange Admin template to show quality-blocked and partial-rejection feedback.

**Tech Stack:** Flask/Python backend in `admin_console/app.py`, helper rules in `admin_console/topic_plan.py` and `admin_console/prompt_matrix.py`, Alpine-based Admin UI in `admin_console/templates/admin.html`, pytest.

---

### Task 1: Shared Quality-Blocked Metrics

**Files:**
- Modify: `admin_console/app.py`
- Test: `admin_console/tests/test_topic_plan_api.py`
- Test: `admin_console/tests/test_prompt_matrix_api.py`
- Test: `admin_console/tests/test_query_pool_backend.py`

- [ ] **Step 1: Write failing tests for zero-accepted quality-gated runs**

Add tests that execute the worker helpers with fake LLM output rejected by quality rules. Assert the run is terminal, `llm_error` is `quality_gate_blocked`, and `metrics_json` or `preflight_summary` contains `accepted=0`, `rejected_total>0`, `quality_blocked=true`, and `by_reason`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
py -m pytest admin_console/tests/test_topic_plan_api.py admin_console/tests/test_prompt_matrix_api.py admin_console/tests/test_query_pool_backend.py -q
```

Expected: new tests fail because zero-accepted Topic/Prompt runs currently complete, and Query Pool does not expose the same quality-blocked contract.

- [ ] **Step 3: Implement the shared metrics shape**

Update `_compute_generation_metrics` to add `quality_blocked` when `accepted == 0` and `rejected_total > 0`. For Query Pool, add equivalent fields into `_query_pool_summary` or the completion path without changing existing candidate rows.

- [ ] **Step 4: Mark quality-blocked Topic/Prompt runs failed**

After metrics are computed in `_execute_topic_plan_generation` and `_execute_prompt_matrix_generation`, if `quality_blocked` is true, persist `status='failed'`, `llm_error='quality_gate_blocked'`, `metrics_json`, `completed_at`, and `updated_at`. Keep partial-rejection runs as `completed`.

- [ ] **Step 5: Run focused tests and commit**

Run the focused pytest command again. Commit backend behavior when green.

### Task 2: Generation Prompts Stay Quality-First

**Files:**
- Modify: `admin_console/topic_plan.py`
- Modify: `admin_console/prompt_matrix.py`
- Modify: `admin_console/app.py`
- Test: `admin_console/tests/test_topic_plan_utils.py`
- Test: `admin_console/tests/test_prompt_matrix_utils.py`
- Test: `admin_console/tests/test_query_pool_backend.py`

- [ ] **Step 1: Write failing prompt-contract tests**

Assert Topic Plan messages explain that Topic titles may be consumer subject phrases but reject internal operator work. Assert Prompt Matrix messages require complete natural questions and do not permit SEO titles. Assert Query Pool LLM messages require personalized natural questions and mention quality repair/rejection.

- [ ] **Step 2: Run focused tests and verify failures**

Run:

```powershell
py -m pytest admin_console/tests/test_topic_plan_utils.py admin_console/tests/test_prompt_matrix_utils.py admin_console/tests/test_query_pool_backend.py -q
```

- [ ] **Step 3: Adjust only generation instructions**

Tighten prompt text and examples. Do not relax Prompt or Query natural-question gates. Keep Topic rules rejecting internal operator language.

- [ ] **Step 4: Run focused tests and commit**

Run the focused pytest command again. Commit prompt-contract changes when green.

### Task 3: Admin UI Feedback

**Files:**
- Modify: `admin_console/templates/admin.html`
- Test: `admin_console/tests/test_topic_plan_admin_template.py`
- Test: `admin_console/tests/test_prompt_matrix_admin_template.py`

- [ ] **Step 1: Write failing template tests**

Assert the template includes `quality_gate_blocked` handling, `qualityBlockedRunMessage`, updated rejection reason labels for Topic/Prompt/Query, and polling failure stopping for Prompt Matrix and Query Pool.

- [ ] **Step 2: Run template tests and verify failures**

Run:

```powershell
py -m pytest admin_console/tests/test_topic_plan_admin_template.py admin_console/tests/test_prompt_matrix_admin_template.py -q
```

- [ ] **Step 3: Implement UI helpers and polling behavior**

Add a helper that converts run metrics into user-facing text. On completed runs with rejections, show partial quality warnings. On failed `quality_gate_blocked`, clear loading state and show the top rejection reasons and samples. Make Prompt Matrix and Query Pool polling stop after repeated failures like Topic Plan already does.

- [ ] **Step 4: Run template tests and commit**

Run the template pytest command again. Commit UI behavior when green.

### Task 4: Full Verification and Publish

**Files:**
- All changed files

- [ ] **Step 1: Run full Admin tests**

Run:

```powershell
py -m pytest admin_console/tests -q
py -m compileall -q admin_console
```

- [ ] **Step 2: Inspect diff**

Run:

```powershell
git diff --stat origin/main...HEAD
git status --short --branch
```

- [ ] **Step 3: Push, open PR, merge after green CI**

Push the branch, create PR, wait for checks, merge, and watch Build & Deploy.

- [ ] **Step 4: Post-deploy CI/CD diagnostic**

Run server diagnostics or a focused production probe to confirm the deployed image SHA and that quality-blocked runs are terminal with visible metrics.
