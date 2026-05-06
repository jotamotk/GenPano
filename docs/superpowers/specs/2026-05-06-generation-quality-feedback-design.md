# Generation Quality Feedback Design

Date: 2026-05-06

## Scope

Unify the Topic Plan, Prompt Matrix, and Query Pool generation flows so quality
gates improve output without silently hiding all generated data. This applies to
generation prompts, backend run metrics, terminal run status, and Admin UI
feedback.

## Layer Rules

Topic Plan generates consumer-facing topic subjects. A Topic may be a natural
search subject such as a guide, review, comparison, troubleshooting method, or
shopping question. It must reject internal operator work such as CRM, private
domain operations, user portraits, conversion paths, channel operations, and
corporate group wording.

Prompt Matrix generates complete user prompts. A Prompt must be a natural
consumer question or request, must match the selected language, must stay tied to
its source Topic, and must not include profile-personalized anchors.

Query Pool generates profile-personalized queries. A Query must remain a natural
consumer question after personalization. Query Pool may repair a bad LLM query
into a safe query, but repairs must be counted and surfaced.

## Run Metrics Contract

Each generation run should expose comparable metrics:

- `requested`: requested or estimated output count.
- `llm_returned`: number of LLM items seen when known.
- `accepted`: items inserted for review.
- `rejected_total`: items rejected by quality gates or limits.
- `by_reason`: reason-code counts.
- `rejected_sample`: capped examples for Admin UI diagnostics.
- `quality_blocked`: true when LLM returned or produced candidates but none
  passed quality gates.

Reason codes should stay stable enough for UI labels: duplicate, layer boundary,
not natural, language mismatch, topic mismatch, brand leak, selected entity
mismatch, over limit, and repaired query.

## Run Status Semantics

If some candidates pass, the run completes even when some items are rejected.
The UI shows a yellow quality warning with counts and samples.

If no candidates pass because quality gates rejected all generated items, the run
is marked `failed` with `llm_error = quality_gate_blocked`. Metrics remain
persisted so the UI can explain what happened instead of spinning forever or
showing an empty review table without context.

If no candidates exist because there was no input scope, no gaps, no selected
topics, or no profile pool, existing validation errors remain distinct from
quality gate failures.

## Frontend Behavior

Topic Plan, Prompt Matrix, and Query Pool polling must stop on completed,
failed, cancelled, or repeated polling failures. Loading state must be cleared in
all terminal cases.

For quality-blocked runs, Admin should show a direct message:

`生成结果全部被质检拦截：<top reason labels>. 可展开查看样例。`

For partially rejected runs, Admin should show:

`已进入待审核 <accepted> 条，质检拦截 <rejected_total> 条。`

The review list remains scoped to the current run when a run id is available,
but an empty list should not be the only signal.

## Verification

Backend tests must cover:

- Topic Plan quality-blocked run persists metrics and fails terminally.
- Prompt Matrix quality-blocked run persists metrics and fails terminally.
- Query Pool quality-blocked or repaired output exposes comparable preflight
  metrics.
- Prompt and Query quality gates remain strict natural-question gates.
- Topic quality gate accepts consumer subject titles without accepting internal
  operator topics.

Template tests must cover visible quality-blocked messaging and polling failure
handling for all three generation surfaces.
