/**
 * BrandPanoramaPanelLive — rich brand panorama, fully driven by backend.
 *
 * Restores the visual layout of the original BrandPanoramaPanel but
 * sources every chart from real endpoints:
 *   - Hero + 5 KPIs           ← /v1/projects/:id/overview (kpi_cards)
 *   - SoV pie                 ← /v1/projects/:id/competitors/metrics (avg_sov)
 *   - 4-quadrant bubble       ← competitors/metrics (avg_sov × avg_sentiment)
 *   - 30d PANO trend          ← /v1/projects/:id/overview (geo_score_30d)
 *   - SoV / sentiment trend   ← overview (sov_30d / sentiment_30d)
 *   - Top alerts              ← /v1/projects/:id/diagnostics
 *
 * No mock imports. Renders explicit empty / loading / error states for
 * each block independently so partial backend data still shows what's
 * available.
 */
import { useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
  ReferenceLine,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  AreaChart,
  Area,
} from 'recharts';
import { Badge, Button, Card } from '../ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useBrandOverview, isLiveProjectId } from '../../hooks/useBrandOverview';
import { useCompetitorMetrics } from '../../hooks/useBrandMetrics';
import { useDiagnostics, toMockShape } from '../../hooks/useDiagnostics';

const SOV_COLORS = [
  '#635bff',
  '#16a34a',
  '#f59e0b',
  '#dc2626',
  '#0ea5e9',
  '#a855f7',
  '#94a3b8',
];

const SEVERITY_COLORS: Record<string, string> = {
  P0: '#dc2626',
  P1: '#ea580c',
  P2: '#ca8a04',
  P3: '#64748b',
};

interface Props {
  projectId: string;
  /** When true, hides the inline header; the parent renders its own */
  embedded?: boolean;
}

export default function BrandPanoramaPanelLive({ projectId, embedded }: Props) {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const overviewQ = useBrandOverview(projectId);
  const compQ = useCompetitorMetrics(
    isLiveProjectId(projectId) ? projectId : null,
  );
  const diagQ = useDiagnostics(
    isLiveProjectId(projectId) ? projectId : null,
    { status: 'open', limit: 5 },
  );

  if (overviewQ.isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载真实数据…</div>
      </Card>
    );
  }
  if (overviewQ.error) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted mb-3">
          加载失败:{' '}
          {overviewQ.error instanceof Error ? overviewQ.error.message : 'unknown'}
        </div>
        <Button variant="secondary" size="sm" onClick={() => overviewQ.refetch()}>
          重试
        </Button>
      </Card>
    );
  }
  const overview = overviewQ.data;
  if (!overview || overview.state === 'empty') {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">📡</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          首批数据采集中
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          后端已经收到该 Project, 但还没有 LLM 响应入库. 通常首批查询在
          24h 内完成, 之后该页将填充真实 GEO 指标 / SoV / 情感 / 引用 / 诊断.
        </p>
        <Button variant="primary" size="sm" onClick={() => overviewQ.refetch()}>
          刷新
        </Button>
      </Card>
    );
  }

  const compRows = compQ.data?.competitors ?? [];
  const primary = compQ.data?.primary ?? null;
  const allComp = primary ? [primary, ...compRows] : compRows;

  // SoV pie data (top 6 brands + others)
  const sovData = allComp
    .filter((r) => r.avg_sov != null)
    .slice(0, 6)
    .map((r) => ({
      name: r.brand_name ?? `Brand #${r.brand_id}`,
      value: (r.avg_sov ?? 0) * 100,
    }));
  if (sovData.length > 0) {
    const totalShown = sovData.reduce((acc, x) => acc + x.value, 0);
    const others = Math.max(0, 100 - totalShown);
    if (others > 1) sovData.push({ name: '其他', value: others });
  }

  // 4-quadrant bubble: SoV × sentiment
  const bubble = allComp
    .filter((r) => r.avg_sov != null && r.avg_sentiment != null)
    .map((r) => ({
      x: (r.avg_sov ?? 0) * 100,
      y: r.avg_sentiment ?? 0,
      z: r.co_mention_count + 30,
      brand_id: r.brand_id,
      name: r.brand_name ?? `Brand #${r.brand_id}`,
      isPrimary: r.brand_id === primary?.brand_id,
    }));
  const avgSov =
    bubble.length > 0
      ? bubble.reduce((a, b) => a + b.x, 0) / bubble.length
      : 0;
  const avgSent =
    bubble.length > 0
      ? bubble.reduce((a, b) => a + b.y, 0) / bubble.length
      : 0;

  const brandLabel = overview.brand_name ?? `Brand #${overview.brand_id ?? '?'}`;
  const periodLabel = `${formatDate(overview.period.from)} – ${formatDate(overview.period.to)}`;

  // Combine geo + sov trends into one merged shape for one chart
  const trendDates = new Set<string>();
  for (const p of overview.geo_score_30d) trendDates.add(p.date);
  for (const p of overview.sov_30d) trendDates.add(p.date);
  for (const p of overview.sentiment_30d) trendDates.add(p.date);
  const sortedDates = Array.from(trendDates).sort();
  const lookup = (
    arr: { date: string; value: number }[],
    d: string,
  ): number | null => {
    const found = arr.find((p) => p.date === d);
    return found ? found.value : null;
  };
  const trendMerged = sortedDates.map((d) => ({
    date: d,
    geo_score: lookup(overview.geo_score_30d, d),
    sov: (lookup(overview.sov_30d, d) ?? 0) * 100,
    sentiment: lookup(overview.sentiment_30d, d),
  }));

  const openDiags = (diagQ.data?.items ?? []).map(toMockShape);
  const topAlerts = openDiags
    .filter((d) => d.severity === 'P0' || d.severity === 'P1')
    .slice(0, 3);

  return (
    <div className="space-y-6">
      {!embedded && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-baseline gap-3 flex-wrap">
            <Badge variant="default">LIVE</Badge>
            <h1 className="text-heading-2 text-themed-primary font-bold">
              {brandLabel}
            </h1>
            <span className="text-sm text-themed-muted">{periodLabel}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate('/project-settings')}
            >
              管理 Project
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/brand/diagnostics')}
            >
              查看诊断
            </Button>
          </div>
        </div>
      )}

      {/* Top alerts strip (P0/P1) */}
      {topAlerts.length > 0 && (
        <Card className="p-4" onClick={undefined} style={{}}>
          <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
            <h3 className="text-sm font-semibold text-themed-primary">
              ⚠️ 关键诊断 ({topAlerts.length})
            </h3>
            <button
              type="button"
              onClick={() => navigate('/brand/diagnostics')}
              className="text-xs text-themed-accent hover:opacity-80"
            >
              查看全部 →
            </button>
          </div>
          <ul className="space-y-2">
            {topAlerts.map((alert) => (
              <li
                key={alert.id}
                className="flex items-start gap-3 text-sm border-b border-themed-subtle pb-2 last:border-b-0"
              >
                <span
                  className="px-2 py-0.5 rounded-pill text-[11px] font-bold text-white shrink-0"
                  style={{
                    background:
                      SEVERITY_COLORS[alert.severity as string] ?? '#64748b',
                  }}
                >
                  {alert.severity}
                </span>
                <span className="text-themed-secondary flex-1">
                  {alert.title}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* 5 KPI cards */}
      {overview.kpi_cards.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {overview.kpi_cards.map((kpi, idx) => (
            <KpiCard key={idx} kpi={kpi} />
          ))}
        </div>
      )}

      {/* Competitor landscape: SoV pie + 4-quadrant */}
      {allComp.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card className="p-5" onClick={undefined} style={{}}>
            <h3 className="text-sm font-semibold text-themed-primary mb-3">
              竞品 SoV 分布
            </h3>
            {sovData.length === 0 ? (
              <p className="text-xs text-themed-muted">数据采集中…</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={sovData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={95}
                    label={(d) =>
                      typeof d.value === 'number' ? `${d.value.toFixed(1)}%` : ''
                    }
                  >
                    {sovData.map((_, i) => (
                      <Cell
                        key={i}
                        fill={SOV_COLORS[i % SOV_COLORS.length]}
                        stroke="white"
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => `${v.toFixed(1)}%`}
                  />
                  <Legend
                    verticalAlign="bottom"
                    wrapperStyle={{ fontSize: 11 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>

          <Card className="p-5" onClick={undefined} style={{}}>
            <h3 className="text-sm font-semibold text-themed-primary mb-1">
              竞品四象限 (SoV × 情感)
            </h3>
            <p className="text-xs text-themed-muted mb-3">
              横轴 = SoV%, 纵轴 = 平均情感, 气泡大小 = 共现次数
            </p>
            {bubble.length === 0 ? (
              <p className="text-xs text-themed-muted">数据采集中…</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-chart-line-grid)" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    name="SoV"
                    unit="%"
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    name="情感"
                    domain={[-1, 1]}
                    tick={{ fontSize: 10 }}
                  />
                  <ZAxis type="number" dataKey="z" range={[60, 400]} />
                  <ReferenceLine x={avgSov} stroke="#94a3b8" strokeDasharray="3 3" />
                  <ReferenceLine y={avgSent} stroke="#94a3b8" strokeDasharray="3 3" />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    content={({ active, payload }) => {
                      if (!active || !payload || payload.length === 0) return null;
                      const d = payload[0].payload;
                      return (
                        <div
                          className="text-xs"
                          style={{
                            background: 'var(--color-bg-card)',
                            border: '1px solid var(--color-border-subtle)',
                            borderRadius: 6,
                            padding: '6px 10px',
                          }}
                        >
                          <div className="font-semibold text-themed-primary">
                            {d.name}
                          </div>
                          <div>SoV: {d.x.toFixed(1)}%</div>
                          <div>情感: {d.y.toFixed(2)}</div>
                          <div>共现: {d.z - 30}</div>
                        </div>
                      );
                    }}
                  />
                  <Scatter
                    data={bubble.filter((b) => !b.isPrimary)}
                    fill="#94a3b8"
                  />
                  <Scatter
                    data={bubble.filter((b) => b.isPrimary)}
                    fill="#635bff"
                  />
                </ScatterChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>
      )}

      {/* 30d trend */}
      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          30 天趋势
        </h3>
        {trendMerged.length === 0 ? (
          <p className="text-xs text-themed-muted">数据采集中…</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendMerged}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-chart-line-grid)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d) =>
                  formatDate(d, { month: 'short', day: 'numeric' })
                }
              />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                labelFormatter={(d) =>
                  formatDate(d, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })
                }
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="geo_score"
                name="GEO 综合分"
                stroke="#635bff"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="sov"
                name="SoV (%)"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="sentiment"
                name="情感"
                stroke="#f59e0b"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Top prompts table */}
      {overview.top_prompts.length > 0 && (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <div className="px-5 py-3 border-b border-themed-subtle">
            <h3 className="text-sm font-semibold text-themed-primary">
              Top 提及 Prompt (30d)
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                  <th className="py-2 pl-5">Prompt</th>
                  <th className="py-2 px-3 text-right">提及次数</th>
                  <th className="py-2 px-3 text-right">平均位置</th>
                  <th className="py-2 px-3 text-right">情感</th>
                </tr>
              </thead>
              <tbody>
                {overview.top_prompts.map((row) => (
                  <tr
                    key={row.prompt_id ?? row.prompt_text}
                    className="border-t border-themed-subtle"
                  >
                    <td className="py-2 pl-5 pr-3 text-themed-primary truncate max-w-md">
                      {row.prompt_text}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.mention_count}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.avg_position_rank != null
                        ? `#${row.avg_position_rank.toFixed(1)}`
                        : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.avg_sentiment_score != null
                        ? row.avg_sentiment_score.toFixed(2)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Same-group shared domains */}
      {overview.same_group_shared_domains.length > 0 && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-1">
            同集团共享域名
          </h3>
          <p className="text-xs text-themed-muted mb-3">
            来自 brand_group_shared_domains (Phase A.6)
          </p>
          <ul className="space-y-2">
            {overview.same_group_shared_domains.map((row) => (
              <li
                key={row.domain}
                className="flex items-center justify-between text-sm border-b border-themed-subtle pb-2 last:border-b-0"
              >
                <span className="text-themed-primary">{row.domain}</span>
                <span className="text-themed-muted text-xs">
                  跨 {row.brand_count} 品牌 · {row.total_mentions} 提及
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {overview.state === 'partial' && (
        <p className="text-[11px] text-themed-muted">
          ⚠️ 数据状态: partial — 后端聚合还未跑齐, 部分图表可能滞后.
        </p>
      )}
    </div>
  );
}

interface KpiCardData {
  label_zh: string;
  label_en: string;
  value: number;
  unit: string | null;
  delta_30d_pct: number | null;
  direction: 'up' | 'down' | 'flat' | null;
}

function KpiCard({ kpi }: { kpi: KpiCardData }) {
  const direction = kpi.direction ?? 'flat';
  const colors: Record<string, string> = {
    up: '#16a34a',
    down: '#dc2626',
    flat: '#64748b',
  };
  const icons: Record<string, string> = {
    up: '↑',
    down: '↓',
    flat: '→',
  };
  return (
    <Card className="p-4" onClick={undefined} style={{}}>
      <p className="text-[11px] text-themed-muted uppercase tracking-wider">
        {kpi.label_zh}
      </p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-themed-primary">
        {kpi.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
        {kpi.unit ? (
          <span className="text-sm font-normal ml-0.5">{kpi.unit}</span>
        ) : null}
      </p>
      {kpi.delta_30d_pct != null && (
        <p
          className="mt-1 text-xs tabular-nums"
          style={{ color: colors[direction] }}
        >
          {icons[direction]} {kpi.delta_30d_pct.toFixed(1)}% (30d)
        </p>
      )}
    </Card>
  );
}
