/**
 * IndustryTopCitationDomains — PRD §4.6.1e §B 段 ⑧ (v2 新增)
 * ─────────────────────────────────────────────────
 * 行业 Top 10 引用源. 列: 域名 / 引用数 / 份额 / 权威 Tier / 覆盖品牌数 /
 * 我是否被此源引用. Tier badge 分色 (Tier 1 官方 / 2 权威媒体 /
 * 3 KOL / 4 UGC).
 *
 * 复用 TOP_CITED_DOMAINS mock (已存在).
 * 回答: "我要做 PR 该打哪些媒体? 我在这些源里有没有被引用?"
 */
import React, { useMemo } from 'react';
import Badge from '../ui/Badge';
import { MetricLabel } from '../ui';

const TIER_LABEL = {
  0: '未知',
  1: '官方',
  2: '权威媒体',
  3: 'KOL',
  4: 'UGC',
};
const TIER_VARIANT = {
  0: 'default',
  1: 'green',
  2: 'blue',
  3: 'purple',
  4: 'orange',
};

function Bar({ value, max }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-16 h-1.5 rounded-full bg-themed-subtle/50 overflow-hidden">
      <div
        className="h-full bg-[var(--color-accent)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function IndustryTopCitationDomains({
  domains = [],
  primaryBrandId = null,
  limit = 10,
}) {
  const rows = useMemo(() => {
    return [...domains]
      .filter((d) => d.domain !== 'others')
      .sort((a, b) => b.citations - a.citations)
      .slice(0, limit);
  }, [domains, limit]);

  const maxCitations = rows[0]?.citations || 1;

  if (!rows.length) {
    return (
      <div className="t-card p-3 text-xs text-themed-muted">
        引用源数据暂无
      </div>
    );
  }

  const myAttributedCount = rows.filter((r) =>
    (r.brandsAttributed || []).includes(primaryBrandId)
  ).length;

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            <MetricLabel helpText="按行业内被 AI 回答引用的次数排序，用于识别 PR 和内容合作候选源。">
              行业 Top {limit} 引用源
            </MetricLabel>
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            {primaryBrandId && (
              <>
                <MetricLabel helpText="Top 引用源中已经引用主品牌的来源数量。">我被引用</MetricLabel>{' '}
                <span
                  className={
                    myAttributedCount >= limit / 2
                      ? 'text-[var(--color-success)]'
                      : 'text-[var(--color-warning)]'
                  }
                >
                  {myAttributedCount}/{limit}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <table className="t-table w-full text-[13px]">
        <thead>
          <tr className="text-[11px] text-themed-muted">
            <th className="text-left py-1.5">域名</th>
            <th className="text-left py-1.5">权威</th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="该域名在行业 AI 回答中被引用的次数。">引用</MetricLabel>
            </th>
            <th className="py-1.5 w-20"></th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="该域名引用量占 Top 引用源总量的比例。">份额</MetricLabel>
            </th>
            <th className="text-right py-1.5">
              <MetricLabel helpText="该域名引用覆盖到的品牌数量。">覆盖品牌</MetricLabel>
            </th>
            <th className="text-center py-1.5">我</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => {
            const iAmThere = (d.brandsAttributed || []).includes(
              primaryBrandId
            );
            return (
              <tr
                key={d.domain}
                className={`transition-colors ${
                  primaryBrandId && !iAmThere
                    ? 'bg-themed-subtle/20'
                    : ''
                }`}
              >
                <td className="py-1.5">
                  <div className="text-themed-primary font-medium truncate max-w-[180px]">
                    {d.domain}
                  </div>
                </td>
                <td className="py-1.5">
                  <Badge
                    variant={TIER_VARIANT[d.authorityTier] || 'default'}
                    size="xs"
                  >
                    T{d.authorityTier} {TIER_LABEL[d.authorityTier]}
                  </Badge>
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {d.citations}
                </td>
                <td className="py-1.5">
                  <Bar value={d.citations} max={maxCitations} />
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {d.share.toFixed(1)}%
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {(d.brandsAttributed || []).length}
                </td>
                <td className="py-1.5 text-center">
                  {primaryBrandId ? (
                    iAmThere ? (
                      <span className="text-[var(--color-success)] text-xs">✓</span>
                    ) : (
                      <span className="text-[var(--color-warning)] text-xs">
                        ○
                      </span>
                    )
                  ) : (
                    <span className="text-themed-muted text-xs">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
