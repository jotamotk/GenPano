from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_schedule_editor_reads_admin_brand_options_shape() -> None:
    html = _admin_html()
    section = html[
        html.index("async loadScheduleEditorBrands") : html.index("async loadScheduleEditorTopics")
    ]

    assert "data.brands" in section
    assert "data.rows" in section


def test_schedule_editor_creates_plans_from_query_pool_candidates() -> None:
    html = _admin_html()

    assert "base.querySource = isNew ? 'pool' : 'custom';" in html
    assert "async loadScheduleEditorCandidates" in html
    assert "API_BASE + '/admin/query-pool/candidates?'" in html
    assert "qp.set('status', 'ready')" in html
    assert "selectedScheduleEditorCandidateRows()" in html
    assert "query_text: candidate.actualQueryText" in html
    assert "prompt_id: candidate.promptId" in html
    assert "brand_id: candidate.brandId" in html
