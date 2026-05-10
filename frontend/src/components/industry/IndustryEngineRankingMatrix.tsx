/**
 * IndustryEngineRankingMatrix — PRD §4.6.1f §B 段 ⑥
 * ─────────────────────────────────────────────────────
 * Top 10 品牌 × 3 引擎 (ChatGPT / 豆包 / DeepSeek) rank heatmap.
 * 格子 = 排名 #N, 色深按排名 (越靠前色越深, sequential heatmap seq-0..5).
 * 尾列 ΔMax = 3 引擎最大 - 最小 (波动越大颜色越重).
 * 行 click → /brand/overview?brandId=:id&engines=:engine (带引擎筛选).
 *
 * 色带契约 C9-1: 只用 --color-heatmap-seq-0..5, 禁借 chart-N / sentiment-*.
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { rankingByEngine } from '../../lib/industry/statistics';
import { MetricLabel } from '../ui';

const ENGINES = [
  { key: 'chatgpt', label: 'ChatGPT' },
  { key: 'doubao', label: '豆包' },
  { key: 'deepseek', label: 'DeepSeek' },
];

function intensityBucket(rank, maxRank) {
  if (rank == null) return 0;
  const pct = rank / Math.max(maxRank, 1);
  if (pct <= 0.15) return 5;
  if (pct <= 0.3) return 4;
  if (pct <= 0.5) return 3;
  if (pct <= 0.7) return 2;
  if (pct <= 0.85) return 1;
  return 0;
}

function bucketBg(bucket) {
  return `var(--color-heatmap-seq-${bucket})`;
}

function bucketFg(bucket) {
  return bucket >= 3 ? '#fff' : 'var(--color-text-primary)';
}

export default function IndustryEngineRankingMatrix({
  brands = [],
  primaryBrandId = null,
  limit = 10,
}) {
  const navigate = useNavigate();

  const rows = useMemo(() => {
    const topBrands = [...brands]
      .sort((a, b) => (b.panoScore || 0) - (a.panoScore || 0))
      .slice(0, limit);
    return topBrands.map((b) => {
      const engineRanks = rankingByEngine(b) || {
        chatgpt: null,
        doubao: null,
        deepseek: null,
        maxDelta: 0,
      };
      return { ...b, engineRanks };
    });
  }, [brands, limit]);

  const totalBrands = brands.length;

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            <MetricLabel helpText="比较同一品牌在不同 AI 引擎上的行业排名差异。">
              引擎分位矩阵
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
              {ENGINES.map((e) => (
                <th
                  key={e.key}
                  className="text-center font-normal pb-2 px-1"
                  style={{ minWidth: 72 }}
                >
                <MetricLabel helpText={`${e.label} 中的品牌行业排名。`}>
                  {e.label}
                </MetricLabel>
                </th>
              ))}
              <th
                className="text-center font-normal pb-2 pl-1"
                style={{ minWidth: 80 }}
              >
                <MetricLabel helpText="三个引擎排名中的最大差值，越大表示引擎间波动越明显。">
                  ΔMax
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
                  className="border-t border-themed-subtle"
                  style={
                    isPrimary
                      ? { background: 'color-mix(in srgb, var(--color-primary) 8%, transparent)' }
                      : undefined
                  }
                >
                  <td className="py-1.5 pr-2">
                    <div className="flex items-center gap-2">
                      {isPrimary && (
                        <span
                          className="text-[10px] font-semibold"
                          style={{ color: 'var(--color-primary)' }}
                        >
                          ▲
                        </span>
                      )}
                      <div className="text-themed-primary font-medium">
                        {b.name}
                      </div>
                    </div>
                  </td>
                  {ENGINES.map((e) => {
                    const r = b.engineRanks[e.key];
                    const bucket = intensityBucket(r, totalBrands);
                    return (
                      <td
                        key={e.key}
                        className="text-center px-1 py-1.5 cursor-pointer"
                        onClick={() =>
                          navigate(
                            `/brand/overview?brandId=${b.id}&engines=${e.key}`
                          )
                        }
                      >
                        <div
                          className="rounded-card tabular-nums text-[12px] font-semibold py-1.5"
                          style={{
                            background: bucketBg(bucket),
                            color: bucketFg(bucket),
                          }}
                        >
                          {r != null ? `#${r}` : '—'}
                        </div>
                      </td>
                    );
                  })}
                  <td className="text-center pl-1 py-1.5 tabular-nums">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-[11px]"
                      style={{
                        background:
                          b.engineRanks.maxDelta >= 4
                            ? 'color-mix(in srgb, var(--color-warning) 20%, transparent)'
                            : 'var(--color-surface-subtle)',
                        color:
                          b.engineRanks.maxDelta >= 4
                            ? 'var(--color-warning)'
                            : 'var(--color-text-primary)',
                      }}
                    >
                      {b.engineRanks.maxDelta}
                    </span>
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
