/**
 * IndustryTrendChart — PRD §4.6.1e §B 段 ⑤ (趋势)
 * ────────────────────────────────────────────
 * 行业 PANO 均值折线 + 主品牌 PANO 折线叠加. 复用 TrendChart 组件.
 * 数据由页面生成 (行业均值走 brands.avg, 主品牌走其 sparkPano 如有, 否则
 * 模拟).
 */
import React from 'react';
import TrendChart from '../charts/TrendChart';

const LINES = [
  { key: 'industryAvg', label: '行业均值', color: 'var(--color-chart-axis-text)', dashed: true, area: false },
  { key: 'myBrand',     label: '我的品牌', color: 'var(--color-accent)',         area: true },
];

export default function IndustryTrendChart({ data = [], hasPrimary = false }) {
  if (!data.length) {
    return (
      <div className="t-card p-3 text-xs text-themed-muted">趋势数据暂无</div>
    );
  }
  const lines = hasPrimary ? LINES : LINES.filter((l) => l.key !== 'myBrand');

  return (
    <div className="t-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[13px] font-medium text-themed-primary">
          PANO 趋势 · 近 30 天
        </div>
        <div className="flex gap-3 text-[11px]">
          {lines.map((l) => (
            <div key={l.key} className="flex items-center gap-1 text-themed-muted">
              <span
                className="inline-block w-2.5 h-0.5"
                style={{ background: l.color, borderStyle: l.dashed ? 'dashed' : 'solid' }}
              />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
      </div>
      <TrendChart data={data} lines={lines} height={200} />
    </div>
  );
}
