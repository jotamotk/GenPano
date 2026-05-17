"""LLM-narration pipeline for report sections (PRD §4.7.3 / audit #1044 B2-4).

PRD §4.7.3 Step 3 mandates 6-8 LLM calls per report — each section
must ship with an LLM-generated paragraph distinct from the stat-heavy
`summary` field. Before this module, every section's prose was a
Python f-string, which materially misrepresented the product
positioning ("LLM-driven insights report").

This module is the pluggable narration layer:

  - `narrate(section, ctx)` runs after each section render.
  - When ``LLM_NARRATIVE_PROVIDER`` is set to ``doubao`` / ``ark`` /
    ``deepseek`` / ``openai`` and the matching credentials are
    available, an HTTP request is made to the provider's OpenAI-
    compatible ``/chat/completions`` endpoint with a section-aware
    prompt (see ``_build_messages``). The returned prose replaces the
    deterministic fallback.
  - Any failure (missing config, network error, bad status, empty
    completion) is logged and the call falls through to the
    deterministic fallback path. PRD §4.7.3 mandates this graceful
    degradation — reports never block on an LLM outage.
  - When the provider is unset / off / noop, the deterministic path
    runs directly without any HTTP round-trip.

The provider integration uses the same OpenAI-compatible chat
protocol that ``app.admin.topic_plan.lib.load_doubao_config`` already
ships against Doubao (Volcengine Ark), DeepSeek and OpenAI. No new
SDKs are introduced — just an httpx POST.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from app.reports.sections.base import ReportContext, SectionData

log = logging.getLogger(__name__)

_LLM_TIMEOUT_S = 8.0  # PRD §4.7.3 — fall back if > 8s
_LLM_MAX_TOKENS = 600  # Per-section narrative; ~120 words.
_LLM_TEMPERATURE = 0.4  # Some variation but consistent across runs.
_LLM_OFF_VALUES = {"", "noop", "off", "none", "fallback"}
_LLM_PROVIDERS_OPENAI_COMPAT = {"doubao", "ark", "deepseek", "openai"}


async def narrate(section: SectionData, ctx: ReportContext) -> str | None:
    """Return the narrative string for a section, or None if no
    narrative is appropriate for that section type.

    Idempotent: if `section.narrative` is already set (e.g. the section
    rendered its own LLM-driven copy), this is a no-op pass-through.
    """
    if section.narrative is not None:
        return section.narrative

    provider = (os.environ.get("LLM_NARRATIVE_PROVIDER") or "").strip().lower()
    if provider and provider not in _LLM_OFF_VALUES:
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
    """Dispatch to the configured LLM provider's chat-completions
    endpoint and return a single prose paragraph for the section.

    All currently-supported providers (Doubao / Ark, DeepSeek, OpenAI)
    share the OpenAI chat protocol, so dispatch is one HTTP POST.
    Provider-specific selection happens entirely via env vars consumed
    by `_resolve_llm_endpoint`.

    Returns None when:
      - provider config is missing (no API key / base URL / model)
      - HTTP call fails or times out
      - response has no completion text

    On None, the caller falls back to the deterministic narrator path.
    """
    if provider not in _LLM_PROVIDERS_OPENAI_COMPAT:
        log.warning(
            "report_narrator.llm_unknown_provider",
            extra={"provider": provider, "section_type": section.section_type},
        )
        return None

    endpoint = _resolve_llm_endpoint(provider)
    if endpoint is None:
        log.info(
            "report_narrator.llm_config_missing",
            extra={"provider": provider, "section_type": section.section_type},
        )
        return None
    api_key, base_url, model = endpoint

    messages = _build_messages(section, ctx)
    body = {
        "model": model,
        "messages": messages,
        "temperature": _LLM_TEMPERATURE,
        "max_tokens": _LLM_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = base_url.rstrip("/") + "/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_S) as client:
            response = await client.post(url, json=body, headers=headers)
    except httpx.RequestError as exc:
        log.warning(
            "report_narrator.llm_request_failed",
            extra={
                "provider": provider,
                "section_type": section.section_type,
                "error": str(exc),
            },
        )
        return None

    if response.status_code != 200:
        log.warning(
            "report_narrator.llm_http_error",
            extra={
                "provider": provider,
                "section_type": section.section_type,
                "status_code": response.status_code,
                "body_excerpt": response.text[:200],
            },
        )
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content") or ""
    text = _normalize_completion(content)
    if not text:
        return None

    log.info(
        "report_narrator.llm_ok",
        extra={
            "provider": provider,
            "section_type": section.section_type,
            "locale": ctx.locale,
            "chars": len(text),
        },
    )
    return text


def _resolve_llm_endpoint(provider: str) -> tuple[str, str, str] | None:
    """Read provider credentials from env. Returns (api_key, base_url,
    model) or None when any required field is missing.

    Resolution rules:
      - api_key: provider-specific env first (`DOUBAO_API_KEY` /
        `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`), then generic
        `LLM_API_KEY` / `ARK_API_KEY` as fallback.
      - base_url: provider-specific (`DOUBAO_BASE_URL` etc.), then
        generic `LLM_BASE_URL` / `ARK_BASE_URL`.
      - model: provider-specific (`DOUBAO_MODEL` etc.), then generic
        `LLM_NARRATIVE_MODEL` / `LLM_MODEL`. A scoped
        `LLM_NARRATIVE_MODEL` lets operators pick a smaller/faster
        model for the narrator without affecting other LLM features.
    """
    env = os.environ

    def _first(*keys: str) -> str:
        for k in keys:
            v = (env.get(k) or "").strip()
            if v:
                return v
        return ""

    if provider in {"doubao", "ark"}:
        api_key = _first("DOUBAO_API_KEY", "ARK_API_KEY", "VOLCENGINE_ARK_API_KEY", "LLM_API_KEY")
        base_url = _first(
            "DOUBAO_BASE_URL",
            "ARK_BASE_URL",
            "VOLCENGINE_ARK_BASE_URL",
            "LLM_BASE_URL",
        )
        model = _first(
            "LLM_NARRATIVE_MODEL",
            "DOUBAO_MODEL",
            "ARK_MODEL",
            "LLM_MODEL",
        )
    elif provider == "deepseek":
        api_key = _first("DEEPSEEK_API_KEY", "LLM_API_KEY")
        base_url = _first("DEEPSEEK_BASE_URL", "LLM_BASE_URL") or "https://api.deepseek.com/v1"
        model = _first("LLM_NARRATIVE_MODEL", "DEEPSEEK_MODEL", "LLM_MODEL") or "deepseek-chat"
    elif provider == "openai":
        api_key = _first("OPENAI_API_KEY", "LLM_API_KEY")
        base_url = _first("OPENAI_BASE_URL", "LLM_BASE_URL") or "https://api.openai.com/v1"
        model = _first("LLM_NARRATIVE_MODEL", "OPENAI_MODEL", "LLM_MODEL") or "gpt-4o-mini"
    else:
        return None

    if not api_key or not base_url or not model:
        return None
    return api_key, base_url, model


def _build_messages(section: SectionData, ctx: ReportContext) -> list[dict[str, str]]:
    """Build the OpenAI chat messages list for one section.

    System message frames the task: brand-operations analyst writing
    one prose paragraph in the target locale.

    User message carries the structured input (section type, summary,
    a curated metric subset, and tables truncated to first-3-rows) as
    JSON so the model has a single, parsable context block. We
    explicitly forbid markdown and JSON in the output to keep the
    paragraph drop-in-able into Markdown / CSV / PDF renderers.
    """
    is_zh = ctx.locale.startswith("zh")
    locale_hint = "Simplified Chinese (zh-CN)" if is_zh else "English (en-US)"
    word_target = "80-120 字" if is_zh else "80-120 words"

    system = (
        "You are a brand-operations analyst writing the narrative "
        "paragraph for one section of a GenPano brand report. The "
        "audience is operators/managers reviewing brand performance "
        "in LLM ecosystems. Write in "
        f"{locale_hint}. Output one short paragraph, "
        f"{word_target}. No markdown, no headings, no bullet lists, "
        "no JSON — plain prose only. Anchor the paragraph in the "
        "provided metrics; do not invent numbers."
    )

    payload = {
        "section_type": section.section_type,
        "title": section.title,
        "summary": section.summary,
        "metrics": _trim_metrics(section.metrics),
        "tables": _trim_tables(section.tables),
    }
    user = (
        "Section data follows as JSON. Produce the prose paragraph "
        "for this section.\n\n" + json.dumps(payload, ensure_ascii=False, default=str)
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _trim_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Keep the prompt small: drop None values, cap at 10 keys, stringify
    nested dicts/lists to compact JSON so the model sees a flat KV view."""
    if not metrics:
        return {}
    trimmed: dict[str, Any] = {}
    for k, v in metrics.items():
        if v is None:
            continue
        if isinstance(v, dict | list):
            trimmed[k] = json.dumps(v, ensure_ascii=False, default=str)[:400]
        else:
            trimmed[k] = v
        if len(trimmed) >= 10:
            break
    return trimmed


def _trim_tables(tables: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """First 3 rows of the first 2 tables. The model rarely needs
    more than a few rows to ground the paragraph; keeping tokens low
    is more important."""
    if not tables:
        return []
    out: list[dict[str, Any]] = []
    for tbl in tables[:2]:
        out.append(
            {
                "name": tbl.get("name"),
                "row_count": len(tbl.get("rows") or []),
                "rows": (tbl.get("rows") or [])[:3],
            }
        )
    return out


def _normalize_completion(content: str) -> str:
    """Strip markdown fences / leading bullets / surrounding quotes the
    model might inject despite the prompt. Collapse internal whitespace."""
    text = (content or "").strip()
    if not text:
        return ""
    # Drop a fenced block if the whole response is wrapped in one.
    if text.startswith("```") and text.endswith("```"):
        inner = text.strip("`")
        if "\n" in inner:
            _, _, body = inner.partition("\n")
            text = body.strip()
    # Drop leading bullet/quote characters.
    while text and text[0] in {"-", "*", ">", '"', "'"}:
        text = text[1:].lstrip()
    return " ".join(text.split())


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
