from pathlib import Path


ADMIN_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "admin.html"


def test_prompt_matrix_template_uses_real_api_hooks():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "/admin/prompt-matrix/config" in html
    assert "/admin/prompt-matrix/topics" in html
    assert "/admin/prompt-matrix/gaps" in html
    assert "/admin/prompt-matrix/generate" in html
    assert "/admin/prompt-matrix/candidates" in html
    assert "/admin/prompt-matrix/prompts" in html


def test_prompt_matrix_selector_controls_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'x-model="promptMatrixTopicQuery"' in html
    assert 'onPromptMatrixTopicFilterChanged()' in html
    assert "setPromptMatrixTopics(true, 'page')" in html
    assert "setPromptMatrixTopics(true, 'filtered')" in html
    assert "setPromptMatrixTopics(false, 'page')" in html
    assert "setPromptMatrixTopics(false, 'all')" in html
    assert "changePromptMatrixTopicPage(1)" in html
    assert "changePromptMatrixTopicPage(-1)" in html


def test_prompt_matrix_toolbar_generate_runs_directly_without_candidate_panel():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert '@click="startPromptMatrixGenerate()"' in html
    assert "openPromptMatrixPanel('generate', { autoStart: true })" not in html
    assert "options.autoStart" not in html
    assert "this.openPromptMatrixPanel('pending');" not in html
    assert "Prompt 生成任务已启动" in html
    assert "待审核列表已刷新" in html


def test_prompt_matrix_candidate_review_tabs_and_pagination_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "promptMatrixCandidateTabs()" in html
    assert "setPromptMatrixCandidateStatus(tab.status)" in html
    assert "promptMatrixCandidatePageRangeText()" in html
    assert "changePromptMatrixCandidatePage(1)" in html
    assert "changePromptMatrixCandidatePage(-1)" in html
    assert "per_page:String(this.promptMatrixCandidatePerPage || 20)" in html
    assert "promptMatrixActionPanel==='pending'" not in html
    assert "候选 Prompt" in html
    assert "Topic → Prompt" in html
    assert "生成逻辑" in html
    assert "promptMatrixGenerationTrace(item)" in html


def test_prompt_matrix_candidate_bulk_review_is_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "promptMatrixSelectedCandidateIds: {}" in html
    assert "setPromptMatrixCandidatePageSelection($event.target.checked)" in html
    assert "bulkReviewPromptCandidates('approved')" in html
    assert "bulkReviewPromptCandidates('rejected')" in html
    assert "/admin/prompt-matrix/candidates/bulk-review" in html
    assert "selectedPromptMatrixCandidateIds()" in html


def test_prompt_matrix_workspace_tabs_separate_review_and_coverage():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "promptMatrixWorkspaceTab: 'review'" in html
    assert "setPromptMatrixWorkspaceTab('review')" in html
    assert "setPromptMatrixWorkspaceTab('coverage')" in html
    assert "promptMatrixWorkspaceTab==='review'" in html
    assert "promptMatrixWorkspaceTab==='coverage'" in html
    prompt_matrix_section = html.index("page==='planner-prompt-matrix'")
    assert html.index("promptMatrixWorkspaceTab==='review'") > prompt_matrix_section


def test_prompt_matrix_no_longer_seeds_mock_topics_or_prompts():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "seedPromptMatrixTopics" not in html
    assert "promptMatrixTopics: []" in html
    assert "promptMatrixPendingItems: []" in html
    assert "promptDetailList: []" in html


def test_query_pool_prompt_selector_is_paginated_for_large_prompt_sets():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "loadQueryPoolPrompts()" in html
    assert "queryPoolSelectedPromptIds: {}" in html
    assert "queryPoolSelectionMode: 'explicit'" in html
    assert "setQueryPoolPrompts(true, 'filtered')" in html
    assert "setQueryPoolPrompts($event.target.checked, 'page')" in html
    assert "changeQueryPoolPromptPage(1)" in html
    assert "queryPoolPromptPageRangeText()" in html
    assert "filteredQueryPoolPrompts()" not in html


def test_query_pool_budget_cap_is_numeric_input():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'x-model.number="queryPoolConfig.budgetCap"' in html
    assert 'type="number" min="1" step="10"' in html
    assert 'x-model="queryPoolConfig.budgetCap"' not in html


def test_profile_groups_are_labeled_as_segments_with_profile_drilldown():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "label:'Segment'" in html
    assert "+ 新建 Segment" in html
    assert "segmentProfiles:" in html
    assert "Segment 内用于 Query 采样的单个 Profile" in html
    assert "+ 新建 ProfileGroup" not in html
