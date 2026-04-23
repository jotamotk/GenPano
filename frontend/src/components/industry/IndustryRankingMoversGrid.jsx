/**
 * IndustryRankingMoversGrid — PRD §4.6.1f §B 段 ⑤
 * ──────────────────────────────────────────────────
 * 30d 排名异动 Top 5 涨 / Top 5 跌 两列并排.
 * 每卡: 品牌名 + Δ (#M → #N) + 迷你 sparkline (30 点, Y 倒置) + PANO change.
 * 数据从 statistics.rankingDelta30d 合成.
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { rankingDelta30d } from '../../lib/industry/statistics';

const DRIVER_LABELS = {
  panoScore: 'PANO',
  sov: 'SoV',
  citationShare: '引用份额',
  sentiment: '情感',
};

function Sparkline({ points = [], positive = true, width = 96, height = 28 }) {
  if (!points.length) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  // Invert Y for rank (smaller rank = higher visually)
  const pts = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = ((p - min) / span) * height; // NOT inverted for rank: smaller = higher
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const stroke = positive
    ? 'var(--color-success)'
    : 'var(--color-danger)';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline
        points={pts}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MoverCard({ brand, delta, positive, onClick }) {
  const Icon = positive ? TrendingUp : TrendingDown;
  const color = positive ? 'var(--color-success)' : 'var(--color-danger)';
  return (
    <div
      onClick={onClick}
      className="t-card t-card-interactive p-3 cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-themed-primary truncate">
            {brand.name}
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            #{delta.rankFrom} → #{delta.rankTo}
          </div>
        </div>
        <div
          className="flex items-center gap-1 text-sm font-semibold tabular-nums"
          style={{ color }}
        >
          <Icon size={14} />
          {positive ? '+' : ''}
          {delta.delta}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <Sparkline points={delta.trend} positive={positive} />
        <div className="text-[11px] text-themed-muted tabular-nums">
          PANO {brand.change}
        </div>
      </div>
      <div className="mt-1 text-[10px] text-themed-muted">
        主驱动 · {DRIVER_LABELS[delta.primaryDriver] || delta.primaryDriver}
      </div>
    </div>
  );
}

export default function IndustryRankingMoversGrid({ brands = [], limit = 5 }) {
  const navigate = useNavigate();

  const { gainers, losers } = useMemo(() => {
    const withDelta = brands
      .map((b) => ({ brand: b, delta: rankingDelta30d(b) }))
      .filter((x) => x.delta && x.delta.delta !== 0);
    const gainers = [...withDelta]
      .filter((x) => x.delta.delta > 0)
      .sort((a, b) => b.delta.delta - a.delta.delta)
      .slice(0, limit);
    const losers = [...withDelta]
      .filter((x) => x.delta.delta < 0)
      .sort((a, b) => a.delta.delta - b.delta.delta)
      .slice(0, limit);
    return { gainers, losers };
  }, [brands, limit]);

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            30 天排名异动 Top {limit}
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            谁在往榜单上爬 / 谁在往下掉, 带主要驱动指标
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div
            className="text-[11px] font-medium mb-2 flex items-center gap-1"
            style={{ color: 'var(--color-success)' }}
          >
            <TrendingUp size={12} />
            上涨
          </div>
          <div className="space-y-2">
            {gainers.length === 0 ? (
              <div className="text-[11px] text-themed-muted py-4 text-center">
                30d 无显著上涨品牌
              </div>
            ) : (
              gainers.map(({ brand, delta }) => (
                <MoverCard
                  key={brand.id}
                  brand={brand}
                  delta={delta}
                  positive
                  onClick={() =>
                    navigate(`/brand/overview?brandId=${brand.id}`)
                  }
                />
              ))
            )}
          </div>
        </div>
        <div>
          <div
            className="text-[11px] font-medium mb-2 flex items-center gap-1"
            style={{ color: 'var(--color-danger)' }}
          >
            <TrendingDown size={12} />
            下跌
          </div>
          <div className="space-y-2">
            {losers.length === 0 ? (
              <div className="text-[11px] text-themed-muted py-4 text-center">
                30d 无显著下跌品牌
              </div>
            ) : (
              losers.map(({ brand, delta }) => (
                <MoverCard
                  key={brand.id}
                  brand={brand}
                  delta={delta}
                  positive={false}
                  onClick={() =>
                    navigate(`/brand/overview?brandId=${brand.id}`)
                  }
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
