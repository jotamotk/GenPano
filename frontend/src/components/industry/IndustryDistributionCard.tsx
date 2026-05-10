/**
 * IndustryDistributionCard — PRD §4.6.1e §B 段 ③
 * ───────────────────────────────────────────
 * 单张 IQR 箱线卡 (5 张 map 实例: 提及率/SoV/情感/引用份额/排名).
 * 自定义 SVG box plot (Recharts 没有原生 BoxPlot 组件, 这是 Recharts
 * 官方 recipe 推荐手绘方式).
 *
 * Props:
 *   label            展示名 ("提及率" / "SoV" 等)
 *   unit             单位 ("%" / "" / "#")
 *   stats            computeIQR 返回对象 ({ p25, p50, p75, min, max, outliers, n, tooSmall, statOnly })
 *   primaryValue     主品牌当前值 (可选, 有值时画 ▲ marker)
 *   primaryName      主品牌名 (可选, ▲ tooltip 文案用)
 *   direction        'higher_is_better' | 'lower_is_better' — 排名用 lower_is_better
 *   formatValue      (v) => string, 自定义格式化
 *
 * Harness §G.2: ▲ marker 必须 `{primaryValue != null && (<...>)}` 守卫
 * Harness §G.3: 禁 inline percentile 计算, 使用 lib/industry/statistics.js
 */
import React from 'react';
import { MetricLabel } from '../ui';

export default function IndustryDistributionCard({
  label,
  unit = '',
  stats,
  primaryValue = null,
  primaryName = null,
  direction = 'higher_is_better',
  formatValue = (v) => (v == null ? '—' : v.toFixed(1)),
}) {
  if (!stats) {
    return (
      <div className="t-card p-3 space-y-2">
        <div className="text-[13px] font-medium text-themed-primary">
          <MetricLabel helpText="该指标在当前行业品牌样本中的分布。">{label}</MetricLabel>
        </div>
        <div className="text-xs text-themed-muted">暂无样本</div>
      </div>
    );
  }

  // Scale to [0%, 100%] of card width
  const { min, max, p25, p50, p75, n, tooSmall } = stats;
  const range = max - min || 1;
  const scale = (v) => ((v - min) / range) * 100;

  const medianDelta =
    primaryValue != null ? primaryValue - p50 : null;
  const medianDeltaText =
    medianDelta == null
      ? null
      : direction === 'lower_is_better'
      ? medianDelta > 0
        ? `距中位数 +${Math.abs(medianDelta).toFixed(1)}${unit} (落后)`
        : medianDelta < 0
        ? `距中位数 -${Math.abs(medianDelta).toFixed(1)}${unit} (领先)`
        : `与中位数持平`
      : medianDelta > 0
      ? `距中位数 +${medianDelta.toFixed(1)}${unit} (领先)`
      : medianDelta < 0
      ? `距中位数 ${medianDelta.toFixed(1)}${unit} (落后)`
      : `与中位数持平`;

  const deltaColor =
    medianDelta == null
      ? ''
      : (direction === 'higher_is_better' ? medianDelta > 0 : medianDelta < 0)
      ? 'text-[var(--color-success)]'
      : 'text-[var(--color-danger)]';

  return (
    <div className="t-card p-3 space-y-3">
      {/* Header: label + P50 text */}
      <div className="flex items-baseline justify-between">
        <div className="text-[13px] font-medium text-themed-primary">
          <MetricLabel helpText="该指标在当前行业品牌样本中的 IQR 分布；三角标记为主品牌位置。">
            {label}
          </MetricLabel>
        </div>
        <div className="text-xs text-themed-muted tabular-nums">
          <MetricLabel helpText="行业样本品牌在该指标上的中位数。">
            中位数 {formatValue(p50)}
            {unit}
          </MetricLabel>
        </div>
      </div>

      {/* Box plot track */}
      <div className="relative h-10">
        {/* Axis line min → max */}
        <div
          className="absolute top-1/2 h-px bg-themed-subtle"
          style={{ left: '0%', right: '0%', transform: 'translateY(-0.5px)' }}
        />
        {/* Box: P25 to P75 */}
        {!tooSmall && (
          <div
            className="absolute top-1/2 h-4 rounded-sm bg-[var(--color-accent)]/15 border border-[var(--color-accent)]/40"
            style={{
              left: `${scale(p25)}%`,
              width: `${scale(p75) - scale(p25)}%`,
              transform: 'translateY(-50%)',
            }}
          />
        )}
        {/* Median line */}
        {!tooSmall && (
          <div
            className="absolute top-1/2 w-0.5 h-5 bg-[var(--color-accent)]"
            style={{
              left: `${scale(p50)}%`,
              transform: 'translate(-50%, -50%)',
            }}
          />
        )}
        {/* Too-small fallback: dot row */}
        {tooSmall && (
          <div className="absolute inset-0 flex items-center">
            {[...Array(n)].map((_, i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]/60 mx-0.5"
              />
            ))}
          </div>
        )}
        {/* Primary brand ▲ marker — guarded per §G.2 */}
        {primaryValue != null && (
          <div
            className="absolute top-0 text-[var(--color-accent)]"
            style={{
              left: `${Math.max(0, Math.min(100, scale(primaryValue)))}%`,
              transform: 'translateX(-50%)',
            }}
            title={`${primaryName || '主品牌'}: ${formatValue(primaryValue)}${unit}`}
          >
            <svg width="12" height="8" viewBox="0 0 12 8" aria-label="主品牌">
              <polygon points="6,0 12,8 0,8" fill="currentColor" />
            </svg>
          </div>
        )}
      </div>

      {/* Stats row + median delta */}
      <div className="flex items-center justify-between text-[11px] text-themed-muted tabular-nums">
        <span>
          {formatValue(min)}
          {unit}
        </span>
        {medianDeltaText ? (
          <span className={deltaColor}>{medianDeltaText}</span>
        ) : (
          <span className="text-themed-muted">样本 n={n}</span>
        )}
        <span>
          {formatValue(max)}
          {unit}
        </span>
      </div>

      {/* Sample size hint */}
      {tooSmall && (
        <div className="text-[11px] text-themed-muted">样本量小 · 仅呈点阵</div>
      )}
    </div>
  );
}
