"""PDF renderer for report payloads (PRD §4.7.5 / audit #1044 B2-12).

Server-side PDF generation using `fpdf2` — pure Python (no system
dependencies like Cairo / WeasyPrint / wkhtmltopdf). The output is a
single-column page-broken document with headers, sub-headers, summary
+ narrative text blocks, key/value metric lists, and Markdown-style
data tables.

Trade-offs vs. WeasyPrint:
  - No external system deps → ships with the backend container
  - Limited typography (one Helvetica family + sans-serif core fonts)
  - Tables are simple grids (no CSS-style merged cells)
  - Charts render as a fenced JSON placeholder (same shape as Markdown
    renderer) — full SVG/PNG chart rendering is a follow-up that
    requires generating chart images first
  - CJK support requires the built-in 'helvetica' font; non-Latin
    characters are transliterated when the active font lacks glyphs.
    A real deployment should register a CJK font via FPDF.add_font();
    docstring documents the operator hook.

Used by `GET /v1/projects/:id/reports/:rid/download?format=pdf`.
"""

from __future__ import annotations

import io
import json
from typing import Any

_LABELS = {
    "zh-CN": {
        "report": "报告",
        "period": "时间范围",
        "project": "项目",
        "perspective": "视角",
        "summary": "摘要",
        "narrative": "洞察",
        "metrics": "指标",
        "tables": "数据表",
        "charts": "图表",
        "no_data": "本期无数据。",
    },
    "en-US": {
        "report": "Report",
        "period": "Period",
        "project": "Project",
        "perspective": "Reader",
        "summary": "Summary",
        "narrative": "Narrative",
        "metrics": "Metrics",
        "tables": "Tables",
        "charts": "Charts",
        "no_data": "No data this period.",
    },
}


def _labels(locale: str) -> dict[str, str]:
    return _LABELS.get(locale, _LABELS["en-US"])


def _safe_text(value: Any) -> str:
    """Coerce arbitrary values to a string that fpdf2's core font can
    safely encode. Built-in Helvetica is latin-1; non-Latin glyphs need
    a registered Unicode font. Until that's wired we fall back to a
    `?`-prefixed transliteration so the PDF still renders rather than
    raising at write time."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(value)
    s = str(value)
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        # Replace each non-latin1 char with `?` so we never block on
        # encoding. Operators wanting CJK should call
        # `register_cjk_font(pdf, font_path)` before render_pdf().
        return s.encode("latin-1", errors="replace").decode("latin-1")


def render_pdf(payload: dict[str, Any]) -> bytes:
    """Render a `build_report()` payload to PDF bytes.

    No external system deps. Output mirrors the Markdown renderer's
    structure section-by-section so downstream consumers can compare
    apples to apples between the `?format=markdown` and `?format=pdf`
    downloads.
    """
    from fpdf import FPDF

    locale = payload.get("locale", "en-US")
    lang = _labels(locale)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)

    report_type = payload.get("report_type", "weekly")
    pdf.cell(
        0,
        10,
        _safe_text(f"{lang['report']}: {report_type.upper()}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )

    period = payload.get("period", {})
    period_from = period.get("from", "—")
    period_to = period.get("to", "—")
    perspective = payload.get("reader_perspective", "manager")
    project_id = payload.get("project_id", "")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    meta = (
        f"{lang['project']}: {project_id}  |  "
        f"{lang['perspective']}: {perspective}  |  "
        f"{lang['period']}: {period_from} -> {period_to}"
    )
    pdf.cell(0, 6, _safe_text(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    sections = payload.get("sections", [])
    if not sections:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, _safe_text(lang["no_data"]), new_x="LMARGIN", new_y="NEXT")
        return _output_bytes(pdf)

    for sec in sections:
        _render_section(pdf, sec, lang)

    return _output_bytes(pdf)


def _output_bytes(pdf: Any) -> bytes:
    """fpdf2's .output() returns either bytes or bytearray depending on
    the version; normalize to bytes for the FastAPI Response."""
    raw = pdf.output()
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    # Older fpdf returned str-encoded latin-1 — coerce.
    return str(raw).encode("latin-1")


def _render_section(pdf: Any, sec: dict[str, Any], lang: dict[str, str]) -> None:
    title = sec.get("title") or sec.get("section_type", "Section")

    pdf.set_font("Helvetica", "B", 14)
    pdf.ln(2)
    pdf.cell(0, 8, _safe_text(title), new_x="LMARGIN", new_y="NEXT")

    summary = sec.get("summary")
    if summary:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _safe_text(summary))
        pdf.ln(1)

    narrative = sec.get("narrative")
    if narrative:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _safe_text(lang["narrative"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _safe_text(narrative))
        pdf.ln(1)

    metrics = sec.get("metrics") or {}
    if metrics:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _safe_text(lang["metrics"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for key, value in metrics.items():
            pdf.cell(
                0,
                5,
                _safe_text(f"  {key}: {value}"),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.ln(1)

    for table in sec.get("tables") or []:
        _render_table(pdf, table, lang)

    for chart in sec.get("charts") or []:
        _render_chart_placeholder(pdf, chart, lang)


def _render_table(pdf: Any, table: dict[str, Any], lang: dict[str, str]) -> None:
    rows = table.get("rows") or []
    if not rows:
        return
    name = table.get("name", "table")
    columns = list(rows[0].keys())

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0,
        6,
        _safe_text(f"{lang['tables']}: {name}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # Equal-width columns sized to page width minus margins.
    epw = pdf.w - 2 * pdf.l_margin
    col_w = max(epw / max(len(columns), 1), 20.0)
    pdf.set_font("Helvetica", "B", 8)
    for col in columns:
        pdf.cell(col_w, 6, _safe_text(col), border=1, align="L")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for row in rows:
        for col in columns:
            cell = _safe_text(row.get(col, ""))
            # Truncate long cell contents so we don't overflow the row.
            if len(cell) > 40:
                cell = cell[:37] + "..."
            pdf.cell(col_w, 6, cell, border=1, align="L")
        pdf.ln()
    pdf.ln(2)


def _render_chart_placeholder(pdf: Any, chart: dict[str, Any], lang: dict[str, str]) -> None:
    name = chart.get("name", chart.get("type", "chart"))
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0,
        6,
        _safe_text(f"{lang['charts']}: {name}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    spec_str = _safe_text(json.dumps(chart, ensure_ascii=False, sort_keys=True))
    if len(spec_str) > 220:
        spec_str = spec_str[:217] + "..."
    pdf.multi_cell(0, 5, spec_str)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def register_cjk_font(pdf: Any, font_path: str, family: str = "cjk") -> None:
    """Operator hook for production deployments needing CJK glyphs.
    Call before `render_pdf` to swap the Latin-only Helvetica out for a
    Unicode TTF (e.g. NotoSansCJK). Example:

        from fpdf import FPDF
        from app.reports.renderers.pdf_renderer import register_cjk_font, render_pdf
        pdf = FPDF()
        register_cjk_font(pdf, "/usr/share/fonts/NotoSansCJK-Regular.ttc")
        # rebuild rendering loop with set_font('cjk', ...) — current
        # renderer hardcodes Helvetica; the cleanest hook is to pass a
        # `font_family` parameter through render_pdf in a follow-up PR.
    """
    pdf.add_font(family, "", font_path, uni=True)


def render_pdf_to_stream(payload: dict[str, Any]) -> io.BytesIO:
    """Convenience wrapper returning a BytesIO for callers that need a
    file-like object (e.g. SMTP attachment helpers)."""
    return io.BytesIO(render_pdf(payload))
