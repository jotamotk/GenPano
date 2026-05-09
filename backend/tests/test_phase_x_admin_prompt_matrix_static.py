from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_prompt_matrix_generation_count_uses_manual_numeric_cap() -> None:
    html = _admin_html()

    assert "maxPrompts: 10," in html
    assert 'x-model.number="promptMatrixConfig.maxPerTopic"' in html
    assert ':max="promptMatrixMaxPerTopicCap()"' in html
    assert "promptMatrixMaxPerTopicValue()" in html
    assert 'x-model="promptMatrixConfig.maxPerTopic"' not in html
    assert 'x-model.number="promptMatrixConfig.maxPrompts"' in html
    assert 'type="number" min="1" step="1"' in html
    assert ':max="promptMatrixMaxPromptsCap()"' in html
    assert "promptMatrixRawPromptCount()" in html
    assert "promptMatrixMaxPromptsCap()" in html
    assert "qp.set('max_per_topic', this.promptMatrixMaxPerTopicValue());" in html
    assert "max_per_topic: this.promptMatrixMaxPerTopicValue()," in html
    assert "this.promptMatrixConfig.maxPrompts || 8000" not in html
    assert "Number(this.promptMatrixConfig.maxPrompts) || 8000" not in html


def test_prompt_matrix_copy_distinguishes_quantity_from_allowed_cap() -> None:
    html = _admin_html()
    max_per_topic_index = html.index('x-model.number="promptMatrixConfig.maxPerTopic"')
    overflow_policy_index = html.index('x-model="promptMatrixConfig.overflowPolicy"', max_per_topic_index)
    prompt_matrix_controls = html[max_per_topic_index - 500 : overflow_policy_index + 500]

    assert "每 Topic 上限" in prompt_matrix_controls
    assert "生成数量" in prompt_matrix_controls
    assert "本次生成" in html
    assert "可填上限" in html
    assert "生成上限" not in prompt_matrix_controls
    assert "总上限 ${this.promptMatrixMaxPromptsValue()" not in html
