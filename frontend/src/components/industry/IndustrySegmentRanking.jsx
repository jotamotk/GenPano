/**
 * IndustrySegmentRanking — PRD §4.6.1f §B 段 ⑦
 * ────────────────────────────────────────────────
 * 按 BRANDS.positioning 字段分 3 列 (国际高端 / 大众高端 / 小众-新锐).
 * 每列独立 Top 5, 每行: 品牌名 + PANO + change Δ + → 跳 Brand Mode.
 *
 * 赛道映射 (MVP 硬编码, Admin 维护移 Phase 2 per §4.6.1f.G):
 *   - '国际高端' → global_premium
 *   - '大众高端' → mass_premium
 *   - '小众|新锐|设计师|未标记' → niche
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, TrendingUp, TrendingDown } from 'lucide-react';

const SEGMENTS = [
  {
    key: 'global_premium',
    label: '国际高端',
    tone: 'var(--color-chart-2)',
    matcher: (b) => b.positioning === '国际高端',
  },
  {
    key: 'mass_premium',
    label: '大众高端',
    tone: 'var(--color-chart-3)',
    matcher: (b) => b.positioning === '大众高端',
  },
  {
    key: 'niche',
    label: '小众 / 新锐',
    tone: 'var(--color-chart-6)',
    matcher: (b) =>
      !['国际高端', '大众高端'].includes(b.positioning),
  },
];

export default function IndustrySegmentRanking({
  brands = [],
  primaryBrandId = null,
  limit = 5,
}) {
  const navigate = useNavigate();

  const segments = useMemo(() => {
    return SEGMENTS.map((s) => ({
      ...s,
      brands: [...brands]
        .filter((b) => s.matcher(b))
        .sort((a, b) => (b.panoScore || 0) - (a.panoScore || 0))
        .slice(0, limit),
    }));
  }, [brands, limit]);

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            赛道分层 Ranking
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            不同定位分赛道的 Top {limit} — 国际高端和小众新锐的 PANO 不可直接比较
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {segments.map((s) => (
          <div key={s.key} className="space-y-2">
            <div className="flex items-center justify-between pb-1 border-b border-themed-subtle">
              <span
                className="text-[11px] font-medium"
                style={{ color: s.tone }}
              >
                {s.label}
              </span>
              <span className="text-[10px] text-themed-muted tabular-nums">
                共 {s.brands.length}
              </span>
            </div>
            {s.brands.length === 0 ? (
              <div className="text-[11px] text-themed-muted py-4 text-center">
                此赛道当前无品牌
              </div>
            ) : (
              s.brands.map((b, i) => {
                const delta = parseFloat(b.change);
                const isUp = delta > 0;
                const isPrimary = b.id === primaryBrandId;
                return (
                  <div
                    key={b.id}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-card cursor-pointer hover:bg-themed-subtle"
                    style={
                      isPrimary
                        ? { background: 'color-mix(in srgb, var(--color-primary) 8%, transparent)' }
                        : undefined
                    }
                    onClick={() =>
                      navigate(`/brand/overview?brandId=${b.id}`)
                    }
                  >
                    <span
                      className="text-[10px] font-semibold text-themed-muted tabular-nums"
                      style={{ minWidth: 18 }}
                    >
                      #{i + 1}
                    </span>
                    {isPrimary && (
                      <span
                        className="text-[10px] font-semibold"
                        style={{ color: 'var(--color-primary)' }}
                      >
                        ▲
                      </span>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] text-themed-primary font-medium truncate">
                        {b.name}
                      </div>
                    </div>
                    <span className="text-[11px] text-themed-muted tabular-nums">
                      {Math.round(b.panoScore)}
                    </span>
                    <span
                      className="flex items-center gap-0.5 text-[11px] font-medium tabular-nums"
                      style={{
                        color: isUp
                          ? 'var(--color-success)'
                          : delta < 0
                          ? 'var(--color-danger)'
                          : 'var(--color-text-muted)',
                      }}
                    >
                      {isUp ? (
                        <TrendingUp size={10} />
                      ) : delta < 0 ? (
                        <TrendingDown size={10} />
                      ) : null}
                      {b.change}
                    </span>
                    <ChevronRight size={12} className="text-themed-muted" />
                  </div>
                );
              })
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
