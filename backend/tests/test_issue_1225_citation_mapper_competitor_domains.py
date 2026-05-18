"""Issue #1225: ``CitationMapper.map_citations`` must seed
``brand_domains`` from configured competitor websites as well as the
target brand's website. Without this, citations on a competitor's
official domain (e.g. ``larocheposay.com.cn``) fall into the unresolved
bucket and the citation_share denominator collapses to ``target_sum``,
producing the user-visible ``引用份额 = 100%`` regression on the
bestCoffer brand-overview dashboard.

Captured evidence (workflow run 26026560992, project
``7380c0e0-8798-4a5f-998f-42010a7d9caa``, brand_id=24 bestCoffer):

  - ``brands.website`` empty for bestCoffer (24), 欧莱雅 (11), 雅诗兰黛 (12).
  - Top-1 unresolved citation domain: ``bestcoffer.com`` with 200 rows
    across 44 responses (target's own domain in the unresolved bucket).
  - Configured competitor: 理肤泉 (brand_id=2) with website
    ``https://www.larocheposay.com.cn``.
  - ``response_analyses`` rows are split: 146 with ``geo_score`` populated,
    122 NULL — proving the analyzer is running on the project, so the
    citation rollup gap is in mapping, not data.

These fixtures use the captured shape unmodified per AGENTS.md Hard
Rule 4 (evidence-grounded, not synthesized). The Brand stand-ins
mirror what the cli.py call site would pass after the companion
migration ``20260518_backfill_brand_websites`` backfills the empty
``brands.website`` rows.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Stub ``openai`` before importing geo_tracker.analyzer.citation_mapper.
# ``geo_tracker.analyzer.__init__`` eagerly imports ``LLMAnalyzer``,
# which imports ``openai.AsyncOpenAI`` even though our test only needs
# the citation mapper. The backend venv does not ship openai because
# the live LLM call lives in the worker-side environment. Mirrors the
# same pattern used in tests/test_issue_588_pipeline_profile_analyzer.py.
class _FakeAsyncOpenAI:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


_openai_stub = types.ModuleType("openai")
_openai_stub.AsyncOpenAI = _FakeAsyncOpenAI  # type: ignore[attr-defined]
sys.modules.setdefault("openai", _openai_stub)

from geo_tracker.analyzer.brand_detector import DetectedBrand  # noqa: E402
from geo_tracker.analyzer.citation_mapper import CitationMapper  # noqa: E402
from geo_tracker.db.models import Brand  # noqa: E402


def _target_bestcoffer() -> Brand:
    """bestCoffer post-migration: ``website`` backfilled to ``bestcoffer.com``."""
    return Brand(id=24, name="bestCoffer", website="bestcoffer.com")


def _competitor_larocheposay() -> Brand:
    """Captured competitor: brand_id=2 with website
    ``https://www.larocheposay.com.cn`` (already populated on main,
    not part of the migration backfill).
    """
    return Brand(id=2, name="理肤泉", website="https://www.larocheposay.com.cn")


def _competitor_loreal_empty_website() -> Brand:
    """欧莱雅 (brand_id=11) — captured with empty website. Used to
    pin the loop's resilience to NULL/empty rows (the migration
    backfills this, but the code must not depend on the migration
    having run).
    """
    return Brand(id=11, name="欧莱雅", website="")


# ── Core gate: competitor domain attributes to competitor ──


def test_competitor_official_domain_attributes_to_competitor() -> None:
    """A citation on ``larocheposay.com.cn`` must map to the competitor
    brand ``理肤泉`` once the competitor list is passed in. This is the
    #1225 fix: without the new ``competitor_brands`` arg, the URL fell
    through to either the title-match branch (which only fires when
    the title literally names a brand) or the response-level fallback
    (target-only by design), leaving the citation_sources row with
    ``brand_name=None`` and ``mention_id=NULL``, which downstream
    collapses ``competitive_citation_count`` to 0.
    """
    target = _target_bestcoffer()
    competitors = [_competitor_larocheposay()]
    # detected_brands carries both target and competitor — the response
    # talked about both, but the citation title is generic so the
    # title-match branch will NOT save the competitor URL.
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=2),
        DetectedBrand(brand_name="理肤泉", brand_id=2, is_target=False, mention_count=1),
    ]
    citations_json = [
        {
            "url": "https://www.larocheposay.com.cn/products/cicaplast",
            "title": "Cicaplast 修复霜",
            "index": 1,
        },
    ]

    mappings = CitationMapper().map_citations(
        citations_json,
        detected,
        target,
        competitor_brands=competitors,
    )

    assert len(mappings) == 1
    assert mappings[0].brand_name == "理肤泉", (
        "Competitor domain ``larocheposay.com.cn`` must map to "
        "competitor ``理肤泉`` once competitor websites are in brand_domains. "
        "Got brand_name=" + repr(mappings[0].brand_name)
    )
    assert mappings[0].source_type == "official_site", (
        "Competitor official domain must also classify as official_site "
        "(symmetric to target domain). Got source_type=" + repr(mappings[0].source_type)
    )


# ── Target domain still wins (no regression of existing behaviour) ──


def test_target_official_domain_still_attributes_to_target() -> None:
    """The existing target-domain match continues to fire when
    competitor_brands is also supplied. This guards against a refactor
    that accidentally lets a later competitor entry overwrite the
    target-domain → target-name mapping.
    """
    target = _target_bestcoffer()
    competitors = [_competitor_larocheposay()]
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=2),
    ]
    citations_json = [
        {
            "url": "https://www.bestcoffer.com/products/desensitization",
            "title": "数据脱敏方案",
            "index": 1,
        },
    ]

    mappings = CitationMapper().map_citations(
        citations_json,
        detected,
        target,
        competitor_brands=competitors,
    )

    assert len(mappings) == 1
    assert mappings[0].brand_name == "bestCoffer"
    assert mappings[0].source_type == "official_site"


# ── Empty competitor website must not crash and must not appear ──


def test_competitor_with_empty_website_is_skipped_gracefully() -> None:
    """欧莱雅 (brand_id=11) was captured with ``website=''`` in the
    bestCoffer probe. The loop must skip it without raising and must
    not poison ``brand_domains`` with an empty string key. A citation
    on a neutral domain remains unattributed (or falls through to the
    target-fallback when target is detected — covered separately).
    """
    target = _target_bestcoffer()
    # Mix of populated and empty-website competitors. The empty one
    # must NOT crash the function and must NOT inject ``''`` into
    # brand_domains.
    competitors = [
        _competitor_larocheposay(),
        _competitor_loreal_empty_website(),
    ]
    # Target NOT detected so the response-level fallback stays silent
    # and we can directly observe whether the empty-website loop leaked.
    detected: list[DetectedBrand] = [
        DetectedBrand(brand_name="理肤泉", brand_id=2, is_target=False, mention_count=1),
    ]
    citations_json = [
        # Citation on the populated competitor → must still attribute.
        {
            "url": "https://www.larocheposay.com.cn/page",
            "title": "页面",
            "index": 1,
        },
        # Neutral third-party domain — no domain match, no title match,
        # target not detected, so brand_name must be None.
        {
            "url": "https://arxiv.org/abs/9999.0001",
            "title": "Neutral preprint",
            "index": 2,
        },
    ]

    mappings = CitationMapper().map_citations(
        citations_json,
        detected,
        target,
        competitor_brands=competitors,
    )

    assert len(mappings) == 2
    by_url = {m.url: m for m in mappings}
    assert by_url["https://www.larocheposay.com.cn/page"].brand_name == "理肤泉"
    # arxiv must NOT have been hijacked by an empty-string domain key.
    arxiv_mapping = by_url["https://arxiv.org/abs/9999.0001"]
    assert arxiv_mapping.brand_name is None, (
        "Neutral third-party citation must remain unattributed when target "
        "is not detected; an empty competitor website must not introduce "
        "a wildcard match. Got brand_name=" + repr(arxiv_mapping.brand_name)
    )
    assert arxiv_mapping.source_type != "official_site"


# ── Neutral third-party citation: explicit cause-and-effect pin ──


def test_neutral_third_party_citation_remains_unattributed_when_target_not_detected() -> None:
    """When the target brand is NOT detected in the response and the
    URL belongs to neither target nor any configured competitor, the
    citation must come back with ``brand_name=None``. This is the
    captured shape for many of the 1243 unresolved rows in the
    bestCoffer probe — neutral references (arxiv.org, cloud.baidu.com,
    iclr.cc, ibm.com, etc.) where no fallback should fire.

    Per spec, this test asserts the **None** outcome explicitly rather
    than allowing the target-via-fallback alternative. The fallback
    only fires when the target is detected; here it is not.
    """
    target = _target_bestcoffer()
    competitors = [_competitor_larocheposay()]
    detected: list[DetectedBrand] = []  # target absent → no fallback
    citations_json = [
        {"url": "https://arxiv.org/abs/9999.0002", "title": "Some paper", "index": 1},
    ]

    mappings = CitationMapper().map_citations(
        citations_json,
        detected,
        target,
        competitor_brands=competitors,
    )

    assert len(mappings) == 1
    assert mappings[0].brand_name is None


# ── Backward compatibility: omitting the new arg keeps prior behaviour ──


def test_omitting_competitor_brands_preserves_prior_behaviour() -> None:
    """Call sites that have not yet been updated must continue to
    behave exactly as they did pre-#1225: only the target brand's
    website seeds ``brand_domains``, and competitor URLs without title
    matches stay unattributed. This is the contract that lets the
    fix land without a sweeping call-site migration.
    """
    target = _target_bestcoffer()
    detected = [
        DetectedBrand(brand_name="bestCoffer", brand_id=24, is_target=True, mention_count=2),
        DetectedBrand(brand_name="理肤泉", brand_id=2, is_target=False, mention_count=1),
    ]
    citations_json = [
        {
            "url": "https://www.larocheposay.com.cn/products/cicaplast",
            "title": "通用页面",  # title does NOT contain 理肤泉 ⇒ no title-match save.
            "index": 1,
        },
    ]

    # No competitor_brands kwarg → legacy code path.
    mappings = CitationMapper().map_citations(citations_json, detected, target)

    assert len(mappings) == 1
    # Pre-fix: competitor URL falls through to the response-level
    # target fallback because bestCoffer is detected. We pin this
    # explicitly so a future change to the fallback semantics is
    # caught.
    assert mappings[0].brand_name == "bestCoffer", (
        "Without competitor_brands the competitor URL must continue "
        "to land on the target-fallback (target is detected in the "
        "response). Got brand_name=" + repr(mappings[0].brand_name)
    )
