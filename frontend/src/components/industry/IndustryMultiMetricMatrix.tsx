/**
 * IndustryMultiMetricMatrix — PRD §4.6.1f §B 段 ④
 * ──────────────────────────────────────────────────
 * Top 15 品牌 × (PANO / SoV / 引用 / 情感) 4 列排名 + "排名离散度 σ" 列.
 * 主品牌行高亮; rank pill 按段位着色 (top-3 绿 / mid 灰 / bottom 红).
 * 点击任何列可排序 (默认按 综合 PANO rank 升序).
 *
 * σ (dispersion) 来自 statistics.rankDispersion — 4 列 rank 的标准差,
 * 高 σ = 综合排但单项表现不稳.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { rankDispersion } from '../../lib/industry/statistics';
import { MetricLabel } from '../ui';

const FIELDS = [
  { key: 'panoScore', label: '综合' },
  { key: 'sov', label: 'SoV' },
  { key: 'citationShare', label: '引用' },
  { key: 'sentiment', label: '情感' },
];

function rankPillStyle(rank, total) {
  if (rank == null) return { background: 'var(--color-surface-subtle)', color: 'var(--color-text-muted)' };
  const pct = rank / Math.max(total, 1);
  if (rank <= 3) return { background: 'color-mix(in srgb, var(--color-success) 15%, transparent)', color: 'var(--color-success)' };
  if (pct <= 0.5) return { background: 'var(--color-surface-subtle)', color: 'var(--color-text-primary)' };
  return { background: 'color-mix(in srgb, var(--color-danger) 12%, transparent)', color: 'var(--color-danger)' };
}

export default function IndustryMultiMetricMatrix({
  brands = [],
  primaryBrandId = null,
  limit = 15,
}) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState('panoScore');

  // Pre-compute ranks per field for every brand
  const rankMap = useMemo(() => {
    const out = {};
    for (const field of FIELDS.map((f) => f.key)) {
      const sorted = [...brands]
        .filter((b) => typeof b[field] === 'number')
        .sort((a, b) => b[field] - a[field]);
      sorted.forEach((b, i) => {
        if (!out[b.id]) out[b.id] = {};
        out[b.id][field] = i + 1;
      });
    }
    return out;
  }, [brands]);

  const rows = useMemo(() => {
    const withRanks = brands.map((b) => {
      const ranks = rankMap[b.id] || {};
      const { sigma } = rankDispersion(
        b,
        brands,
        FIELDS.map((f) => f.key)
      );
      return { ...b, ranks, sigma };
    });
    const sortField = sortKey === 'sigma' ? 'sigma' : sortKey;
    const sorted = withRanks.sort((a, b) => {
      if (sortField === 'sigma') return b.sigma - a.sigma;
      const ra = a.ranks[sortField] ?? 9999;
      const rb = b.ranks[sortField] ?? 9999;
      return ra - rb;
    });
    return sorted.slice(0, limit);
  }, [brands, rankMap, sortKey, limit]);

  const total = brands.length;

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            <MetricLabel helpText="按 PANO、SoV、引用和情感四个口径比较品牌排名。">
              多指标交叉排名矩阵
            </MetricLabel>
          </div>
        </div>
        <div className="text-[11px] text-themed-muted">Top {rows.length}</div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-[11px] text-themed-muted">
              <th className="text-left font-normal pb-2 pr-2">品牌</th>
              {FIELDS.map((f) => (
                <th
                  key={f.key}
                  className="text-center font-normal pb-2 px-1 cursor-pointer hover:text-themed-primary"
                  onClick={() => setSortKey(f.key)}
                >
                  <MetricLabel helpText={`${f.label} 口径下的行业排名。`}>
                    {f.label} {sortKey === f.key ? '↓' : ''}
                  </MetricLabel>
                </th>
              ))}
              <th
                className="text-center font-normal pb-2 pl-1 cursor-pointer hover:text-themed-primary"
                onClick={() => setSortKey('sigma')}
              >
                <MetricLabel helpText="多个指标排名的标准差；数值越高说明单项表现越不均衡。">
                  σ 离散度 {sortKey === 'sigma' ? '↓' : ''}
                </MetricLabel>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const isPrimary = b.id === primaryBrandId;
              return (
                <tr
                  key={b.id}
                  className="border-t border-themed-subtle cursor-pointer hover:bg-themed-subtle"
                  style={
                    isPrimary
                      ? { background: 'color-mix(in srgb, var(--color-primary) 8%, transparent)' }
                      : undefined
                  }
                  onClick={() =>
                    navigate(`/brand/overview?brandId=${b.id}`)
                  }
                >
                  <td className="py-2 pr-2">
                    <div className="flex items-center gap-2">
                      {isPrimary && (
                        <span
                          className="text-[10px] font-semibold"
                          style={{ color: 'var(--color-primary)' }}
                        >
                          ▲
                        </span>
                      )}
                      <div>
                        <div className="text-themed-primary font-medium">
                          {b.name}
                        </div>
                        <div className="text-[10px] text-themed-muted">
                          {b.positioning}
                        </div>
                      </div>
                    </div>
                  </td>
                  {FIELDS.map((f) => {
                    const r = b.ranks[f.key];
                    return (
                      <td key={f.key} className="text-center px-1 py-2">
                        <span
                          className="inline-block px-1.5 py-0.5 rounded-full text-[11px] tabular-nums font-medium"
                          style={rankPillStyle(r, total)}
                        >
                          {r != null ? `#${r}` : '—'}
                        </span>
                      </td>
                    );
                  })}
                  <td className="text-center pl-1 py-2 tabular-nums text-themed-primary">
                    {b.sigma.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
