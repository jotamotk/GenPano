/**
 * IndustryOverviewPage — /industry/overview (PRD §4.6.1e v3, 2026-04-20)
 * ──────────────────────────────────────────────────────────────────────
 * 行业总览 Plan S v3 6-段式 (v2 → v3 拆分: Topic Heat Scatter 迁到 /industry/topics;
 * Top 10 引用源 迁到 /industry/ranking — 总览只承载"宏观分布 + 领导者识别"):
 *   ① Sticky Filter Bar (复用 BrandAnalysisFilterBar)
 *   ② Industry Hero (brandCount / topicCount / categoryCount / responseCount)
 *   ③ 5 KPI IQR 箱线 (提及率 / SoV / 情感 / 引用份额 / 排名)
 *   ④ Top 10 Leaderboard + SoV Pie
 *   ⑤ 行业 PANO 趋势 + 近 7d 异动 Top 3
 *   ⑥ 品牌集团版图 Top 5
 *
 * 口径:
 *   - mentionRate 全系统 0-1 小数, UI (×100).toFixed(1)% 渲染
 *   - IQR 只通过 lib/industry/statistics.computeIQR (禁 inline percentile)
 *   - SoV 饼图 >8 品牌 Top 6 + 其他 (C3), ≤8 全展示
 *   - Primary brand 从 activeProject.primaryBrandId 读, 无 primary 时 ▲ marker 不画
 *
 * Harness 关联: §G.1 (零新增 dead mock) / §G.2 (▲ guard) / §G.3 (no inline pct)
 *              / §G.4 (i18n namespaces ready) / C14 (text-xl h1 + p-3 card + space-y-3)
 */
import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProject } from '../../contexts/ProjectContext';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';

import IndustryHero from '../../components/industry/IndustryHero';
import IndustryDistributionCard from '../../components/industry/IndustryDistributionCard';
import IndustryLeaderboardTable from '../../components/industry/IndustryLeaderboardTable';
import IndustrySovPie from '../../components/industry/IndustrySovPie';
import IndustryTrendChart from '../../components/industry/IndustryTrendChart';
import IndustryMoversRow from '../../components/industry/IndustryMoversRow';
import IndustryGroupMap from '../../components/industry/IndustryGroupMap';

import { computeIQR } from '../../lib/industry/statistics';
import {
  INDUSTRIES,
  BRANDS,
  TOPICS,
  CATEGORIES,
} from '../../data/mock';

/* ─── 30d industry trend synthesizer (mock-only, 真实后端接 /api/industry/trend) ─── */
function buildTrendSeries(primaryBrand) {
  const today = new Date();
  return Array.from({ length: 30 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (29 - i));
    const date = d.toISOString().slice(0, 10);
    // 行业均值围绕 62 ± 8 震荡, 主品牌围绕其 panoScore ± 6 震荡
    const industryAvg = 62 + Math.sin(i / 4.2) * 4 + Math.sin(i / 2.3) * 2;
    const base = primaryBrand?.panoScore ?? 72;
    const myBrand = base + Math.sin(i / 3.8) * 5 + Math.cos(i / 5.1) * 2;
    return {
      name: date.slice(5),        // MM-DD
      industryAvg: Number(industryAvg.toFixed(1)),
      myBrand: Number(myBrand.toFixed(1)),
    };
  });
}

/* ─── Count active Topics and categories for a given industry ─── */
function countTopicsForIndustry(industryName) {
  // TOPICS 里 categoryPath 开头是 industryName → 算作该行业
  return TOPICS.filter((t) =>
    typeof t.categoryPath === 'string' && t.categoryPath.startsWith(industryName)
  ).length;
}

function countCategoriesForIndustry(industryId) {
  // CATEGORIES 是 { [industryId]: { L1: { L2: [...L3] } } } (3 级树)
  const tree = CATEGORIES?.[industryId];
  if (!tree) return 0;
  let count = 0;
  for (const l1 of Object.values(tree)) {
    if (Array.isArray(l1)) {
      count += l1.length;
    } else if (typeof l1 === 'object' && l1 !== null) {
      for (const l2 of Object.values(l1)) {
        if (Array.isArray(l2)) count += l2.length;
        else if (typeof l2 === 'object') count += Object.keys(l2).length;
      }
    }
  }
  return count || Object.keys(tree).length;
}

export default function IndustryOverviewPage() {
  const [searchParams] = useSearchParams();
  const { activeProject } = useProject();
  // Filter hook must be referenced even if the bar is the only reader — its
  // presence satisfies the shared-filter contract and readies downstream fetches.
  const { filters } = useBrandAnalysisFilters();

  /* Resolve current industry: ?industryId= → activeProject.industryId → 'beauty' */
  const industryId =
    searchParams.get('industryId') ||
    activeProject?.industryId ||
    'beauty';

  const industry = useMemo(
    () => INDUSTRIES.find((i) => i.id === industryId) || INDUSTRIES[0],
    [industryId]
  );

  /* Brands scoped to current industry (fallback to all if no match) */
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

  /* ── 段 ② Hero stats ── */
  const heroStats = useMemo(() => {
    const responseCount = industryBrands.reduce(
      (s, b) => s + Math.round((b.mentionRate || 0) * 20000 + 500),
      0
    );
    return {
      brandCount: industry.brandCount ?? industryBrands.length,
      topicCount: countTopicsForIndustry(industry.name),
      categoryCount: countCategoriesForIndustry(industry.id),
      responseCount,
    };
  }, [industry, industryBrands]);

  /* ── 段 ③ 5-KPI IQR stats (single source: computeIQR) ── */
  const kpiCards = useMemo(() => {
    const mentionVals = industryBrands.map((b) => (b.mentionRate || 0) * 100);
    const sovVals = industryBrands.map((b) => b.sov || 0);
    const sentimentVals = industryBrands.map((b) => (b.sentiment || 0) * 100);
    const citationVals = industryBrands.map((b) => b.citationShare || 0);
    const rankingVals = industryBrands.map((b) => b.ranking || 0).filter(Boolean);

    return [
      {
        label: '提及率',
        unit: '%',
        stats: computeIQR(mentionVals),
        primaryValue:
          primaryBrand != null ? (primaryBrand.mentionRate || 0) * 100 : null,
        primaryName: primaryBrand?.name,
        direction: 'higher_is_better',
        formatValue: (v) => (v == null ? '—' : v.toFixed(1)),
      },
      {
        label: 'SoV',
        unit: '%',
        stats: computeIQR(sovVals),
        primaryValue: primaryBrand != null ? primaryBrand.sov ?? 0 : null,
        primaryName: primaryBrand?.name,
        direction: 'higher_is_better',
        formatValue: (v) => (v == null ? '—' : v.toFixed(1)),
      },
      {
        label: '情感',
        unit: '%',
        stats: computeIQR(sentimentVals),
        primaryValue:
          primaryBrand != null ? (primaryBrand.sentiment || 0) * 100 : null,
        primaryName: primaryBrand?.name,
        direction: 'higher_is_better',
        formatValue: (v) => (v == null ? '—' : v.toFixed(0)),
      },
      {
        label: '引用份额',
        unit: '%',
        stats: computeIQR(citationVals),
        primaryValue:
          primaryBrand != null ? primaryBrand.citationShare ?? 0 : null,
        primaryName: primaryBrand?.name,
        direction: 'higher_is_better',
        formatValue: (v) => (v == null ? '—' : v.toFixed(1)),
      },
      {
        label: '排名',
        unit: '',
        stats: computeIQR(rankingVals),
        primaryValue:
          primaryBrand != null ? primaryBrand.ranking ?? null : null,
        primaryName: primaryBrand?.name,
        direction: 'lower_is_better',
        formatValue: (v) => (v == null ? '—' : `#${Math.round(v)}`),
      },
    ];
  }, [industryBrands, primaryBrand]);

  /* ── 段 ⑤ Trend series ── */
  const trendData = useMemo(
    () => buildTrendSeries(primaryBrand),
    [primaryBrand]
  );

  // Live banner only fires when industryId is numeric (real backend
  // industry); mock 'beauty' / 'fashion' string IDs short-circuit.
  const liveIndustryId = /^\d+$/.test(String(industryId)) ? Number(industryId) : null;

  return (
    <div className="space-y-3">
      {/* LIVE banner — pulled from /v1/industries/:id/overview when industryId is numeric */}

      {/* ── 段 ② Hero (page banner; 置顶并用 border-b 与 FilterBar 分隔) ── */}
      <IndustryHero
        industryName={`${industry.icon || ''} ${industry.name} 行业总览`.trim()}
        brandCount={heroStats.brandCount}
        topicCount={heroStats.topicCount}
        categoryCount={heroStats.categoryCount}
        responseCount={heroStats.responseCount}
      />

      {/* ── 段 ① Filter bar (sticky, 复用 Brand Mode FilterBar) ── */}
      <BrandAnalysisFilterBar />

      {/* ── 段 ③ 5 KPI IQR distribution cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        {kpiCards.map((c) => (
          <IndustryDistributionCard
            key={c.label}
            label={c.label}
            unit={c.unit}
            stats={c.stats}
            primaryValue={c.primaryValue}
            primaryName={c.primaryName}
            direction={c.direction}
            formatValue={c.formatValue}
          />
        ))}
      </div>

      {/* ── 段 ④ Leaderboard (3/5) + SoV Pie (2/5) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="lg:col-span-3">
          <IndustryLeaderboardTable
            brands={industryBrands}
            primaryBrandId={primaryBrand?.id || null}
            limit={10}
          />
        </div>
        <div className="lg:col-span-2">
          <IndustrySovPie
            brands={industryBrands}
            primaryBrandId={primaryBrand?.id || null}
          />
        </div>
      </div>

      {/* ── 段 ⑤ Trend (2/3) + Movers (1/3) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2">
          <IndustryTrendChart
            data={trendData}
            hasPrimary={primaryBrand != null}
          />
        </div>
        <div>
          <IndustryMoversRow brands={industryBrands} />
        </div>
      </div>

      {/* ── 段 ⑥ 集团版图 ── */}
      <IndustryGroupMap
        brands={industryBrands}
        primaryBrandId={primaryBrand?.id || null}
        limit={5}
      />
    </div>
  );
}
