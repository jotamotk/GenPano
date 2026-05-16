"""[#1044 P1] Renderer + variant fixes (B2-10, B2-11).

- B2-10: variant=='simple' drops tables/charts; variant=='focus'
         filters tables to primary brand. Variant choices that don't
         actually change output were a PRD §4.7.2 violation.
- B2-11: Markdown renderer emits charts (was silently dropping);
         CSV renderer emits metrics-only sections (was dropping any
         section without tables, losing executive_summary entirely).
"""

from __future__ import annotations

from app.reports.renderers.csv_renderer import render_csv
from app.reports.renderers.markdown import render_markdown

# ── B2-10 simple variant projection ─────────────────────────────


def test_b2_10_simple_drops_tables_and_charts_from_payload():
    """When SECTION_MATRIX assigns `variant='simple'`, the resulting
    section dict in the payload must have empty tables + charts."""
    from app.reports.builder import _apply_variant
    from app.reports.sections.base import SectionData

    sec = SectionData(
        section_type="pano_score",
        title="PANO",
        summary="PANO 80 (Grade A)",
        narrative="prose",
        metrics={"primary": {"pano_total": 80}},
        tables=[{"name": "pano_by_brand", "rows": [{"brand_id": 1, "pano_total": 80}]}],
        charts=[{"type": "waterfall", "data": {}}],
        chosen_variant="simple",
    )
    _apply_variant(sec, primary_brand_id=1)
    assert sec.tables == []
    assert sec.charts == []
    # Metrics + summary + narrative preserved
    assert sec.metrics == {"primary": {"pano_total": 80}}
    assert sec.summary
    assert sec.narrative


def test_b2_10_full_variant_is_passthrough():
    from app.reports.builder import _apply_variant
    from app.reports.sections.base import SectionData

    sec = SectionData(
        section_type="pano_score",
        title="PANO",
        summary="...",
        metrics={"primary": {}},
        tables=[{"name": "t", "rows": [{"brand_id": 1}, {"brand_id": 2}]}],
        chosen_variant="full",
    )
    _apply_variant(sec, primary_brand_id=1)
    assert sec.tables == [{"name": "t", "rows": [{"brand_id": 1}, {"brand_id": 2}]}]


def test_b2_10_focus_variant_filters_to_primary_brand():
    from app.reports.builder import _apply_variant
    from app.reports.sections.base import SectionData

    sec = SectionData(
        section_type="brand_performance",
        title="...",
        summary="...",
        tables=[
            {
                "name": "brand_performance",
                "rows": [
                    {"brand_id": 1, "is_primary": True, "geo_score": 80},
                    {"brand_id": 2, "is_primary": False, "geo_score": 75},
                    {"brand_id": 3, "is_primary": False, "geo_score": 70},
                ],
            }
        ],
        chosen_variant="focus",
    )
    _apply_variant(sec, primary_brand_id=1)
    rows = sec.tables[0]["rows"]
    assert len(rows) == 1
    assert rows[0]["brand_id"] == 1


def test_b2_10_focus_drops_empty_tables_after_filter():
    from app.reports.builder import _apply_variant
    from app.reports.sections.base import SectionData

    sec = SectionData(
        section_type="brand_performance",
        title="...",
        summary="...",
        tables=[
            {
                "name": "brand_performance",
                "rows": [{"brand_id": 2, "is_primary": False, "geo_score": 75}],
            }
        ],
        chosen_variant="focus",
    )
    _apply_variant(sec, primary_brand_id=1)
    # No primary brand row → table dropped entirely.
    assert sec.tables == []


# ── B2-11 Markdown emits charts ─────────────────────────────────


def test_b2_11_markdown_emits_charts_as_fenced_json():
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "pano_score",
                "title": "PANO",
                "summary": "...",
                "metrics": {},
                "tables": [],
                "charts": [{"name": "waterfall", "type": "bar", "data": [1, 2, 3]}],
            }
        ],
    }
    out = render_markdown(payload)
    assert "**Charts: waterfall**" in out
    assert '"type": "bar"' in out
    # Fenced code block for downstream consumers
    assert "```json" in out


def test_b2_11_markdown_emits_narrative_block():
    """Narrative (from narrator) should appear as a distinct block,
    not just blended into the summary."""
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "Executive Summary",
                "summary": "GEO score 80, mention rate 50%.",
                "narrative": "This period the GEO score rose 5 points...",
                "metrics": {"geo_score": 80, "mention_rate": 0.5},
                "tables": [],
            }
        ],
    }
    out = render_markdown(payload)
    assert "**Narrative**" in out
    assert "GEO score rose 5 points" in out


# ── B2-11 CSV emits metrics-only sections ───────────────────────


def test_b2_11_csv_emits_metrics_only_section():
    """exec_summary is metrics-only (no tables). Previous renderer
    skipped it entirely; new renderer must emit a `## metrics` block."""
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "Executive Summary",
                "summary": "...",
                "metrics": {
                    "geo_score": 80,
                    "mention_rate": 0.5,
                    "samples": 7,
                },
                "tables": [],
            }
        ],
    }
    out = render_csv(payload)
    assert "# Executive Summary" in out
    assert "## metrics" in out
    assert "key,value" in out
    assert "geo_score,80" in out
    assert "samples,7" in out


def test_b2_11_csv_emits_both_metrics_and_tables():
    """When a section has BOTH metrics and tables, CSV emits both
    blocks under the same section header."""
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "pano_score",
                "title": "PANO",
                "summary": "...",
                "metrics": {"weights": {"V": 0.30}, "primary": {"pano_total": 80}},
                "tables": [
                    {
                        "name": "pano_by_brand",
                        "rows": [{"brand_id": 1, "pano_total": 80}],
                    }
                ],
            }
        ],
    }
    out = render_csv(payload)
    assert "# PANO" in out
    assert "## metrics" in out
    assert "## pano_by_brand" in out
    assert "brand_id,pano_total" in out


def test_b2_11_csv_skips_truly_empty_section():
    """A section with no metrics + no tables produces no header line —
    don't pollute the CSV with empty section markers."""
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "cta",
                "title": "CTA",
                "summary": "Contact us",
                "metrics": {},
                "tables": [],
            }
        ],
    }
    out = render_csv(payload)
    assert "# CTA" not in out
