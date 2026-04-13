"""
Stage 1: 品牌预检测 — 规则匹配 + 别名表

本地计算，成本=0。作为大模型分析的"参考输入"而非最终结果。
局限性由 Stage 3 LLM 弥补（验证误匹配、补全遗漏）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from geo_tracker.db.models import Brand, Competitor


@dataclass
class DetectedBrand:
    brand_name: str
    brand_id: int | None = None
    is_target: bool = False
    mention_count: int = 0
    context_snippets: list[str] = field(default_factory=list)


class BrandDetector:
    """基于已知品牌/竞品列表 + 别名表的规则预检测"""

    SNIPPET_RADIUS = 80  # 品牌前后各取 80 字符作为上下文

    def detect(
        self,
        response_text: str,
        target_brand: Brand,
        competitors: list[Competitor],
    ) -> list[DetectedBrand]:
        """
        1. 构建匹配词典（名称 + aliases）
        2. 大小写不敏感匹配
        3. 提取 context_snippet
        4. 返回预检测结果
        """
        if not response_text:
            return []

        # Build search terms: {lowercase_term: (canonical_name, brand_id, is_target)}
        search_map: dict[str, tuple[str, int | None, bool]] = {}

        # Target brand
        self._add_brand_terms(
            search_map, target_brand.name, target_brand.id, is_target=True,
            aliases=target_brand.aliases,
        )

        # Competitors
        for comp in competitors:
            self._add_brand_terms(
                search_map, comp.name, None, is_target=False,
                aliases=comp.aliases,
            )

        # Match against response text
        text_lower = response_text.lower()
        results: dict[str, DetectedBrand] = {}

        for term, (canonical, brand_id, is_target) in search_map.items():
            for match in self._find_all(text_lower, term):
                start, end = match
                # Extract context snippet from original text
                snippet_start = max(0, start - self.SNIPPET_RADIUS)
                snippet_end = min(len(response_text), end + self.SNIPPET_RADIUS)
                snippet = response_text[snippet_start:snippet_end]

                if canonical not in results:
                    results[canonical] = DetectedBrand(
                        brand_name=canonical,
                        brand_id=brand_id,
                        is_target=is_target,
                    )
                results[canonical].mention_count += 1
                # Keep up to 3 snippets
                if len(results[canonical].context_snippets) < 3:
                    results[canonical].context_snippets.append(snippet)

        return list(results.values())

    @staticmethod
    def _add_brand_terms(
        search_map: dict,
        name: str,
        brand_id: int | None,
        is_target: bool,
        aliases: list[str] | None = None,
    ) -> None:
        """Add a brand name and its aliases to the search map."""
        canonical = name
        terms = [name]
        if aliases:
            terms.extend(aliases)
        for t in terms:
            lower = t.strip().lower()
            if lower and lower not in search_map:
                search_map[lower] = (canonical, brand_id, is_target)

    @staticmethod
    def _find_all(text_lower: str, term: str) -> list[tuple[int, int]]:
        """
        Find all occurrences of term in text (case-insensitive, already lowered).
        Uses word-boundary for Latin terms, plain search for CJK.
        """
        if not term:
            return []

        is_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in term)

        if is_cjk:
            # Plain substring search for Chinese
            positions = []
            start = 0
            while True:
                idx = text_lower.find(term, start)
                if idx == -1:
                    break
                positions.append((idx, idx + len(term)))
                start = idx + 1
            return positions
        else:
            # Word-boundary regex for Latin text
            pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
            return [(m.start(), m.end()) for m in pattern.finditer(text_lower)]
