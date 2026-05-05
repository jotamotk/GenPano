"""Phase RP.8 — lead_diagnostic 4-layer report builder.

Per PRD §4.7.2.8, the lead_diagnostic report type renders an opinionated
4-layer summary (NOT the SECTION_MATRIX layout) used when a user submits
a commercial lead — auto-generated PDF emailed to the BD team.

Layer structure:
  L1 — Current state one-liner + 4 key metric cards (geo_score / mention_rate /
       sov / sentiment) for the project's primary brand.
  L2 — Top 3 open P0/P1 diagnostics with industry comparison (where available).
  L3 — One-sentence directional summary (current trajectory + recommendation).
  L4 — CTA to contact a consultant (deep link with project_id).

Output dict shape mirrors the SECTION_MATRIX builder so the same renderer
chain (markdown / json / csv) can ingest it without special-casing.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import Diagnostic, GeoScoreDaily, Project
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def build_lead_diagnostic(
    session: AsyncSession,
    *,
    project: Project,
    locale: str = "zh-CN",
    days: int = 30,
) -> dict[str, Any]:
    """Build a 4-layer lead_diagnostic payload for `project`."""
    today = date.today()
    from_d = today - timedelta(days=days - 1)

    layer1 = await _layer1_metric_cards(session, project, from_d, today, locale)
    layer2 = await _layer2_top_diagnostics(session, project, locale)
    layer3 = _layer3_summary(layer1, layer2, locale)
    layer4 = _layer4_cta(project, locale)

    return {
        "report_type": "lead_diagnostic",
        "locale": locale,
        "reader_perspective": "lead",
        "period": {"from": from_d.isoformat(), "to": today.isoformat()},
        "project_id": project.id,
        "layers": [layer1, layer2, layer3, layer4],
        # Mirror SECTION_MATRIX shape so renderers can consume uniformly
        "sections": [
            {
                "section_type": f"layer_{i + 1}",
                "title": layer["title"],
                "summary": layer.get("summary", ""),
                "metrics": layer.get("metrics", {}),
                "tables": layer.get("tables", []),
                "charts": [],
                "variant": "lead",
            }
            for i, layer in enumerate([layer1, layer2, layer3, layer4])
        ],
    }


async def _layer1_metric_cards(
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    locale: str,
) -> dict[str, Any]:
    title = "现状速览" if locale.startswith("zh") else "Current State"
    if not project.primary_brand_id:
        return {
            "title": title,
            "summary": (
                "尚未关联主品牌, 数据待补。"
                if locale.startswith("zh")
                else "No primary brand linked yet."
            ),
            "metrics": {},
        }

    stmt = select(
        func.avg(GeoScoreDaily.avg_geo_score),
        func.avg(GeoScoreDaily.mention_rate),
        func.avg(GeoScoreDaily.avg_sov),
        func.avg(GeoScoreDaily.avg_sentiment),
        func.count(GeoScoreDaily.id),
    ).where(
        and_(
            GeoScoreDaily.brand_id == project.primary_brand_id,
            GeoScoreDaily.date >= from_d,
            GeoScoreDaily.date <= to_d,
        )
    )
    row = (await session.execute(stmt)).one()
    geo = round(row[0] or 0, 2)
    mention = round(row[1] or 0, 4)
    sov = round(row[2] or 0, 4)
    sentiment = round(row[3] or 0, 3)
    samples = int(row[4] or 0)

    if locale.startswith("zh"):
        summary = (
            f"近 30 天 GEO 总分 {geo}, 提及率 {mention * 100:.1f}%, "
            f"SoV {sov * 100:.1f}%, 情感分 {sentiment}."
        )
    else:
        summary = (
            f"Last 30 days: GEO score {geo}, mention rate {mention * 100:.1f}%, "
            f"SoV {sov * 100:.1f}%, sentiment {sentiment}."
        )

    return {
        "title": title,
        "summary": summary,
        "metrics": {
            "geo_score": geo,
            "mention_rate": mention,
            "sov": sov,
            "sentiment": sentiment,
            "samples": samples,
        },
    }


async def _layer2_top_diagnostics(
    session: AsyncSession, project: Project, locale: str
) -> dict[str, Any]:
    """Top 3 open P0/P1 diagnostics for the project."""
    stmt = (
        select(Diagnostic)
        .where(
            and_(
                Diagnostic.project_id == project.id,
                Diagnostic.status == "open",
                Diagnostic.severity.in_(["P0", "P1"]),
            )
        )
        .order_by(Diagnostic.severity, Diagnostic.detected_at.desc())
        .limit(3)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    title = "关键诊断" if locale.startswith("zh") else "Top Diagnostics"
    if not rows:
        return {
            "title": title,
            "summary": (
                "本期未触发 P0/P1 诊断, 状态健康。"
                if locale.startswith("zh")
                else "No open P0/P1 diagnostics — project is healthy."
            ),
            "tables": [],
        }
    items = [
        {
            "id": d.id,
            "severity": d.severity,
            "category": d.category,
            "title": d.title,
            "direction": d.direction or "",
        }
        for d in rows
    ]
    return {
        "title": title,
        "summary": (
            f"{len(rows)} 条 P0/P1 诊断未处理。"
            if locale.startswith("zh")
            else f"{len(rows)} open P0/P1 diagnostics."
        ),
        "tables": [{"name": "top_p0_p1", "rows": items}],
    }


def _layer3_summary(layer1: dict[str, Any], layer2: dict[str, Any], locale: str) -> dict[str, Any]:
    """One-sentence directional summary based on layer 1 + 2."""
    metrics = layer1.get("metrics", {})
    geo = metrics.get("geo_score", 0)
    diag_count = len(layer2.get("tables", [{}])[0].get("rows", [])) if layer2.get("tables") else 0

    if locale.startswith("zh"):
        if not metrics.get("samples"):
            sentence = "数据采集尚未启动, 建议立即配置首次采集任务。"
        elif diag_count >= 2:
            sentence = (
                f"GEO 总分 {geo}, 但有 {diag_count} 条 P0/P1 诊断待处理, 建议尽快约顾问梳理优先级。"
            )
        elif geo < 60:
            sentence = f"GEO 总分仅 {geo}, 处于行业偏低区, 建议系统性优化。"
        else:
            sentence = f"GEO 总分 {geo}, 整体健康, 顾问可协助进一步精细化。"
    elif not metrics.get("samples"):
        sentence = "Data collection has not started — kick off your first crawl now."
    elif diag_count >= 2:
        sentence = (
            f"GEO score {geo} but {diag_count} open P0/P1 issues — schedule a "
            "consultation to triage priorities."
        )
    elif geo < 60:
        sentence = f"GEO score {geo} is below industry baseline — systemic uplift recommended."
    else:
        sentence = f"GEO score {geo} is healthy — a consultant can help refine further."

    return {
        "title": "方向" if locale.startswith("zh") else "Direction",
        "summary": sentence,
    }


def _layer4_cta(project: Project, locale: str) -> dict[str, Any]:
    title = "下一步" if locale.startswith("zh") else "Next Step"
    if locale.startswith("zh"):
        summary = "顾问可在 1 个工作日内联系您, 解读完整数据 + 给出 30 天行动方案。"
        action_label = "立即预约顾问"
    else:
        summary = (
            "Our consultant will reach out within one business day to walk through "
            "the full data and a 30-day action plan."
        )
        action_label = "Book a consultant"
    return {
        "title": title,
        "summary": summary,
        "metrics": {
            "cta_label": action_label,
            "cta_link": f"/contact?source=lead_diagnostic&project_id={project.id}",
        },
    }
