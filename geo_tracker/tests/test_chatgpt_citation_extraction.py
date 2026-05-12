from geo_tracker.agent.citation_extraction import (
    classify_citation_extraction,
    extract_citations_from_html,
)


def test_extract_citations_from_chatgpt_response_html_skips_shell_links() -> None:
    html = """
    <nav>
      <a href="https://help.openai.com/">Help link outside the assistant answer</a>
    </nav>
    <article data-message-author-role="assistant">
      <div class="markdown">
        <p>bestCoffer market context.</p>
        <a href="https://chatgpt.com/c/abc">internal chat</a>
        <a href="https://example.com/report">Example Report</a>
        <a data-url="https://news.example.org/story">Story title</a>
      </div>
    </article>
    """

    citations = extract_citations_from_html(html, llm_name="chatgpt")

    assert citations == [
        {"url": "https://example.com/report", "title": "Example Report", "index": 1},
        {"url": "https://news.example.org/story", "title": "Story title", "index": 2},
    ]


def test_classifies_chatgpt_plain_answer_without_source_ui_as_not_applicable() -> None:
    result = classify_citation_extraction(
        "chatgpt",
        raw_text="Plain recommendation list without citations, sources, links, or search results.",
        response_html="<div data-message-author-role='assistant'><p>plain answer</p></div>",
        citations=[],
    )

    assert result["status"] == "citation_not_applicable"
    assert result["reason"] == "no_source_markers_or_external_links"


def test_classifies_chatgpt_source_ui_without_urls_as_review_gap() -> None:
    result = classify_citation_extraction(
        "chatgpt",
        raw_text="I found sources for this comparison.",
        response_html=(
            "<div data-message-author-role='assistant'>"
            "<button aria-label='Sources'>Sources</button>"
            "</div>"
        ),
        citations=[],
    )

    assert result["status"] == "citation_extractor_gap"
    assert result["reason"] == "source_markers_without_extractable_urls"


def test_classifies_chatgpt_clicked_source_ui_without_urls_as_review_gap() -> None:
    result = classify_citation_extraction(
        "chatgpt",
        raw_text="I found sources for this comparison.",
        response_html="<div data-message-author-role='assistant'><p>answer text</p></div>",
        citations=[],
        source_ui_seen=True,
        source_ui_clicked=True,
    )

    assert result["status"] == "citation_extractor_gap"
    assert result["reason"] == "source_markers_without_extractable_urls"
    assert result["source_ui_seen"] is True
    assert result["source_ui_clicked"] is True
