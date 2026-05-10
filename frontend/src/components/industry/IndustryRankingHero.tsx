/**
 * IndustryRankingHero — PRD §4.6.1f §B 段 ②
 * ────────────────────────────────────────────
 * 行业名 + 3 count (覆盖品牌数 / 集团数 / 平均 PANO).
 * 主品牌存在时并列展示 "我的位置" 小卡: 综合/SoV/引用/情感 4 个 #N + 近 30d ±N 位 + 最弱维度.
 *
 * 契约:
 *   - h1 = text-xl (C14-1)
 *   - "我的位置" 卡 click → /brand/overview?brandId=:primary (跨 Mode 深度)
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, TrendingUp, TrendingDown } from 'lucide-react';
import { rankDispersion, rankingDelta30d } from '../../lib/industry/statistics';
import { MetricLabel } from '../ui';

const KPI_FIELDS = ['panoScore', 'sov', 'citationShare', 'sentiment'];
const KPI_LABELS = {
  panoScore: '综合',
  sov: 'SoV',
  citationShare: '引用',
  sentiment: '情感',
};

export default function IndustryRankingHero({
  industryName,
  industryBrands = [],
  primaryBrand = null,
}) {
  const navigate = useNavigate();

  const stats = useMemo(() => {
    const brandCount = industryBrands.length;
    const groupCount = new Set(
      industryBrands.map((b) => b.parentCompany).filter(Boolean)
    ).size;
    const avgPano =
      brandCount === 0
        ? 0
        : industryBrands.reduce((s, b) => s + (b.panoScore || 0), 0) / brandCount;
    return { brandCount, groupCount, avgPano };
  }, [industryBrands]);

  const myPosition = useMemo(() => {
    if (!primaryBrand) return null;
    const { ranks } = rankDispersion(primaryBrand, industryBrands, KPI_FIELDS);
    const delta30 = rankingDelta30d(primaryBrand);
    // Weakest dimension = highest rank number (worst)
    const validRanks = Object.entries(ranks).filter(([, v]) => typeof v === 'number');
    const weakest = validRanks.length
      ? validRanks.reduce((worst, cur) => (cur[1] > worst[1] ? cur : worst))
      : null;
    return { ranks, delta30, weakest };
  }, [primaryBrand, industryBrands]);

  return (
    <div className="flex items-start justify-between gap-4 pb-3 border-b border-themed-subtle">
      <div className="flex-1">
        <h1 className="text-xl font-semibold text-themed-primary">
          <MetricLabel helpText="按综合分、SoV、引用、情感、引擎分位和赛道分层观察行业排名。">
            {industryName || '行业排行榜'}
          </MetricLabel>
        </h1>
        <div className="flex gap-6 mt-3">
          <div>
            <div className="text-xl font-semibold text-themed-primary tabular-nums">
              {stats.brandCount}
            </div>
            <div className="text-[11px] text-themed-muted mt-0.5">
              <MetricLabel helpText="进入当前行业排名样本的品牌数量。">覆盖品牌</MetricLabel>
            </div>
          </div>
          <div>
            <div className="text-xl font-semibold text-themed-primary tabular-nums">
              {stats.groupCount}
            </div>
            <div className="text-[11px] text-themed-muted mt-0.5">
              <MetricLabel helpText="进入当前行业排名样本的母集团数量。">覆盖集团</MetricLabel>
            </div>
          </div>
          <div>
            <div className="text-xl font-semibold text-themed-primary tabular-nums">
              {Math.round(stats.avgPano)}
            </div>
            <div className="text-[11px] text-themed-muted mt-0.5">
              <MetricLabel helpText="当前行业样本品牌的 PANO Score 平均值。">平均 PANO</MetricLabel>
            </div>
          </div>
        </div>
      </div>

      {myPosition && (
        <div
          className="t-card t-card-interactive p-3 min-w-[320px] cursor-pointer"
          onClick={() =>
            navigate(`/brand/overview?brandId=${primaryBrand.id}`)
          }
        >
          <div className="flex items-center justify-between mb-2">
            <div className="text-[13px] font-medium text-themed-primary">
              主品牌位置 · {primaryBrand.name}
            </div>
            <ArrowRight size={14} className="text-themed-muted" />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {KPI_FIELDS.map((f) => (
              <div key={f} className="text-center">
                <div className="text-sm font-semibold text-themed-primary tabular-nums">
                  {myPosition.ranks[f] != null ? `#${myPosition.ranks[f]}` : '—'}
                </div>
                <div className="text-[10px] text-themed-muted mt-0.5">
                  <MetricLabel helpText={`主品牌在行业内的${KPI_LABELS[f]}排名。`}>
                    {KPI_LABELS[f]}
                  </MetricLabel>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-themed-subtle flex items-center justify-between text-[11px]">
            <span className="flex items-center gap-1 tabular-nums">
              {myPosition.delta30 && myPosition.delta30.delta !== 0 ? (
                myPosition.delta30.delta > 0 ? (
                  <>
                    <TrendingUp
                      size={11}
                      style={{ color: 'var(--color-success)' }}
                    />
                    <span style={{ color: 'var(--color-success)' }}>
                      近 30d ↑{myPosition.delta30.delta}
                    </span>
                  </>
                ) : (
                  <>
                    <TrendingDown
                      size={11}
                      style={{ color: 'var(--color-danger)' }}
                    />
                    <span style={{ color: 'var(--color-danger)' }}>
                      近 30d ↓{Math.abs(myPosition.delta30.delta)}
                    </span>
                  </>
                )
              ) : (
                <span className="text-themed-muted">近 30d 持平</span>
              )}
            </span>
            {myPosition.weakest && (
              <span className="text-themed-muted">
                最弱 · {KPI_LABELS[myPosition.weakest[0]]}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
