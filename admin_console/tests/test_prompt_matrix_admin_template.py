from pathlib import Path


ADMIN_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "admin.html"
ADMIN_PRD = Path(__file__).resolve().parents[2] / "docs" / "ADMIN_PRD_B_PIPELINE.md"


def test_prompt_matrix_template_uses_real_api_hooks():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "/admin/prompt-matrix/config" in html
    assert "/admin/prompt-matrix/topics" in html
    assert "/admin/prompt-matrix/gaps" in html
    assert "/admin/prompt-matrix/generate" in html
    assert "/admin/prompt-matrix/candidates" in html
    assert "/admin/prompt-matrix/prompts" in html


def test_products_and_hotspots_new_admin_actions_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "/admin/brands/' + e.brand_id + '/products/discover" in html
    assert "openProductDiscoveryModal()" in html
    assert "productDiscoveryModalOpen" in html
    assert "/admin/hot-topics/batch" in html
    assert "selectedHotspotIds()" in html
    assert "hotspotFilter.brandId" in html
    assert "hotspotFilter.industry" in html


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


def test_prompt_lists_can_filter_by_topic():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'x-model="promptMatrixPromptTopic"' in html
    assert 'x-model="queryPoolPromptTopic"' in html
    assert "if (filters.topic_id) qp.set('topic_id', filters.topic_id);" in html
    assert "if (this.promptMatrixPromptTopic) qp.set('topic_id', this.promptMatrixPromptTopic);" in html


def test_segment_llm_brand_selects_use_brand_ids_for_disambiguation():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'x-model="segmentLlmForm.brandId"' in html
    assert 'x-model="llmForm.brandId"' in html
    assert ':value="brand.id"' in html
    assert "selectedBrandOptionById" in html


def test_brand_management_enrich_uses_filled_fields_and_disambiguates_choices():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "enrichContextPayload()" in html
    assert "JSON.stringify({ ...this.enrichContextPayload(), async: true })" in html
    assert "choice.description" in html
    assert "choice.industry" in html
    assert 'x-model="form.industry" list="brand-mgmt-industry-options-form"' in html
    assert '<select x-model="form.industry"' not in html


def test_query_pool_assembly_panel_only_exposes_actionable_controls():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]
    for active_phrase in (
        "Segment/Profile 采样",
        "候选组装",
        "每 Prompt Profile",
        "总上限",
        "超限处理",
    ):
        assert active_phrase in query_pool_section
    for inactive_phrase in (
        "候选组装设置",
        "配置 Prompt x Segment x Profile 候选生成所需的采样、数量与上限",
        "候选生成",
        "Topic 覆盖",
        "执行安排",
        "调度页管理",
        "采样 / 数量 / 上限",
        "执行引擎、预算与优先级在调度页统一管理",
        "引擎策略",
        "预算上限",
        "入队窗口",
        "去重策略",
        "执行优先级",
        "Segment 适配范围",
        "评分维度",
        "无适配处理",
        "Segment 上下文适配评分",
        "当前仅开放后端已生效项",
        "后端已生效",
        "后端组装会实际使用",
        "已收敛",
        "待后端接入",
        "当前真实返回",
    ):
        assert inactive_phrase not in query_pool_section
    for inactive_model in (
        "queryPoolConfig.desiredEnginePolicy",
        "queryPoolConfig.budgetCap",
        "queryPoolConfig.scheduleWindow",
        "queryPoolConfig.dedupePolicy",
        "queryPoolConfig.priorityMode",
        "queryPoolConfig.segmentBindingPolicy",
        "queryPoolConfig.segmentScorePolicy",
        "queryPoolConfig.unmatchedSegmentPolicy",
    ):
        assert inactive_model not in html
    assert "queryPoolConfig.engineCount" not in html


def test_query_pool_estimates_candidates_without_engine_expansion():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "候选就绪" in html
    assert "已选 Prompt x 每 Prompt Profile" in html
    assert "return promptCount * profiles;" in html
    assert "promptCount * profiles * engines" not in html


def test_query_pool_kpis_are_candidate_quality_not_execution_success():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    for label in (
        "候选就绪",
        "渲染通过率",
        "Segment 覆盖",
        "Profile 覆盖",
        "重复待审",
        "调度接收",
    ):
        assert label in html
    query_pool_section = html[html.index("Query Pool") :]
    assert "Engine Success Rate" not in query_pool_section
    assert "Per-Segment Execution Success" not in query_pool_section


def test_query_pool_quality_metrics_are_not_static_mock_values():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]
    for mock_value in ("4,680", "99.2%", "82%", "3 个待审", "queries:4680"):
        assert mock_value not in query_pool_section
    assert "queryPoolQualityGateRows()" in query_pool_section
    assert "queryPoolPreflightRows()" in query_pool_section
    assert "queryPoolCostRows()" in query_pool_section
    assert "queryPoolPreflightSummary" in html
    assert "applyQueryPoolPreflightSummary" in html


def test_query_pool_preflight_button_calls_backend_preflight():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]
    assert '@click="startQueryPoolPreflight()"' in query_pool_section
    assert "API_BASE + '/admin/query-pool/preflight'" in html


def test_query_pool_frontend_marks_topic_segment_alignment_as_future_backend_rule():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]
    for phrase in (
        "Segment-Profile 可采样",
    ):
        assert phrase in query_pool_section
    for outdated_phrase in (
        "Topic eligible Segment",
        "Topic eligible 池",
        "Segment 仅从 Topic eligible 池采样",
        "预检将阻断",
        "按 Brand / Topic / Intent 打适配分",
        "仅用于展示",
        "待后端接入",
        "Topic 覆盖",
        "用于确认所选 Prompt 的主题覆盖",
    ):
        assert outdated_phrase not in query_pool_section
    assert "queryPoolPromptTopicLabel(prompt)" in query_pool_section
    assert "queryPoolPromptEligibilityText(prompt)" in query_pool_section
    assert "segment_binding_policy" not in html
    assert "segment_score_policy" not in html
    assert "unmatched_segment_policy" not in html


def test_query_pool_candidate_list_is_server_paginated_for_large_volume():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "loadQueryPoolCandidates()" in html
    assert "API_BASE + '/admin/query-pool/candidates?'" in html
    assert "API_BASE + '/admin/query-pool/assemble'" in html
    assert "queryPoolCurrentRunId" in html
    assert "queryPoolCandidateRows: []" in html
    assert "queryPoolCandidateCursor" in html
    assert "queryPoolCandidatePageRangeText()" in html
    assert "当前窗口" in html
    candidate_section = html[html.index("Query 候选列表") :]
    assert 'x-for="q in queryPoolCandidateRows"' in candidate_section
    assert 'x-for="q in queryDetailList"' not in candidate_section
    loader_section = html[html.index("async loadQueryPoolCandidates") : html.index("openQueryPoolPanel")]
    assert "this.queryDetailList" not in loader_section
    assert "filteredRows" not in loader_section


def test_query_pool_candidate_list_is_prompt_first_and_deemphasizes_topic():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    candidate_section = html[html.index("Query 候选列表") : html.index("async loadQueryPoolCandidates")]

    assert "q.promptText" in candidate_section
    assert "topicTitle(q.topicId)" not in candidate_section
    assert "q.topicText" in candidate_section


def test_query_pool_candidate_delete_controls_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    candidate_section = html[html.index("Query 候选列表") : html.index("async loadQueryPoolCandidates")]

    assert "queryPoolSelectedCandidateIds: {}" in html
    assert "selectedQueryPoolCandidateIds()" in html
    assert "setQueryPoolCandidatePageSelection($event.target.checked)" in candidate_section
    assert "deleteQueryPoolCandidate(q)" in candidate_section
    assert "deleteSelectedQueryPoolCandidates()" in candidate_section
    assert "API_BASE + '/admin/query-pool/candidates/bulk-delete'" in html
    assert "DELETE" in html


def test_query_pool_assemble_resets_candidate_filters_before_new_run():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assemble_start = html.index("async startQueryPoolAssemble")
    assemble_setup = html[assemble_start : html.index("try {", assemble_start)]

    assert "this.queryPoolCandidateQuery = ''" in assemble_setup
    assert "this.queryPoolCandidateSegment = ''" in assemble_setup
    assert "this.queryPoolCandidateProfile = ''" in assemble_setup
    assert "this.queryPoolCandidateStatus = ''" in assemble_setup
    assert "this.queryPoolCandidateRows = []" in assemble_setup
    assert "this.queryPoolCandidateCursor = { next: null, prev: null }" in assemble_setup


def test_query_pool_primary_assemble_button_starts_backend_run():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]
    primary_actions = query_pool_section[
        query_pool_section.index("预估成本") : query_pool_section.index("组装配置")
    ]
    assert '@click="startQueryPoolAssemble()"' in primary_actions
    assert "queryPoolAssembling ? '组装中...' : '组装 Query'" in primary_actions
    assert 'id="query-pool-action-panel"' in query_pool_section
    assert "document.getElementById('query-pool-action-panel')" in html


def test_query_pool_assemble_uses_run_polling_and_persistent_error():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[
        html.index('<h3 class="text-[15px] font-bold text-ink">Query Pool</h3>')
        : html.index("<!-- ============ PAGE: PIPELINE PROXY")
    ]

    assert "queryPoolAssembleError" in html
    assert "startQueryPoolRunPolling" in html
    assert "loadQueryPoolRun" in html
    assert "Query 组装失败" in query_pool_section
    assert "'/api/admin/query-pool/runs/'" in html


def test_query_pool_polling_refreshes_candidates_while_run_is_running():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    polling = html[html.index("startQueryPoolRunPolling") : html.index("async startQueryPoolPreflight")]

    assert "const assembledCount = Number(run.candidates_assembled || 0);" in polling
    assert "assembledCount > Number(this.queryPoolCandidatePageInfo.approxTotal || 0)" in polling
    assert "await this.loadQueryPoolCandidates();" in polling


def test_query_pool_run_polling_retry_does_not_mark_assembly_failed():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    polling = html[html.index("startQueryPoolRunPolling") : html.index("async startQueryPoolPreflight")]

    assert "queryPoolRunLoadFailures" in html
    assert "queryPoolRunStatusNotice" in html
    assert "this.queryPoolRunLoadFailures = 0" in polling
    assert "this.queryPoolRunStatusNotice = ''" in polling
    assert "await this.loadQueryPoolCandidates()" in polling
    assert "this.queryPoolRunLoadFailures >= Number(this.queryPoolRunPollMaxFailures || 3)" in polling
    assert "this.queryPoolAssembleError = error.message || 'Query run polling failed'" in polling


def test_prompt_matrix_quality_blocked_and_poll_failure_feedback_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    apply_start = html.index("promptMatrixApplyRunProgress(run)")
    apply_section = html[apply_start:html.index("promptMatrixRunStatusLabel()", apply_start)]
    polling = html[html.index("startPromptMatrixRunPolling") : html.index("async startPromptMatrixGenerate")]

    assert "promptMatrixRunPollFailures" in html
    assert "promptMatrixRunPollMaxFailures" in html
    assert "this.promptMatrixRunPollFailures += 1" in polling
    assert "this.clearPromptMatrixRunPolling()" in polling
    assert "quality_gate_blocked" in html
    assert "prompt_not_natural" in html
    assert "this.promptMatrixShowRejected = true" in apply_section
    assert "this.generationQualityBlockedMessage('Prompt', run.metrics" in apply_section


def test_query_pool_quality_blocked_feedback_and_poll_limit_are_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    polling = html[html.index("startQueryPoolRunPolling") : html.index("async startQueryPoolPreflight")]

    assert "queryPoolRunPollMaxFailures" in html
    assert "this.queryPoolAssembling = false" in polling
    assert "queryPoolQualityBlockedMessage()" in html
    assert "this.generationQualityBlockedMessage('Query', s)" in html
    assert "query_not_natural" in html
    assert "query_repaired" in html


def test_query_pool_visible_copy_is_chinese():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    query_pool_section = html[html.index("Query Pool") : html.index("<!-- ============ PAGE: PIPELINE PROXY")]
    for phrase in (
        "Candidate Assembly",
        "Candidate Ready",
        "Render Pass Rate",
        "Profile Coverage",
        "Duplicate Review",
        "Scheduler Intake",
        "Candidate Quality",
        "Query Candidate List",
        "Search prompt, segment, text",
        "Profiles per Prompt",
        "Routing intent",
        "Engine policy:",
        "Loading candidates",
        "No candidates",
        " candidates",
        "candidate pool",
        "Prompt load failed",
    ):
        assert phrase not in query_pool_section


def test_prd_defines_large_scale_query_candidate_contract():
    prd = ADMIN_PRD.read_text(encoding="utf-8")
    assert "100M to 1B+ rows" in prd
    assert "server-side cursor/keyset pagination" in prd
    assert "query_generation_candidates" in prd
    assert "POST /api/admin/query-pool/preflight" in prd
    assert "POST /api/admin/query-pool/assemble" in prd
    assert "GET /api/admin/query-pool/candidates" in prd
    assert "POST /api/admin/query-pool/candidates/:id/review" in prd
    assert "GET /admin/api/v1/pipeline/query-pool/candidates" in prd
    assert "Do not use offset pagination for large runs" in prd
    assert "Prompt x Segment x Profile candidate" in prd
    assert "preflight_summary" in prd
    assert "不允许静态 mock 数值" in prd
    assert "只开放后端当前真实生效的候选组装参数" in prd
    assert "不作为 Query Pool 的可操作选项" in prd
    assert "去重策略当前为后端固定的渲染文本 hash 去重" in prd
    assert "页面必须标注为待后端接入" in prd


def test_profile_groups_are_labeled_as_segments_with_profile_drilldown():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert "label:'Segment'" in html
    assert "+ 新建 Segment" in html
    assert "segmentProfiles:" in html
    assert "Segment 内用于 Query 采样的单个 Profile" in html
    assert "+ 新建 ProfileGroup" not in html


def test_topic_plan_generation_status_and_stop_button_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'stopTopicPlanGenerate()' in html
    assert 'topicPlanStopLoading' in html
    assert 'topicPlanRunStatusLabel()' in html
    assert "/admin/topic-plan/runs/" in html
    assert "stop'" in html or 'stop", {' in html or 'stop\', {' in html


def test_prompt_matrix_generation_status_and_stop_button_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'stopPromptMatrixGenerate()' in html
    assert 'promptMatrixStopLoading' in html
    assert 'promptMatrixRunStatusLabel()' in html
    assert "/admin/prompt-matrix/runs/" in html


def test_query_pool_generation_status_and_stop_button_wired():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    assert 'stopQueryPoolAssemble()' in html
    assert 'queryPoolStopLoading' in html
    assert 'queryPoolRunStatusLabel()' in html
    assert "/admin/query-pool/runs/" in html
