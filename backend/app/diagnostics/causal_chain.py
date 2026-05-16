"""Phase D.4 — causal chain stub (deterministic fallback, no LLM call).

Per PRD §4.7, every diagnostic carries a `causal_chain` JSON describing:
  - hypothesizedMechanism: 1-2 sentence explanation of WHY this triggered
  - alternativeHypotheses: 1-3 alternative explanations the user should rule out
  - supportingEvidence: link to row in evidence dict
  - confidenceLevel: 'high' | 'med' | 'low'

Phase D.4 plan calls for an LLM-driven generator (豆包 / DeepSeek) cached
24h per (project_id, rule_id, brand_id, day). This stub provides a
deterministic fallback so the field is never null — the LLM can be
swapped in later by replacing the `build_causal_chain` impl.

Each rule_id has a static template baked in. Rules without a template
fall back to a generic "metric drift detected" pattern.
"""

from __future__ import annotations

from typing import Any

# Per-rule causal chain templates. Each template returns a dict matching
# the schema above. Placeholders {brand}, {value}, {prev_value}, {pct}
# are substituted from the diagnostic's evidence dict.
RULE_TEMPLATES: dict[str, dict[str, Any]] = {
    "visibility_decline_v1": {
        "mechanism": (
            "提及率从 {prev_value} 降至 {value} ({pct}%下滑), 通常源于 "
            "搜索结果中竞品占位 / 内容覆盖度下降 / engine 版本偏移这三类。"
        ),
        "alternatives": [
            "竞品近期发起 PR / 内容投放, 抢占了相同 query 空间",
            "Engine 训练数据更新, 模型对该品牌的 priors 减弱",
            "采集 query 集变化, 触发了 sample bias",
        ],
        "confidence": "med",
    },
    "negative_sentiment_growth_v1": {
        "mechanism": (
            "负面情绪占比上升通常由具体事件驱动 (产品故障 / 公关事件 / "
            "竞品对比文章), 而非渐进性观感变化。"
        ),
        "alternatives": [
            "近期是否有产品质量 / 服务事故被媒体报道",
            "竞品发起的负面对比内容增加",
            "采集语料样本偏向某个负面 topic",
        ],
        "confidence": "med",
    },
    "geo_score_drop_v1": {
        "mechanism": (
            "GEO 总分下滑同时影响 visibility / sentiment / SoV / citation 四维, "
            "建议先看哪一维拖累最严重再单点优化。"
        ),
        "alternatives": [
            "单维度拖累 (mention_rate 主因)",
            "多维度同时下滑 (系统性问题)",
            "竞品反超抢占 share-of-voice",
        ],
        "confidence": "med",
    },
    "sentiment_drop_v1": {
        "mechanism": (
            "平均情感分下滑常见两种成因: 中性话题增加 (品牌曝光稀释) "
            "或负面话题增加 (实际口碑受损)。看 sentiment_drivers 分布判断。"
        ),
        "alternatives": [
            "中性 / 平淡 query 增加, 摊薄了情感分",
            "具体负面事件被多条 query 反复触发",
            "采样 query 类型偏移到对品牌中性的细分领域",
        ],
        "confidence": "med",
    },
    "monitoring_outage_v1": {
        "mechanism": (
            "24h+ 没有新数据流入通常是 engine adapter / 代理池 / cookie "
            "失效, 或者 scheduler 任务错过窗口。"
        ),
        "alternatives": [
            "Engine adapter 报错 (查 engine_health_daily)",
            "代理池被封 (查 proxy_pool/blocked)",
            "Cookie 过期 / 账号池补给延迟",
        ],
        "confidence": "high",
    },
}


_GENERIC_TEMPLATE: dict[str, Any] = {
    "mechanism": (
        "指标 {category} 触发阈值, 建议结合 evidence 字段中的 "
        "before/after 数据 + 时间趋势综合判断。"
    ),
    "alternatives": [
        "竞品行动驱动",
        "采样 / 数据集偏移",
        "engine / pipeline 侧异常",
    ],
    "confidence": "low",
}


def build_causal_chain(
    *, rule_id: str, evidence: dict[str, Any], brand_name: str | None = None
) -> dict[str, Any]:
    """Return a causal_chain dict for a diagnostic.

    `evidence` is the rule's evidence dict (per Diagnostic.evidence). It
    carries snake_case keys (`previous_value`, `current_value`,
    `change_percent`, `affected_queries`) — matching the producer in
    `rules.py`. Templates fill in placeholders from these keys.
    """
    tpl = RULE_TEMPLATES.get(rule_id, _GENERIC_TEMPLATE)
    mechanism = tpl["mechanism"]

    fill = {
        "brand": brand_name or "品牌",
        "value": _fmt_value(_pick(evidence, "current_value", "currentValue")),
        "prev_value": _fmt_value(_pick(evidence, "previous_value", "previousValue")),
        "pct": _fmt_pct(_pick(evidence, "change_percent", "changePercent")),
        "category": evidence.get("metric", "indicator"),
    }
    try:
        mechanism = mechanism.format(**fill)
    except (KeyError, IndexError):
        pass

    supporting = _pick(evidence, "affected_queries", "affectedQueries") or []
    return {
        "hypothesizedMechanism": mechanism,
        "alternativeHypotheses": tpl["alternatives"],
        "supportingEvidence": supporting[:3],
        "confidenceLevel": tpl["confidence"],
        "source": "deterministic_v1",
    }


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _fmt_value(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) >= 1 else f"{v:.4f}"
    return str(v)


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "?"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "?"
