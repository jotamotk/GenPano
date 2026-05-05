"""Markdown renderer for report payloads (Phase RP.5).

Consumes the dict returned by `app.reports.build_report` and produces a
single Markdown document. Used by:
  - GET /v1/projects/:id/reports/:rid/download?format=markdown (Phase RP.6)
  - `genpano_generate_report` MCP tool (Phase M.3)
  - Email digest body (Phase N follow-up)

Locale-aware headings (zh / en) — falls back to English if locale is
unrecognised.
"""

from __future__ import annotations

from typing import Any

_LABELS = {
    "zh-CN": {
        "report": "报告",
        "period": "时间范围",
        "from": "从",
        "to": "至",
        "project": "项目",
        "perspective": "视角",
        "section": "章节",
        "summary": "摘要",
        "metrics": "指标",
        "tables": "数据表",
        "no_data": "本期无数据。",
    },
    "en-US": {
        "report": "Report",
        "period": "Period",
        "from": "From",
        "to": "To",
        "project": "Project",
        "perspective": "Reader",
        "section": "Section",
        "summary": "Summary",
        "metrics": "Metrics",
        "tables": "Tables",
        "no_data": "No data this period.",
    },
}


def _labels(locale: str) -> dict[str, str]:
    return _LABELS.get(locale, _LABELS["en-US"])


def _md_table(rows: list[dict[str, Any]]) -> str:
    """Render a list-of-dicts as a Markdown table."""
    if not rows:
        return ""
    columns = list(rows[0].keys())
    lines: list[str] = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for r in rows:
        cells = [str(r.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a build_report() payload to Markdown."""
    locale = payload.get("locale", "en-US")
    lang = _labels(locale)
    report_type = payload.get("report_type", "weekly")
    period = payload.get("period", {})
    period_from = period.get("from", "—")
    period_to = period.get("to", "—")
    perspective = payload.get("reader_perspective", "manager")
    project_id = payload.get("project_id", "")

    parts: list[str] = []
    parts.append(f"# {lang['report']}: {report_type.upper()}")
    parts.append("")
    parts.append(
        f"**{lang['project']}**: `{project_id}`  ·  "
        f"**{lang['perspective']}**: {perspective}  ·  "
        f"**{lang['period']}**: {period_from} → {period_to}"
    )
    parts.append("")

    sections = payload.get("sections", [])
    if not sections:
        parts.append(f"_{lang['no_data']}_")
        return "\n".join(parts).rstrip() + "\n"

    for sec in sections:
        title = sec.get("title", sec.get("section_type", "Section"))
        parts.append(f"## {title}")
        parts.append("")
        summary = sec.get("summary")
        if summary:
            parts.append(summary)
            parts.append("")

        metrics = sec.get("metrics") or {}
        if metrics:
            parts.append(f"**{lang['metrics']}**")
            parts.append("")
            for k, v in metrics.items():
                parts.append(f"- `{k}`: {v}")
            parts.append("")

        for table in sec.get("tables") or []:
            name = table.get("name", "table")
            rows = table.get("rows") or []
            if not rows:
                continue
            parts.append(f"**{lang['tables']}: {name}**")
            parts.append("")
            parts.append(_md_table(rows))
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"
