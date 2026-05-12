import React from 'react'

import { Badge, Card } from '../../components/ui'
import {
  APP_ANALYZER_CHART_CONTRACTS,
  analyzerContractPages,
  analyzerContractStatusTotals,
  type AnalyzerChartContract,
} from '../../data/appChartDataContract'

const STATUS_STYLES = {
  ok: 'green',
  partial: 'orange',
  empty: 'default',
} as const

function TextList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item} className="leading-snug">
          {item}
        </li>
      ))}
    </ul>
  )
}

function StatusCell({
  label,
  text,
}: {
  label: keyof typeof STATUS_STYLES
  text: string
}) {
  return (
    <div className="min-w-[190px] space-y-1">
      <Badge variant={STATUS_STYLES[label]} size="xs">
        {label}
      </Badge>
      <p className="text-[11px] leading-snug text-themed-muted">{text}</p>
    </div>
  )
}

function MatrixRow({ item }: { item: AnalyzerChartContract }) {
  return (
    <tr>
      <td className="align-top">
        <div className="font-semibold text-themed-primary">{item.page}</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {item.prdRefs.map((ref) => (
            <Badge key={ref} variant="info" size="xs">
              {ref}
            </Badge>
          ))}
        </div>
      </td>
      <td className="align-top">
        <div className="font-medium text-themed-primary">{item.chartKpi}</div>
        <code className="mt-1 block text-[11px] text-themed-muted">{item.metricKey}</code>
      </td>
      <td className="align-top text-[11px] leading-snug text-themed-muted">{item.numerator}</td>
      <td className="align-top text-[11px] leading-snug text-themed-muted">{item.denominator}</td>
      <td className="align-top text-[11px] text-themed-muted">
        <TextList items={item.requiredSourceFacts} />
      </td>
      <td className="align-top text-[11px] text-themed-muted">
        <TextList items={item.optionalSourceFacts} />
      </td>
      <td className="align-top text-[11px] leading-snug text-themed-muted">{item.acceptedValueScale}</td>
      <td className="align-top text-[11px] leading-snug text-themed-muted">{item.failureState}</td>
      <td className="align-top">
        <StatusCell label="ok" text={item.visibleBehavior.ok} />
      </td>
      <td className="align-top">
        <StatusCell label="partial" text={item.visibleBehavior.partial} />
      </td>
      <td className="align-top">
        <StatusCell label="empty" text={item.visibleBehavior.empty} />
      </td>
    </tr>
  )
}

function PageSummary() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Card className="p-3">
        <div className="text-[11px] uppercase tracking-wide text-themed-muted">Routes</div>
        <div className="mt-1 text-2xl font-brand font-bold text-themed-primary tabular-nums">
          {analyzerContractStatusTotals.pages.size}
        </div>
      </Card>
      <Card className="p-3">
        <div className="text-[11px] uppercase tracking-wide text-themed-muted">Rows</div>
        <div className="mt-1 text-2xl font-brand font-bold text-themed-primary tabular-nums">
          {analyzerContractStatusTotals.rows}
        </div>
      </Card>
      <Card className="p-3">
        <div className="text-[11px] uppercase tracking-wide text-themed-muted">PRD IDs</div>
        <div className="mt-1 text-2xl font-brand font-bold text-themed-primary tabular-nums">
          {analyzerContractStatusTotals.prdRefs.size}
        </div>
      </Card>
      <Card className="p-3">
        <div className="text-[11px] uppercase tracking-wide text-themed-muted">States</div>
        <div className="mt-2 flex gap-1.5">
          <Badge variant="green" size="sm">ok</Badge>
          <Badge variant="orange" size="sm">partial</Badge>
          <Badge variant="default" size="sm">empty</Badge>
        </div>
      </Card>
    </div>
  )
}

export default function AppAnalyzerContractPage() {
  return (
    <div className="space-y-4 pb-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="accent" size="sm">Refs #481</Badge>
          <Badge variant="accent" size="sm">Refs #600</Badge>
          <Badge variant="orange" size="sm">Frontend visualization</Badge>
        </div>
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            Analyzer chart data contract
          </h2>
          <p className="mt-1 max-w-5xl text-sm leading-relaxed text-themed-muted">
            Every row below is a frontend demand contract for analyzer-backed App data across{' '}
            {analyzerContractPages.join(', ')}.
          </p>
        </div>
      </header>

      <PageSummary />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4 border-l-4" style={{ borderLeftColor: 'var(--color-warning)' }}>
          <h3 className="text-sm font-semibold text-themed-primary">SoV reset rule</h3>
          <p className="mt-2 text-sm leading-relaxed text-themed-muted">
            SoV requires response-level competitive brand extraction from the response content,
            not target-only mentions or stale aggregate fallback. Configured competitors are
            hints, not the denominator.
          </p>
        </Card>
        <Card className="p-4 border-l-4" style={{ borderLeftColor: 'var(--color-accent)' }}>
          <h3 className="text-sm font-semibold text-themed-primary">Sentiment reset rule</h3>
          <p className="mt-2 text-sm leading-relaxed text-themed-muted">
            Sentiment needs score, label, driver, and source quote provenance for explanatory
            modules to be ok. Score-only evidence stays partial where the UI explains why
            sentiment moved.
          </p>
        </Card>
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Chart inventory matrix</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="t-table w-full min-w-[1800px]">
            <thead>
              <tr>
                <th>Page</th>
                <th>Chart/KPI</th>
                <th>Numerator</th>
                <th>Denominator</th>
                <th>Required source facts</th>
                <th>Optional source facts</th>
                <th>Accepted value scale</th>
                <th>Failure state</th>
                <th>ok</th>
                <th>partial</th>
                <th>empty</th>
              </tr>
            </thead>
            <tbody>
              {APP_ANALYZER_CHART_CONTRACTS.map((item) => (
                <MatrixRow key={`${item.page}:${item.metricKey}`} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
