"""Phase RP.2 report engine.

Public API:

    from app.reports import build_report

    payload = await build_report(
        session, project=project, report_type="weekly", locale="zh-CN"
    )

The builder consults `SECTION_MATRIX` (PRD §4.7.2 — 4 reportType x 10 section
x 3 variant x 3 reader perspective) and dispatches to per-section renderers
under `app.reports.sections.*`.
"""

from app.reports.builder import SECTION_MATRIX, build_report

__all__ = ["SECTION_MATRIX", "build_report"]
