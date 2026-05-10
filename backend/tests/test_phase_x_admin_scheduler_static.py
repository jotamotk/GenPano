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


def test_admin_error_panel_stringifies_object_detail() -> None:
    html = _admin_html()

    assert "formatAdminErrorDetail" in html
    assert "JSON.stringify(value)" in html
    assert "const detail = formatAdminErrorDetail(body.detail)" in html


def test_scheduler_schedule_list_has_brand_filter_and_pagination() -> None:
    html = _admin_html()

    assert "scheduleFilterBrandId" in html
    assert "schedulePage" in html
    assert "schedulePerPage" in html
    assert "params.set('brand_id', this.scheduleFilterBrandId)" in html
    assert "API_BASE + '/scheduler/schedules?' + params.toString()" in html
    assert "scheduleTotalPages()" in html


def test_scheduler_manual_trigger_uses_selected_brand_scope() -> None:
    html = _admin_html()
    section = html[
        html.index("async manualTriggerScheduler")
        : html.index("async toggleSchedulerMode", html.index("async manualTriggerScheduler"))
    ]

    assert "payload.brand_id = parseInt(this.scheduleFilterBrandId)" in section
    assert "limit: this.scheduleFilterBrandId ? 2000 : 50" in section


def test_scheduler_manual_trigger_surfaces_dispatch_result() -> None:
    html = _admin_html()
    section = html[
        html.index("async manualTriggerScheduler")
        : html.index("async toggleSchedulerMode", html.index("async manualTriggerScheduler"))
    ]

    assert "body.dispatched" in section
    assert "body.dispatch_failed" in section
    assert "派发成功" in section
    assert "派发失败" in section


def test_schedule_editor_creates_plans_from_query_pool_candidates() -> None:
    html = _admin_html()
    pool_section = html[
        html.index("if (e.querySource === 'pool' && !e.id)")
        : html.index("if (!e.id)", html.index("if (e.querySource === 'pool' && !e.id)"))
    ]

    assert "base.querySource = isNew ? 'pool' : 'custom';" in html
    assert "async loadScheduleEditorCandidates" in html
    assert "API_BASE + '/admin/query-pool/candidates?'" in html
    assert "qp.set('all_runs', '1')" in html
    assert "qp.set('status', 'ready')" in html
    assert "cursor" in html
    assert "body.next_cursor" in html
    assert "selectedScheduleEditorCandidateRows()" in html
    assert "selectedScheduleEditorTargetLlms()" in html
    assert "scheduleEditor.target_llms" in html
    assert "scheduleEditorQueryLanguage" in html
    assert "query_text: candidate.actualQueryText" in html
    assert "prompt_id: candidate.promptId" in html
    assert "brand_id: candidate.brandId" in html
    assert "query_items:" in pool_section
    assert "target_llms: selectedLlms" in pool_section
    assert "brand_id: batchBrandId ? parseInt(batchBrandId) : null" in pool_section
    assert "API_BASE + '/scheduler/schedules'" in pool_section
    assert "for (const targetLlm of selectedLlms)" not in pool_section
