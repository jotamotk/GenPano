"""Phase D.5 — anchor questions for diagnostics.

Per PRD §4.7, each diagnostic carries a `anchor_questions` JSON keyed by
reader_perspective ('operator' | 'manager' | 'branding'). These are
follow-up prompts that help the reader translate the data into action.

Static templates per (category x reader). Diagnostic specifics (brand,
metric value, change pct) are filled in via .format() with the evidence
dict's data + project context.
"""

from __future__ import annotations

from typing import Any

# Per-(category, reader) template strings. Reader keys: operator (运营者),
# manager (管理者), branding (品牌负责人).
TEMPLATES: dict[str, dict[str, list[str]]] = {
    "visibility_decline": {
        "manager": [
            "{brand} 在 {category} 主题的 SoV 下滑 {pct}%, 是否需要重新分配 PR 预算?",
            "竞品 {top_competitor} 抢占了哪些 query? 是否有针对性反制内容?",
            "本季度品牌曝光预算结构是否要调整?",
        ],
        "branding": [
            "近 30 天 {brand} 的关键叙事是否被竞品稀释?",
            "需要 / 已经投放的核心内容主题是否仍占主导?",
            "是否需要 1 篇里程碑型内容 (案例 / 白皮书) 拉回认知?",
        ],
        "operator": [
            "Engine adapter 是否有 cookie / proxy 异常?",
            "是否需要扩展采集 query 集到新主题?",
            "Top 10 query 的失败率是否上升?",
        ],
    },
    "sentiment_drop": {
        "manager": [
            "近 30 天负面 sentiment 主要话题是哪个?",
            "是否需要单点公关 (产品 / 客服 / 渠道) 介入?",
            "竞品的正面叙事强度是否同步上升?",
        ],
        "branding": [
            "用户对 {brand} 的负面归因主要落在哪个产品维度?",
            "是否需要发起 listening + 主动澄清?",
        ],
        "operator": [
            "Sentiment analyzer 是否需要重训练?",
            "采集语料是否偏向负面 topic?",
        ],
    },
    "negative_sentiment_growth": {
        "manager": [
            "{brand} 负面情绪占比 {pct}%, 是否需要紧急公关?",
            "Top 3 负面 driver 是否集中在某个产品 / 服务?",
        ],
        "branding": [
            "是否需要 24 小时内发出官方澄清?",
            "客服 / 销售对接是否需要话术更新?",
        ],
        "operator": [
            "近期是否有大规模负面 query 涌入?",
            "Sentiment driver 抽样验证是否准确?",
        ],
    },
    "geo_score_drop": {
        "manager": [
            "GEO 总分下滑哪一维拖累最严重?",
            "是否需要重新评估 Q3 投放结构?",
        ],
        "branding": [
            "{brand} 的核心叙事是否仍清晰传达?",
        ],
        "operator": [
            "Pipeline 三个阶段 (采集 / 分析 / 聚合) 哪一步数据缺失?",
        ],
    },
    "monitoring_outage": {
        "manager": [
            "{brand} 已经 24h+ 无新数据, 监控盲区是否需要主动告知客户?",
        ],
        "branding": [],
        "operator": [
            "Engine 是否需要切换到备用 adapter?",
            "代理池是否需要扩容 / 切换?",
            "Scheduler 是否需要手动重跑?",
        ],
    },
}


_GENERIC_QUESTIONS: dict[str, list[str]] = {
    "manager": [
        "{brand} 当前指标变化是否需要管理层介入?",
        "是否需要重新评估当前阶段策略?",
    ],
    "branding": [
        "{brand} 的核心传播信息是否仍被市场理解?",
    ],
    "operator": [
        "数据采集 / 分析 / 聚合三阶段是否有异常?",
    ],
}


def build_anchor_questions(
    *,
    category: str,
    reader_hints: list[str],
    evidence: dict[str, Any],
    brand_name: str | None = None,
    top_competitor: str | None = None,
) -> dict[str, list[str]]:
    """Return anchor_questions dict, only for the readers in `reader_hints`.

    Each value is a list of fill-in question strings.
    """
    by_reader = TEMPLATES.get(category, _GENERIC_QUESTIONS)
    fill = {
        "brand": brand_name or "品牌",
        "category": category,
        "pct": _fmt_pct(evidence.get("changePercent")),
        "top_competitor": top_competitor or "竞品",
    }
    out: dict[str, list[str]] = {}
    for reader in reader_hints:
        templates = by_reader.get(reader, [])
        out[reader] = [_safe_format(t, fill) for t in templates]
    return out


def _safe_format(template: str, fill: dict[str, Any]) -> str:
    try:
        return template.format(**fill)
    except (KeyError, IndexError):
        return template


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "?"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "?"
