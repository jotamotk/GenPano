import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, MockDataBadge } from '../../components/ui';
import { MiniSparkline, CompetitorQuadrantChart } from '../../components/charts';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useBrandOverview';
import { useBrandProducts } from '../../hooks/useBrandMetrics';
import { useProductRelations } from '../../hooks/useCharts';
import { adaptProductRelations } from '../../adapters/chartAdapters';
import {
  BRANDS,
  PRODUCTS,
  PRODUCT_RELATIONS,
} from '../../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandProductsPage — /brand/products (§4.6-IA-v2.C.2.2e)
   ─────────────────────────────────────────────────────────────
   品牌下产品组合视图, 4 区结构:

   ① BCG 气泡矩阵               — 产品在提及率 × 增长趋势中的位置
   ③ 产品趋势 Sparkline Grid    — 前 9 款产品 SoV 快视图
   ④ 产品列表 Table             — 详细数据表格
   ⑤ 产品关系快照               — 产品间竞争/替代/搭配关系

   点击任一产品跳到 /brand/products/:productId?brandId=:brandId 详情页 (BrandProductDetailPage).
*/

export default function BrandProductsPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { activeProject } = useProject();
  const primary = BRANDS.find((b) => b.id === activeProject?.primaryBrandId) || BRANDS[1];
  useBrandAnalysisFilters(); // C10: mount filter state in URL (filters read inside subcomponents)

  // ── Live data hooks ──
  const { data: liveProjects } = useProjects();
  const liveProjectId = liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const isLive = isLiveProjectId(liveProjectId);
  const productsQ = useBrandProducts(isLive ? liveProjectId : null);
  const relationsQ = useProductRelations(isLive ? liveProjectId : null);

  // Filter products by brand, sort by sov desc so products[0] is flagship.
  const mockProducts = useMemo(() => {
    return PRODUCTS.filter(
      (p) =>
        p.brand === primary.name ||
        p.brandEn === primary.nameEn ||
        p.brandId === primary.id,
    ).sort((a, b) => (b.sov || 0) - (a.sov || 0));
  }, [primary.id, primary.name, primary.nameEn]);

  const liveProducts = useMemo(() => {
    if (!isLive || !productsQ.data || productsQ.data.items.length === 0) return null;
    return productsQ.data.items.map((p) => ({
      id: p.product_id,
      primaryName: p.product_name,
      brand: primary.name,
      brandEn: primary.nameEn,
      brandId: p.brand_id ?? primary.id,
      category: p.category,
      categoryName: p.category,
      mentionRate: p.mention_rate ?? 0,
      mentionCount: p.mention_count,
      sov: p.sov ?? 0,
      sentiment: p.avg_sentiment ?? 0,
      ranking: p.ranking,
      trend: p.trend_30d ?? 0,
      sparkData: p.sparkline ?? [],
      panoScore: p.avg_geo_score,
    }));
  }, [isLive, productsQ.data, primary]);
  const products = liveProducts ?? mockProducts;
  const productsIsMock = !liveProducts;

  // ─── ① BCG data ─────────────────────────────────────────────
  const bcgData = useMemo(() => {
    if (!products.length) return [];
    const primaryProductId = products[0]?.id;
    return products.map((p: any) => ({
      name: p.primaryName,
      x: p.mentionRate || 0,
      y: p.trend || 0,
      z: p.mentionCount || 100,
      isPrimary: p.id === primaryProductId,
      productId: p.id,
    }));
  }, [products]);

  // ─── ⑤ product relations ────────────────────────────────────
  const liveRelations = adaptProductRelations(relationsQ.data);
  const productRelations = useMemo(() => {
    if (isLive && liveRelations.length > 0) {
      return liveRelations.map((r) => ({
        productA: r.productA,
        productB: r.productB,
        type: r.type,
        confidence: r.confidence,
      }));
    }
    if (products.length < 3) return [];
    const productIds = (products as any[]).map((p) => p.id);
    return PRODUCT_RELATIONS.filter(
      (r) => productIds.includes(r.productA) && productIds.includes(r.productB),
    );
  }, [products, isLive, liveRelations]);
  const relationsIsMock = !(isLive && liveRelations.length > 0);

  const handleBubbleClick = (item) =>
    navigate(`/brand/products/${item.productId}?brandId=${primary.id}`);
  const handleProductRowClick = (productId) =>
    navigate(`/brand/products/${productId}?brandId=${primary.id}`);

  const relationBadgeVariant = (type) => ({
    COMPETES_WITH: 'red',
    SUBSTITUTES: 'blue',
    PAIRS_WITH: 'green',
    UPGRADES_TO: 'yellow',
    BUDGET_ALT_OF: 'gray',
  }[type] || 'gray');

  const relationTypeLabel = (type) => ({
    COMPETES_WITH: t('product.relation_competes', { defaultValue: '竞争' }) || '竞争',
    SUBSTITUTES: t('product.relation_substitutes', { defaultValue: '替代' }) || '替代',
    PAIRS_WITH: t('product.relation_pairs', { defaultValue: '搭配' }) || '搭配',
    UPGRADES_TO: t('product.relation_upgrades', { defaultValue: '升级' }) || '升级',
    BUDGET_ALT_OF: t('product.relation_budget_alt', { defaultValue: '平替' }) || '平替',
  }[type] || type);

  const relationTypeColor = (type) => ({
    COMPETES_WITH: 'var(--color-danger)',
    SUBSTITUTES: 'var(--color-chart-2)',
    PAIRS_WITH: 'var(--color-success)',
    UPGRADES_TO: 'var(--color-warning)',
    BUDGET_ALT_OF: 'var(--color-chart-line-grid)',
  }[type] || 'var(--color-chart-line-grid)');

  return (
    <div className="space-y-3">
      {/* Page title */}
      <div>
        <h2 className="text-xl font-brand font-bold text-themed-primary flex items-center gap-2">
          {t('brand_products.page_title', '产品组合')}
          {productsIsMock && <MockDataBadge />}
        </h2>
        <p className="text-xs text-themed-muted mt-0.5">
          {t('brand_products.page_subtitle', { brand: primary.name, count: products.length })}
        </p>
      </div>

      {/* Filter bar */}
      <BrandAnalysisFilterBar />

      {/* ① BCG 气泡矩阵 */}
      <Card className="p-3">
        <div className="flex items-baseline justify-between mb-1">
          <h3 className="text-[13px] font-semibold text-themed-primary">
            {t('brand_products.section_bcg', 'BCG 矩阵')}
          </h3>
          <span className="text-[11px] text-themed-muted">
            {t('brand_products.section_bcg_hint', '产品在提及率 × 增长趋势中的位置')}
          </span>
        </div>
        {bcgData.length > 0 ? (
          <div className="mt-2">
            <CompetitorQuadrantChart
              data={bcgData}
              xLabel={t('brand_products.bcg_x', '提及率')}
              yLabel={t('brand_products.bcg_y', '增长趋势')}
              zLabel={t('brand_products.bcg_z', '提及量')}
              quadrantLabels={{
                topRight: t('brand_products.quad_star', '明星'),
                topLeft: t('brand_products.quad_question', '问题'),
                bottomRight: t('brand_products.quad_cow', '金牛'),
                bottomLeft: t('brand_products.quad_dog', '瘦狗'),
              }}
              xMidpoint={0.15}
              yMidpoint={0}
              onBubbleClick={handleBubbleClick}
              xFormat={(v) => `${Math.round(v * 100)}%`}
              yFormat={(v) => `${Math.round(v * 100)}%`}
              height={360}
            />
          </div>
        ) : (
          <div className="h-60 flex items-center justify-center text-themed-muted text-sm">
            {t('brand_products.no_data', '暂无产品数据')}
          </div>
        )}
      </Card>

      {/* ③ 产品趋势 Sparkline Grid */}
      {products.length > 0 && (
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-[13px] font-semibold text-themed-primary">
              {t('brand_products.section_trends', '产品趋势')}
            </h3>
            <span className="text-[11px] text-themed-muted">
              {t('brand_products.section_trends_hint', '各产品 SoV 和情感表现')}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {products.slice(0, 9).map((p) => {
              const delta = (p.sov || 0) - ((products[0]?.sov || 0) * 0.9);
              const isDelta = Math.abs(delta) > 0.5;
              return (
                <Card
                  key={p.id}
                  className="p-3 cursor-pointer transition-shadow hover:shadow-card-hover"
                  onClick={() => handleProductRowClick(p.id)}
                >
                  <div className="flex items-start justify-between mb-1.5">
                    <div>
                      <p className="font-medium text-themed-primary text-sm">
                        {p.primaryName}
                      </p>
                      <p className="text-[11px] text-themed-muted mt-0.5">
                        {p.categoryName || p.category}
                      </p>
                    </div>
                    <Badge variant={isDelta && delta > 0 ? 'green' : 'gray'} size="sm">
                      {isDelta ? (delta > 0 ? '+' : '') + delta.toFixed(1) : '—'}
                    </Badge>
                  </div>
                  <div className="mb-1.5">
                    <p className="text-lg font-brand font-bold text-themed-primary tabular-nums leading-none">
                      {(p.sov || 0).toFixed(1)}%
                    </p>
                  </div>
                  {p.sparkData && p.sparkData.length > 0 && (
                    <div className="h-6 -mx-1 mb-1.5">
                      <MiniSparkline data={p.sparkData} color="var(--color-accent)" />
                    </div>
                  )}
                  <div className="flex items-center justify-between text-[10px] text-themed-muted">
                    <span>
                      {t('brand_products.sentiment_label', '情感')}: {Math.round((p.sentiment || 0) * 100)}%
                    </span>
                    <span className={p.trend >= 0 ? 'text-themed-success' : 'text-themed-danger'}>
                      {p.trend >= 0 ? '▲' : '▼'} {Math.abs(Math.round(p.trend * 100))}%
                    </span>
                  </div>
                </Card>
              );
            })}
          </div>
        </Card>
      )}

      {/* ④ 产品列表 Table */}
      {products.length > 0 && (
        <Card className="p-3">
          <div className="mb-2">
            <h3 className="text-[13px] font-semibold text-themed-primary">
              {t('brand_products.list_title', '产品列表')}
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-themed-card">
                  <th className="py-2 px-3 text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_product', '产品名')}
                  </th>
                  <th className="py-2 px-3 text-left text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_category', '品类')}
                  </th>
                  <th className="py-2 px-3 text-right text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_mention', '提及率')}
                  </th>
                  <th className="py-2 px-3 text-right text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_sov', 'SoV')}
                  </th>
                  <th className="py-2 px-3 text-right text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_sentiment', '情感')}
                  </th>
                  <th className="py-2 px-3 text-right text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_trend', '趋势')}
                  </th>
                  <th className="py-2 px-3 text-right text-[10px] uppercase tracking-wider text-themed-muted">
                    {t('brand_products.col_ranking', '排名')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {products.map((p, idx) => (
                  <tr
                    key={p.id}
                    className={`border-b border-themed-card cursor-pointer transition-colors hover:bg-themed-subtle ${
                      idx === 0 ? 'bg-themed-accent-soft' : ''
                    }`}
                    onClick={() => handleProductRowClick(p.id)}
                  >
                    <td className="py-2 px-3 font-medium text-themed-primary text-sm">
                      {p.primaryName}
                    </td>
                    <td className="py-2 px-3 text-themed-muted text-sm">
                      {p.categoryName || p.category || '—'}
                    </td>
                    <td className="py-2 px-3 text-right text-sm tabular-nums">
                      {((p.mentionRate || 0) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-3 text-right text-sm tabular-nums">
                      {(p.sov || 0).toFixed(1)}%
                    </td>
                    <td className="py-2 px-3 text-right text-sm tabular-nums">
                      {Math.round((p.sentiment || 0) * 100)}%
                    </td>
                    <td className="py-2 px-3 text-right text-sm">
                      <span className={p.trend >= 0 ? 'text-themed-success' : 'text-themed-danger'}>
                        {p.trend >= 0 ? '▲' : '▼'} {Math.abs(Math.round(p.trend * 100))}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right text-themed-muted text-sm">
                      #{p.ranking || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ⑤ 产品关系快照 */}
      {productRelations.length > 0 && (
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_products.section_relations', '产品关系')}
              {relationsIsMock && <MockDataBadge />}
            </h3>
            <span className="text-[11px] text-themed-muted">
              {t('brand_products.section_relations_hint', '产品间的竞争、替代、搭配关系')}
            </span>
          </div>
          <div className="space-y-1.5">
            {productRelations.map((rel, idx) => {
              const pA = products.find((p) => p.id === rel.productA);
              const pB = products.find((p) => p.id === rel.productB);
              const borderColor = relationTypeColor(rel.type);
              return (
                <div
                  key={idx}
                  className="flex items-center gap-3 p-2 rounded border-l-4 hover:bg-themed-subtle transition-colors"
                  style={{ borderLeftColor: borderColor }}
                >
                  <span className="text-sm text-themed-primary flex-1 font-medium">
                    {pA?.primaryName} ↔ {pB?.primaryName}
                  </span>
                  <Badge variant={relationBadgeVariant(rel.type)} size="sm">
                    {relationTypeLabel(rel.type)}
                  </Badge>
                  <span className="text-[10px] text-themed-muted shrink-0">
                    {Math.round(rel.confidence * 100)}%
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
