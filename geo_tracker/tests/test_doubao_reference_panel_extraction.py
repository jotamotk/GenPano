"""Failing-then-passing tests for the Doubao reference-panel extraction gap.

Refs #570 #904 #901. Evidence: workflow run 25851188421, artifact
query-evidence-185003-25851188421, query_id=185003, response_id=657.

The production-persisted ``llm_responses.response_html`` for Q-185003 contains
zero Doubao reference-panel markers
(``entry-btn-v3=0, container-outer=0, search-item-=0, ...``) even though the
user's screenshot proves 8 visible numbered reference cards and a "参考 12
篇资料" footer. The worker captures ``resp_html`` BEFORE clicking the
``entry-btn-v3`` trigger to open the right-side drawer, so the drawer DOM
never lands in DB and the HTML-fallback extractor cannot recover citations
even when the live ``page.evaluate`` extractor races the drawer animation.

These tests pin both halves of the fix:

* The pre-open HTML the worker actually saved today yields 0 citations
  (regression guard — proves the failure shape, must NOT silently start
  returning citations on the same input).
* The post-open drawer HTML must surface eight citations with per-card
  URL/title/source/index metadata via a Doubao-specific helper, so that
  appending the opened drawer HTML to ``resp_html`` is sufficient to feed
  the downstream citation pipeline.
"""

from __future__ import annotations

from pathlib import Path

from geo_tracker.agent.citation_extraction import (
    extract_citations_from_html,
    extract_doubao_panel_citations_from_html,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_pre_open_response_html_yields_zero_citations_matching_q185003_state() -> None:
    """Production DB state for Q-185003: persisted response_html has no drawer.

    Server Diagnostics run 25851188421 reported
    ``citations_json_count=0`` and ``response_html`` marker counts of
    ``entry-btn-v3=0, container-outer=0, search-item-=0``. This test pins
    that current state so any "fix" that fabricates citations from the
    pre-open HTML alone is caught.
    """
    html = _read_fixture("doubao_response_html_q185003_preopen.html")

    citations = extract_citations_from_html(html, llm_name="doubao")

    assert citations == [], (
        "Pre-open response_html must not surface drawer citations; "
        "the fix path is to append the opened drawer HTML before extraction, "
        "not to invent citations from the assistant message body."
    )


def test_opened_drawer_html_yields_eight_external_citations() -> None:
    """The opened ``container-outer[data-visible=true]`` drawer must extract.

    The Q-185003 screenshot shows eight numbered cards in the drawer plus a
    "参考 12 篇资料" footer. Drawer-internal anchors point to external sources
    (non-doubao, non-bytedance). The new helper must return one citation per
    card with the URL, title text, source publisher, and 1-based footer
    index preserved.
    """
    html = _read_fixture("doubao_reference_panel_q185003.html")

    citations = extract_doubao_panel_citations_from_html(html)

    assert len(citations) == 8, citations
    urls = [c["url"] for c in citations]
    assert urls == [
        "https://example.com/article-1",
        "https://news.example.org/story-2",
        "https://research.example.net/paper-3",
        "https://blog.example.io/post-4",
        "https://docs.example.gov/guide-5",
        "https://forum.example.cn/thread-6",
        "https://media.example.tv/video-7",
        "https://wiki.example.org/page-8",
    ]


def test_opened_drawer_html_preserves_card_index_and_source() -> None:
    html = _read_fixture("doubao_reference_panel_q185003.html")

    citations = extract_doubao_panel_citations_from_html(html)

    # 1-based footer index from [class*=footer-citation] must round-trip.
    assert [c["index"] for c in citations] == [1, 2, 3, 4, 5, 6, 7, 8]
    # Publisher from [class*=footer-title] must round-trip.
    assert citations[0]["source"] == "example.com"
    assert citations[1]["source"] == "news.example.org"
    assert citations[-1]["source"] == "wiki.example.org"
    # Title from [class*=search-item-title] must round-trip.
    assert "白皮书" in citations[0]["title"]
    assert citations[4]["title"].startswith("国标数据脱敏分级分类")


def test_opened_drawer_html_drops_self_doubao_or_bytedance_links() -> None:
    html = """
    <div class="container-outer-xyz" data-visible="true">
      <div class="page-search-xyz"><span>参考资料</span></div>
      <div class="search-item-xyz">
        <a href="https://doubao.com/internal"><div class="search-item-title-xyz">self link</div></a>
        <div class="search-item-footer-xyz">
          <span class="footer-title-xyz">doubao.com</span>
          <span class="footer-citation-xyz">1</span>
        </div>
      </div>
      <div class="search-item-xyz">
        <a href="https://www.bytedance.com/about"><div class="search-item-title-xyz">own brand</div></a>
        <div class="search-item-footer-xyz">
          <span class="footer-title-xyz">bytedance.com</span>
          <span class="footer-citation-xyz">2</span>
        </div>
      </div>
      <div class="search-item-xyz">
        <a href="https://external.example.com/a"><div class="search-item-title-xyz">real source</div></a>
        <div class="search-item-footer-xyz">
          <span class="footer-title-xyz">external.example.com</span>
          <span class="footer-citation-xyz">3</span>
        </div>
      </div>
    </div>
    """

    citations = extract_doubao_panel_citations_from_html(html)

    assert [c["url"] for c in citations] == ["https://external.example.com/a"]


def test_opened_drawer_html_ignores_inner_class_search_item_title_as_container() -> None:
    """Regression: ``search-item-title-XXX`` and ``search-item-footer-XXX`` are
    INNER child class prefixes, not the card container. The extractor must
    not treat them as the card root or it would lose the link, source, and
    index that live on sibling/parent nodes.
    """
    html = """
    <div class="container-outer-x" data-visible="true">
      <div class="page-search-x"><span>参考资料</span></div>
      <div class="search-item-x">
        <a href="https://only.example.org/x"><div class="search-item-title-x">titled</div></a>
        <div class="search-item-footer-x">
          <span class="footer-title-x">only.example.org</span>
          <span class="footer-citation-x">9</span>
        </div>
      </div>
    </div>
    """

    citations = extract_doubao_panel_citations_from_html(html)

    assert len(citations) == 1
    assert citations[0]["url"] == "https://only.example.org/x"
    assert citations[0]["source"] == "only.example.org"
    assert citations[0]["index"] == 9


def test_opened_drawer_html_returns_empty_for_invisible_panel() -> None:
    """If the panel is rendered but not opened (data-visible=false), do not
    extract — the user has not actually surfaced references."""
    html = """
    <div class="container-outer-x" data-visible="false">
      <div class="page-search-x"><span>参考资料</span></div>
      <div class="search-item-x">
        <a href="https://hidden.example.org/x"><div class="search-item-title-x">should not extract</div></a>
        <div class="search-item-footer-x">
          <span class="footer-title-x">hidden.example.org</span>
          <span class="footer-citation-x">1</span>
        </div>
      </div>
    </div>
    """

    citations = extract_doubao_panel_citations_from_html(html)

    assert citations == []


def test_full_fixture_response_html_with_drawer_appended_yields_citations() -> None:
    """End-to-end fixture: when the worker appends the opened drawer HTML to
    the pre-open response_html (the proposed fix), the generic and
    Doubao-specific extractors both surface the references.
    """
    pre_open = _read_fixture("doubao_response_html_q185003_preopen.html")
    drawer = _read_fixture("doubao_reference_panel_q185003.html")
    combined = pre_open + "\n<!-- doubao-references -->\n" + drawer

    panel_citations = extract_doubao_panel_citations_from_html(combined)
    assert len(panel_citations) == 8

    # The generic extractor (used downstream by analyze_response) also picks
    # the external anchors up once they're in resp_html, so the citation
    # pipeline becomes feedable from response_html alone.
    generic = extract_citations_from_html(combined, llm_name="doubao")
    assert {c["url"] for c in generic} >= {c["url"] for c in panel_citations}
