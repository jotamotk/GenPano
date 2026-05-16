"""PDF renderer for report payloads (PRD §4.7.5 / audit #1044 B2-12).

Server-side PDF generation using `fpdf2` — pure Python (no Cairo /
WeasyPrint / wkhtmltopdf required).

CJK font handling
─────────────────
fpdf2's built-in Helvetica covers Latin-1 only. Since the default
report `locale` is `zh-CN`, we MUST be able to render Chinese glyphs
or the entire default-flow PDF ends up as "?". This module:

  1. At import time, scans well-known system font paths for a Unicode
     TTF/TTC that covers CJK. The backend Docker image installs
     `fonts-wqy-microhei` (see backend/Dockerfile) so the path
     `/usr/share/fonts/truetype/wqy/wqy-microhei.ttc` is the typical
     hit in production.
  2. Operators can override via `GENPANO_PDF_CJK_FONT_PATH` env.
  3. If a CJK font is found, every text write uses it as the active
     font family — so zh-CN payloads render correctly. Latin text
     still renders fine through the same font.
  4. If no CJK font is found (e.g. local dev without the apt package),
     we fall back to Helvetica + Latin-1 transliteration AND prepend a
     warning page header so the operator sees the cause immediately.

This guarantees the renderer is usable in the default zh-CN flow on
production deploys, while keeping local/CI environments working
without forcing every contributor to install a CJK font.

Used by `GET /v1/projects/:id/reports/:rid/download?format=pdf`.
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
        "no_cjk_warning": (
            "[警告] 后端未安装 CJK 字体,中文内容已转写为占位符。"
            "Operator: 在容器中安装 fonts-wqy-microhei 或设置 "
            "GENPANO_PDF_CJK_FONT_PATH 环境变量后重启。"
        ),
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
        "no_cjk_warning": (
            "[WARNING] Backend has no CJK font installed; non-Latin "
            "characters are transliterated. Operator: install "
            "fonts-wqy-microhei or set GENPANO_PDF_CJK_FONT_PATH."
        ),
    },
}


def _labels(locale: str) -> dict[str, str]:
    return _LABELS.get(locale, _LABELS["en-US"])


_CJK_FONT_SEARCH_PATHS: tuple[str, ...] = (
    # Linux apt: fonts-wqy-microhei
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    # Linux apt: fonts-wqy-zenhei
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    # Linux apt: fonts-noto-cjk
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    # Custom vendored path (operator drops a TTF under static/)
    "/app/static/fonts/cjk.ttf",
)

_CJK_FONT_FAMILY = "CJK"
_CJK_FONT_ENV_VAR = "GENPANO_PDF_CJK_FONT_PATH"


def _resolve_cjk_font_path() -> str | None:
    """Pick the first CJK font path that actually exists on disk.

    Order of preference:
      1. `GENPANO_PDF_CJK_FONT_PATH` env var (explicit operator override)
      2. Standard system paths from `_CJK_FONT_SEARCH_PATHS`

    Returns None when none are present, in which case rendering falls
    back to Latin-1 transliteration + a visible warning header.
    """
    override = os.environ.get(_CJK_FONT_ENV_VAR, "").strip()
    if override and Path(override).exists():
        return override
    for path in _CJK_FONT_SEARCH_PATHS:
        if Path(path).exists():
            return path
    return None


# Resolve once per process. Re-importing is cheap; the path check is
# stat() and not a font parse.
_CJK_FONT_PATH: str | None = _resolve_cjk_font_path()
if _CJK_FONT_PATH is None:
    log.warning(
        "pdf_renderer.cjk_font_missing",
        extra={
            "searched": _CJK_FONT_SEARCH_PATHS,
            "env_var": _CJK_FONT_ENV_VAR,
        },
    )


def _latin1_safe(value: Any) -> str:
    """Coerce arbitrary values to Latin-1-safe text. Only used when no
    CJK font is registered — drops non-Latin1 glyphs to a `?`
    placeholder so fpdf2's core Helvetica can encode without raising."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            value = str(value)
    s = str(value)
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        return s.encode("latin-1", errors="replace").decode("latin-1")


def _unicode_safe(value: Any) -> str:
    """Coerce arbitrary values to a string. CJK font path — no
    transliteration needed; fpdf2 emits UTF-8 text directly."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def render_pdf(payload: dict[str, Any]) -> bytes:
    """Render a `build_report()` payload to PDF bytes.

    Auto-registers a CJK font when one is available on disk so zh-CN
    payloads render correctly without operator action. Falls back to a
    Helvetica+transliteration mode with a visible warning page header
    when no CJK font is found.
    """
    from fpdf import FPDF

    locale = payload.get("locale", "en-US")
    lang = _labels(locale)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    if _CJK_FONT_PATH:
        try:
            pdf.add_font(_CJK_FONT_FAMILY, "", _CJK_FONT_PATH)
            font_family = _CJK_FONT_FAMILY
            text_fn = _unicode_safe
            warning_header: str | None = None
        except Exception as exc:  # pragma: no cover — defensive
            log.warning(
                "pdf_renderer.cjk_font_load_failed",
                extra={"path": _CJK_FONT_PATH, "error": str(exc)},
            )
            font_family = "Helvetica"
            text_fn = _latin1_safe
            warning_header = lang["no_cjk_warning"] if locale.startswith("zh") else None
    else:
        font_family = "Helvetica"
        text_fn = _latin1_safe
        # Only show the warning on zh-* locales — en-US doesn't need CJK.
        warning_header = lang["no_cjk_warning"] if locale.startswith("zh") else None

    pdf.add_page()

    if warning_header:
        pdf.set_font(font_family, "", 9)
        pdf.set_text_color(180, 60, 60)
        pdf.multi_cell(0, 5, text_fn(warning_header))
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    pdf.set_font(font_family, "", 18)
    report_type = payload.get("report_type", "weekly")
    pdf.cell(
        0,
        10,
        text_fn(f"{lang['report']}: {report_type.upper()}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )

    period = payload.get("period", {})
    period_from = period.get("from", "—")
    period_to = period.get("to", "—")
    perspective = payload.get("reader_perspective", "manager")
    project_id = payload.get("project_id", "")

    pdf.set_font(font_family, "", 10)
    pdf.set_text_color(80, 80, 80)
    meta = (
        f"{lang['project']}: {project_id}  |  "
        f"{lang['perspective']}: {perspective}  |  "
        f"{lang['period']}: {period_from} -> {period_to}"
    )
    pdf.cell(0, 6, text_fn(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    sections = payload.get("sections", [])
    if not sections:
        pdf.set_font(font_family, "", 11)
        pdf.cell(0, 8, text_fn(lang["no_data"]), new_x="LMARGIN", new_y="NEXT")
        return _output_bytes(pdf)

    for sec in sections:
        _render_section(pdf, sec, lang, font_family=font_family, text_fn=text_fn)

    return _output_bytes(pdf)


def _output_bytes(pdf: Any) -> bytes:
    """fpdf2's .output() returns either bytes or bytearray; normalize."""
    raw = pdf.output()
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    return str(raw).encode("latin-1")


def _render_section(
    pdf: Any,
    sec: dict[str, Any],
    lang: dict[str, str],
    *,
    font_family: str,
    text_fn: Any,
) -> None:
    title = sec.get("title") or sec.get("section_type", "Section")

    pdf.set_font(font_family, "", 14)
    pdf.ln(2)
    pdf.cell(0, 8, text_fn(title), new_x="LMARGIN", new_y="NEXT")

    summary = sec.get("summary")
    if summary:
        pdf.set_font(font_family, "", 10)
        pdf.multi_cell(0, 6, text_fn(summary))
        pdf.ln(1)

    narrative = sec.get("narrative")
    if narrative:
        pdf.set_font(font_family, "", 10)
        pdf.cell(
            0,
            6,
            text_fn(lang["narrative"]),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.multi_cell(0, 6, text_fn(narrative))
        pdf.ln(1)

    metrics = sec.get("metrics") or {}
    if metrics:
        pdf.set_font(font_family, "", 10)
        pdf.cell(
            0,
            6,
            text_fn(lang["metrics"]),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font(font_family, "", 9)
        for key, value in metrics.items():
            pdf.cell(
                0,
                5,
                text_fn(f"  {key}: {value}"),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.ln(1)

    for table in sec.get("tables") or []:
        _render_table(pdf, table, lang, font_family=font_family, text_fn=text_fn)

    for chart in sec.get("charts") or []:
        _render_chart_placeholder(pdf, chart, lang, font_family=font_family, text_fn=text_fn)


def _render_table(
    pdf: Any,
    table: dict[str, Any],
    lang: dict[str, str],
    *,
    font_family: str,
    text_fn: Any,
) -> None:
    rows = table.get("rows") or []
    if not rows:
        return
    name = table.get("name", "table")
    columns = list(rows[0].keys())

    pdf.set_font(font_family, "", 10)
    pdf.cell(
        0,
        6,
        text_fn(f"{lang['tables']}: {name}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # Equal-width columns sized to page width minus margins.
    epw = pdf.w - 2 * pdf.l_margin
    col_w = max(epw / max(len(columns), 1), 20.0)
    pdf.set_font(font_family, "", 8)
    for col in columns:
        pdf.cell(col_w, 6, text_fn(col), border=1, align="L")
    pdf.ln()
    for row in rows:
        for col in columns:
            cell = text_fn(row.get(col, ""))
            if len(cell) > 40:
                cell = cell[:37] + "..."
            pdf.cell(col_w, 6, cell, border=1, align="L")
        pdf.ln()
    pdf.ln(2)


def _render_chart_placeholder(
    pdf: Any,
    chart: dict[str, Any],
    lang: dict[str, str],
    *,
    font_family: str,
    text_fn: Any,
) -> None:
    name = chart.get("name", chart.get("type", "chart"))
    pdf.set_font(font_family, "", 10)
    pdf.cell(
        0,
        6,
        text_fn(f"{lang['charts']}: {name}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font(font_family, "", 8)
    pdf.set_text_color(80, 80, 80)
    spec_str = text_fn(json.dumps(chart, ensure_ascii=False, sort_keys=True))
    if len(spec_str) > 220:
        spec_str = spec_str[:217] + "..."
    pdf.multi_cell(0, 5, spec_str)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def render_pdf_to_stream(payload: dict[str, Any]) -> io.BytesIO:
    """Convenience wrapper returning a BytesIO for callers that need a
    file-like object (e.g. SMTP attachment helpers)."""
    return io.BytesIO(render_pdf(payload))


def cjk_font_is_available() -> bool:
    """Helper for tests + ops dashboards: True when the renderer has a
    registered CJK font path. Tests with zh-CN payloads can use this to
    decide whether to assert glyph fidelity vs warning-header presence."""
    return _CJK_FONT_PATH is not None


def _refresh_cjk_font_path_for_tests() -> None:
    """Re-resolve `_CJK_FONT_PATH` after env mutation. Public to tests
    via monkeypatch.setattr — production code should not call this."""
    global _CJK_FONT_PATH
    _CJK_FONT_PATH = _resolve_cjk_font_path()
