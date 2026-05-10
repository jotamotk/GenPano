import React from 'react';
import { Card, Badge, MetricLabel } from '../ui';

/* ─────────────────────────────────────────────────────────────
   SameGroupAndAcquisition — PRD §4.2.7.D v1.1
   ─────────────────────────────────────────────────────────────
   两个轻量信息块:
     ① Same-Group 共享域名 (同集团兄弟品牌共享的官域)
     ② Acquisition Event Stream (近 30 天新 Tier 1+2 来源首次出现)
─────────────────────────────────────────────────────────────── */

/* ─────── Same-Group ─────── */
function SameGroupCard({ data }) {
  if (!data || !data.group) return null;
  const externalShared = (data.sharedDomains || []).filter(
    (d) => !d.sharedWith?.includes(data.currentBrand)
  );
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-themed-primary">
            <MetricLabel helpText={`集团: ${data.group}；同集团品牌共享引用比例 ${(data.sharedRatio * 100).toFixed(0)}%。`}>
              同集团共享资产
            </MetricLabel>
          </h3>
        </div>
        <Badge variant="accent" size="sm">
          共享 {externalShared.length} 个兄弟官域
        </Badge>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {data.siblingBrands.map((b) => (
          <span
            key={b}
            className="px-2.5 py-1 rounded-pill text-xs"
            style={{
              background: 'var(--color-bg-subtle-2)',
              color: 'var(--color-text-secondary)',
            }}
          >
            {b}
          </span>
        ))}
      </div>

      <ul className="space-y-2">
        {externalShared.map((d) => (
          <li
            key={d.domain}
            className="flex items-center justify-between text-sm"
          >
            <span className="text-themed-primary font-medium">{d.domain}</span>
            <span className="flex items-center gap-2">
              <Badge variant="accent" size="sm">T{d.tier}</Badge>
              <span className="text-[11px] text-themed-muted">
                共享于 {d.sharedWith?.join(', ')}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* ─────── Acquisition Stream ─────── */
function AcquisitionStream({ events }) {
  if (!events?.length) return null;
  return (
    <Card className="p-5">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-themed-primary">
          <MetricLabel helpText="Tier 1+2 域名首次把你引到 AI 回答里，每一条都是权威背书的新增量。">
            新获得的权威来源 · 近 30 天
          </MetricLabel>
        </h3>
      </div>
      <ol className="relative border-l-2 border-themed-subtle pl-5 space-y-4">
        {events.map((ev) => (
          <li key={`${ev.date}-${ev.domain}`} className="relative">
            <span
              className="absolute -left-[27px] w-3 h-3 rounded-full"
              style={{
                background:
                  ev.tier === 1
                    ? 'var(--color-success)'
                    : 'var(--color-accent)',
                border: '2px solid var(--color-bg-card)',
                boxShadow: '0 0 0 1.5px var(--color-border-subtle)',
              }}
            />
            <div className="flex items-start gap-3 flex-wrap">
              <span className="text-[11px] text-themed-muted tabular-nums shrink-0">
                {ev.date}
              </span>
              <span className="text-sm font-medium text-themed-primary">
                {ev.domain}
              </span>
              <Badge
                variant={ev.tier === 1 ? 'accent' : 'orange'}
                size="sm"
              >
                T{ev.tier}
              </Badge>
            </div>
            {ev.note && (
              <p className="text-xs text-themed-secondary mt-1 leading-relaxed">
                {ev.note}
              </p>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

/* ─────── Umbrella ─────── */
export default function SameGroupAndAcquisition({
  sameGroup,
  acquisitionEvents = [],
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <SameGroupCard data={sameGroup} />
      <AcquisitionStream events={acquisitionEvents} />
    </div>
  );
}

export { SameGroupCard, AcquisitionStream };
