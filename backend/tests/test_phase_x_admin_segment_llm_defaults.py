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
    assert "产品线请用上方产品下拉选择" in html


def test_segment_brand_selection_refreshes_prompt_defaults() -> None:
    html = _admin_html()

    assert "segmentLlmPromptDefaults" in html
    assert "resetSegmentLlmPromptDefaults(false)" in html


def test_segment_llm_uses_product_picker_and_removes_operator_goal_fields() -> None:
    html = _admin_html()

    assert 'x-model="segmentLlmForm.productId"' in html
    assert "loadSegmentLlmProducts" in html
    assert "syncSelectedProduct" in html
    assert 'x-model="segmentLlmForm.goal"' not in html
    assert 'x-model="segmentLlmForm.constraints"' not in html
    assert '"product_id": this.segmentLlmForm.productId' in html
    assert '"product_name": this.segmentLlmForm.productName' in html
