import { Card, Badge, MetricLabel } from '../ui'

type AnalyticsState = 'ok' | 'partial' | 'empty' | 'error'
type PercentScale = 'decimal' | 'percent'

interface MetricFixture {
  key: string
  label: string
  value: number | null
  scale: PercentScale
  denominator: string
  sourceField: string
  evidence: string
}

interface StateFixture {
  state: AnalyticsState
  label: string
  badge: string
  badgeVariant: string
  summary: string
  metrics: MetricFixture[]
}

const overviewStates: StateFixture[] = [
  {
    state: 'ok',
    label: 'Non-empty',
    badge: 'ok',
    badgeVariant: 'green',
    summary: 'Estee Lauder / 雅诗兰黛 has real eligible responses, brand mentions, competitive-set mentions, sentiment, citations, and PANO trend points.',
    metrics: [
      {
        key: 'mention_rate',
        label: 'Mention rate',
        value: 0.162,
        scale: 'decimal',
        denominator: '70 brand-mentioned responses / 432 non-brand category responses',
        sourceField: 'kpi_cards[].metric_key=mention_rate, value_scale=decimal',
        evidence: 'Shows 16.2%, never 1620%.',
      },
      {
        key: 'sov',
        label: 'SoV',
        value: 38.4,
        scale: 'percent',
        denominator: '70 Estee Lauder mentions / 182 competitive-set brand mentions',
        sourceField: 'kpi_cards[].metric_key=sov, value_scale=percent',
        evidence: 'Different denominator from mention rate.',
      },
      {
        key: 'pano',
        label: 'PANO score',
        value: 78.1,
        scale: 'percent',
        denominator: 'weighted V/R/S/C/A components, 0..100 score',
        sourceField: 'kpi_cards[].metric_key=pano_score, value_scale=score_0_100',
        evidence: 'Trend should contain component coverage, not only final score.',
      },
    ],
  },
  {
    state: 'partial',
    label: 'Partial',
    badge: 'partial',
    badgeVariant: 'orange',
    summary: 'Core visibility metrics are available, but citation authority and product dimensions are not fully produced yet.',
    metrics: [
      {
        key: 'mention_rate',
        label: 'Mention rate',
        value: 0.118,
        scale: 'decimal',
        denominator: '39 brand-mentioned responses / 331 eligible non-brand responses',
        sourceField: 'series.metric=mention_rate, points[].value_scale=decimal',
        evidence: 'Rendered with partial badge and missing-dimension note.',
      },
      {
        key: 'sov',
        label: 'SoV',
        value: 31.7,
        scale: 'percent',
        denominator: '39 Estee Lauder mentions / 123 competitive-set brand mentions',
        sourceField: 'sov_30d[].value, value_scale=percent',
        evidence: 'Still not reused as mention rate.',
      },
      {
        key: 'citation_share',
        label: 'Citation share',
        value: null,
        scale: 'percent',
        denominator: 'citation_sources joined to brand mentions',
        sourceField: 'missing_reasons[].field=citation_share',
        evidence: 'Shown as partial, not 0%.',
      },
    ],
  },
  {
    state: 'empty',
    label: 'Empty',
    badge: 'empty',
    badgeVariant: 'default',
    summary: 'The project has no eligible non-brand category responses in the selected window, so charts explain missing source data.',
    metrics: [
      {
        key: 'mention_rate',
        label: 'Mention rate',
        value: null,
        scale: 'decimal',
        denominator: '0 eligible non-brand category responses',
        sourceField: 'state=empty, evidence_counts.eligible_response_count=0',
        evidence: 'No fake zero; card reads no eligible source data.',
      },
      {
        key: 'sov',
        label: 'SoV',
        value: null,
        scale: 'percent',
        denominator: '0 competitive-set brand mentions',
        sourceField: 'evidence_counts.competitive_mention_count=0',
        evidence: 'No donut segment pretending the brand has 0 share.',
      },
      {
        key: 'pano',
        label: 'PANO score',
        value: null,
        scale: 'percent',
        denominator: 'no scored aggregation rows',
        sourceField: 'missing_reasons[].field=pano_score',
        evidence: 'Shows empty chart state with recovery hint.',
      },
    ],
  },
  {
    state: 'error',
    label: 'Error',
    badge: 'error',
    badgeVariant: 'red',
    summary: 'The API request failed or returned an invalid metric contract; the page shows an actionable error state instead of stale mock truth.',
    metrics: [
      {
        key: 'overview_api',
        label: 'Overview API',
        value: null,
        scale: 'percent',
        denominator: 'GET /api/v1/projects/:project_id/overview?brand_id=:brand_id',
        sourceField: 'request_id, status_code, message',
        evidence: 'Preserves request_id for Release/CI and QA follow-up.',
      },
      {
        key: 'contract_guard',
        label: 'Contract guard',
        value: null,
        scale: 'percent',
        denominator: 'metric values must declare value_scale',
        sourceField: 'invalid_fields[]',
        evidence: 'Blocks ambiguous 16.2 vs 0.162 rendering.',
      },
      {
        key: 'fallback_policy',
        label: 'Fallback policy',
        value: null,
        scale: 'percent',
        denominator: 'live project mode',
        sourceField: 'state=error',
        evidence: 'Do not silently mix mock data into live charts.',
      },
    ],
  },
]

const pageInventory = [
  {
    page: '/brand/overview',
    target: 'First Estee Lauder vertical slice: KPI cards, PANO trend, SoV donut, sentiment trend, competitor bubble, diagnostics.',
    state: 'Visualized here: ok / partial / empty / error.',
    handoff: '/overview, /metrics, /competitors/metrics, /competitors/trends, /diagnostics, /group-shared-domains',
  },
  {
    page: '/brand/visibility',
    target: 'Mention rate and SoV must remain separate in KPI cards, per-engine bars, position distribution, and topic heatmap.',
    state: 'Needs Backend API fields for denominators and value_scale before integration.',
    handoff: '/metrics, /metrics/by-engine, /position-distribution, /topic-heatmap?metric=mention_rate',
  },
  {
    page: '/brand/sentiment',
    target: 'Sentiment distribution, by-engine stack, trend-by-engine, topic heatmap, attribution, and samples.',
    state: 'Partial until sentiment counts and sample evidence are populated.',
    handoff: '/sentiment, /sentiment/by-engine, /sentiment/trend-by-engine, /sentiment/topic-attribution, /mention-samples',
  },
  {
    page: '/brand/citations',
    target: 'Authority trend, composition, top domains/pages, content gaps, PR targets, and simulator baseline.',
    state: 'Partial or empty when authority tiers, attribution type, or page type are missing.',
    handoff: '/citations, /citations/authority-trend, /citations/composition, /citations/content-gap, /citations/pr-targets',
  },
  {
    page: '/brand/products',
    target: 'Product bubble, product list metrics, sparklines, features/scenarios, and product relations.',
    state: 'Empty if no product-linked mention facts exist.',
    handoff: '/products, /products/relations',
  },
  {
    page: '/brand/competitors',
    target: 'Threat cards, PANO/SoV/sentiment/citation comparisons, authority radar, topic heatmap, and same-group domains.',
    state: 'Partial when competitor set or group-domain facts are missing.',
    handoff: '/competitors/metrics, /competitors/trends, /competitors/authority-radar, /topic-heatmap, /group-shared-domains',
  },
]

const payloadFields = [
  'project_id',
  'primary_brand_id',
  'brand_id',
  'brand_name',
  'period.from',
  'period.to',
  'state',
  'state_reason',
  'request_id',
  'data_freshness.generated_at',
  'evidence_counts.eligible_response_count',
  'evidence_counts.brand_mentioned_response_count',
  'evidence_counts.competitive_mention_count',
  'kpi_cards[].metric_key',
  'kpi_cards[].label_zh',
  'kpi_cards[].label_en',
  'kpi_cards[].value',
  'kpi_cards[].value_scale',
  'kpi_cards[].unit',
  'kpi_cards[].delta_30d_pct',
  'kpi_cards[].denominator_label',
  'series[].metric',
  'series[].value_scale',
  'series[].points[].date',
  'series[].points[].value',
  'geo_score_30d[].date',
  'geo_score_30d[].value',
  'geo_score_30d[].components.visibility',
  'geo_score_30d[].components.rank',
  'geo_score_30d[].components.sentiment',
  'geo_score_30d[].components.citation',
  'sov_30d[].date',
  'sov_30d[].value',
  'sentiment_30d[].date',
  'sentiment_30d[].value',
  'top_prompts[].prompt_text',
  'top_prompts[].mention_count',
  'top_prompts[].avg_position_rank',
  'missing_reasons[].field',
  'missing_reasons[].reason',
  'invalid_fields[].field',
  'invalid_fields[].reason',
]

export function formatMetricPercent(value: number | null, scale: PercentScale): string {
  if (value == null || !Number.isFinite(value)) return 'No source data'
  const pct = scale === 'decimal' ? value * 100 : value
  return `${pct.toFixed(1)}%`
}

function StateBadge({ state, variant }: { state: AnalyticsState; variant: string }) {
  return (
    <Badge variant={variant} size="sm" className="uppercase">
      {state}
    </Badge>
  )
}

function MetricRow({ metric }: { metric: MetricFixture }) {
  return (
    <div className="rounded-md border p-3" style={{ borderColor: 'var(--color-border-subtle)' }}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <MetricLabel helpText={`${metric.denominator}. Source: ${metric.sourceField}`}>
            <span className="text-sm font-semibold text-themed-primary">{metric.label}</span>
          </MetricLabel>
          <p className="mt-1 text-[11px] text-themed-muted">{metric.denominator}</p>
        </div>
        <span className="text-lg font-bold tabular-nums text-themed-primary whitespace-nowrap">
          {formatMetricPercent(metric.value, metric.scale)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
        <span className="rounded px-2 py-1 text-themed-muted" style={{ background: 'var(--color-bg-subtle)' }}>
          scale: {metric.scale}
        </span>
        <span className="rounded px-2 py-1 text-themed-muted" style={{ background: 'var(--color-bg-subtle)' }}>
          {metric.evidence}
        </span>
      </div>
    </div>
  )
}

export default function AnalyticsVisualizationContract() {
  return (
    <section className="space-y-4" data-testid="analytics-visualization-contract">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="accent" size="sm">Issue #482</Badge>
              <Badge variant="info" size="sm">Estee Lauder / 雅诗兰黛</Badge>
            </div>
            <h2 className="text-xl font-brand font-bold text-themed-primary">
              App analytics visualization contract
            </h2>
            <p className="mt-2 text-sm text-themed-muted">
              First vertical slice for /brand/overview: show real non-empty data when available, expose partial or empty upstream gaps, and surface API errors without falling back to mock truth.
            </p>
          </div>
          <div className="rounded-md px-3 py-2 text-xs text-themed-muted" style={{ background: 'var(--color-bg-subtle)' }}>
            Route: /brand/overview?viz=analytics-contract
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {overviewStates.map((item) => (
          <Card key={item.state} className="p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-themed-primary">{item.label}</h3>
                  <StateBadge state={item.state} variant={item.badgeVariant} />
                </div>
                <p className="mt-1 text-xs text-themed-muted">{item.summary}</p>
              </div>
            </div>
            <div className="space-y-2">
              {item.metrics.map((metric) => (
                <MetricRow key={`${item.state}-${metric.key}`} metric={metric} />
              ))}
            </div>
          </Card>
        ))}
      </div>

      <Card className="p-4">
        <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
          <h3 className="text-base font-semibold text-themed-primary">Brand Mode chart inventory</h3>
          <span className="text-xs text-themed-muted">Frontend handoff only; no backend wiring in this PR.</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="text-themed-muted">
              <tr>
                <th className="py-2 pr-4 font-medium">Page</th>
                <th className="py-2 pr-4 font-medium">Target state</th>
                <th className="py-2 pr-4 font-medium">Current visualization decision</th>
                <th className="py-2 font-medium">Backend/API handoff</th>
              </tr>
            </thead>
            <tbody>
              {pageInventory.map((row) => (
                <tr key={row.page} className="border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
                  <td className="py-3 pr-4 font-semibold text-themed-primary whitespace-nowrap">{row.page}</td>
                  <td className="py-3 pr-4 text-themed-muted min-w-[260px]">{row.target}</td>
                  <td className="py-3 pr-4 text-themed-muted min-w-[220px]">{row.state}</td>
                  <td className="py-3 text-themed-muted min-w-[260px]">{row.handoff}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-4">
        <h3 className="text-base font-semibold text-themed-primary mb-2">Requested overview payload fields</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {payloadFields.map((field) => (
            <code
              key={field}
              className="rounded px-2 py-1 text-[11px] text-themed-muted"
              style={{ background: 'var(--color-bg-subtle)' }}
            >
              {field}
            </code>
          ))}
        </div>
      </Card>
    </section>
  )
}
