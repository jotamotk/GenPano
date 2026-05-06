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
