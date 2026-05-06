import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from 'recharts';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import { useRunSimulator } from '../hooks/useSimulator';
import { isLiveProjectId } from '../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  ErrorCard,
} from './brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页通过 POST /v1/projects/:id/simulator/run.
   Mock-only client-side calcDelta retired; sim now strictly server-side. */
export default function BrandSimulatorPage() {
  const navigate = useNavigate();
  const { formatNumber } = useLocale();
  const { data: projects, isLoading: projLoading } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const liveBrandId = projects?.[0]?.primary_brand_id ?? null;
  const runSim = useRunSimulator(liveProjectId);
  const [tier1, setTier1] = useState(0);
  const [tier2, setTier2] = useState(0);
  const [tier3, setTier3] = useState(0);

  if (projLoading) return <LoadingCard />;
  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="Authority 模拟器" />
    );
  if (liveBrandId == null)
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <p className="text-sm text-themed-muted">
          Project 还没设置主品牌, 无法模拟. 请到{' '}
          <button
            type="button"
            onClick={() => navigate('/project-settings')}
            className="text-themed-accent underline"
          >
            项目设置
          </button>{' '}
          配置后再试.
        </p>
      </Card>
    );

  const handleRun = () => {
    runSim.mutate({
      brand_id: liveBrandId,
      delta_by_tier: { '1': tier1, '2': tier2, '3': tier3 },
    });
  };

  const result = runSim.data;
  const breakdownData = result
    ? [
        { name: '可见度', value: result.delta_breakdown.visibility, color: '#635bff' },
        { name: 'SoV', value: result.delta_breakdown.sov, color: '#16a34a' },
        { name: '情感', value: result.delta_breakdown.sentiment, color: '#f59e0b' },
        {
          name: '权威',
          value: result.delta_breakdown.citation_authority,
          color: '#dc2626',
        },
      ]
    : [];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">
          Authority 模拟器
        </h2>
        <span className="text-sm text-themed-muted">
          POST /v1/projects/:id/simulator/run
        </span>
      </div>

      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          调整每个 tier 的引用增量
        </h3>
        <p className="text-xs text-themed-muted mb-4">
          Tier 1 = 官方 / 头部权威站; Tier 2 = 知名媒体 / KOL; Tier 3 = 长尾 / UGC.
          调整后点击"运行"看后端真实计算的 PANO_A 增量.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SliderCard label="Tier 1 (官方/头部)" value={tier1} onChange={setTier1} />
          <SliderCard label="Tier 2 (媒体/KOL)" value={tier2} onChange={setTier2} />
          <SliderCard label="Tier 3 (长尾/UGC)" value={tier3} onChange={setTier3} />
        </div>

        <div className="flex items-center gap-3 mt-5">
          <Button
            variant="primary"
            size="md"
            onClick={handleRun}
            disabled={runSim.isPending}
          >
            {runSim.isPending ? '运行中…' : '运行模拟'}
          </Button>
          <Button
            variant="outline"
            size="md"
            onClick={() => {
              setTier1(0);
              setTier2(0);
              setTier3(0);
            }}
          >
            重置
          </Button>
        </div>

        {runSim.isError && (
          <ErrorCard
            msg={
              runSim.error instanceof Error ? runSim.error.message : 'unknown'
            }
            onRetry={handleRun}
          />
        )}
      </Card>

      {result && (
        <>
          <Card className="p-5" onClick={undefined} style={{}}>
            <h3 className="text-sm font-semibold text-themed-primary mb-3">
              模拟结果
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiBox
                label="当前 PANO_A"
                value={result.current_pano_a.toFixed(1)}
              />
              <KpiBox
                label="模拟 PANO_A"
                value={result.simulated_pano_a.toFixed(1)}
                tone={result.delta >= 0 ? 'good' : 'bad'}
              />
              <KpiBox
                label="Δ"
                value={`${result.delta >= 0 ? '+' : ''}${result.delta.toFixed(1)}`}
                tone={result.delta >= 0 ? 'good' : 'bad'}
              />
              <KpiBox
                label="等价 PR 投入"
                value={`¥${formatNumber(result.base_price_equivalent_cny, {
                  maximumFractionDigits: 0,
                })}`}
              />
            </div>
            <p className="text-[11px] text-themed-muted mt-3">
              置信度: {(result.confidence * 100).toFixed(0)}%
            </p>
          </Card>

          <Card className="p-5" onClick={undefined} style={{}}>
            <h3 className="text-sm font-semibold text-themed-primary mb-3">
              四维分解
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={breakdownData}>
                <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {breakdownData.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </>
      )}
    </div>
  );
}

function SliderCard({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <div
      className="rounded-card border p-4"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border-subtle)',
      }}
    >
      <div className="text-xs text-themed-muted mb-2">{label}</div>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={-20}
          max={50}
          step={1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1"
        />
        <span className="tabular-nums text-sm font-semibold text-themed-primary w-12 text-right">
          {value > 0 ? '+' : ''}
          {value}
        </span>
      </div>
    </div>
  );
}

function KpiBox({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'good' | 'bad';
}) {
  const color =
    tone === 'good' ? '#16a34a' : tone === 'bad' ? '#dc2626' : undefined;
  return (
    <div
      className="rounded-card border p-4"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border-subtle)',
      }}
    >
      <p className="text-[11px] uppercase tracking-wider text-themed-muted">
        {label}
      </p>
      <p
        className="mt-1 text-2xl font-bold tabular-nums"
        style={{ color: color ?? 'var(--color-text-primary)' }}
      >
        {value}
      </p>
    </div>
  );
}
