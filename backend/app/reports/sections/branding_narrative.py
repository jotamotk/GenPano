"""branding_narrative section (PRD §4.7.2 / audit #1044 B2-5).

Surfaces "what the AI is saying ABOUT the brand" — the narrative arc:

  - top positive sentiment drivers (keyword + sample quote count)
  - top negative sentiment drivers (same)
  - emerging topics from TopicScoreDaily (highest mention growth)

PRD §4.7.2 calls this "Branding 叙事弧" — the narrative-flow lens that
sits adjacent to PANO Score but focuses on language/topic shifts
rather than numeric metrics.

Data source: `sentiment_drivers` (per BrandMention) + `topic_score_daily`.
Both already populated by the analyzer pipeline.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from genpano_models import BrandMention, SentimentDriver, TopicScoreDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData

_TOP_K_DRIVERS = 5
_TOP_K_TOPICS = 5


class BrandingNarrativeSection(BaseSection):
    section_type = "branding_narrative"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        if ctx.project.primary_brand_id is None:
            return _empty(ctx, variant, "no_primary_brand")

        window_start = datetime.combine(ctx.from_date, time.min)
        window_end = datetime.combine(ctx.to_date + timedelta(days=1), time.min)

        # Sentiment drivers join through BrandMention to scope to this
        # brand id — see #1046 B1-8 (don't join on brand_name string).
        positive_stmt = (
            select(
                SentimentDriver.driver_text,
                func.count(SentimentDriver.id),
            )
            .select_from(SentimentDriver)
            .join(BrandMention, BrandMention.id == SentimentDriver.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == ctx.project.primary_brand_id,
                    SentimentDriver.polarity == "positive",
                    SentimentDriver.created_at >= window_start,
                    SentimentDriver.created_at < window_end,
                )
            )
            .group_by(SentimentDriver.driver_text)
            .order_by(func.count(SentimentDriver.id).desc())
            .limit(_TOP_K_DRIVERS)
        )
        negative_stmt = (
            select(
                SentimentDriver.driver_text,
                func.count(SentimentDriver.id),
            )
            .select_from(SentimentDriver)
            .join(BrandMention, BrandMention.id == SentimentDriver.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == ctx.project.primary_brand_id,
                    SentimentDriver.polarity == "negative",
                    SentimentDriver.created_at >= window_start,
                    SentimentDriver.created_at < window_end,
                )
            )
            .group_by(SentimentDriver.driver_text)
            .order_by(func.count(SentimentDriver.id).desc())
            .limit(_TOP_K_DRIVERS)
        )
        topic_stmt = (
            select(
                TopicScoreDaily.topic_id,
                func.sum(TopicScoreDaily.mention_count),
                func.avg(TopicScoreDaily.avg_sentiment_score),
            )
            .where(
                and_(
                    TopicScoreDaily.brand_id == ctx.project.primary_brand_id,
                    TopicScoreDaily.date >= ctx.from_date,
                    TopicScoreDaily.date <= ctx.to_date,
                )
            )
            .group_by(TopicScoreDaily.topic_id)
            .order_by(func.sum(TopicScoreDaily.mention_count).desc())
            .limit(_TOP_K_TOPICS)
        )

        positive_rows = [
            {"driver": r[0], "count": int(r[1] or 0)}
            for r in (await ctx.session.execute(positive_stmt)).all()
        ]
        negative_rows = [
            {"driver": r[0], "count": int(r[1] or 0)}
            for r in (await ctx.session.execute(negative_stmt)).all()
        ]
        topic_rows = [
            {
                "topic_id": int(r[0]),
                "mention_count": int(r[1] or 0),
                "avg_sentiment": (round(float(r[2]), 3) if r[2] is not None else None),
            }
            for r in (await ctx.session.execute(topic_stmt)).all()
        ]

        if not (positive_rows or negative_rows or topic_rows):
            return _empty(ctx, variant, "no_signals_in_window")

        tables: list[dict[str, Any]] = []
        if positive_rows:
            tables.append({"name": "top_positive_drivers", "rows": positive_rows})
        if negative_rows:
            tables.append({"name": "top_negative_drivers", "rows": negative_rows})
        if topic_rows:
            tables.append({"name": "top_topics", "rows": topic_rows})

        metrics = {
            "positive_driver_count": len(positive_rows),
            "negative_driver_count": len(negative_rows),
            "topic_count": len(topic_rows),
        }
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_summary(ctx.locale, positive_rows, negative_rows, topic_rows),
            metrics=metrics,
            tables=tables,
            chosen_variant=variant,
        )


def _empty(ctx: ReportContext, variant: str, reason: str) -> SectionData:
    is_zh = ctx.locale.startswith("zh")
    return SectionData(
        section_type="branding_narrative",
        title=_title(ctx.locale),
        summary=(
            "本期暂无情感驱动 / 话题信号(可能采集量较低或品牌新入)。"
            if is_zh
            else (
                "No sentiment driver or topic signal this period "
                "(low collection volume or new brand)."
            )
        ),
        metrics={"empty_reason": reason},
        chosen_variant=variant,
    )


def _title(locale: str) -> str:
    return "Branding 叙事弧" if locale.startswith("zh") else "Branding Narrative"


def _summary(
    locale: str,
    positive: list[dict[str, Any]],
    negative: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> str:
    is_zh = locale.startswith("zh")
    if is_zh:
        parts = []
        if positive:
            top_p = positive[0]
            parts.append(f"正面驱动 Top:'{top_p['driver']}'({top_p['count']} 次)")
        if negative:
            top_n = negative[0]
            parts.append(f"负面驱动 Top:'{top_n['driver']}'({top_n['count']} 次)")
        if topics:
            parts.append(f"主导话题 {len(topics)} 个")
        return ";".join(parts) + "。" if parts else "本期无明显叙事信号。"
    parts = []
    if positive:
        parts.append(f"top positive: '{positive[0]['driver']}' (x{positive[0]['count']})")
    if negative:
        parts.append(f"top negative: '{negative[0]['driver']}' (x{negative[0]['count']})")
    if topics:
        parts.append(f"{len(topics)} dominant topic(s)")
    return "; ".join(parts) + "." if parts else "No notable narrative signal this period."
