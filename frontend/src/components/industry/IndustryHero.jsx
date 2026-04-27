/**
 * IndustryHero — PRD §4.6.1e §B 段 ②
 * ─────────────────────────────────
 * 无卡片边框的 count KPI strip: 覆盖品牌数 / 活跃 Topic 数 / 品类数 +
 * 近 30d Response 总数. 作为行业总览的"门面"告诉用户"这个行业多大"。
 */
import React from 'react';

function formatCompact(n) {
  if (n == null) return '—';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function IndustryHero({
  industryName,
  brandCount,
  topicCount,
  categoryCount,
  responseCount,
}) {
  const stats = [
    { label: '覆盖品牌', value: brandCount, suffix: '' },
    { label: '活跃 Topic', value: topicCount, suffix: '' },
    { label: '品类 (三级)', value: categoryCount, suffix: '' },
    { label: '近 30 天 Response', value: responseCount, suffix: '', compact: true },
  ];

  return (
    <div className="flex items-baseline justify-between gap-4 pb-4 border-b border-themed-subtle">
      <div>
        <h1 className="text-xl font-semibold text-themed-primary">
          {industryName || '行业总览'}
        </h1>
        <p className="text-xs text-themed-muted mt-1">
          行业宏观横向视角 · 品牌分布 · 集团版图 · 领导者识别
        </p>
      </div>
      <div className="flex gap-6">
        {stats.map((s) => (
          <div key={s.label} className="text-right">
            <div className="text-2xl font-semibold text-themed-primary tabular-nums">
              {s.compact ? formatCompact(s.value) : (s.value ?? '—')}
              {s.suffix}
            </div>
            <div className="text-[11px] text-themed-muted mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
