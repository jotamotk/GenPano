"""pano_score section — PANO Score per PRD §4.7.4 (V/S/R/A weighted formula).

Implements [audit #1044 B2-2] + [audit #1044 B2-3, partial]:

    PANO = 0.30 * V + 0.20 * S + 0.25 * R + 0.25 * A

Sub-scores per PRD §4.7.4.1, each in [0, 100]:

    V — Visibility   : 0.5 * mention_rate_100 + 0.3 * sov_100 + 0.2 * first_place_rate_100
    S — Sentiment    : clamp((avg_sentiment + 1) / 2 * 100, 0, 100)
    R — Reputation   : 0.6 * cite_count_norm + 0.4 * unique_domain_norm
    A — Authority    : 0.5 * authoritative_share + 0.5 * unique_authoritative_domains_norm
                       (data-source gap: `authority_confidence` column does not exist
                       yet; proxied via `source_type` IN ('wiki', 'official_%').
                       Tracked for follow-up under §4.7.4.1 data backfill.)

Period delta — `pano_score.delta_total` and per-subdim deltas are computed
against the immediately preceding equal-length window. When prior window
has no data, delta is `None` (PRD §4.7.4.6: "绝不输出 0 误导").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from genpano_models import BrandMention, CitationSource, GeoScoreDaily
from sqlalchemy import and_, func, or_, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData

# Locked product weights — PRD §4.7.4.2; do NOT retune in engineering.
W_V = 0.30
W_S = 0.20
W_R = 0.25
W_A = 0.25

# Reference scales for normalize-to-100 of citation counts and unique
# domains. Industry p95 normalization (PRD §4.7.4.1) is the long-term
# target; until `industry_benchmark_daily` exposes p95 columns we use
# these absolute floors as a stable starting point.
CITE_COUNT_FULL_SCORE = 200  # ≥200 citations in window scores 100 on R
UNIQUE_DOMAIN_FULL_SCORE = 30  # ≥30 unique cited domains scores 100 on R


@dataclass
class _SubScores:
    v: float
    s: float
    r: float
    a: float
    total: float


class PanoScoreSection(BaseSection):
    section_type = "pano_score"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        window_days = (ctx.to_date - ctx.from_date).days + 1
        prior_to = ctx.from_date - timedelta(days=1)
        prior_from = prior_to - timedelta(days=window_days - 1)

        rows: list[dict[str, Any]] = []
        for bid in ctx.brand_ids:
            cur = await _compute_subscores(
                ctx, brand_id=bid, from_date=ctx.from_date, to_date=ctx.to_date
            )
            if cur is None:
                continue
            prev = await _compute_subscores(
                ctx, brand_id=bid, from_date=prior_from, to_date=prior_to
            )
            delta = _delta(cur, prev)
            row = {
                "brand_id": bid,
                "is_primary": bid == ctx.project.primary_brand_id,
                "pano_total": round(cur.total, 2),
                "grade": _grade(cur.total),
                "subdim": {
                    "V": round(cur.v, 2),
                    "S": round(cur.s, 2),
                    "R": round(cur.r, 2),
                    "A": round(cur.a, 2),
                },
                "weights": {"V": W_V, "S": W_S, "R": W_R, "A": W_A},
                "delta": delta,
            }
            rows.append(row)

        rows.sort(key=lambda r: r["pano_total"], reverse=True)
        title = "PANO 评分" if ctx.locale.startswith("zh") else "PANO Score"

        primary = next(
            (r for r in rows if r["is_primary"]),
            rows[0] if rows else None,
        )
        metrics: dict[str, Any] = {
            "weights": {"V": W_V, "S": W_S, "R": W_R, "A": W_A},
            "primary": primary,
        }
        if primary is not None and variant == "full":
            metrics["waterfall"] = _waterfall(primary)

        summary = _build_summary(ctx.locale, primary)
        return SectionData(
            section_type=self.section_type,
            title=title,
            summary=summary,
            metrics=metrics,
            tables=[{"name": "pano_by_brand", "rows": rows}],
            chosen_variant=variant,
        )


async def _compute_subscores(
    ctx: ReportContext, *, brand_id: int, from_date: date, to_date: date
) -> _SubScores | None:
    """Return V/S/R/A and PANO total for one brand over [from_date, to_date].

    Returns None when there is no GeoScoreDaily row in the window — the
    caller treats this as "no data" and skips the brand (or marks delta
    as None for the prior-period case).
    """
    geo_stmt = select(
        func.avg(GeoScoreDaily.mention_rate),
        func.avg(GeoScoreDaily.avg_sov),
        func.avg(GeoScoreDaily.first_place_rate),
        func.avg(GeoScoreDaily.avg_sentiment_score),
        func.count(GeoScoreDaily.id),
    ).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= from_date,
            GeoScoreDaily.date <= to_date,
        )
    )
    geo_row = (await ctx.session.execute(geo_stmt)).one()
    samples = int(geo_row[4] or 0)
    if samples == 0:
        return None

    mention_rate = float(geo_row[0] or 0.0)
    avg_sov = float(geo_row[1] or 0.0)
    first_place_rate = float(geo_row[2] or 0.0)
    avg_sentiment_score = float(geo_row[3] or 0.0)

    v = (
        0.5 * _clamp(mention_rate * 100, 0, 100)
        + 0.3 * _clamp(avg_sov * 100, 0, 100)
        + 0.2 * _clamp(first_place_rate * 100, 0, 100)
    )
    s = _clamp((avg_sentiment_score + 1.0) / 2.0 * 100.0, 0, 100)

    cite_stmt = (
        select(
            func.count(CitationSource.id),
            func.count(func.distinct(CitationSource.domain)),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= from_date,
                CitationSource.created_at <= to_date,
            )
        )
    )
    cite_row = (await ctx.session.execute(cite_stmt)).one()
    cite_count = int(cite_row[0] or 0)
    unique_domains = int(cite_row[1] or 0)
    r = 0.6 * _clamp(cite_count / CITE_COUNT_FULL_SCORE * 100, 0, 100) + 0.4 * _clamp(
        unique_domains / UNIQUE_DOMAIN_FULL_SCORE * 100, 0, 100
    )

    # A: count of authoritative citations / total citations, plus a unique-
    # domain factor. Authoritative = `source_type` starts with 'official'
    # or equals 'wiki'. Proxied stand-in until `authority_confidence` is
    # available on `citation_sources`.
    auth_stmt = (
        select(
            func.count(CitationSource.id),
            func.count(func.distinct(CitationSource.domain)),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= from_date,
                CitationSource.created_at <= to_date,
                or_(
                    CitationSource.source_type.like("official%"),
                    CitationSource.source_type == "wiki",
                ),
            )
        )
    )
    auth_row = (await ctx.session.execute(auth_stmt)).one()
    auth_count = int(auth_row[0] or 0)
    auth_unique = int(auth_row[1] or 0)
    auth_share = (auth_count / cite_count) if cite_count > 0 else 0.0
    a = 0.5 * _clamp(auth_share * 100, 0, 100) + 0.5 * _clamp(
        auth_unique / UNIQUE_DOMAIN_FULL_SCORE * 100, 0, 100
    )

    total = W_V * v + W_S * s + W_R * r + W_A * a
    return _SubScores(v=v, s=s, r=r, a=a, total=total)


def _delta(cur: _SubScores, prev: _SubScores | None) -> dict[str, Any]:
    """Per-subdim delta + weighted contribution. None when prior is empty
    (PRD §4.7.4.6: don't emit 0 — emit null so FE renders '—')."""
    if prev is None:
        return {
            "total": None,
            "V": None,
            "S": None,
            "R": None,
            "A": None,
            "contribution": None,
        }
    dv = cur.v - prev.v
    ds = cur.s - prev.s
    dr = cur.r - prev.r
    da = cur.a - prev.a
    return {
        "total": round(cur.total - prev.total, 2),
        "V": round(dv, 2),
        "S": round(ds, 2),
        "R": round(dr, 2),
        "A": round(da, 2),
        "contribution": {
            "V": round(W_V * dv, 2),
            "S": round(W_S * ds, 2),
            "R": round(W_R * dr, 2),
            "A": round(W_A * da, 2),
        },
    }


def _waterfall(primary: dict[str, Any]) -> dict[str, Any]:
    """PRD §4.7.4.4 waterfall — period total + sub-scores + per-dim
    contribution to delta. Caller only invokes for variant='full'."""
    sub = primary["subdim"]
    delta = primary["delta"]
    return {
        "total": primary["pano_total"],
        "grade": primary["grade"],
        "subscores": [
            {"dim": "V", "score": sub["V"], "weight": W_V, "delta": delta.get("V")},
            {"dim": "S", "score": sub["S"], "weight": W_S, "delta": delta.get("S")},
            {"dim": "R", "score": sub["R"], "weight": W_R, "delta": delta.get("R")},
            {"dim": "A", "score": sub["A"], "weight": W_A, "delta": delta.get("A")},
        ],
        "delta_total": delta.get("total"),
        "contribution": delta.get("contribution"),
    }


def _grade(total: float) -> str:
    """PRD §4.7.4.3 grade mapping."""
    if total >= 90:
        return "S"
    if total >= 80:
        return "A"
    if total >= 70:
        return "B"
    if total >= 60:
        return "C"
    return "D"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _build_summary(locale: str, primary: dict[str, Any] | None) -> str:
    if primary is None:
        return "(no data)"
    total = primary["pano_total"]
    grade = primary["grade"]
    delta_total = primary["delta"]["total"]
    if locale.startswith("zh"):
        base = f"PANO {total} (Grade {grade})"
        if delta_total is None:
            return base + ",环比无对照"
        sign = "+" if delta_total >= 0 else ""
        return base + f",环比 {sign}{delta_total}"
    base = f"PANO {total} (Grade {grade})"
    if delta_total is None:
        return base + ", no prior-period comparison"
    sign = "+" if delta_total >= 0 else ""
    return base + f", WoW {sign}{delta_total}"
