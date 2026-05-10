/**
 * IndustryLeaderboardTable — PRD §4.6.1e §B 段 ④ (左表)
 * ─────────────────────────────────────────────────
 * Top 10 品牌 leaderboard. 列: 排名 / 品牌 / PANO / 提及率 / SoV / 情感 /
 * 引用份额 / Δ30d. 支持简单 sort 切换 (默认按 panoScore desc). 点击行
 * 跳 /brand/overview?brandId=:id.
 *
 * 主品牌行带左侧 accent bar 高亮.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MetricLabel } from '../ui';

const SORT_KEYS = [
  { key: 'panoScore',     label: 'PANO',    format: (v) => Math.round(v) },
  { key: 'mentionRate',   label: '提及率',  format: (v) => `${(v * 100).toFixed(1)}%` },
  { key: 'sov',           label: 'SoV',     format: (v) => `${v.toFixed(1)}%` },
  { key: 'sentiment',     label: '情感',    format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: 'citationShare', label: '引用份额', format: (v) => `${v.toFixed(1)}%` },
];

export default function IndustryLeaderboardTable({
  brands = [],
  primaryBrandId = null,
  limit = 10,
}) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState('panoScore');

  const rows = useMemo(() => {
    return [...brands]
      .sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0))
      .slice(0, limit);
  }, [brands, sortKey, limit]);

  if (!rows.length) {
    return (
      <div className="t-card p-4 text-xs text-themed-muted">暂无品牌数据</div>
    );
  }

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[13px] font-medium text-themed-primary">
          Top {limit} 品牌
        </div>
        <div className="flex gap-1">
          {SORT_KEYS.map((sk) => (
            <button
              key={sk.key}
              onClick={() => setSortKey(sk.key)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                sortKey === sk.key
                  ? 'bg-[var(--color-accent)]/15 text-[var(--color-accent)] font-medium'
                  : 'text-themed-muted hover:text-themed-primary'
              }`}
            >
              {sk.label}
            </button>
          ))}
        </div>
      </div>
      <table className="t-table w-full text-[13px]">
        <thead>
          <tr className="text-[11px] text-themed-muted">
            <th className="text-left py-1.5 w-8">#</th>
            <th className="text-left py-1.5">品牌</th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="品牌在 AI 回答中的综合表现分。">PANO</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="基于品类通用问题计算，排除直接询问品牌的问题。">提及率</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="在已命中任一品牌的回答中，该品牌占有的声量份额。">SoV</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="品牌相关回答的情感加权平均。">情感</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="品牌相关回答中的引用份额。">引用</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="近 30 天该品牌排名或分数的变化。">Δ30d</MetricLabel>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, idx) => {
            const isPrimary = b.id === primaryBrandId;
            const changeNum = parseFloat(b.change || '0');
            return (
              <tr
                key={b.id}
                onClick={() =>
                  navigate(`/brand/overview?brandId=${b.id}`)
                }
                className={`cursor-pointer transition-colors hover:bg-themed-subtle/40 ${
                  isPrimary
                    ? 'bg-[var(--color-accent)]/5'
                    : ''
                }`}
              >
                <td className="py-1.5 text-themed-muted tabular-nums">
                  {idx + 1}
                </td>
                <td className="py-1.5">
                  <span className="flex items-center gap-1.5">
                    {isPrimary && (
                      <span
                        className="inline-block w-1 h-3 bg-[var(--color-accent)] rounded"
                        aria-label="主品牌"
                      />
                    )}
                    <span className="text-themed-primary">{b.name}</span>
                    {isPrimary && (
                      <span className="text-[10px] text-[var(--color-accent)]">
                        (主品牌)
                      </span>
                    )}
                  </span>
                </td>
                <td className="py-1.5 text-right tabular-nums font-medium">
                  {Math.round(b.panoScore ?? 0)}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {((b.mentionRate ?? 0) * 100).toFixed(1)}%
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {(b.sov ?? 0).toFixed(1)}%
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {Math.round((b.sentiment ?? 0) * 100)}%
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {(b.citationShare ?? 0).toFixed(1)}%
                </td>
                <td
                  className={`py-1.5 text-right tabular-nums ${
                    changeNum > 0
                      ? 'text-[var(--color-success)]'
                      : changeNum < 0
                      ? 'text-[var(--color-danger)]'
                      : 'text-themed-muted'
                  }`}
                >
                  {b.change || '0'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
