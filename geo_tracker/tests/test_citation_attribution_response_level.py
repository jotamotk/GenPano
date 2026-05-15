"""Tests for response-level citation attribution fallback.

Refs #570 (canonical citation track), #948 (Human Input parent),
#901 (Doubao citation Human Input).

Original gap: ``CitationMapper._match_brand`` only attributed a citation
to a brand when the citation's URL domain matched the target brand's
website OR the citation's title contained a detected brand name. Both
conditions miss the common case where the response is "about" the target
brand but cites third-party sources (review sites, news, wikipedia)
whose titles do not literally name the brand. Live evidence for
bestCoffer (project ``7380c0e0-…``): ``analyzer_citation_count=888``
yet ``analyzer_attributed_citation_count=0`` because every citation's
``CitationMapping.brand_name`` resolved to ``None`` and
``_find_mention_for_brand`` therefore returned ``None`` for all 888 rows.

Fix: when the target brand was detected in the response (BrandMention
exists), attribute orphan citations to the target brand as a
response-level proximity match. This mirrors SoV's behaviour, where the
target brand's mention is what makes the response "competitive" — the
same logic should make accompanying references count as the target
brand's citations.

These tests pin both the new fallback and the protection against
over-attribution: competitor citations whose title explicitly names a
competitor must keep going to the competitor, NOT fall through to the
target brand.
"""

from __future__ import annotations

from dataclasses import dataclass

from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.citation_mapper import CitationMapper


@dataclass
class _StubBrand:
    """Minimal Brand stand-in for the CitationMapper signature.

    We use a dataclass rather than the real ORM Brand to keep these
    tests free of DB dependencies. The mapper only reads ``.name``,
    ``.id``, and ``.website``.
    """

    id: int
    name: str
    website: str | None = None


def _bestcoffer() -> _StubBrand:
    return _StubBrand(id=24, name="bestCoffer", website=None)


def _competitor_ibm() -> _StubBrand:
    return _StubBrand(id=2, name="IBM Security", website=None)


def test_response_with_target_brand_attributes_orphan_citation_to_target() -> None:
    """The #948 fix: bestCoffer mentioned in response → orphan citation
    (third-party news domain, title without "bestcoffer") still
    attributes to bestCoffer.
    """
    target = _bestcoffer()
    detected = [
        DetectedBrand(
            brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=3,
        ),
    ]
    citations_json = [
        # Wikipedia-style orphan citation — generic title, third-party domain.
        {"url": "https://en.wikipedia.org/wiki/Data_masking", "title": "Data masking", "index": 1},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)

    assert len(mappings) == 1
    assert mappings[0].brand_name == "bestCoffer", (
        "Orphan citation in a bestCoffer-mentioning response must attribute to bestCoffer"
    )


def test_response_without_target_brand_leaves_orphan_citation_unattributed() -> None:
    """No regression of strictness: if the target brand was NOT detected
    in the response, orphan citations remain unattributed. This is what
    makes the fallback safe — we never invent attribution from thin air.
    """
    target = _bestcoffer()
    detected: list[DetectedBrand] = []  # target not mentioned anywhere
    citations_json = [
        {"url": "https://example.org/article", "title": "Unrelated AI article", "index": 1},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)

    assert len(mappings) == 1
    assert mappings[0].brand_name is None


def test_competitor_titled_citation_still_attributes_to_competitor() -> None:
    """Anti-regression: if a competitor name is in the citation title,
    the citation goes to the COMPETITOR, not the target — even if the
    target was also mentioned in the response. Otherwise the fallback
    would cannibalise competitor citation share.
    """
    target = _bestcoffer()
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=3),
        DetectedBrand(brand_name="IBM Security", brand_id=2, is_target=False, mention_count=2),
    ]
    citations_json = [
        {
            "url": "https://media.example.cn/article",
            "title": "Comparing IBM Security and others",
            "index": 1,
        },
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)

    assert len(mappings) == 1
    assert mappings[0].brand_name == "IBM Security"


def test_target_domain_match_still_wins_over_response_proximity() -> None:
    """Domain match remains the highest-priority signal. A citation
    whose URL points at the target brand's own website attributes via
    domain even when the response also mentions a competitor.
    """
    target = _StubBrand(id=24, name="bestCoffer", website="https://www.bestcoffer.com")
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=3),
        DetectedBrand(brand_name="IBM Security", brand_id=2, is_target=False, mention_count=2),
    ]
    citations_json = [
        {
            "url": "https://www.bestcoffer.com/products/desensitization",
            "title": "Generic product page",
            "index": 1,
        },
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)

    assert len(mappings) == 1
    assert mappings[0].brand_name == "bestCoffer"
    assert mappings[0].source_type == "official_site"


def test_target_detected_via_is_target_flag_alone_triggers_fallback() -> None:
    """The detection signal can land via three independent fields
    (``brand_id``, ``is_target``, name match). All three must reach the
    fallback. This guards against future BrandDetector refactors that
    drop one signal — the fallback should still fire as long as ANY
    target signal is present.
    """
    target = _bestcoffer()
    # Detection has no brand_id (e.g. detected via alias the brand
    # table doesn't carry yet) but `is_target` flag is true.
    detected = [
        DetectedBrand(brand_name="best-coffer", brand_id=None, is_target=True, mention_count=1),
    ]
    citations_json = [
        {"url": "https://news.example.cn/article-42", "title": "市场观察", "index": 1},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)
    assert mappings[0].brand_name == "bestCoffer"


def test_target_detected_via_name_match_triggers_fallback() -> None:
    """Another guard: detection landed without ``brand_id`` and without
    ``is_target`` but the detected brand name equals the target brand
    name (case-insensitive). Fallback still fires.
    """
    target = _bestcoffer()
    detected = [
        DetectedBrand(
            brand_name="BESTCOFFER", brand_id=None, is_target=False, mention_count=1,
        ),
    ]
    citations_json = [
        {"url": "https://blog.example.io/post", "title": "随笔", "index": 1},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)
    assert mappings[0].brand_name == "bestCoffer"


def test_only_competitor_detected_does_not_attribute_to_target() -> None:
    """No false-positive: if the response mentions ONLY a competitor,
    orphan citations do NOT attribute to the target.
    """
    target = _bestcoffer()
    detected = [
        DetectedBrand(brand_name="IBM Security", brand_id=2, is_target=False, mention_count=2),
    ]
    citations_json = [
        {"url": "https://docs.example.gov/guide-5", "title": "Compliance guide", "index": 1},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)
    assert mappings[0].brand_name is None


def test_empty_citation_url_is_skipped() -> None:
    """Regression: skipping logic for malformed citations untouched."""
    target = _bestcoffer()
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=1),
    ]
    citations_json = [
        {"url": "", "title": "Empty", "index": 1},
        {"url": "https://news.example.cn/x", "title": "Real", "index": 2},
    ]

    mappings = CitationMapper().map_citations(citations_json, detected, target)
    assert len(mappings) == 1
    assert mappings[0].url == "https://news.example.cn/x"
    assert mappings[0].brand_name == "bestCoffer"
