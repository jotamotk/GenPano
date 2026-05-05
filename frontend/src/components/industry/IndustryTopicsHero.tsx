/**
 * IndustryTopicsHero — PRD §4.6.1g §B 段 ② (v3.1, 2026-04-20)
 * ────────────────────────────────────────────────────────────
 * 3 count: 活跃 Topic 数 / 新兴 Topic 数 (isEmerging true) / 行业平均情感.
 * v3.1 删除"总提及量": MVP mock 数据无法科学刻画绝对提及量, 保留"相对/比较型"指标.
 * 与 §4.6.1e IndustryHero 同规 (text-xl h1, tabular-nums, pb-3 border-b).
 */
import React, { useMemo } from 'react';

export default function IndustryTopicsHero({
  industryName,
  heatmap = [],
}) {
  const stats = useMemo(() => {
    const activeCount = heatmap.length;
    const emergingCount = heatmap.filter((t) => t.isEmerging === true).length;
    const avgSentiment =
      activeCount === 0
        ? 0
        : heatmap.reduce((s, t) => s + (t.avgSentiment || 0), 0) / activeCount;
    return {
      activeCount,
      emergingCount,
      avgSentiment,
    };
  }, [heatmap]);

  const cards = [
    { label: '活跃 Topic', value: stats.activeCount },
    { label: '新兴 Topic', value: stats.emergingCount, accent: true },
    {
      label: '平均情感',
      value: `${Math.round(stats.avgSentiment * 100)}`,
      suffix: '%',
    },
  ];

  return (
    <div className="flex items-baseline justify-between gap-4 pb-3 border-b border-themed-subtle">
      <div>
        <h1 className="text-xl font-semibold text-themed-primary">
          {industryName || '行业 Topic 格局'}
        </h1>
        <p className="text-xs text-themed-muted mt-1">
          话题格局 · 品牌覆盖矩阵 · 新兴与衰退 · Intent 交叉 · 详情深挖
        </p>
      </div>
      <div className="flex gap-6">
        {cards.map((s) => (
          <div key={s.label} className="text-right">
            <div
              className="text-xl font-semibold tabular-nums"
              style={{
                color: s.accent
                  ? 'var(--color-primary)'
                  : 'var(--color-text-primary)',
              }}
            >
              {s.value ?? '—'}
              {s.suffix || ''}
            </div>
            <div className="text-[11px] text-themed-muted mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
