import React, { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from 'recharts';
import { Badge, Card } from '../components/ui';
import ProductDetailLiveBanner from '../components/brand/ProductDetailLiveBanner';
import { useLocale } from '../contexts/LocaleContext';
import {
  BRANDS, PRODUCTS, INDUSTRIES, CATEGORIES,
  PRODUCT_RELATIONS, MENTION_DETAIL_LIST,
} from '../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandProductDetailPage — PRD §4.6-IA-v2.C.2.2e / §4.6.1d 品牌下钻第三层
   ─────────────────────────────────────────────────────────────
   URL: /brand/products/:productId?brandId=:brandId
     - productId 是 path param (useParams)
     - brandId 是 query string (useSearchParams), 因为在 V2 Brand Mode 下
       brandId 由 BrandPicker 驱动, URL 前缀 /brand/* 固定, 不把 brandId 嵌入路径
   旧 URL /brands/:brandId/products/:productId 301 重定向到本路径 (App.jsx).
   独立 URL, SSR 友好, SEO 可作为长尾落地页.

   页面内容:
     - 面包屑 (行业 → 品类 → 产品)
     - 产品 PANO / SoV / 情感 / 引用 子指标
     - 推荐语境分类 (Response 挖掘, MVP: 水平柱状)
     - 产品关系视图 (MVP: 分类列表, Phase 2: AntV G6)
     - Prompt 命中 Top 20

   🚫 本页不做:
     - 品牌评分 (PanoRing)        → 品牌详情
     - 跨品牌竞争视图            → 面板
     - 跨产品 BCG 矩阵           → 品牌详情"产品" Tab
*/

const CONTEXT_COLORS = [
  'var(--color-accent)',
  'var(--color-chart-3)',
  'var(--color-chart-2)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
];

function flattenCategories(categoriesByIndustry) {
  const flat = [];
  Object.entries(categoriesByIndustry).forEach(([industryId, list]) => {
    list.forEach((c) => {
      flat.push({ ...c, industryId });
      (c.children || []).forEach((child) => flat.push({ ...child, industryId, parentId: c.id }));
    });
  });
  return flat;
}

export default function BrandProductDetailPage() {
  const { productId } = useParams();
  const [searchParams] = useSearchParams();
  // brandId from query string in V2 Brand Mode routing (not path param)
  const brandId = searchParams.get('brandId');
  const navigate = useNavigate();
  const { t, formatNumber } = useLocale();

  const product = useMemo(() => PRODUCTS.find((p) => p.id === productId), [productId]);
  // brand is optional — if brandId missing from query, fall back to product.brand heuristic
  const brand = useMemo(() => {
    if (brandId) return BRANDS.find((b) => b.id === brandId);
    // fallback: match product.brand name to BRANDS (tolerant of missing query param)
    if (product) return BRANDS.find((b) => b.name === product.brand || b.nameEn === product.brandEn);
    return null;
  }, [brandId, product]);

  if (!product) {
    return (
      <Card className="p-8 text-center text-sm text-themed-muted">
        {t('common.empty')}
      </Card>
    );
  }

  const industry = brand ? INDUSTRIES.find((i) => i.id === brand.industryId) : null;
  const flatCats = useMemo(() => flattenCategories(CATEGORIES), []);
  // Heuristic: first category in brand's industry (mock lacks product.categoryId)
  const category = brand ? flatCats.find((c) => c.industryId === brand.industryId) : null;

  // Context categories — mock derived from product mentionRate split
  const contexts = useMemo(() => {
    const base = product.mentionRate;
    return [
      { name: '干皮推荐',      value: Math.round(base * 1.6 * 10) / 10 },
      { name: '送礼首选',      value: Math.round(base * 1.2 * 10) / 10 },
      { name: '抗衰老',        value: Math.round(base * 1.4 * 10) / 10 },
      { name: '性价比',        value: Math.round(base * 0.6 * 10) / 10 },
      { name: '敏感肌',        value: Math.round(base * 0.8 * 10) / 10 },
    ].sort((a, b) => b.value - a.value);
  }, [product.id]);

  // Product relations — filter from PRODUCT_RELATIONS mock
  const relations = useMemo(() => {
    return PRODUCT_RELATIONS
      .filter((r) => r.productA === product.id || r.productB === product.id)
      .map((r) => {
        const otherId = r.productA === product.id ? r.productB : r.productA;
        const other = PRODUCTS.find((p) => p.id === otherId);
        return other ? { ...r, target: other } : null;
      })
      .filter(Boolean);
  }, [product.id]);

  const relationsByType = useMemo(() => {
    const grouped = {};
    relations.forEach((r) => {
      if (!grouped[r.type]) grouped[r.type] = [];
      grouped[r.type].push(r);
    });
    return grouped;
  }, [relations]);

  // Prompt hits — use MENTION_DETAIL_LIST as proxy
  const promptHits = MENTION_DETAIL_LIST.slice(0, 20);

  return (
    <div className="space-y-6">
      {/* Breadcrumb + back */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => navigate(brand ? `/brand/products?brandId=${brand.id}` : '/brand/products')}
          className="text-sm text-themed-muted hover:text-themed-primary transition-colors"
        >
          {t('product_detail.back_to_brand')}
        </button>
        <div className="h-4 w-px bg-themed-card" />
        <nav className="text-xs text-themed-muted flex items-center gap-1.5 flex-wrap">
          <span>{industry?.name || t('product_detail.breadcrumb_industry')}</span>
          <span>/</span>
          <span>{category?.name || t('product_detail.breadcrumb_category')}</span>
          <span>/</span>
          <span className="text-themed-primary font-medium">{product.name}</span>
        </nav>
      </div>

      {/* LIVE strip — surfaces this product from /v1/projects/:id/products
          when it matches by numeric product_id; null otherwise. */}
      <ProductDetailLiveBanner productId={productId} />

      {/* Product hero */}
      <Card className="p-6">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-xl font-brand font-bold text-themed-primary">
              {product.name}
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={() => brand && navigate(`/brand/overview?brandId=${brand.id}`)}
                className="text-sm text-themed-accent hover:underline"
                disabled={!brand}
              >
                {brand?.name || product.brand}
              </button>
              <span className="text-[11px] text-themed-muted">{brand?.nameEn || product.brandEn}</span>
              <Badge variant="secondary" size="sm">#{product.ranking}</Badge>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-6">
            <div>
              <p className="text-[11px] text-themed-muted">{t('product_detail.pano_card_title')}</p>
              <p className="text-2xl font-bold tabular-nums text-themed-primary">{product.panoScore}</p>
            </div>
            <div>
              <p className="text-[11px] text-themed-muted">{t('product_detail.sov_label')}</p>
              <p className="text-2xl font-bold tabular-nums text-themed-primary">
                {formatNumber(product.sov, { maximumFractionDigits: 1 })}%
              </p>
            </div>
            <div>
              <p className="text-[11px] text-themed-muted">{t('product_detail.sentiment_label')}</p>
              <p className="text-2xl font-bold tabular-nums text-themed-primary">
                {formatNumber(0.72 + (product.panoScore - 70) * 0.004, { maximumFractionDigits: 2 })}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-themed-muted">{t('product_detail.citation_label')}</p>
              <p className="text-2xl font-bold tabular-nums text-themed-primary">
                {Math.round(product.panoScore * 0.7)}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Context + Relations */}
      <div className="grid grid-cols-12 gap-6">
        <Card className="col-span-7 p-5">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('product_detail.context_title')}
          </h3>
          <p className="text-xs text-themed-muted mt-1 mb-4">
            {t('product_detail.context_subtitle')}
          </p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={contexts} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 16 }}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
                axisLine={{ stroke: 'var(--color-border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                dataKey="name"
                type="category"
                tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
                axisLine={false}
                tickLine={false}
                width={80}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-btn)',
                  fontSize: 12,
                  boxShadow: 'var(--shadow-card-hover)',
                }}
              />
              <Bar dataKey="value" radius={[4, 4, 4, 4]}>
                {contexts.map((_, i) => (
                  <Cell key={i} fill={CONTEXT_COLORS[i % CONTEXT_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="col-span-5 p-5">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('product_detail.relations_title')}
          </h3>
          <p className="text-xs text-themed-muted mt-1 mb-4">
            {t('product_detail.relations_subtitle')}
          </p>
          {relations.length === 0 ? (
            <p className="text-xs text-themed-muted py-6 text-center">
              {t('product_detail.relations_empty')}
            </p>
          ) : (
            <div className="space-y-4">
              {Object.entries(relationsByType).map(([type, list]) => (
                <div key={type}>
                  <h4 className="text-[11px] uppercase tracking-wider text-themed-muted mb-1.5">
                    {t(`product_detail.rel_type.${type}`)} · {list.length}
                  </h4>
                  <div className="space-y-1.5">
                    {list.map((r) => {
                      // find which brand the related product belongs to (mock: by product.brand name)
                      const targetBrand = BRANDS.find((b) => b.name === r.target.brand || b.nameEn === r.target.brandEn);
                      return (
                        <button
                          key={r.target.id}
                          onClick={() => targetBrand && navigate(`/brand/products/${r.target.id}?brandId=${targetBrand.id}`)}
                          className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-btn text-left transition-colors hover:bg-themed-subtle"
                          style={{ border: '1px solid var(--color-border-subtle)' }}
                        >
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-themed-primary truncate">
                              {r.target.name}
                            </div>
                            <div className="text-[11px] text-themed-muted truncate">
                              {r.target.brand} · {r.target.brandEn}
                            </div>
                          </div>
                          <span className="text-[11px] tabular-nums text-themed-muted shrink-0">
                            {Math.round((r.confidence || 0) * 100)}%
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Prompt hits */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-themed-subtle">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('product_detail.prompt_hits_title')}
          </h3>
          <p className="text-xs text-themed-muted mt-1">
            {t('product_detail.prompt_hits_subtitle')}
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full t-table">
            <thead>
              <tr>
                <th className="text-left py-2.5 px-5 text-xs font-medium text-themed-muted">
                  {t('product_detail.prompt_col.topic')}
                </th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('product_detail.prompt_col.prompt')}
                </th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('product_detail.prompt_col.position')}
                </th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('product_detail.prompt_col.engine')}
                </th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">
                  {t('product_detail.prompt_col.time')}
                </th>
              </tr>
            </thead>
            <tbody>
              {promptHits.map((row) => (
                <tr key={row.id} className="border-t border-themed-subtle">
                  <td className="py-2.5 px-5 text-sm text-themed-primary">{row.topic}</td>
                  <td className="py-2.5 px-4 text-sm text-themed-secondary truncate max-w-xs">{row.prompt}</td>
                  <td className="py-2.5 px-4 text-sm text-themed-secondary">{row.position}</td>
                  <td className="py-2.5 px-4 text-sm text-themed-secondary">{row.engine}</td>
                  <td className="py-2.5 px-4 text-xs text-themed-muted tabular-nums">{row.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
