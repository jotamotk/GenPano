"""cta section — consulting-CTA copy block per PRD §4.7.6.

This is a fixed-copy section (no data aggregation). PRD §4.7.6 is the
canonical statement of the business boundary: GenPano reports give
*direction* via diagnostics, never *playbook* — playbook delivery is
paid consulting. The CTA section is where that boundary becomes a
deliberate user-facing surface.

In the SECTION_MATRIX it appears as:
  - weekly:  variant='full', primary_reader='manager'
  - monthly: variant='full', primary_reader='manager'
  - on_demand: variant='optional' (skipped by builder when 'optional')
  - lead_diagnostic: variant='strengthened' (PRD §4.7.6 — stronger copy
    + explicit CTA url; the dedicated lead_diagnostic view actually
    renders the 4-layer structure separately, so this section is the
    fallback when builder is invoked on lead_diagnostic without the
    dedicated path)
"""

from __future__ import annotations

import os

from app.reports.sections.base import BaseSection, ReportContext, SectionData

_CTA_DEFAULT_URL = "https://genpano.com/consulting"


def _cta_url() -> str:
    """Operators may pin a tenant-specific CTA URL via env."""
    return os.environ.get("GENPANO_CONSULTING_CTA_URL", _CTA_DEFAULT_URL).strip()


def _title(locale: str) -> str:
    return "咨询服务" if locale.startswith("zh") else "Consulting"


def _body(locale: str, *, strengthened: bool) -> str:
    is_zh = locale.startswith("zh")
    if strengthened:
        return (
            "您看到的 P0/P1 诊断已经明确了"
            "**方向**;若需要把每个方向拆成可执行的剧本"
            "(里程碑、负责人、ROI 模型),GenPano 咨询团队提供"
            "一对一深度交付。本期诊断中至少 3 项已被标记为"
            "Consulting Accelerators,值得优先沟通。"
            if is_zh
            else (
                "The P0/P1 diagnostics above point you in a direction. "
                "If you need an executable playbook for each — milestones, "
                "owners, ROI model — GenPano Consulting delivers 1-on-1 "
                "engagements. At least 3 items this period are flagged as "
                "Consulting Accelerators worth prioritizing."
            )
        )
    return (
        "GenPano 报告只提供诊断方向,不提供执行剧本。需要把诊断落地为可执行计划,可联系咨询服务团队。"
        if is_zh
        else (
            "GenPano reports give diagnostic direction, not execution "
            "playbooks. To translate diagnostics into an actionable plan, "
            "reach out to the consulting team."
        )
    )


class CtaSection(BaseSection):
    section_type = "cta"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        strengthened = variant == "strengthened"
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_body(ctx.locale, strengthened=strengthened),
            metrics={
                "cta_url": _cta_url(),
                "cta_label": (
                    "联系咨询团队" if ctx.locale.startswith("zh") else "Contact consulting"
                ),
                "strengthened": strengthened,
            },
            chosen_variant=variant,
        )
