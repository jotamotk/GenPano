import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine,
} from 'recharts';
import { Card, Badge, Button } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import {
  BRANDS,
  SIMULATOR_BASELINE,
  SIMULATOR_PRESETS,
} from '../data/mock';
import { useProjects } from '../hooks/useProjects';
import { useRunSimulator } from '../hooks/useSimulator';

/* ─────────────────────────────────────────────────────────────
   BrandSimulatorPage — PRD §4.2.7.E v1.1 "PANO A 模拟器"
   URL: /brands/:id/simulator
   ─────────────────────────────────────────────────────────────
   价值: 回答"如果我把 Tier 2 权威媒体引用数增加 N, PANO A 会涨多少?"

   计算公式 (展示用, 与 §4.2.6.F 同构, 不重写业务逻辑):
     PANO A' = PANO A + Σ_tier (tier_weight × confidence × Δcount × normalizer)

   简化展示版:
     expectedDelta = Σ_tier tierWeight × defaultConfidence × deltaCount × scale
     其中 scale 是一个只用于前端预览的常数; 真实分数由后端 /api/brands/:id/simulate-authority-boost 返回.

   PRD §4.2.7.E 约束:
     - basePriceByTier 来自 Admin 参数服务, 不是硬编码 (mock 里仅作参考)
     - ROI 卡显示"估计预算 / 每 +1 PANO A" 但不承诺价格
     - 最终 CTA = "联系咨询团队", 不给自动下单
─────────────────────────────────────────────────────────────── */

const TIER_LABEL = {
  1: 'Tier 1 · 官方',
  2: 'Tier 2 · 权威媒体',
  3: 'Tier 3 · KOL',
  4: 'Tier 4 · UGC',
};

const SCALE = 0.42; // 纯展示层常数, 真实值由后端返回

const calcDelta = (deltaByTier, baseline) => {
  let total = 0;
  Object.entries(deltaByTier || {}).forEach(([tier, count]) => {
    const w = baseline.tierWeights?.[tier] || 0;
    const c = baseline.defaultConfidence?.[tier] || 0;
    total += w * c * (Number(count) || 0) * SCALE;
  });
  return Math.round(total * 10) / 10;
};

const calcBudget = (deltaByTier, baseline) => {
  let total = 0;
  Object.entries(deltaByTier || {}).forEach(([tier, count]) => {
    const price = baseline.basePriceByTier?.[tier] || 0;
    total += price * (Number(count) || 0);
  });
  return total;
};

const fmtCNY = (n) =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  }).format(n);

/* ─────── Tier 滑杆 ─────── */
function TierDeltaSlider({ tier, label, value, onChange, maxDelta }) {
  return (
    <div className="py-3 border-b border-themed-subtle last:border-b-0">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-sm text-themed-primary font-medium">{label}</span>
        <span className="text-sm tabular-nums text-themed-primary">
          <span className="text-themed-muted">+</span>
          {value}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={maxDelta}
        step={1}
        value={value}
        onChange={(e) => onChange(tier, Number(e.target.value))}
        className="w-full accent-[var(--color-accent)]"
      />
      <div className="flex justify-between text-[11px] text-themed-muted mt-1">
        <span>0</span>
        <span className="tabular-nums">{maxDelta}</span>
      </div>
    </div>
  );
}

/* ─────── Main Page ─────── */
export default function BrandSimulatorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useLocale();

  const brand = useMemo(
    () => BRANDS.find((b) => b.id === id) || BRANDS[0],
    [id]
  );

  const baseline =
    SIMULATOR_BASELINE?.brandId === id
      ? SIMULATOR_BASELINE
      : { ...SIMULATOR_BASELINE, brandId: id };

  const [deltaByTier, setDeltaByTier] = useState({ 1: 0, 2: 0, 3: 0, 4: 0 });

  const setTierDelta = (tier, value) =>
    setDeltaByTier((prev) => ({ ...prev, [tier]: value }));

  const applyPreset = (preset) => {
    setDeltaByTier({
      1: preset.deltaByTier?.[1] || 0,
      2: preset.deltaByTier?.[2] || 0,
      3: preset.deltaByTier?.[3] || 0,
      4: preset.deltaByTier?.[4] || 0,
    });
  };

  const reset = () => setDeltaByTier({ 1: 0, 2: 0, 3: 0, 4: 0 });

  const expectedDelta = calcDelta(deltaByTier, baseline);
  const expectedNewScore = Math.round((baseline.currentPanoA + expectedDelta) * 10) / 10;

  // Live-mode hook: only fires when there's a real backend Project.
  // The brand_id passed to the API must be int — falls back to a
  // placeholder for mock-shape ids so the button can still render.
  const { data: liveProjects } = useProjects();
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const numericBrandId = id && /^\d+$/.test(id) ? Number(id) : null;
  const liveBrandId = numericBrandId ?? liveProjects?.[0]?.primary_brand_id ?? null;
  const runSim = useRunSimulator(liveProjectId);
  const liveCanRun = liveProjectId != null && liveBrandId != null;
  const budget = calcBudget(deltaByTier, baseline);
  const budgetPerPoint =
    expectedDelta > 0 ? Math.round(budget / expectedDelta) : null;

  const compareData = [
    { label: '当前', value: baseline.currentPanoA, color: 'var(--color-text-muted)' },
    { label: '模拟后', value: expectedNewScore, color: 'var(--color-accent)' },
    { label: '行业中位', value: baseline.industryMedian, color: 'var(--color-chart-3)' },
    { label: 'Top 3 均值', value: baseline.industryTop3Avg, color: 'var(--color-chart-6)' },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-6 p-6">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <button
            className="text-sm text-themed-muted hover:text-themed-primary transition-colors"
            onClick={() => navigate(`/brands/${brand.id}?tab=content-gap`)}
          >
            ← 返回品牌详情
          </button>
          <h1 className="text-xl font-bold text-themed-primary mt-2">
            PANO A 模拟器 · {brand.name}
          </h1>
          <p className="text-sm text-themed-muted mt-1">
            调一调各 Tier 增加的引用数, 看 PANO A 会走到哪里, 以及大概需要投入多少
          </p>
        </div>
        <div className="flex items-center gap-2">
          {liveCanRun && (
            <Button
              variant="primary"
              size="sm"
              onClick={() =>
                runSim.mutate({
                  brand_id: liveBrandId as number,
                  delta_by_tier: Object.fromEntries(
                    Object.entries(deltaByTier).map(([k, v]) => [k, Number(v)]),
                  ),
                })
              }
              disabled={runSim.isPending}
            >
              {runSim.isPending ? '后端计算中…' : '运行真实模拟'}
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={reset}>
            重置
          </Button>
        </div>
      </div>

      {/* Live result panel — shows the authoritative simulated_pano_a
          + base price equivalent from /v1/projects/:id/simulator/run */}
      {runSim.data && (
        <Card
          className="p-4 border"
          onClick={undefined}
          style={{
            background: 'linear-gradient(135deg, rgba(99, 91, 255, 0.06), rgba(139, 92, 246, 0.04))',
            borderColor: 'var(--color-accent, #635bff)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <span
              className="px-2 py-0.5 rounded-pill text-[10px] font-bold tabular-nums"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              LIVE
            </span>
            <span className="text-sm font-semibold text-themed-primary">后端真实模拟结果</span>
            <span className="text-[10px] text-themed-faint">
              POST /v1/projects/.../simulator/run
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-card p-3" style={{ background: 'var(--color-bg-card, #fff)' }}>
              <div className="text-[11px] uppercase text-themed-muted mb-1">当前 PANO A</div>
              <div className="text-xl font-bold tabular-nums text-themed-primary">
                {runSim.data.current_pano_a.toFixed(1)}
              </div>
            </div>
            <div className="rounded-card p-3" style={{ background: 'var(--color-bg-card, #fff)' }}>
              <div className="text-[11px] uppercase text-themed-muted mb-1">模拟后 PANO A</div>
              <div className="text-xl font-bold tabular-nums" style={{ color: '#635bff' }}>
                {runSim.data.simulated_pano_a.toFixed(1)}
              </div>
            </div>
            <div className="rounded-card p-3" style={{ background: 'var(--color-bg-card, #fff)' }}>
              <div className="text-[11px] uppercase text-themed-muted mb-1">Δ</div>
              <div className="text-xl font-bold tabular-nums" style={{ color: '#16a34a' }}>
                +{runSim.data.delta.toFixed(1)}
              </div>
            </div>
            <div className="rounded-card p-3" style={{ background: 'var(--color-bg-card, #fff)' }}>
              <div className="text-[11px] uppercase text-themed-muted mb-1">估算预算 (CNY)</div>
              <div className="text-xl font-bold tabular-nums text-themed-primary">
                {runSim.data.base_price_equivalent_cny.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="text-[11px] text-themed-faint mt-2">
            置信度 {(runSim.data.confidence * 100).toFixed(0)}% · citation_authority Δ{' '}
            {runSim.data.delta_breakdown.citation_authority.toFixed(2)}
          </div>
        </Card>
      )}

      {/* Presets */}
      <div className="flex flex-wrap gap-2">
        {SIMULATOR_PRESETS.map((p) => (
          <button
            key={p.id}
            onClick={() => applyPreset(p)}
            className="px-3 py-1.5 rounded-pill text-xs font-medium transition-colors"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {p.label}
            <span className="ml-1.5 text-themed-muted tabular-nums">
              · 约 +{p.expectedDeltaPanoA}
            </span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Left: Input column */}
        <Card className="col-span-12 lg:col-span-5 p-5">
          <h3 className="text-sm font-semibold text-themed-primary mb-4">
            增加引用数 (模拟输入)
          </h3>
          {[1, 2, 3, 4].map((tier) => (
            <TierDeltaSlider
              key={tier}
              tier={tier}
              label={TIER_LABEL[tier]}
              value={deltaByTier[tier]}
              onChange={setTierDelta}
              maxDelta={tier === 3 ? 80 : tier === 4 ? 120 : 40}
            />
          ))}
          <div className="mt-4 pt-4 border-t border-themed-subtle">
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-xs text-themed-muted">预计预算区间</span>
              <span className="text-sm font-semibold tabular-nums text-themed-primary">
                {fmtCNY(budget)}
              </span>
            </div>
            <p className="text-[11px] text-themed-faint leading-relaxed">
              仅基于 Admin 参数服务的基础单价估算, 实际项目执行价格请联系咨询团队
            </p>
          </div>
        </Card>

        {/* Right: Outcome column */}
        <div className="col-span-12 lg:col-span-7 space-y-4">
          <Card className="p-5">
            <p className="text-xs text-themed-muted">预期新 PANO A 分数</p>
            <div className="flex items-baseline gap-3 mt-1">
              <span className="text-4xl font-bold tabular-nums text-themed-primary">
                {expectedNewScore}
              </span>
              <span
                className="text-sm font-semibold tabular-nums"
                style={{
                  color:
                    expectedDelta > 0
                      ? 'var(--color-success)'
                      : 'var(--color-text-muted)',
                }}
              >
                {expectedDelta > 0 ? `+${expectedDelta}` : expectedDelta}
              </span>
            </div>

            <ResponsiveContainer width="100%" height={180} className="mt-4">
              <BarChart
                data={compareData}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 48 }}
              >
                <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
                  axisLine={{ stroke: 'var(--color-border-subtle)' }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--color-bg-card)',
                    border: '1px solid var(--color-border-subtle)',
                    borderRadius: 'var(--radius-btn)',
                    fontSize: 12,
                    boxShadow: 'var(--shadow-card-hover)',
                  }}
                />
                <ReferenceLine x={baseline.currentPanoA} stroke="var(--color-text-muted)" strokeDasharray="3 3" />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {compareData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card className="p-5">
            <h4 className="text-sm font-semibold text-themed-primary mb-3">
              ROI 概览
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-themed-muted">每 +1 PANO A 估计预算</p>
                <p className="text-lg font-bold tabular-nums text-themed-primary mt-1">
                  {budgetPerPoint !== null ? fmtCNY(budgetPerPoint) : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-themed-muted">距行业中位差距</p>
                <p className="text-lg font-bold tabular-nums text-themed-primary mt-1">
                  {Math.round((baseline.industryMedian - expectedNewScore) * 10) / 10}
                </p>
              </div>
              <div>
                <p className="text-xs text-themed-muted">距 Top 3 均值差距</p>
                <p className="text-lg font-bold tabular-nums text-themed-primary mt-1">
                  {Math.round((baseline.industryTop3Avg - expectedNewScore) * 10) / 10}
                </p>
              </div>
              <div>
                <p className="text-xs text-themed-muted">Tier 2 新增占比</p>
                <p className="text-lg font-bold tabular-nums text-themed-primary mt-1">
                  {Object.values(deltaByTier).reduce((s, v) => s + v, 0) > 0
                    ? Math.round(
                        (deltaByTier[2] /
                          Object.values(deltaByTier).reduce((s, v) => s + v, 0)) *
                          100
                      )
                    : 0}
                  %
                </p>
              </div>
            </div>
          </Card>

          <Card className="p-5" style={{ background: 'var(--color-accent-subtle)' }}>
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h4 className="text-sm font-semibold text-themed-primary">
                  把这个模拟结果变成行动
                </h4>
                <p className="text-xs text-themed-secondary mt-1 leading-relaxed">
                  GEO 顾问会基于你当前结构给出可执行方案 · 不收订阅费, 按项目计费
                </p>
              </div>
              <Button variant="primary" size="sm">
                联系咨询团队
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
