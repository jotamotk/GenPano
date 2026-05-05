/**
 * IndustryRankingPage — /industry/ranking (PRD §4.6.1f v3, 2026-04-20)
 * ────────────────────────────────────────────────────────────────────
 * 行业多口径排行 8-段式 (从 Overview v3 迁入 Top Citation Domains 段):
 *   ① Sticky Filter Bar (复用 BrandAnalysisFilterBar)
 *   ② Ranking Hero (Top 3 / Top 10 / 总排名数 + 我的位置卡)
 *   ③ Tier Breakdown (Top 3 / 4-10 / 11-25 / 26+, 高度 ∝ totalSov)
 *   ④ Multi-Metric Matrix (Top 15 × PANO/SoV/引用/情感/提及 5 口径 + σ dispersion)
 *   ⑤ Ranking Movers Grid (30d gainers / losers 2-col + sparkline + 主驱动)
 *   ⑥ Engine Ranking Matrix (Top 10 × 3 引擎 heatmap + ΔMax warning)
 *   ⑦ Top 10 引用源 (从 Overview v2 段⑧ 迁入 — 权威域在"谁能赢"里是关键)
 *   ⑧ Segment Ranking (国际高端 / 大众高端 / 小众-新锐 3 列 Top 5)
 *
 * 字段契约 (§4.6.1f.D 硬约束):
 *   - 禁 b.primaryName (→ b.name) / b.isPrimary (→ b.id === primaryBrandId)
 *   - 禁 b.categoryName (行业排行不分品类)
 *   - 禁 Math.round(v * 100) on sov / citationShare (已是 0-100 整数)
 *   - mentionRate 0-1 小数, UI (×100).toFixed(1)% 渲染
 */
import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProject } from '../../contexts/ProjectContext';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';

import IndustryRankingHero from '../../components/industry/IndustryRankingHero';
import IndustrySubpageLiveBanner from '../../components/industry/IndustrySubpageLiveBanner';
import IndustryTierBreakdown from '../../components/industry/IndustryTierBreakdown';
import IndustryMultiMetricMatrix from '../../components/industry/IndustryMultiMetricMatrix';
import IndustryRankingMoversGrid from '../../components/industry/IndustryRankingMoversGrid';
import IndustryEngineRankingMatrix from '../../components/industry/IndustryEngineRankingMatrix';
import IndustryTopCitationDomains from '../../components/industry/IndustryTopCitationDomains';
import IndustrySegmentRanking from '../../components/industry/IndustrySegmentRanking';

import { INDUSTRIES, BRANDS, TOP_CITED_DOMAINS } from '../../data/mock';

export default function IndustryRankingPage() {
  const [searchParams] = useSearchParams();
  const { activeProject } = useProject();
  // 占位: FilterBar 是 URL-driven 单一真相源, 组件读 filters 未来扩筛选下钻用
  const { filters } = useBrandAnalysisFilters();
  void filters;

  /* Resolve industry: ?industryId= → activeProject.industryId → 'beauty' */
  const industryId =
    searchParams.get('industryId') || activeProject?.industryId || 'beauty';
  const industry = useMemo(
    () => INDUSTRIES.find((i) => i.id === industryId) || INDUSTRIES[0],
    [industryId]
  );

  /* Brands scoped to industry */
  const industryBrands = useMemo(() => {
    const filtered = BRANDS.filter((b) => b.industryId === industry.id);
    return filtered.length ? filtered : BRANDS;
  }, [industry.id]);

  const primaryBrand = useMemo(
    () =>
      activeProject?.primaryBrandId
        ? industryBrands.find((b) => b.id === activeProject.primaryBrandId) ||
          BRANDS.find((b) => b.id === activeProject.primaryBrandId) ||
          null
        : null,
    [activeProject?.primaryBrandId, industryBrands]
  );

  const liveIndustryId = /^\d+$/.test(String(industryId)) ? Number(industryId) : null;

  return (
    <div className="space-y-3">
      <IndustrySubpageLiveBanner variant="ranking" industryId={liveIndustryId} />
      {/* ── 段 ② Hero (page banner, 置顶且 border-b 与 FilterBar 分隔) ── */}
      <IndustryRankingHero
        industryName={`${industry.icon || ''} ${industry.name} 排行榜`.trim()}
        brands={industryBrands}
        primaryBrand={primaryBrand}
      />

      {/* ── 段 ① Filter bar (sticky, 复用 Brand Mode FilterBar) ── */}
      <BrandAnalysisFilterBar />

      {/* ── 段 ③ Tier Breakdown ── */}
      <IndustryTierBreakdown
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
      />

      {/* ── 段 ④ Multi-Metric Matrix (Top 15 × 5 口径 + σ) ── */}
      <IndustryMultiMetricMatrix
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
        limit={15}
      />

      {/* ── 段 ⑤ 30d Movers grid (gainers / losers) ── */}
      <IndustryRankingMoversGrid
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
      />

      {/* ── 段 ⑥ Engine Ranking Matrix (Top 10 × 3 引擎) ── */}
      <IndustryEngineRankingMatrix
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
        limit={10}
      />

      {/* ── 段 ⑦ Top 10 引用源 (从 Overview v2 段⑧ 迁入) ── */}
      <IndustryTopCitationDomains
        domains={TOP_CITED_DOMAINS}
        primaryBrandId={primaryBrand?.id || null}
        limit={10}
      />

      {/* ── 段 ⑧ Segment Ranking (3 赛道 × Top 5) ── */}
      <IndustrySegmentRanking
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
        limit={5}
      />
    </div>
  );
}
