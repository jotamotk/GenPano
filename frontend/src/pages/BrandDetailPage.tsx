import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  useNavigate, useParams, useSearchParams, useLocation,
} from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { Badge, Button, Card } from '../components/ui';
import { DiagnosticCard, LeadFormModal } from '../components/diagnostics';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import WatchBrandButton from '../components/brand/WatchBrandButton';
import ProfileGroupFilter, { ProfileGroupSampleWarning } from '../components/filters/ProfileGroupFilter';
import ProjectRequiredBanner from '../components/ProjectRequiredBanner';
import AuthorityShareTimeSeries from '../components/citation/AuthorityShareTimeSeries';
import ContentGapPanel from '../components/citation/ContentGapPanel';
import PrTargetsPanel from '../components/citation/PrTargetsPanel';
import AuthorityRadarChart from '../components/citation/AuthorityRadarChart';
import SameGroupAndAcquisition from '../components/citation/SameGroupAndAcquisition';
import BrandPanoramaPanel from '../components/dashboard/BrandPanoramaPanel';
import BrandDetailLiveBanner from '../components/brand/BrandDetailLiveBanner';
import {
  BRANDS, PRODUCTS, DIAGNOSTICS,
  SENTIMENT_DISTRIBUTION,
  ENGINES,
  AUTHORITY_SHARE_SERIES,
  ATTRIBUTION_MISMATCH_DIAGNOSTIC,
  CONTENT_GAP_TOPICS,
  CONTENT_GAP_PAGE_TYPE_DISTRIBUTION,
  PR_TARGETS,
  TIER2_COVERAGE_MATRIX,
  KOL_SCORECARDS,
  AUTHORITY_RADAR_DATA,
  SAME_GROUP_SHARED,
  ACQUISITION_EVENTS,
} from '../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandDetailPage — PRD §4.6.1b 单品牌深度视角
   ─────────────────────────────────────────────────────────────
   ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
     本页职责: 单品牌纵深 (Pano + 诊断 + 产品 + 引擎对比). 跨品牌
     SoV / 竞品四象限 / 跨品牌 PANO 趋势属于 /dashboard. 这段说明
     仅给 Claude Code/人类读者; 不得以 i18n key / JSX 文本节点形式
     呈现给最终用户.

   URL: /brands/:id?tab=overview|diagnostics|products|engines
        &range=30d&engines=chatgpt,doubao&profileGroup=<id>

   顶栏: ← 返回面板 / 品牌切换器 / 画像筛选 / 分享 PDF
   子 Tab (5):
     概览       - BrandPanoramaPanel 单品牌全景 (Hero/5 KPI/SoV+四象限/趋势/告警)
                  ⚠️ 2026-04-19 重构: 概览 Tab 复用 /dashboard 的 BrandPanoramaPanel,
                  与市场宏观视角一致; 原 V/S/R/A + Mention Top20 结构已弃用.
     诊断       - 该品牌 Diagnostics (P0/P1/P2), 下载 PDF
     产品       - BCG 矩阵 + 产品列表 (brand.id === this.id)
     引擎对比   - 3 引擎并排卡片

   ProfileGroupFilter 仅在 overview / diagnostics / engines 三 Tab
   显示, 产品 Tab 不接入 (PRD §4.6.1b — 产品级样本稀疏).

   样式: 颜色全部走 var(--color-*) / .text-themed-*.
*/

const TAB_IDS = ['overview', 'diagnostics', 'content-gap', 'products', 'engines'];

/* ─────────────────────────────────────────────────────────────
   Top Bar — 返回 / 品牌切换 / 一键监控 / 时间-引擎 / PDF
   PRD §4.1.1b + §4.1.2a + §4.6.1b
   - 面包屑由 ?from= 决定 (industry/dashboard/brands/product)
   - 品牌切换器仅在"已监控/主品牌"上下文 (state A) 显示, 避免向陌生
     游客/未监控用户暴露竞品池
   - <WatchBrandButton> 始终显示, 由 6 状态机自管显示形式
─────────────────────────────────────────────────────────────── */
function BrandTopBar({
  brand, brandOptions, primaryId, onSwitchBrand, onSharePdf,
  showProfileFilter, showBrandSwitcher, breadcrumbKey, breadcrumbHref,
  t,
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div className="flex flex-wrap items-center gap-3 justify-between">
      <div className="flex items-center gap-3 flex-wrap">
        <button
          className="text-sm text-themed-muted hover:text-themed-primary transition-colors"
          onClick={() => navigate(breadcrumbHref || '/dashboard')}
        >
          ← {t(breadcrumbKey || 'brand_watch.breadcrumb.from_dashboard')}
        </button>
        <div className="h-4 w-px bg-themed-card" />

        {/* Brand switcher — only when user has a project context (state A) */}
        {showBrandSwitcher ? (
          <div className="relative" ref={ref}>
            <button
              onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-pill text-sm font-medium transition-colors"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
              }}
            >
              <span className="text-themed-primary">{brand.name}</span>
              <span className="text-[11px] text-themed-muted">{brand.nameEn}</span>
              {brand.id === primaryId && (
                <Badge variant="accent" size="sm">{t('brand.detail.primary_label')}</Badge>
              )}
              <span className="text-themed-muted">▾</span>
            </button>
            {open && (
              <div
                className="absolute left-0 top-full mt-1 w-64 z-20 rounded-card overflow-hidden"
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  boxShadow: 'var(--shadow-card-hover)',
                }}
              >
                {brandOptions.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => { setOpen(false); onSwitchBrand(b.id); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-themed-subtle ${
                      b.id === brand.id ? 'text-themed-accent' : 'text-themed-primary'
                    }`}
                  >
                    <span className="flex-1 truncate">{b.name}</span>
                    <span className="text-[11px] text-themed-muted">{b.nameEn}</span>
                    {b.id === primaryId && (
                      <Badge variant="accent" size="sm">
                        {t('brand.detail.primary_label')}
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          // Static brand label — no switcher when not in project context
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-pill text-sm font-medium"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
            }}
          >
            <span className="text-themed-primary">{brand.name}</span>
            <span className="text-[11px] text-themed-muted">{brand.nameEn}</span>
          </div>
        )}

        {/* PRD §4.1.2a — 一键加入竞品监控按钮 (6 状态机) */}
        <WatchBrandButton brand={brand} showCrossIndustryHint={false} />
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {/* Profile Group filter — hidden on Products Tab per PRD §4.6.1b */}
        {showProfileFilter && <ProfileGroupFilter />}
        <Button variant="secondary" size="sm" onClick={onSharePdf}>
          {t('brand.detail.share_pdf')}
        </Button>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Banner — PRD §4.6.1b 三状态
   - state A (watching/primary): 不渲染 banner
   - state B (logged-in, not watching): 浅灰色提示条 + upsell link
   - state C (anonymous): 浅蓝色 + register CTA
─────────────────────────────────────────────────────────────── */
function BrandStateBanner({ state, brand, t, formatBrand }) {
  if (!state || state.kind === 'primary' || state.kind === 'watching') return null;
  const brandName = formatBrand(brand);

  if (state.kind === 'anonymous') {
    return (
      <div
        className="rounded-card p-4 flex items-start gap-3"
        style={{
          background: 'var(--color-info-subtle, var(--color-accent-bg-light))',
          border: '1px solid var(--color-info, var(--color-accent-alpha-30))',
        }}
      >
        <span
          className="w-1.5 self-stretch rounded-full flex-shrink-0"
          style={{ background: 'var(--color-info, var(--color-accent))' }}
        />
        <div className="flex-1">
          <div className="text-sm font-semibold text-themed-primary">
            {t('brand_watch.banner.anonymous_title')}
          </div>
          <div className="text-xs text-themed-secondary mt-1 leading-relaxed">
            {t('brand_watch.banner.anonymous_body')}
          </div>
        </div>
        <WatchBrandButton brand={brand} showCrossIndustryHint={false} />
      </div>
    );
  }

  // state B (no_project / not_watching_*) — light gray
  return (
    <div
      className="rounded-card p-4 flex items-start gap-3"
      style={{
        background: 'var(--color-bg-subtle-2)',
        border: '1px solid var(--color-border-subtle)',
      }}
    >
      <span
        className="w-1.5 self-stretch rounded-full flex-shrink-0"
        style={{ background: 'var(--color-text-muted)' }}
      />
      <div className="flex-1">
        <div className="text-sm font-semibold text-themed-primary">
          {t('brand_watch.banner.not_watching_title', { brand: brandName })}
        </div>
        <div className="text-xs text-themed-secondary mt-1 leading-relaxed">
          {t('brand_watch.banner.not_watching_body')}
        </div>
      </div>
      <WatchBrandButton brand={brand} showCrossIndustryHint={false} />
    </div>
  );
}

/* Sticky bottom CTA only for state C (anonymous) */
function AnonymousStickyCta({ state, brand, t, formatBrand, onCta }) {
  if (!state || state.kind !== 'anonymous') return null;
  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-[900] px-4 py-3 flex justify-center"
      style={{
        background: 'var(--color-bg-card)',
        borderTop: '1px solid var(--color-border-subtle)',
        boxShadow: '0 -4px 12px rgba(0,0,0,0.06)',
      }}
    >
      <div className="flex items-center gap-3 max-w-3xl w-full justify-between">
        <span className="text-sm text-themed-secondary">
          {t('brand_watch.banner.sticky_cta', { brand: formatBrand(brand) })}
        </span>
        <button
          onClick={onCta}
          className="px-4 py-2 rounded-pill text-sm font-medium"
          style={{
            background: 'var(--color-accent)',
            color: 'var(--color-on-accent, #fff)',
          }}
        >
          {t('brand_watch.banner.anonymous_cta')}
        </button>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Tab: 概览 — 2026-04-19 重构
   复用 BrandPanoramaPanel (与 /dashboard 完全同款单品牌全景视图)
   包含: Hero / 5 KPI / SoV 饼图 + 竞品四象限 / PANO 趋势 + KPI sparkline / 告警条
─────────────────────────────────────────────────────────────── */
function OverviewTab({ brand }) {
  return (
    <BrandPanoramaPanel
      primary={brand}
      scrollAnchorId={`brand-${brand.id}-competition`}
    />
  );
}

/* ─────────────────────────────────────────────────────────────
   Tab: 诊断 (该品牌 Diagnostics)
   PRD §4.7.0-a / §4.8.2 / §4.8.6
   - 使用统一 <DiagnosticCard /> 渲染洞察 Stack
   - 严禁渲染 optimizationSteps 或任何剧本式建议
─────────────────────────────────────────────────────────────── */
function DiagnosticsTab({ brand, t, onDownloadPdf, highlightId, showUpsellStrip }) {
  const [expandedId, setExpandedId] = useState(highlightId || null);
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadDiagId, setLeadDiagId] = useState(null);

  // 优先按 brandId 精确匹配; 为 mock 数据兼容, 也保留品牌名称 fallback.
  // PRD §4.2.7.A — citation_attribution_mismatch 诊断 (P2) 按 brandId 合流到诊断列表.
  const brandDiags = useMemo(() => {
    const keywords = [brand.name, brand.nameEn].filter(Boolean);
    const base = DIAGNOSTICS.filter((d) => {
      if (d.type === 'industry') return false;
      if (d.brandId && d.brandId === brand.id) return true;
      return keywords.some(
        (k) =>
          d.title?.includes(k) ||
          d.description?.includes(k) ||
          d.industryBenchmark?.topCompetitor?.brandName?.includes(k)
      );
    });
    const extras = [];
    if (ATTRIBUTION_MISMATCH_DIAGNOSTIC?.brandId === brand.id) {
      extras.push(ATTRIBUTION_MISMATCH_DIAGNOSTIC);
    }
    return [...base, ...extras];
  }, [brand.id, brand.name, brand.nameEn]);

  const groups = useMemo(() => {
    const g = { P0: [], P1: [], P2: [], P3: [] };
    brandDiags.forEach((d) => {
      if (g[d.severity]) g[d.severity].push(d);
    });
    return g;
  }, [brandDiags]);

  const openLeadForm = (diagId) => {
    setLeadDiagId(diagId);
    setShowLeadForm(true);
  };

  const leadDiag = leadDiagId ? DIAGNOSTICS.find((d) => d.id === leadDiagId) : null;

  const renderGroup = (sev) => {
    const arr = groups[sev];
    if (!arr || arr.length === 0) return null;
    const heading =
      sev === 'P0'
        ? t('brand.detail.diagnostics.group_p0', { count: arr.length })
        : sev === 'P1'
        ? t('brand.detail.diagnostics.group_p1', { count: arr.length })
        : sev === 'P2'
        ? t('brand.detail.diagnostics.group_p2', { count: arr.length })
        : `P3 信息 (${arr.length})`;

    return (
      <div key={sev} className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-themed-muted">
          {heading}
        </h4>
        <div className="space-y-2">
          {arr.map((d) => (
            <DiagnosticCard
              key={d.id}
              diag={d}
              expanded={expandedId === d.id}
              onToggle={() => setExpandedId(expandedId === d.id ? null : d.id)}
              onContactConsultant={openLeadForm}
            />
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('brand.detail.diagnostics.title')}
          </h3>
          <p className="text-xs text-themed-muted mt-1">
            {t('brand.detail.diagnostics.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <WatchBrandButton brand={brand} showCrossIndustryHint={false} />
          <Button variant="primary" size="sm" onClick={onDownloadPdf}>
            {t('brand.detail.diagnostics.download_pdf')}
          </Button>
        </div>
      </div>

      {/* PRD §4.6.1b — state B (logged-in not watching) 黄色 upsell 条
          诊断完整可见, 不做 paywall, 仅说明加入监控会获得"持续追踪 + 周报 + Branding Narrative" */}
      {showUpsellStrip && (
        <div
          className="rounded-card p-3 flex items-center gap-3"
          style={{
            background: 'var(--color-warning-subtle, #fef9c3)',
            border: '1px solid var(--color-warning, #facc15)',
          }}
        >
          <span className="text-base">⚡</span>
          <span className="text-xs text-themed-secondary leading-relaxed flex-1">
            {t('brand_watch.banner.diagnostics_upsell')}
          </span>
        </div>
      )}

      {brandDiags.length === 0 ? (
        <Card className="p-8 text-center text-sm text-themed-muted">
          {t('brand.detail.diagnostics.no_data')}
        </Card>
      ) : (
        <div className="space-y-5">
          {renderGroup('P0')}
          {renderGroup('P1')}
          {renderGroup('P2')}
          {renderGroup('P3')}
        </div>
      )}

      <LeadFormModal
        open={showLeadForm}
        onClose={() => setShowLeadForm(false)}
        diagnostic={leadDiag}
        defaultBrand={brand.name || brand.nameEn || ''}
        defaultEmail="frankwangfj@gmail.com"
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Tab: 内容缺口 (Content Gap) — PRD §4.2.7.B + §4.2.7.A 时序 + §4.2.7.C PR
   ─────────────────────────────────────────────────────────────
   - 顶部: 归因方法时序堆叠图 (AuthorityShareTimeSeries)
   - 中部: Top N 缺口 Topic + 页面类型分布对比 (ContentGapPanel)
   - 底部: PR 候选 + Tier2 矩阵 + KOL 评分卡 (PrTargetsPanel)

   为什么这三块放一起: 从"发现缺口"→"定位缺口类型"→"找到可投放渠道"
   是一条闭环动作链, 每一步都用真实数据说话, 不给剧本 (§4.8.6 Layer 3 边界).
─────────────────────────────────────────────────────────────── */
function ContentGapTab({ brand, t }) {
  const navigate = useNavigate();

  // MVP 阶段 mock 只基于 estee-lauder 填充数据; 其他品牌走空态.
  const hasData =
    ATTRIBUTION_MISMATCH_DIAGNOSTIC?.brandId === brand.id ||
    brand.id === 'estee-lauder';

  if (!hasData) {
    return (
      <Card className="p-10 text-center">
        <p className="text-sm text-themed-muted">
          暂未采集到该品牌的 Citation 归因数据
        </p>
        <p className="text-xs text-themed-faint mt-2">
          数据将在首次采集完成后在此自动展示
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* §4.2.7.A 归因方法时序堆叠 */}
      <AuthorityShareTimeSeries
        data={AUTHORITY_SHARE_SERIES}
        title="归因方法构成 · 近 30 天"
        subtitle="被引用时, AI 是怎么把结果归到你名下的 — 官方域 → 共现 → 文本匹配, 越靠前权重越高"
      />

      {/* §4.2.7.B 内容缺口 */}
      <ContentGapPanel
        topics={CONTENT_GAP_TOPICS}
        distribution={CONTENT_GAP_PAGE_TYPE_DISTRIBUTION}
        maxTopics={10}
      />

      {/* §4.2.7.C PR 候选 + Tier2 + KOL */}
      <PrTargetsPanel
        targets={PR_TARGETS}
        tier2Matrix={TIER2_COVERAGE_MATRIX}
        kolScorecards={KOL_SCORECARDS}
      />

      {/* §4.2.7.D v1.1 竞品解构 */}
      <div className="grid gap-6 lg:grid-cols-2">
        <AuthorityRadarChart data={AUTHORITY_RADAR_DATA} />
        <SameGroupAndAcquisition
          sameGroup={SAME_GROUP_SHARED}
          acquisitionEvents={ACQUISITION_EVENTS}
        />
      </div>

      {/* §4.2.7.E v1.1 Simulator 入口 */}
      <Card className="p-5" style={{ background: 'var(--color-accent-subtle)' }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h4 className="text-sm font-semibold text-themed-primary">
              想看看"加 N 个 Tier 2 媒体能涨多少 PANO A"?
            </h4>
            <p className="text-xs text-themed-secondary mt-1 leading-relaxed">
              打开模拟器调一调 · 不承诺结果, 只给基于当前结构的估算
            </p>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate(`/brands/${brand.id}/simulator`)}
          >
            打开 PANO A 模拟器 →
          </Button>
        </div>
      </Card>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Tab: 产品 (BCG 矩阵 + 列表)
─────────────────────────────────────────────────────────────── */
function ProductsTab({ brand, t, formatNumber }) {
  const navigate = useNavigate();

  const brandProducts = useMemo(() => {
    // Match by brand chinese name or english name (mock lacks FK; in prod uses kg_products.brand_id)
    return PRODUCTS.filter(
      (p) => p.brand === brand.name || p.brandEn === brand.nameEn
    );
  }, [brand.id]);

  // For BCG: X = SoV (use mentionRate as proxy), Y = growth rate (use change sign/magnitude)
  // Size = mention count (mentionRate * 100 as proxy)
  const bcgPoints = useMemo(() => {
    return brandProducts.map((p) => {
      const growth = parseFloat(p.change) || 0;
      return {
        id: p.id,
        name: p.name,
        sov: p.mentionRate,
        growth,
        size: Math.max(40, p.mentionRate * 6),
      };
    });
  }, [brandProducts]);

  const sovMax = Math.max(25, ...bcgPoints.map((p) => p.sov * 1.1));
  const growthAbs = Math.max(3, ...bcgPoints.map((p) => Math.abs(p.growth) * 1.3));

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-themed-primary mb-4">
          {t('brand.detail.products.title')}
        </h3>

        {brandProducts.length === 0 ? (
          <p className="text-sm text-themed-muted text-center py-10">
            {t('brand.detail.products.empty')}
          </p>
        ) : (
          <div className="relative" style={{ height: 280 }}>
            {/* Quadrant labels */}
            <span className="absolute top-2 right-4 text-[11px] text-themed-muted">{t('brand.detail.products.q_star')}</span>
            <span className="absolute bottom-10 right-4 text-[11px] text-themed-muted">{t('brand.detail.products.q_cow')}</span>
            <span className="absolute top-2 left-10 text-[11px] text-themed-muted">{t('brand.detail.products.q_question')}</span>
            <span className="absolute bottom-10 left-10 text-[11px] text-themed-muted">{t('brand.detail.products.q_dog')}</span>

            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[]}
                margin={{ top: 8, right: 16, bottom: 32, left: 8 }}
              >
                <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  domain={[0, sovMax]}
                  dataKey="sov"
                  tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
                  axisLine={{ stroke: 'var(--color-border-subtle)' }}
                  tickLine={false}
                  label={{ value: 'SoV %', position: 'insideBottomRight', offset: -4, fontSize: 10, fill: 'var(--color-text-muted)' }}
                />
                <YAxis
                  type="number"
                  domain={[-growthAbs, growthAbs]}
                  dataKey="growth"
                  tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
                  axisLine={{ stroke: 'var(--color-border-subtle)' }}
                  tickLine={false}
                />
              </BarChart>
            </ResponsiveContainer>

            {/* Render bubbles manually as absolute-positioned dots over the axes */}
            <svg
              className="absolute inset-0 pointer-events-none"
              style={{ width: '100%', height: '100%' }}
            >
              {bcgPoints.map((p) => {
                const xPct = (p.sov / sovMax) * 84 + 8; // match axis margins approx
                const yPct = (1 - (p.growth + growthAbs) / (growthAbs * 2)) * 72 + 4;
                const r = Math.sqrt(p.size);
                return (
                  <g
                    key={p.id}
                    style={{ pointerEvents: 'auto', cursor: 'pointer' }}
                    onClick={() => navigate(`/brands/${brand.id}/products/${p.id}`)}
                  >
                    <circle
                      cx={`${xPct}%`}
                      cy={`${yPct}%`}
                      r={r}
                      fill="var(--color-accent)"
                      fillOpacity={0.75}
                      stroke="var(--color-bg-card)"
                      strokeWidth={1.5}
                    />
                    <text
                      x={`${xPct}%`}
                      y={`${yPct}%`}
                      textAnchor="middle"
                      dy={r + 12}
                      fontSize={11}
                      fill="var(--color-text-primary)"
                    >
                      {p.name}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </Card>

      {/* Products list */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-themed-subtle">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('brand.detail.products.list_title')}
          </h3>
        </div>
        {brandProducts.length === 0 ? (
          <p className="text-sm text-themed-muted text-center py-10">
            {t('brand.detail.products.empty')}
          </p>
        ) : (
          <table className="w-full t-table">
            <thead>
              <tr>
                <th className="text-left py-2.5 px-5 text-xs font-medium text-themed-muted">
                  {t('brand.detail.products.list_col.product')}
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('brand.detail.products.list_col.pano')}
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('brand.detail.products.list_col.sov')}
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('brand.detail.products.list_col.sentiment')}
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('brand.detail.products.list_col.top_prompts')}
                </th>
              </tr>
            </thead>
            <tbody>
              {brandProducts.map((p) => (
                <tr
                  key={p.id}
                  className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer transition-colors"
                  onClick={() => navigate(`/brands/${brand.id}/products/${p.id}`)}
                >
                  <td className="py-2.5 px-5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-themed-primary">{p.name}</span>
                      <span className="text-[11px] text-themed-muted">{p.brandEn}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-primary">
                    {p.panoScore}
                  </td>
                  <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                    {formatNumber(p.mentionRate, { maximumFractionDigits: 1 })}%
                  </td>
                  <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                    {formatNumber(0.72 + (p.panoScore - 70) * 0.004, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                    #{p.ranking}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Tab: 引擎对比
─────────────────────────────────────────────────────────────── */
function EnginesTab({ brand, t, formatNumber }) {
  // Per-engine stats derived from ENGINES + SENTIMENT_DISTRIBUTION + brand baselines
  const cards = useMemo(() => {
    return ENGINES.map((e) => {
      const dist = SENTIMENT_DISTRIBUTION.find((d) => d.engine === e.name);
      const baseMention = e.mentionRate * (brand.mentionRate / 16);
      const baseCitation = Math.round(e.score * 0.6 + brand.panoScore * 0.4);
      return {
        engine: e.name,
        color: e.color,
        mentionRate: Math.round(baseMention * 10) / 10,
        sentiment: dist ? (dist.positive / 100) : brand.sentiment,
        citation: baseCitation,
        topPositionShare: Math.round(18 + (brand.panoScore - 70) * 0.7),
      };
    });
  }, [brand.id]);

  const top = cards.reduce((a, b) => (a.mentionRate >= b.mentionRate ? a : b), cards[0]);
  const weak = cards.reduce((a, b) => (a.mentionRate <= b.mentionRate ? a : b), cards[0]);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-themed-primary">
          {t('brand.detail.engines.title')}
        </h3>
        <p className="text-xs text-themed-muted mt-1">
          {t('brand.detail.engines.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {cards.map((c) => (
          <Card key={c.engine} className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ background: 'var(--color-accent)' }}
              />
              <span className="text-sm font-semibold text-themed-primary">{c.engine}</span>
            </div>
            <div className="space-y-3">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-themed-muted">{t('brand.detail.engines.col_mention')}</span>
                <span className="text-lg font-bold tabular-nums text-themed-primary">
                  {formatNumber(c.mentionRate, { maximumFractionDigits: 1 })}%
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-themed-muted">{t('brand.detail.engines.col_sentiment')}</span>
                <span className="text-lg font-bold tabular-nums text-themed-primary">
                  {formatNumber(c.sentiment, { maximumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-themed-muted">{t('brand.detail.engines.col_citation')}</span>
                <span className="text-lg font-bold tabular-nums text-themed-primary">{c.citation}</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-themed-muted">{t('brand.detail.engines.col_position')}</span>
                <span className="text-lg font-bold tabular-nums text-themed-primary">{c.topPositionShare}%</span>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="p-5" style={{ background: 'var(--color-accent-subtle)' }}>
        <h4 className="text-sm font-semibold text-themed-primary mb-2">
          {t('brand.detail.engines.insight_title')}
        </h4>
        <p className="text-xs text-themed-secondary leading-relaxed">
          {t('brand.detail.engines.insight', {
            topEngine: top.engine,
            topRate: formatNumber(top.mentionRate, { maximumFractionDigits: 1 }),
            weakEngine: weak.engine,
            weakRate: formatNumber(weak.mentionRate, { maximumFractionDigits: 1 }),
          })}
        </p>
      </Card>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Main — BrandDetailPage
   PRD §4.1.1b + §4.1.2a + §4.6.1b
─────────────────────────────────────────────────────────────── */

// 把 ?from= 映射到面包屑 i18n key + 返回 href.
const BREADCRUMB_BY_FROM = {
  industry:  { key: 'brand_watch.breadcrumb.from_industry',  href: '/knowledge-graph' },
  dashboard: { key: 'brand_watch.breadcrumb.from_dashboard', href: '/dashboard' },
  brands:    { key: 'brand_watch.breadcrumb.from_brands',    href: '/brands' },
  product:   { key: 'brand_watch.breadcrumb.from_product',   href: '/dashboard' },
};

export default function BrandDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { t, formatNumber, formatBrand } = useLocale();
  const { activeProject, getWatchState } = useProject();

  const primaryId = activeProject?.primaryBrandId;
  const competitorIds = activeProject?.competitorBrandIds || [];
  const scopeIds = [primaryId, ...competitorIds].filter(Boolean);

  const brand = useMemo(
    () => BRANDS.find((b) => b.id === id) || BRANDS.find((b) => b.id === primaryId) || BRANDS[0],
    [id, primaryId]
  );
  const brandOptions = useMemo(
    () => scopeIds.map((bid) => BRANDS.find((b) => b.id === bid)).filter(Boolean),
    [scopeIds.join(',')]
  );

  // PRD §4.6.1b — 三状态分支
  const watchState = useMemo(() => getWatchState(brand), [getWatchState, brand]);
  const isWatching = watchState.kind === 'watching' || watchState.kind === 'primary';
  const isAnonymous = watchState.kind === 'anonymous';

  // PRD §4.1.1b — 面包屑由 ?from= 决定; 默认回 dashboard.
  const fromKey = params.get('from');
  const breadcrumb = BREADCRUMB_BY_FROM[fromKey] || BREADCRUMB_BY_FROM.dashboard;

  const tabParam = params.get('tab');
  const activeTab = TAB_IDS.includes(tabParam) ? tabParam : 'overview';
  const diagId = params.get('diagId');

  const setTab = (tabId) => {
    const next = new URLSearchParams(params);
    next.set('tab', tabId);
    setParams(next);
  };

  const switchBrand = (brandId) => {
    const qs = params.toString();
    navigate(`/brands/${brandId}${qs ? `?${qs}` : ''}`);
  };

  const onSharePdf = () => {
    // Placeholder — in prod would trigger PDF generation
    // eslint-disable-next-line no-console
    console.info(`[PDF] generate brand health report for ${brand.id}`);
  };

  const handleAnonRegister = () => {
    const returnTo = `${location.pathname}${location.search || ''}`;
    const qs = new URLSearchParams();
    qs.set('monitor_brand', brand.id);
    qs.set('return_to', returnTo);
    navigate(`/register?${qs.toString()}`);
  };

  const tabs = [
    { id: 'overview',    label: t('brand.detail.tabs.overview') },
    { id: 'diagnostics', label: t('brand.detail.tabs.diagnostics') },
    // PRD §4.2.7.B — 内容缺口 (Citation 反向归因) 独立 Tab
    { id: 'content-gap', label: t('brand.detail.tabs.content_gap') },
    { id: 'products',    label: t('brand.detail.tabs.products') },
    { id: 'engines',     label: t('brand.detail.tabs.engines') },
  ];

  // 给 anonymous 留底栏空间, 避免 sticky CTA 遮挡尾部内容
  const wrapperPadding = isAnonymous ? 'pb-24' : '';

  return (
    <div className={`space-y-5 ${wrapperPadding}`}>
      {/* PRD §4.1.1d E4 — Gated-surface banner.
          Banner self-gates on `isAuthenticated && projects.length === 0 && !dismissed`,
          and is scoped to the diagnostics sub-tab because overview/products/engines
          still function as read-only industry views without a Project. */}
      {activeTab === 'diagnostics' && <ProjectRequiredBanner />}

      <BrandTopBar
        brand={brand}
        brandOptions={brandOptions}
        primaryId={primaryId}
        onSwitchBrand={switchBrand}
        onSharePdf={onSharePdf}
        showProfileFilter={activeTab !== 'products'}
        showBrandSwitcher={isWatching && brandOptions.length > 1}
        breadcrumbKey={breadcrumb.key}
        breadcrumbHref={breadcrumb.href}
        t={t}
      />

      {/* LIVE strip — primary brand metrics from /v1/projects/:id/metrics */}
      <BrandDetailLiveBanner />

      {/* PRD §4.6.1b — state B / C 顶部 banner */}
      <BrandStateBanner state={watchState} brand={brand} t={t} formatBrand={formatBrand} />

      {/* Profile-group degradation banner — PRD §4.2.3a; 在产品 Tab 不展示 */}
      {activeTab !== 'products' && <ProfileGroupSampleWarning />}

      {/* Sub-tabs */}
      <div className="t-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`t-tab ${activeTab === tab.id ? 't-tab-active' : ''}`}
            onClick={() => setTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'overview' && (
          <OverviewTab brand={brand} />
        )}
        {activeTab === 'diagnostics' && (
          <DiagnosticsTab
            brand={brand}
            t={t}
            onDownloadPdf={onSharePdf}
            highlightId={diagId}
            showUpsellStrip={!isWatching && !isAnonymous}
          />
        )}
        {activeTab === 'content-gap' && (
          <ContentGapTab brand={brand} t={t} />
        )}
        {activeTab === 'products' && (
          <ProductsTab brand={brand} t={t} formatNumber={formatNumber} />
        )}
        {activeTab === 'engines' && (
          <EnginesTab brand={brand} t={t} formatNumber={formatNumber} />
        )}
      </div>

      {/* PRD §4.6.1b — state C 仅匿名用户固定底栏 CTA */}
      <AnonymousStickyCta
        state={watchState}
        brand={brand}
        t={t}
        formatBrand={formatBrand}
        onCta={handleAnonRegister}
      />
    </div>
  );
}
