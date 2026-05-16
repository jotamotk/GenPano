"""LLM-narration pipeline for report sections (PRD §4.7.3 / audit #1044 B2-4).

PRD §4.7.3 Step 3 mandates 6-8 LLM calls per report — each section
must ship with an LLM-generated paragraph distinct from the stat-heavy
`summary` field. Before this module, every section's prose was a
Python f-string, which materially misrepresented the product
positioning ("LLM-driven insights report").

This module is the pluggable narration layer:

  - `narrate(section, ctx)` runs after each section render.
  - If `LLM_NARRATIVE_PROVIDER` env is configured, the LLM path is
    invoked. Implementation surface is intentionally left as a stub
    pending the chosen provider client (Doubao / DeepSeek / OpenAI);
    falls through to fallback on import / network failure per PRD
    §4.7.3 "deterministic fallback".
  - Otherwise, a per-section-type deterministic prose template is
    rendered using locale + metrics + a few signal-derivation rules.
    Produces non-empty, hand-readable narrative — distinguishable
    from the raw summary so report consumers see a real prose layer.

The fallback is **the contract** today; LLM swap-in is a follow-up
that drops in by setting the env var and providing a client adapter
implementing the `_call_llm` hook. PRD §4.7.3 explicitly mandates a
working fallback that is "indistinguishable in KPI content (only
fluency differs)".
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.reports.sections.base import ReportContext, SectionData

log = logging.getLogger(__name__)

_LLM_TIMEOUT_S = 8.0  # PRD §4.7.3 — fall back if > 8s


async def narrate(section: SectionData, ctx: ReportContext) -> str | None:
    """Return the narrative string for a section, or None if no
    narrative is appropriate for that section type.

    Idempotent: if `section.narrative` is already set (e.g. the section
    rendered its own LLM-driven copy), this is a no-op pass-through.
    """
    if section.narrative is not None:
        return section.narrative

    provider = (os.environ.get("LLM_NARRATIVE_PROVIDER") or "").strip().lower()
    if provider and provider not in {"noop", "off", "none", "fallback"}:
        try:
            llm_text = await _call_llm(provider, section, ctx)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning(
                "report_narrator.llm_failed",
                extra={
                    "provider": provider,
                    "section_type": section.section_type,
                    "error": str(exc),
                },
            )
            llm_text = None
        if llm_text:
            return llm_text
        # Fall through to deterministic fallback below.

    return _fallback_narrative(section, ctx)


async def _call_llm(provider: str, section: SectionData, ctx: ReportContext) -> str | None:
    """Hook for the future LLM client. Today: stub that logs + returns
    None so the deterministic fallback runs. When a provider client is
    available, dispatch here based on `provider` ('doubao' / 'deepseek'
    / 'openai' / ...) and return the generated text under
    `_LLM_TIMEOUT_S`."""
    log.info(
        "report_narrator.llm_stub",
        extra={
            "provider": provider,
            "section_type": section.section_type,
            "locale": ctx.locale,
        },
    )
    return None


def _fallback_narrative(section: SectionData, ctx: ReportContext) -> str | None:
    """Deterministic per-section-type prose template. Distinct from
    `section.summary` (which is metric-line-heavy) so renderers can
    show both: summary as the stat line, narrative as the prose."""
    is_zh = ctx.locale.startswith("zh")
    metrics = section.metrics or {}

    structured: str | None = None
    if section.section_type == "executive_summary":
        structured = _exec_summary_narrative(metrics, is_zh=is_zh)
    elif section.section_type == "pano_score":
        structured = _pano_narrative(metrics, is_zh=is_zh)
    elif section.section_type == "competitor_comparison":
        structured = _competitor_narrative(metrics, section, is_zh=is_zh)
    elif section.section_type == "diagnostic_summary":
        structured = _diagnostic_summary_narrative(section, is_zh=is_zh)
    elif section.section_type == "anchor_actions":
        structured = _anchor_narrative(metrics, is_zh=is_zh)
    elif section.section_type == "cta":
        return None  # cta's summary IS the prose; no separate narrative
    return structured or _generic_narrative(section, is_zh=is_zh)


def _generic_narrative(section: SectionData, *, is_zh: bool) -> str:
    """Catch-all for sections whose structured branch produces None
    (e.g. legacy pano_score payloads without `metrics.primary`, or new
    section types added before their narrator branch is registered).
    Keeps the payload contract honest: every non-cta section ships with
    a non-empty narrative."""
    table_count = len(section.tables or [])
    metric_count = len(section.metrics or {})
    if is_zh:
        bits: list[str] = []
        if section.summary:
            bits.append(section.summary)
        if metric_count:
            bits.append(f"涵盖 {metric_count} 项核心指标。")
        if table_count:
            bits.append(f"详见下方 {table_count} 张数据表。")
        return " ".join(bits) or "本节为本期 GenPano 报告的组成部分。"
    bits = []
    if section.summary:
        bits.append(section.summary)
    if metric_count:
        bits.append(f"Covers {metric_count} headline metric(s).")
    if table_count:
        bits.append(f"See the {table_count} table(s) below.")
    return " ".join(bits) or "This section is part of the current GenPano report."


def _exec_summary_narrative(metrics: dict[str, Any], *, is_zh: bool) -> str | None:
    geo = metrics.get("geo_score")
    delta = (metrics.get("delta") or {}).get("geo_score")
    samples = metrics.get("samples")
    if geo is None:
        return None
    if delta is None:
        if is_zh:
            return (
                f"本期 GEO 总分 {geo}(共 {samples} 个采样)。"
                "由于上一周期无对照数据,环比方向暂不可判;待下个周期"
                "采集落地后会给出更明确的趋势判断。"
            )
        return (
            f"This period GEO score is {geo} over {samples} samples. "
            "Prior period has no comparable data, so trend direction is "
            "deferred; the next cycle will give a sharper read."
        )
    if is_zh:
        movement = "回升" if delta > 0 else ("下滑" if delta < 0 else "持平")
        return (
            f"本期 GEO 总分 {geo},较上一周期{movement} "
            f"{abs(delta):.2f} 分(基于 {samples} 个采样)。"
            "请结合下方各 sub-dimension 的环比拆分定位驱动维度。"
        )
    movement = "rose" if delta > 0 else ("fell" if delta < 0 else "held flat")
    return (
        f"GEO score this period is {geo}, which {movement} "
        f"{abs(delta):.2f} points vs the prior period ({samples} samples). "
        "Drill into the per-subdim deltas below to attribute the change."
    )


def _pano_narrative(metrics: dict[str, Any], *, is_zh: bool) -> str | None:
    primary = metrics.get("primary")
    if not primary:
        return None
    total = primary.get("pano_total")
    grade = primary.get("grade")
    sub = primary.get("subdim") or {}
    delta = primary.get("delta") or {}
    if total is None:
        return None
    dom = _dominant_subdim(delta)
    if is_zh:
        head = f"PANO Score {total}(Grade {grade})。"
        sub_line = f"V={sub.get('V')} / S={sub.get('S')} / R={sub.get('R')} / A={sub.get('A')}。"
        if dom is None:
            tail = "本期各子维度变动较小,可视为平稳;关注 R/A 长期资产积累。"
        else:
            dim, dval = dom
            verb = "拉升" if dval > 0 else "拖累"
            tail = (
                f"本期最显著的{verb}维度是 {dim}(贡献 {dval:+.2f} 分),"
                "结合下方 waterfall 看权重 x 子维度增量的整体效应。"
            )
        return head + sub_line + tail
    head = f"PANO Score {total} (Grade {grade}). "
    sub_line = f"V={sub.get('V')} / S={sub.get('S')} / R={sub.get('R')} / A={sub.get('A')}. "
    if dom is None:
        tail = (
            "Sub-dimension moves are small this period; treat as flat and "
            "watch the R/A long-tail-asset accumulation."
        )
    else:
        dim, dval = dom
        verb = "lifted" if dval > 0 else "weighed on"
        tail = (
            f"{dim} {verb} the total most ({dval:+.2f} pts). "
            "See the waterfall below for the weight x subdim breakdown."
        )
    return head + sub_line + tail


def _dominant_subdim(delta: dict[str, Any]) -> tuple[str, float] | None:
    contrib = delta.get("contribution") if isinstance(delta, dict) else None
    if not isinstance(contrib, dict) or not contrib:
        return None
    items: list[tuple[str, float]] = []
    for dim, val in contrib.items():
        if val is None:
            continue
        try:
            items.append((dim, float(val)))
        except (TypeError, ValueError):
            continue
    if not items:
        return None
    items.sort(key=lambda kv: abs(kv[1]), reverse=True)
    if abs(items[0][1]) < 0.05:
        return None
    return items[0]


def _competitor_narrative(
    metrics: dict[str, Any], section: SectionData, *, is_zh: bool
) -> str | None:
    rows: list[dict[str, Any]] = []
    if section.tables:
        rows = section.tables[0].get("rows") or []
    if not rows:
        return None
    primary = next((r for r in rows if r.get("is_primary")), None)
    leader = rows[0]  # already sorted desc by geo_score
    skipped = (metrics or {}).get("skipped_no_data_brand_ids") or []
    if primary is None:
        if is_zh:
            return f"本期主品牌无数据,仅渲染 {len(rows)} 个有数据的竞品作为基准参考。"
        return (
            f"Primary brand has no data this period; {len(rows)} competitor "
            "rows shown as baseline reference."
        )
    if primary.get("brand_id") == leader.get("brand_id"):
        if is_zh:
            return "本期主品牌在竞品集中排名第一;关注前 3 名的差距是否在收敛(看 delta)。" + (
                f" 跳过 {len(skipped)} 个无数据竞品。" if skipped else ""
            )
        return (
            "Primary brand ranked #1 in this competitor set; watch the "
            "top-3 gap for convergence (delta column)."
            + (f" {len(skipped)} competitor(s) skipped for no data." if skipped else "")
        )
    if is_zh:
        return (
            f"本期排名领先的是 brand_id={leader.get('brand_id')}"
            f"(GEO {leader.get('geo_score')}),主品牌 {primary.get('geo_score')}。"
            "看下方 delta 列定位差距是否在缩小。"
            + (f" 跳过 {len(skipped)} 个无数据竞品。" if skipped else "")
        )
    return (
        f"Leader this period is brand_id={leader.get('brand_id')} "
        f"(GEO {leader.get('geo_score')}); primary brand sits at "
        f"{primary.get('geo_score')}. Check the delta column to see "
        "whether the gap is closing."
        + (f" {len(skipped)} competitor(s) skipped for no data." if skipped else "")
    )


def _diagnostic_summary_narrative(section: SectionData, *, is_zh: bool) -> str | None:
    rows: list[dict[str, Any]] = []
    if section.tables:
        rows = section.tables[0].get("rows") or []
    if not rows:
        return None
    counts: dict[str, int] = {}
    for row in rows:
        sev = row.get("severity")
        if isinstance(sev, str):
            counts[sev] = counts.get(sev, 0) + 1
    p0 = counts.get("P0", 0)
    p1 = counts.get("P1", 0)
    if is_zh:
        head = (
            f"本期共 {len(rows)} 条开放诊断:P0x{p0}、P1x{p1}。"
            if (p0 or p1)
            else f"本期共 {len(rows)} 条开放诊断,均为 P2/P3 级别。"
        )
        tail = "P0/P1 需要在 7 天内审阅;P2/P3 列为长期跟踪。"
        return head + tail
    head = (
        f"This period: {len(rows)} open diagnostics — P0x{p0}, P1x{p1}. "
        if (p0 or p1)
        else f"This period: {len(rows)} open diagnostics, all P2/P3. "
    )
    tail = "P0/P1 require review within 7 days; P2/P3 are long-tail tracking."
    return head + tail


def _anchor_narrative(metrics: dict[str, Any], *, is_zh: bool) -> str | None:
    total = metrics.get("total_questions") or 0
    by_reader = metrics.get("by_reader_count") or {}
    if total == 0:
        return None
    if is_zh:
        parts = []
        for reader, label in (
            ("operator", "执行"),
            ("manager", "经营"),
            ("branding", "品牌"),
        ):
            n = by_reader.get(reader, 0)
            if n:
                parts.append(f"{label}视角 {n} 个")
        breakdown = "、".join(parts) if parts else f"{total} 个问题"
        return (
            f"共聚合出 {total} 个锚点问题({breakdown})。"
            "本节问题面向团队复盘,而非执行剧本(参见 PRD §4.8.6)。"
        )
    parts = []
    for reader in ("operator", "manager", "branding"):
        n = by_reader.get(reader, 0)
        if n:
            parts.append(f"{n} for {reader}")
    breakdown = ", ".join(parts) if parts else f"{total} questions"
    return (
        f"Surfaced {total} anchor questions ({breakdown}). "
        "These are reflection prompts for the team — not an execution "
        "playbook (see PRD §4.8.6)."
    )
