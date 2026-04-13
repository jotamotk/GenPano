"""
GEO Score 计算（用户自定义算法）

Overall = clamp(base × (1 + sov_bonus×g + cit_bonus×h), 0, 100)

四维子分数：
- Visibility: 综合可见性 = mention_rate×40% + position×40% + first_place×20%
- Sentiment:  情感分 = raw_sentiment × detail_factor
- SOV:        声量份额 = target_mentions / total_mentions × 100
- Citations:  引用分 = base + source_type 加成
"""
from __future__ import annotations

import math


class GEOScorer:
    """GEO Score 四维算法"""

    # 可通过环境变量覆盖
    BASE_MIN = 20
    BASE_SCALE = 0.65
    SOV_SCALE = 15
    CIT_SCALE = 5
    SOV_BONUS = 0.12
    CIT_BONUS = 0.12

    @classmethod
    def calc_overall(
        cls,
        visibility: float,
        sentiment: float,
        sov: float,
        citations: float,
    ) -> float:
        """
        四维输入 → Overall Score (0~100)

        Args:
            visibility: 综合可见性分 (0~100)
            sentiment:  情感分 (0~100)
            sov:        声量份额 (0~100)
            citations:  引用分 (0~100)
        """
        base_raw = (visibility + sentiment) / 2.0
        base = cls.BASE_MIN + cls.BASE_SCALE * base_raw
        g = 1.0 - math.exp(-sov / cls.SOV_SCALE)
        h = 1.0 - math.exp(-citations / cls.CIT_SCALE)
        score = base * (1.0 + cls.SOV_BONUS * g + cls.CIT_BONUS * h)
        return max(0.0, min(100.0, round(score, 1)))

    @staticmethod
    def calc_visibility(
        is_mentioned: bool,
        position_type: str | None,
        position_rank: int | None,
        mention_rate_pct: float,
    ) -> float:
        """
        综合可见性 (0~100)
        = mention_rate × 40% + position_score × 40% + first_place × 20%
        """
        if not is_mentioned:
            return 0.0

        position_scores = {
            "first_recommendation": 100,
            "comparison_winner": 90,
            "mentioned_only": 30,
            "comparison_loser": 10,
        }
        if position_type == "listed" and position_rank is not None:
            pos_score = max(100 - (position_rank - 1) * 20, 20)
        else:
            pos_score = position_scores.get(position_type or "", 30)

        is_first = 100 if position_type == "first_recommendation" else 0

        return mention_rate_pct * 0.4 + pos_score * 0.4 + is_first * 0.2

    @staticmethod
    def calc_sentiment(
        raw_sentiment_score: float,
        detail_level: str | None,
    ) -> float:
        """
        情感分 (0~100)

        Args:
            raw_sentiment_score: -1.0 ~ 1.0 (火山 NLP 输出)
            detail_level: detailed | brief | passing
        """
        # -1~1 → 0~100
        base = (raw_sentiment_score + 1.0) / 2.0 * 100
        detail_factor = {
            "detailed": 1.0, "brief": 0.7, "passing": 0.4,
        }.get(detail_level or "passing", 0.4)
        return base * (0.7 + 0.3 * detail_factor)

    @staticmethod
    def calc_sov(
        target_mention_count: int,
        total_mention_count: int,
    ) -> float:
        """SOV 声量份额 (0~100)"""
        if total_mention_count == 0:
            return 0.0
        return (target_mention_count / total_mention_count) * 100

    @staticmethod
    def calc_citations(
        citation_count: int,
        has_official: bool,
    ) -> float:
        """引用分 (0~100)"""
        if citation_count == 0:
            return 0.0
        base = min(40 + (citation_count - 1) * 15, 80)
        if has_official:
            base = min(base + 20, 100)
        return float(base)
