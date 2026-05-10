from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_prompt_matrix_generation_count_uses_manual_numeric_cap() -> None:
    html = _admin_html()

    assert "maxPrompts: 10," in html
    assert "promptMatrixMaxPromptsTouched: false" in html
    assert 'x-model.number="promptMatrixConfig.maxPerTopic"' in html
    assert ':max="promptMatrixMaxPerTopicCap()"' in html
    assert "promptMatrixMaxPerTopicValue()" in html
    assert "return 20;" in html
    assert 'x-model="promptMatrixConfig.maxPerTopic"' not in html
    assert 'x-model.number="promptMatrixConfig.maxPrompts"' in html
    assert 'type="number" min="1" step="1"' in html
    assert ':max="promptMatrixMaxPromptsCap()"' in html
    assert '@change="onPromptMatrixMaxPromptsChanged()"' in html
    assert "promptMatrixRawPromptCount()" in html
    assert "promptMatrixSuggestedMaxPromptsValue()" in html
    assert "promptMatrixMaxPromptsCap()" in html
    assert "syncPromptMatrixMaxPromptsWithEstimate()" in html
    assert "onPromptMatrixMaxPromptsChanged()" in html
    assert "qp.set('max_per_topic', this.promptMatrixMaxPerTopicValue());" in html
    assert "max_per_topic: this.promptMatrixMaxPerTopicValue()," in html
    assert "this.promptMatrixConfig.maxPrompts || 8000" not in html
    assert "Number(this.promptMatrixConfig.maxPrompts) || 8000" not in html


def test_prompt_matrix_candidate_filters_include_brand_select() -> None:
    html = _admin_html()

    assert "promptMatrixCandidateBrand: 'all'" in html
    assert "promptMatrixCandidateIntent: 'all'" in html
    assert "promptMatrixCandidateScope: 'all'" in html
    assert 'x-model="promptMatrixCandidateBrand"' in html
    assert 'x-model="promptMatrixCandidateIntent"' in html
    assert 'x-model="promptMatrixCandidateScope"' in html
    assert "promptMatrixTopicBrands()" in html
    assert "qp.set('brand_id', this.promptMatrixCandidateBrand)" in html
    assert "qp.set('intent', this.promptMatrixCandidateIntent)" in html
    assert "qp.set('prompt_scope', this.promptMatrixCandidateScope)" in html


def test_prompt_matrix_candidate_load_has_retry_and_diagnostic_errors() -> None:
    html = _admin_html()
    section = html[
        html.index("promptMatrixCandidateErrorMessage") : html.index(
            "async loadPromptMatrixPrompts"
        )
    ]

    assert "promptMatrixFetchCandidatesJson" in section
    assert "promptMatrixReadJsonResponse" in section
    assert "promptMatrixCandidateErrorMessage" in section
    assert "window.setTimeout(() => controller.abort(), 45000)" in section
    assert "[408, 429, 500, 502, 503, 504].includes(res.status)" in section
    assert "HTTP ' + res.status" in section
    assert "候选 Prompt 加载失败" in section
    assert "Candidate load failed" not in section


def test_prompt_matrix_candidate_rows_show_scope_badges() -> None:
    html = _admin_html()

    assert "promptMatrixScopeLabel(item)" in html
    assert "promptMatrixScopeTone(item)" in html
    assert "promptMatrixCompetitiveTypeLabel(item)" in html
    assert "promptMatrixCompetitorLabel(item)" in html
    assert "promptMatrixProductLabel(item)" in html
    assert "promptMatrixComparisonAxisLabel(item)" in html
    assert "promptMatrixContextVersionLabel(item)" in html
    assert "competitive_type" in html
    assert "competitor_name" in html
    assert "comparison_axis" in html
    assert "brand_context_version" in html


def test_prompt_matrix_candidate_rows_show_quality_gate_badges() -> None:
    html = _admin_html()

    assert "promptMatrixQualityGateLabel(item)" in html
    assert "promptMatrixQualityGateReason(item)" in html
    assert "quality_gate_status" in html
    assert "quality_gate_reason" in html
    assert "promptMatrixCandidateQualityGate: 'all'" in html
    assert 'x-model="promptMatrixCandidateQualityGate"' in html
    assert "qp.set('quality_gate', this.promptMatrixCandidateQualityGate)" in html
    assert "质检拦截" in html


def test_prompt_matrix_reviewed_candidates_can_be_deleted() -> None:
    html = _admin_html()

    assert "promptMatrixCandidateDeleting: false" in html
    assert "promptMatrixCanDeleteCandidate(item)" in html
    assert "deletePromptCandidate(item)" in html
    assert "deleteSelectedPromptCandidates()" in html
    assert "/api/admin/prompt-matrix/candidates/bulk-delete" in html
    assert "method: ids.length === 1 ? 'DELETE' : 'POST'" in html


def test_prompt_matrix_run_polling_handles_errors_locally() -> None:
    html = _admin_html()

    assert (
        "fetch('/api/admin/prompt-matrix/runs/' + encodeURIComponent(runId), "
        "{ credentials:'same-origin', silentError:true })"
    ) in html
    assert "const adminRoot = this;" in html
    assert "typeof adminRoot.showErrorFrom === 'function'" in html


def test_prompt_matrix_copy_distinguishes_quantity_from_allowed_cap() -> None:
    html = _admin_html()
    max_per_topic_index = html.index('x-model.number="promptMatrixConfig.maxPerTopic"')
    overflow_policy_index = html.index(
        'x-model="promptMatrixConfig.overflowPolicy"',
        max_per_topic_index,
    )
    prompt_matrix_controls = html[max_per_topic_index - 500 : overflow_policy_index + 500]

    assert "每 Topic 上限" in prompt_matrix_controls
    assert "生成数量" in prompt_matrix_controls
    assert "本次生成" in html
    assert "可填上限" in html
    assert "生成上限" not in prompt_matrix_controls
    assert "总上限 ${this.promptMatrixMaxPromptsValue()" not in html
