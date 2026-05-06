from pathlib import Path


ADMIN_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "admin.html"


def _topic_plan_section(html: str) -> str:
    start = html.index("page==='planner-topics'")
    end = html.index("<!-- KPI row -->", start)
    return html[start:end]


def _topic_plan_polling_section(html: str) -> str:
    start = html.index("startTopicPlanRunPolling(runId)")
    end = html.index("async startTopicPlanGenerate()", start)
    return html[start:end]


def test_topic_plan_generation_controls_do_not_include_query_pool_profile_sampling():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    topic_plan = _topic_plan_section(html)

    assert "queryPoolConfig.profilesPerPrompt" not in topic_plan


def test_topic_plan_polling_stops_after_repeated_run_load_failures():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    polling = _topic_plan_polling_section(html)

    assert "topicPlanRunPollFailures" in html
    assert "this.topicPlanRunPollFailures += 1" in polling
    assert "this.topicPlanGenerateLoading = false" in polling
    assert "this.clearTopicPlanRunPolling()" in polling


def test_topic_plan_generation_loads_candidates_for_completed_run():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    generate_start = html.index("async startTopicPlanGenerate()")
    generate_end = html.index("async reviewTopicCandidate", generate_start)
    generate_section = html[generate_start:generate_end]
    candidates_start = html.index("async loadTopicPlanCandidates()")
    candidates_end = html.index("topicPlanCandidateBrandOptions()", candidates_start)
    candidates_section = html[candidates_start:candidates_end]

    assert "topicPlanCandidateRunId" in html
    assert "this.topicPlanCandidateRunId = body.run_id || ''" in generate_section
    assert "qp.set('run_id', this.topicPlanCandidateRunId)" in candidates_section


def test_topic_plan_quality_blocked_feedback_is_visible_and_actionable():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    apply_start = html.index("topicPlanApplyRunProgress(run)")
    apply_section = html[apply_start:html.index("async loadProductsList()", apply_start)]
    polling = _topic_plan_polling_section(html)

    assert "generationQualityBlockedMessage(layer, metrics)" in html
    assert "quality_gate_blocked" in html
    assert "topic_not_natural" in html
    assert "this.topicPlanShowRejected = true" in apply_section
    assert "this.generationQualityBlockedMessage('Topic', run.metrics" in apply_section
    assert "this.generationQualityBlockedMessage('Topic', run.metrics" in polling


def test_topic_plan_bulk_review_handles_partial_failures():
    html = ADMIN_TEMPLATE.read_text(encoding="utf-8")
    start = html.index("async bulkReviewTopicCandidates(status)")
    end = html.index("async loadPromptMatrixConfig()", start)
    bulk_review = html[start:end]

    assert "const failed = Array.isArray(body.failed) ? body.failed : []" in bulk_review
    assert "if (res.status !== 409)" in bulk_review
    assert "\\u90e8\\u5206\\u5b8c\\u6210" in bulk_review
