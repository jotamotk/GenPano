from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_prompt_matrix_generation_count_uses_manual_numeric_cap() -> None:
    html = _admin_html()

    assert "maxPrompts: 10," in html
    assert 'x-model.number="promptMatrixConfig.maxPrompts"' in html
    assert 'type="number" min="1" step="1"' in html
    assert ':max="promptMatrixMaxPromptsCap()"' in html
    assert "promptMatrixRawPromptCount()" in html
    assert "promptMatrixMaxPromptsCap()" in html
    assert "this.promptMatrixConfig.maxPrompts || 8000" not in html
    assert "Number(this.promptMatrixConfig.maxPrompts) || 8000" not in html
