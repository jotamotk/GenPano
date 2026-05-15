"""
Stage 4: 引用映射 — 规则匹配

将 LLMResponse.citations_json 中的 URL 与品牌关联，并分类 source_type。
纯本地计算，成本=0。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.db.models import Brand


@dataclass
class CitationMapping:
    url: str
    domain: str
    title: str
    citation_index: int | None
    source_type: str        # official_site | review_site | news | social | wiki | other
    brand_name: str | None  # Associated brand, if any


# Well-known domains for source type classification
REVIEW_DOMAINS = {
    "什么值得买": "review_site", "smzdm.com": "review_site",
    "太平洋电脑网": "review_site", "pconline.com.cn": "review_site",
    "中关村在线": "review_site", "zol.com.cn": "review_site",
    "汽车之家": "review_site", "autohome.com.cn": "review_site",
    "wirecutter.com": "review_site", "rtings.com": "review_site",
    "tomsguide.com": "review_site", "techradar.com": "review_site",
    "consumer reports": "review_site", "consumerreports.org": "review_site",
}

NEWS_DOMAINS = {
    "36kr.com": "news", "sina.com.cn": "news", "sohu.com": "news",
    "163.com": "news", "qq.com": "news", "thepaper.cn": "news",
    "reuters.com": "news", "bloomberg.com": "news",
    "techcrunch.com": "news", "theverge.com": "news",
}

SOCIAL_DOMAINS = {
    "xiaohongshu.com": "social", "weibo.com": "social",
    "zhihu.com": "social", "douyin.com": "social",
    "bilibili.com": "social", "reddit.com": "social",
    "twitter.com": "social", "x.com": "social",
    "youtube.com": "social",
}

WIKI_DOMAINS = {
    "wikipedia.org": "wiki", "baike.baidu.com": "wiki",
}


class CitationMapper:
    """将引用 URL 映射到品牌 + 分类 source_type"""

    def map_citations(
        self,
        citations_json: list[dict] | None,
        detected_brands: list[DetectedBrand],
        target_brand: Brand,
    ) -> list[CitationMapping]:
        """
        Map citation URLs to brands and classify source types.

        Args:
            citations_json: [{url, title, index}] from LLMResponse
            detected_brands: brands detected in the response
            target_brand: the monitored brand
        """
        if not citations_json:
            return []

        # Build domain → brand mapping from target brand website
        brand_domains: dict[str, str] = {}
        official_domains: set[str] = set()
        if target_brand.website:
            domain = self._extract_domain(target_brand.website)
            if domain:
                brand_domains[domain] = target_brand.name
                official_domains.add(domain)

        # Response-level proximity flag (#948 / #570 attribution gap):
        # if the target brand was detected anywhere in this response,
        # citations that have no more specific brand match should still
        # attribute to the target brand. Without this fallback every
        # third-party reference (review sites, news, wikipedia) in a
        # response that talks about the target brand stayed unattributed,
        # so `citation_sources.mention_id` was NULL for all rows and
        # `attributed_count` rolled up to 0 even when hundreds of
        # citations existed for the project. Mirrors SoV's "response-level
        # context owns the orphan signal" semantics.
        target_lower = (target_brand.name or "").lower()
        target_brand_detected = any(
            (b.brand_id is not None and target_brand.id is not None and b.brand_id == target_brand.id)
            or (b.is_target)
            or (b.brand_name and target_lower and b.brand_name.lower() == target_lower)
            for b in detected_brands
        )

        results: list[CitationMapping] = []

        for citation in citations_json:
            url = citation.get("url", "")
            title = citation.get("title", "")
            index = citation.get("index")

            if not url:
                continue

            domain = self._extract_domain(url)
            source_type = self._classify_source(domain, official_domains)
            brand_name = self._match_brand(
                domain, title, brand_domains, detected_brands,
                target_brand_name=target_brand.name,
                target_brand_detected=target_brand_detected,
            )

            results.append(CitationMapping(
                url=url,
                domain=domain,
                title=title,
                citation_index=index,
                source_type=source_type,
                brand_name=brand_name,
            ))

        return results

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL, stripping www prefix."""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            domain = parsed.hostname or ""
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower()
        except Exception:
            return ""

    @staticmethod
    def _classify_source(domain: str, official_domains: set[str]) -> str:
        """Classify a domain into source type."""
        if domain in official_domains:
            return "official_site"

        # Check against known domain lists
        for known_domain, stype in REVIEW_DOMAINS.items():
            if known_domain in domain:
                return stype
        for known_domain, stype in NEWS_DOMAINS.items():
            if known_domain in domain:
                return stype
        for known_domain, stype in SOCIAL_DOMAINS.items():
            if known_domain in domain:
                return stype
        for known_domain, stype in WIKI_DOMAINS.items():
            if known_domain in domain:
                return stype

        return "other"

    @staticmethod
    def _match_brand(
        domain: str,
        title: str,
        brand_domains: dict[str, str],
        detected_brands: list[DetectedBrand],
        target_brand_name: str = "",
        target_brand_detected: bool = False,
    ) -> str | None:
        """Try to associate a citation with a brand.

        Match priority:
          1. Domain match against target brand's website (highest fidelity).
          2. Title contains a detected brand's name (covers competitor citations
             whose title explicitly names a non-target brand — keeps the
             original behaviour and prevents target_brand-only attribution
             from cannibalising competitor citation share).
          3. Response-level proximity fallback: when the target brand was
             detected in the response (BrandMention exists) and no more
             specific match fired, attribute the orphan citation to the
             target brand. Without this, every third-party reference in a
             target-brand-mentioning response stayed unattributed (see #948
             / #570 attribution gap — 888 citations / 0 attributed for
             bestCoffer).
        """
        # Match by domain
        if domain in brand_domains:
            return brand_domains[domain]

        # Match by title containing brand name
        if title:
            title_lower = title.lower()
            for brand in detected_brands:
                if brand.brand_name.lower() in title_lower:
                    return brand.brand_name

        # Response-level proximity fallback for orphan citations.
        if target_brand_detected and target_brand_name:
            return target_brand_name

        return None
