import React, { useMemo, useState } from 'react';
import { Card, Badge, Button, MetricLabel } from '../ui';

/* ─────────────────────────────────────────────────────────────
   PrTargetsPanel — PRD §4.2.7.C 外联 PR 候选清单 + Tier2 矩阵 + KOL 评分卡
   ─────────────────────────────────────────────────────────────
   三个子区块:
     ① PR 候选表 — 按 pr_score 降序, 支持按 "未覆盖 / 全部" 过滤
     ② Tier 2 权威媒体覆盖矩阵 — 行=域, 列=我 + Top 3 竞品
     ③ KOL 评分卡 (Tier 3) — Shannon 多样性 + 每周被引次数

   pr_score 公式 (PRD §4.2.7.C, 展示用途不重算):
     tier_weight × (competitorsCovered/total)^0.7
     × (1 + 0.4 × max(0, trending30dPct/100))
     × (1 if uncovered else 0.3)

   Layer-3 边界 (§4.8.6): 不给"发文流程", 不给价格区间, 只给"值得考察的候选".
─────────────────────────────────────────────────────────────── */

const TIER_LABEL = { 0: '未知', 1: '官方', 2: '权威媒体', 3: 'KOL', 4: 'UGC' };
const TIER_COLOR = {
  0: 'default',
  1: 'accent',
  2: 'orange',
  3: 'red',
  4: 'default',
};

/* ─────── ① PR 候选表 ─────── */
function PrCandidatesTable({ targets }) {
  const [excludeCovered, setExcludeCovered] = useState(true);

  const rows = useMemo(() => {
    return targets.filter((r) =>
      excludeCovered ? r.attributedToMeCount === 0 : true
    );
  }, [targets, excludeCovered]);

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-themed-subtle flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-themed-primary">
            <MetricLabel helpText='按"权威 × 竞品覆盖 × 近 30 天趋势"打分，用于发稿、合作或授权的投入决策。'>
              值得考察的外联域名 Top {rows.length}
            </MetricLabel>
          </h3>
        </div>
        <label className="flex items-center gap-2 text-xs text-themed-muted cursor-pointer">
          <input
            type="checkbox"
            checked={excludeCovered}
            onChange={(e) => setExcludeCovered(e.target.checked)}
            className="accent-[var(--color-accent)]"
          />
          只看你还没覆盖的
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full t-table">
          <thead>
            <tr>
              <th className="text-left py-2.5 px-5 text-xs font-medium text-themed-muted">域名</th>
              <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">层级</th>
              <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                <MetricLabel helpText="该域名近周期覆盖的竞品数量。">竞品覆盖</MetricLabel>
              </th>
              <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                <MetricLabel helpText="近 30 天该域名在 AI 回答中被引用的次数。">30 天被引</MetricLabel>
              </th>
              <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                <MetricLabel helpText="近 30 天引用量相对前期的变化幅度。">趋势</MetricLabel>
              </th>
              <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                <MetricLabel helpText="综合权威层级、竞品覆盖、趋势和自身覆盖状态计算的 PR 候选优先级。">PR 分</MetricLabel>
              </th>
              <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">你当前</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.domain} className="border-t border-themed-subtle hover:bg-themed-subtle transition-colors">
                <td className="py-2.5 px-5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-themed-primary">{r.domain}</span>
                    {r.sameGroupShared && (
                      <Badge variant="default" size="sm">同集团</Badge>
                    )}
                  </div>
                  <span className="text-[11px] text-themed-muted">{r.siteType}</span>
                </td>
                <td className="py-2.5 px-4">
                  <Badge variant={TIER_COLOR[r.authorityTier]} size="sm">
                    T{r.authorityTier} {TIER_LABEL[r.authorityTier]}
                  </Badge>
                </td>
                <td className="py-2.5 px-4 text-right">
                  <span className="text-sm tabular-nums text-themed-primary font-medium">
                    {r.competitorsCount}
                  </span>
                  {r.competitors?.length > 0 && (
                    <div className="text-[11px] text-themed-muted max-w-[160px] truncate inline-block ml-1">
                      {r.competitors.slice(0, 3).join(' · ')}
                      {r.competitors.length > 3 ? '…' : ''}
                    </div>
                  )}
                </td>
                <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                  {r.citations30d}
                </td>
                <td className="py-2.5 px-4 text-right">
                  <span
                    className="text-xs font-medium tabular-nums"
                    style={{
                      color:
                        r.trending30dPct >= 25
                          ? 'var(--color-success)'
                          : r.trending30dPct >= 10
                          ? 'var(--color-accent)'
                          : 'var(--color-text-muted)',
                    }}
                  >
                    {r.trending30dPct >= 0 ? '+' : ''}
                    {r.trending30dPct}%
                  </span>
                </td>
                <td className="py-2.5 px-4 text-right">
                  <span className="text-sm font-semibold tabular-nums text-themed-primary">
                    {r.prScore.toFixed(3)}
                  </span>
                </td>
                <td className="py-2.5 px-4 text-xs text-themed-muted">
                  {r.attributedToMeCount > 0
                    ? `已引用 ${r.attributedToMeCount} 次`
                    : '未覆盖'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-themed-subtle flex items-center justify-between">
        <span className="text-xs text-themed-muted">
          导出完整清单 (50 行) · CSV #9 pr_targets
        </span>
        <Button variant="secondary" size="sm">
          导出 CSV
        </Button>
      </div>
    </Card>
  );
}

/* ─────── ② Tier 2 覆盖矩阵 ─────── */
function Tier2CoverageMatrix({ matrix }) {
  if (!matrix || !matrix.domains?.length) return null;
  const maxVal = useMemo(() => {
    let m = 0;
    matrix.brands.forEach((b) => b.counts.forEach((c) => { if (c > m) m = c; }));
    return m || 1;
  }, [matrix]);

  const heat = (v) => {
    const alpha = 0.08 + (v / maxVal) * 0.72;
    return v === 0 ? 'var(--color-bg-subtle-2)' : `rgba(96, 91, 255, ${alpha.toFixed(2)})`;
  };

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-themed-primary">
          <MetricLabel helpText="对比主品牌与竞品在 Tier 2 权威媒体域名上的引用覆盖。">
            Tier 2 权威媒体覆盖矩阵
          </MetricLabel>
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left px-3 py-2 font-medium text-themed-muted">品牌</th>
              {matrix.domains.map((d) => (
                <th key={d} className="text-center px-2 py-2 font-medium text-themed-muted whitespace-nowrap">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.brands.map((b) => (
              <tr key={b.brandId} className="border-t border-themed-subtle">
                <td className="px-3 py-2 font-medium text-themed-primary">
                  {b.label}
                </td>
                {b.counts.map((c, i) => (
                  <td key={i} className="px-2 py-2 text-center">
                    <span
                      className="inline-flex items-center justify-center rounded-md min-w-[32px] h-7 text-xs tabular-nums"
                      style={{
                        background: heat(c),
                        color: c === 0 ? 'var(--color-text-faint)' : 'var(--color-text-primary)',
                      }}
                    >
                      {c}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─────── ③ KOL 评分卡 (Tier 3) ─────── */
function KolScorecards({ kols }) {
  if (!kols?.length) return null;
  // Shannon entropy max ≈ log2(N); 多样性越高越像"独立声音", 越低越像"竞品独家"
  const divLevel = (d) => {
    if (d >= 2.6) return { label: '高多样性', color: 'var(--color-success)', variant: 'accent' };
    if (d >= 2.0) return { label: '中多样性', color: 'var(--color-accent)', variant: 'accent' };
    return { label: '低多样性 · 可能竞品独家', color: 'var(--color-warning)', variant: 'orange' };
  };

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-themed-primary">
          <MetricLabel helpText="Shannon 多样性 = 该 KOL 近 90 天提到的品牌分散程度；低多样性可能表示竞品独家合作。">
            KOL 多样性评分
          </MetricLabel>
        </h3>
      </div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {kols.map((k) => {
          const lvl = divLevel(k.diversity);
          return (
            <div
              key={k.domain}
              className="rounded-card p-4"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
              }}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-themed-primary truncate">
                    {k.domain}
                  </div>
                  <div className="text-[11px] text-themed-muted tabular-nums">
                    权威置信 {(k.authorityConfidence * 100).toFixed(0)}% · 周均 {k.avgCitationsPerWeek}
                  </div>
                </div>
                <Badge variant={lvl.variant} size="sm">
                  {lvl.label}
                </Badge>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-2xl font-bold tabular-nums text-themed-primary">
                  {k.diversity.toFixed(2)}
                </span>
                <span className="text-[11px] text-themed-muted">
                  / log₂({k.brandDiversity90d.length}) ≈ {Math.log2(Math.max(2, k.brandDiversity90d.length)).toFixed(2)}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                {k.brandDiversity90d.slice(0, 6).map((b) => (
                  <span
                    key={b}
                    className="px-2 py-0.5 rounded-pill text-[11px]"
                    style={{
                      background: 'var(--color-bg-subtle-2)',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    {b}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* ─────── Umbrella Panel ─────── */
export default function PrTargetsPanel({
  targets = [],
  tier2Matrix,
  kolScorecards = [],
}) {
  return (
    <div className="space-y-6">
      <PrCandidatesTable targets={targets} />
      <Tier2CoverageMatrix matrix={tier2Matrix} />
      <KolScorecards kols={kolScorecards} />
    </div>
  );
}

export { PrCandidatesTable, Tier2CoverageMatrix, KolScorecards };
