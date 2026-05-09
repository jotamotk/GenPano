from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_query_pool_candidate_rows_show_inherited_prompt_metadata() -> None:
    html = _admin_html()

    assert "queryPoolCandidateMetadataBadges(q)" in html
    assert "queryPoolCandidateScopeLabel(row)" in html
    assert "queryPoolCandidateContextLabel(q)" in html
    assert "row.metadata || row.metadata_json" in html
    assert "competitor_name" in html
    assert "comparison_axis" in html
    assert "brand_context_version" in html


def test_query_pool_prompt_selection_uses_raw_prompt_id() -> None:
    html = _admin_html()

    assert "if (prompt && prompt.raw_id != null) return String(prompt.raw_id);" in html
