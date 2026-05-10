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


def test_query_pool_candidates_can_filter_by_brand() -> None:
    html = _admin_html()

    assert "queryPoolCandidateBrand: 'all'" in html
    assert 'x-model="queryPoolCandidateBrand"' in html
    assert "queryPoolCandidateBrands()" in html
    assert "qp.set('brand_id', brandFilter)" in html
    assert "qp.set('all_runs', '1')" in html
    assert "this.queryPoolCandidateBrand = 'all'" in html


def test_query_pool_candidates_can_be_marked_ready() -> None:
    html = _admin_html()

    assert "queryPoolCandidateReviewing: false" in html
    assert "reviewSelectedQueryPoolCandidates('ready')" in html
    assert "reviewQueryPoolCandidate(q, 'ready')" in html
    assert "performReviewQueryPoolCandidates" in html
    assert "/api/admin/query-pool/candidates/bulk-review" in html
    assert "q.candidateStatus !== 'ready'" in html


def test_query_pool_ready_from_all_status_refocuses_remaining_candidates() -> None:
    html = _admin_html()

    assert "status === 'ready' && !String(this.queryPoolCandidateStatus || '').trim()" in html
    assert "this.queryPoolCandidateStatus = 'candidate';" in html


def test_query_pool_prompt_selection_uses_raw_prompt_id() -> None:
    html = _admin_html()

    assert "if (prompt && prompt.raw_id != null) return String(prompt.raw_id);" in html
