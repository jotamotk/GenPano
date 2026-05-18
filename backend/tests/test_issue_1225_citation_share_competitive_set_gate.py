"""Issue #1225: citation_share must surface ``partial`` when a project has
competitors configured but zero citation_sources rows attributable to the
competitive set.

User-reported symptom (Human Input, 2026-05-18, project ``bestCoffer`` /
``/brands/24``): the "AI Leader" Brand Overview shows 引用份额 ``100%`` while
the other KPIs (提及率 ``75.5%``, SoV ``54.8%``, 情感得分 ``29%``) look
plausible. Captured DB + API evidence for the affected window
(2026-04-18..2026-05-18, project ``7380c0e0-8798-4a5f-998f-42010a7d9caa``,
brand_id=24):

  evidence_counts:
    citation_source_count=127         # target brand has citations
    competitor_brand_count=1          # 理肤泉 (brand_id=2) is configured
    competitive_mention_count=443     # plenty of competitive brand_mentions
    competitive_citation_count=0      # but ZERO competitor citation_sources
    admin_fact_response_count=220
    geo_score_daily_rows=0

With 0 competitor citation rows, the citation_share aggregator at
``_metrics_service.py:_fact_metric_value`` returns target_sum / total_sum
where total_sum collapses to target_sum (target == total), producing 1.0
(= 100%). PRD-APP-ANALYTICS-002 / 003 / 008 explicitly ban this output;
``_series_missing_inputs`` must surface ``brand_mentions.competitive_set``
as a missing input so the no-fallback contract emits ``partial`` rather
than the false 100%.

Symmetric to the existing SoV gate at
``_metrics_service.py:243-247`` which already guards SoV against the same
target-only collapse using ``competitive_mention_count``.
"""

from __future__ import annotations

import os
from datetime import date

from app.api.v1.projects import _analytics_contract as analytics_contract
from app.api.v1.projects import _metrics_service as metrics_service
from app.api.v1.projects._metrics_dto import MetricSeries, MetricSeriesPoint

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


# Captured verbatim from the readonly evidence workflow run 26022673304 /
# DB probe / API probe (project 7380c0e0-8798-4a5f-998f-42010a7d9caa,
# brand_id=24=bestCoffer, window 2026-04-18..05-18). Used unmodified per
# AGENTS.md Hard Rule 4 (evidence-grounded fixture, not synthesized).
BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE = {
    "citation_source_count": 127,
    "competitor_brand_count": 1,
    "competitive_mention_count": 443,
    "competitive_citation_count": 0,
    "admin_fact_response_count": 220,
    "geo_score_daily_rows": 0,
    "analyzer_citation_count": 908,
    "analyzer_attributed_citation_count": 83,
    "analyzer_unresolved_citation_count": 825,
}

# Positive control: same shape, but one competitor citation_sources row
# attributable to a competitive brand_mention. With non-zero attribution
# the denominator is no longer target-only and the ratio cannot
# degenerate to 1.0 by construction.
BESTCOFFER_EVIDENCE_COUNTS_HEALTHY = {
    **BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE,
    "competitive_citation_count": 7,
}

LAST_DAY = date(2026, 5, 18)


def _context(evidence_counts: dict[str, int]) -> analytics_contract.AnalyticsContractContext:
    return analytics_contract.AnalyticsContractContext(
        project_scope=analytics_contract.ProjectScope(
            project_id="7380c0e0-8798-4a5f-998f-42010a7d9caa",
            primary_brand_id=24,
            requested_brand_id=24,
            competitor_brand_ids=[2],  # 理肤泉
        ),
        state="partial",
        state_reason="partial_data",
        missing_inputs=[],
        missing_sources=[],
        missing_reasons=[],
        evidence_counts=evidence_counts,
        formula_status="missing_required_inputs",
        formula_diagnostics=analytics_contract.formula_diagnostics_for("missing_required_inputs"),
        metric_formula_evidence={},
        source_provenance=["admin_facts"],
    )


def _citation_series_with_one_hundred_percent_point() -> MetricSeries:
    # Reproduces the broken-surface output: the citation series last
    # point reaches the frontend with value 1.0. From the readonly probe
    # the rendered ``引用份额 100%`` proves canUseContractMetricValue
    # accepted the value, so the producer (this backend gate) must be
    # the one to surface ``partial``.
    return MetricSeries(
        metric="citation",
        points=[MetricSeriesPoint(date=LAST_DAY, value=1.0)],
        formula_status="ok",
        missing_inputs=[],
        state="ok",
        evidence_count=127,
    )


# ── Negative case: the captured bug shape ───────────────────────────


def test_citation_series_with_competitors_but_zero_competitive_citations_is_partial() -> None:
    """Captured bestCoffer shape: 127 target citations, 1 configured
    competitor, 443 competitive brand_mentions, but ZERO competitor
    citation_sources. The series must come back ``partial`` with
    ``brand_mentions.competitive_set`` in ``missing_inputs`` so the
    no-fallback contract surfaces ``—`` instead of 100%.
    """
    context = _context(BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE)
    series = [_citation_series_with_one_hundred_percent_point()]

    [citation_series] = metrics_service._apply_metric_series_contract(
        series,
        context,
        evidence_source="admin_facts",
    )

    assert citation_series.state == "partial", (
        "Expected partial state when competitive_citation_count==0 with "
        "competitors configured; got state=" + repr(citation_series.state)
    )
    assert citation_series.formula_status != "ok", (
        "formula_status must not stay ok when the citation denominator "
        "collapses to target-only attribution; got " + repr(citation_series.formula_status)
    )
    assert "brand_mentions.competitive_set" in citation_series.missing_inputs, (
        "missing_inputs must surface brand_mentions.competitive_set so the "
        "frontend gate (canUseContractMetricValue) treats the value as "
        "unprovable; got " + repr(citation_series.missing_inputs)
    )


def test_series_missing_inputs_emits_competitive_set_for_degenerate_citation() -> None:
    """Drive ``_series_missing_inputs`` directly with the bestCoffer
    evidence_counts shape. This is the gate function under test; the
    surrounding ``_apply_metric_series_contract`` test above covers the
    user-visible path, this one isolates the gate.
    """
    context = _context(BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE)

    missing = metrics_service._series_missing_inputs(
        "citation",
        context,
        evidence_source="admin_facts",
    )

    assert "brand_mentions.competitive_set" in missing, (
        "Expected the new gate to emit brand_mentions.competitive_set when "
        "competitor_brand_count>0 and competitive_citation_count<=0; got " + repr(missing)
    )
    # The original ``citation_sources`` branch must NOT regress: this
    # context has citation_source_count=127, so the legacy gate should
    # stay silent for that input.
    assert "citation_sources" not in missing, (
        "citation_source_count=127 > 0; the legacy citation_sources gate "
        "must not fire. Got " + repr(missing)
    )


# ── Positive control: gate stays silent when competitive citations exist ──


def test_citation_series_with_competitive_citations_keeps_ok() -> None:
    """Same project shape but with competitive_citation_count=7. The
    new gate must stay silent; the series must NOT be degraded.
    """
    context = _context(BESTCOFFER_EVIDENCE_COUNTS_HEALTHY)
    series = [_citation_series_with_one_hundred_percent_point()]

    [citation_series] = metrics_service._apply_metric_series_contract(
        series,
        context,
        evidence_source="admin_facts",
    )

    assert citation_series.state == "ok", (
        "Series must not be degraded when competitive_citation_count>0; "
        "got state=" + repr(citation_series.state)
    )
    assert "brand_mentions.competitive_set" not in citation_series.missing_inputs, (
        "missing_inputs must NOT contain brand_mentions.competitive_set "
        "when competitive_citation_count>0; got " + repr(citation_series.missing_inputs)
    )


def test_series_missing_inputs_stays_silent_when_competitive_citation_count_positive() -> None:
    context = _context(BESTCOFFER_EVIDENCE_COUNTS_HEALTHY)

    missing = metrics_service._series_missing_inputs(
        "citation",
        context,
        evidence_source="admin_facts",
    )

    assert missing == [], (
        "Gate must not fire when competitive_citation_count>0 and "
        "citation_source_count>0; got " + repr(missing)
    )


# ── Regression guard: pre-existing ``no citations at all`` branch ──


def test_series_missing_inputs_preserves_legacy_citation_sources_gate() -> None:
    """The pre-#1225 branch — ``citation_source_count<=0`` emits
    ``citation_sources`` on the ``geo_score_daily`` evidence source path
    — must keep working. The admin_facts path delegates this signal to
    the analyzer evidence rollup (`contracts/builder.py:372-380`), so
    this guard targets the legacy branch.
    """
    evidence_counts = {
        **BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE,
        "citation_source_count": 0,
        "competitive_citation_count": 0,
    }
    context = _context(evidence_counts)

    missing = metrics_service._series_missing_inputs(
        "citation",
        context,
        evidence_source="geo_score_daily",
    )

    assert "citation_sources" in missing, (
        "Legacy gate must still fire when citation_source_count<=0 on the "
        "geo_score_daily path; got " + repr(missing)
    )
    # When the project has no citations at all, the more specific
    # competitive-set complaint is redundant — the broader source-missing
    # signal takes precedence.
    assert "brand_mentions.competitive_set" not in missing, (
        "When citation_sources is empty the broader gate covers the diagnosis; got " + repr(missing)
    )


# ── Counter-shape guards ──


def test_gate_silent_when_no_competitors_are_configured() -> None:
    """If the project has NO configured competitors,
    competitive_citation_count==0 is the expected steady-state, not a
    bug. The new gate must remain silent so single-brand projects
    don't get falsely flagged ``partial``.
    """
    evidence_counts = {
        **BESTCOFFER_EVIDENCE_COUNTS_DEGENERATE,
        "competitor_brand_count": 0,
        "competitive_citation_count": 0,
    }
    context = _context(evidence_counts)

    missing = metrics_service._series_missing_inputs(
        "citation",
        context,
        evidence_source="admin_facts",
    )

    assert missing == [], "Gate must stay silent when competitor_brand_count==0; got " + repr(
        missing
    )
