/**
 * IndustryTierBreakdown — PRD §4.6.1f §B 段 ③
 * ───────────────────────────────────────────────
 * 四档 Tier 分层 (Top 3 / 4-10 / 11-25 / 26+).
 * 卡片高度按档内合计 SoV 等比; Tier 1 大字高亮, Tier 4 浅灰底.
 */
import React, { useMemo } from 'react';

const TIERS = [
  { key: 't1', label: 'Top 3 · S 级头部', range: [1, 3] },
  { key: 't2', label: '4-10 · A/B 腰部', range: [4, 10] },
  { key: 't3', label: '11-25 · 挑战者', range: [11, 25] },
  { key: 't4', label: '26+ · 尾部', range: [26, Infinity] },
];

export default function IndustryTierBreakdown({ brands = [] }) {
  const ranked = useMemo(
    () => [...brands].sort((a, b) => (b.panoScore || 0) - (a.panoScore || 0)),
    [brands]
  );

  const tiers = useMemo(() => {
    return TIERS.map((t, idx) => {
      const bs = ranked.filter((_, i) => {
        const rank = i + 1;
        return rank >= t.range[0] && rank <= t.range[1];
      });
      const totalSov = bs.reduce((s, b) => s + (b.sov || 0), 0);
      const avgPano =
        bs.length === 0
          ? 0
          : bs.reduce((s, b) => s + (b.panoScore || 0), 0) / bs.length;
      return {
        ...t,
        idx,
        brands: bs,
        count: bs.length,
        totalSov: Number(totalSov.toFixed(1)),
        avgPano: Math.round(avgPano),
        leaders: bs.slice(0, 2).map((b) => b.name),
      };
    });
  }, [ranked]);

  const maxSov = Math.max(...tiers.map((t) => t.totalSov), 1);

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            Tier 分层 Breakdown
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            卡片高度反映档内合计 SoV, 看 "头部吃多少 / 腰部有多厚"
          </div>
        </div>
        <div className="text-[11px] text-themed-muted tabular-nums">
          共 {ranked.length} 品牌
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3 items-end">
        {tiers.map((t) => {
          const heightPct = Math.max(
            20,
            Math.round((t.totalSov / maxSov) * 100)
          );
          const bgVar =
            t.idx === 0
              ? 'var(--color-chart-2)'
              : t.idx === 1
              ? 'var(--color-chart-3)'
              : t.idx === 2
              ? 'var(--color-chart-6)'
              : 'var(--color-surface-subtle)';
          const fg = t.idx === 3 ? 'var(--color-text-muted)' : '#fff';
          return (
            <div
              key={t.key}
              className="rounded-card p-3 flex flex-col justify-between"
              style={{
                background: bgVar,
                minHeight: `${60 + heightPct * 1.2}px`,
              }}
            >
              <div>
                <div
                  className="text-[11px] font-medium"
                  style={{ color: fg, opacity: 0.9 }}
                >
                  {t.label}
                </div>
                <div
                  className="text-2xl font-semibold tabular-nums mt-1"
                  style={{ color: fg }}
                >
                  {t.count}
                </div>
                <div
                  className="text-[10px]"
                  style={{ color: fg, opacity: 0.8 }}
                >
                  品牌数
                </div>
              </div>
              <div
                className="text-[11px] space-y-0.5 mt-2"
                style={{ color: fg, opacity: 0.85 }}
              >
                <div>PANO 均值 {t.avgPano}</div>
                <div>合计 SoV {t.totalSov}%</div>
                {t.leaders.length > 0 && (
                  <div className="truncate">{t.leaders.join(' / ')}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
