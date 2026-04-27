/**
 * IndustrySovPie — PRD §4.6.1e §B 段 ④ (右饼)
 * ─────────────────────────────────────
 * 行业 SoV 分布饼图. 自适应:
 *  - 品牌数 ≤ 8: 全部展示, 无"其他"桶
 *  - 品牌数 > 8: Top 6 + 其他 (DESIGN_TOKENS C3 约束: 其他 ≤ min(Top 6))
 *
 * 复用现有 DonutChart 组件.
 */
import React, { useMemo } from 'react';
import DonutChart from '../charts/DonutChart';

const COLORS = [
  'var(--color-accent)',
  'var(--color-chart-7)',
  'var(--color-chart-6)',
  'var(--color-chart-3)',
  'var(--color-danger)',
  'var(--color-accent-2)',
  'var(--color-chart-4)',
  'var(--color-chart-2)',
];
const OTHER_COLOR = 'var(--color-chart-line-grid)';

export default function IndustrySovPie({ brands = [], primaryBrandId = null }) {
  const segments = useMemo(() => {
    if (!brands.length) return [];
    const sorted = [...brands]
      .filter(b => typeof b.sov === 'number')
      .sort((a, b) => b.sov - a.sov);

    // Adaptive: ≤8 → show all; >8 → Top 6 + others
    if (sorted.length <= 8) {
      return sorted.map((b, idx) => ({
        name: b.name,
        value: Number((b.sov ?? 0).toFixed(1)),
        color: COLORS[idx % COLORS.length],
        brandId: b.id,
      }));
    }
    const top6 = sorted.slice(0, 6);
    const rest = sorted.slice(6);
    const otherSum = rest.reduce((s, b) => s + (b.sov || 0), 0);
    return [
      ...top6.map((b, idx) => ({
        name: b.name,
        value: Number((b.sov ?? 0).toFixed(1)),
        color: COLORS[idx],
        brandId: b.id,
      })),
      { name: '其他', value: Number(otherSum.toFixed(1)), color: OTHER_COLOR },
    ];
  }, [brands]);

  if (!segments.length) {
    return (
      <div className="t-card p-3 text-xs text-themed-muted">SoV 数据暂无</div>
    );
  }

  return (
    <div className="t-card p-3 space-y-3">
      <div className="text-[13px] font-medium text-themed-primary">
        行业 SoV 分布
      </div>
      <div className="flex items-center gap-4">
        <div className="flex-shrink-0">
          <DonutChart segments={segments} size={160} />
        </div>
        <div className="flex-1 grid grid-cols-2 gap-x-3 gap-y-1.5">
          {segments.map((s) => (
            <div key={s.name} className="flex items-center gap-1.5 min-w-0">
              <div
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: s.color }}
              />
              <span
                className={`text-[11px] truncate flex-1 ${
                  s.brandId === primaryBrandId
                    ? 'text-[var(--color-accent)] font-medium'
                    : 'text-themed-primary'
                }`}
              >
                {s.name}
                {s.brandId === primaryBrandId ? ' ★' : ''}
              </span>
              <span className="text-[11px] font-medium text-themed-primary tabular-nums">
                {s.value}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
