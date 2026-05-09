from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_segment_llm_defaults_are_chinese_and_not_beauty_fixture() -> None:
    html = _admin_html()

    assert "Premium skincare, fragrance, and cosmetics." not in html
    assert "Cover core buyers, price/channel comparers" not in html
    assert "Each Segment must have a clear sampling boundary" not in html
    assert "真实定位" in html
    assert "具体产品请用上方产品多选框选择" in html


def test_segment_brand_selection_refreshes_prompt_defaults() -> None:
    html = _admin_html()

    assert "segmentLlmPromptDefaults" in html
    assert "resetSegmentLlmPromptDefaults(false)" in html


def test_segment_llm_uses_product_picker_and_removes_operator_goal_fields() -> None:
    html = _admin_html()

    assert 'x-model="segmentLlmForm.productIds"' in html
    assert "multiple" in html
    assert "loadSegmentLlmProducts" in html
    assert "syncSelectedProducts" in html
    assert 'x-model="segmentLlmForm.goal"' not in html
    assert 'x-model="segmentLlmForm.constraints"' not in html
    assert '"product_ids": this.segmentLlmForm.productIds' in html
    assert '"products": this.segmentLlmForm.products' in html


def test_profile_llm_uses_same_product_scope_picker() -> None:
    html = _admin_html()

    assert 'x-model="llmForm.productIds"' in html
    assert "loadProfileLlmProducts" in html
    assert "syncProfileLlmProducts" in html
    assert '"product_ids": this.llmForm.productIds' in html
    assert '"products": this.llmForm.products' in html
