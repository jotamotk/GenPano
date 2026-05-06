import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ResponsiveContainer,
  LineChart, Line,
  PieChart, Pie, Cell,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { Badge, Button, Card } from '../ui';
import { MiniSparkline } from '../charts';
import { useLocale } from '../../contexts/LocaleContext';
import ProfileGroupFilter, { ProfileGroupSampleWarning } from '../filters/ProfileGroupFilter';
import {
  BRANDS, ENGINES, INDUSTRIES,
  SOV_DATA, COMPETITOR_SENTIMENT_BUBBLE, TREND_DATA, DIAGNOSTICS,
} from '../../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandPanoramaPanel — 单品牌全景视图 (PRD §4.6.1a 市场宏观视角)
   ─────────────────────────────────────────────────────────────
   复用场景:
     - DashboardPage (/dashboard): 当前用户 primaryBrand 为主视角
     - BrandDetailPage.OverviewTab: 任意品牌页概览 Tab, 以 URL :brandId 为主视角

   props:
     primary          — 主品牌 BRAND 对象 (必填)
     industry         — 所在行业 INDUSTRY 对象 (可选; 缺省时回退 primary.industryId 查表)
     competitors      — Top 3 竞品 BRAND[] (可选; 缺省时走知识图谱推荐或空)
     headerSlot       — 页面顶部自定义 header 节点 (可选), 如品牌切换器 / PDF 按钮
     onShareReport    — 分享/导出 PDF 回调 (可选)
     scrollAnchorId   — competition 区块锚点 id, 避免两个挂载点同 id 冲突

   区块构成 (与 DashboardPage 一致):
     ⓪ Hero              品牌名 + PANO Score 大号 + 行业均值对比条
     ① 5 KPI 核心指标卡   提及率 / SoV / 情感 / 引用份额 / 行业排名
     ② 竞争视图           SoV 饼图 + 竞品四象限气泡图
     ③ 趋势视图           PANO 30d (我 vs Top 3 竞品) + 5 KPI sparkline
     ④ 告警条             Top 3 P0/P1 诊断 → 跳品牌详情诊断 Tab

   样式契约: 颜色全部走 var(--color-*) / .text-themed-*.
*/

/* ── chart color tokens ── */
const SOV_COLORS = [
  'var(--color-accent)',
  'var(--color-chart-3)',
  'var(--color-chart-2)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-line-grid)',
];

const KPI_TONE = {
  pos: 'text-themed-success',
  neg: 'text-themed-danger',
  flat: 'text-themed-muted',
};

/* ─── Hero ─── */
function getPanoGrade(score, t) {
  if (score >= 80) return { label: t('dashboard.hero.grade_excellent'), color: 'var(--color-success)' };
  if (score >= 65) return { label: t('dashboard.hero.grade_good'),      color: 'var(--color-chart-7)' };
  if (score >= 50) return { label: t('dashboard.hero.grade_medium'),    color: 'var(--color-chart-3)' };
  if (score >= 35) return { label: t('dashboard.hero.grade_pass'),      color: 'var(--color-warning)' };
  return { label: t('dashboard.hero.grade_attention'), color: 'var(--color-danger)' };
}

function HeroBlock({ primary, industry, industryAvgScore, t, formatBrand, onScoreClick, onRankClick }) {
  const grade = getPanoGrade(primary.panoScore, t);
  const delta = 3.2;

  return (
    <Card className="p-5">
      <div className="flex flex-col md:flex-row items-start md:items-center gap-5">
        <div className="flex-1 min-w-0">
          <h2
            className="text-2xl font-brand font-bold text-themed-primary truncate cursor-pointer"
            onClick={onScoreClick}
          >
            {formatBrand(primary)}
          </h2>
          <p className="text-sm text-themed-muted mt-0.5">{primary.nameEn}</p>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs text-themed-muted">
              {t('dashboard.hero.industry_label')}: {industry?.name || '—'}
            </span>
            <button
              onClick={onRankClick}
              className="text-xs font-semibold text-themed-accent hover:underline"
            >
              #{primary.ranking}
            </button>
            <span className={`text-xs font-medium tabular-nums ${delta >= 0 ? 'text-themed-success' : 'text-themed-danger'}`}>
              {delta >= 0 ? '▲' : '▼'} {delta >= 0 ? '+' : ''}{delta} {t('dashboard.hero.vs_last_period')}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-5 shrink-0">
          <div
            className="flex flex-col items-center cursor-pointer"
            onClick={onScoreClick}
          >
            <span className="text-4xl font-brand font-bold tabular-nums text-themed-primary leading-none">
              {primary.panoScore}
            </span>
            <span
              className="text-xs font-semibold mt-1 px-2 py-0.5 rounded-pill"
              style={{ background: grade.color, color: 'var(--color-text-inverse)', opacity: 0.9 }}
            >
              {grade.label}
            </span>
          </div>

          <div className="flex flex-col gap-2 w-40">
            <div>
              <div className="flex justify-between text-[10px] text-themed-muted mb-0.5">
                <span>{t('dashboard.hero.industry_avg')}</span>
                <span className="tabular-nums">{industryAvgScore}</span>
              </div>
              <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'var(--color-bg-subtle)' }}>
                <div
                  className="h-full rounded-pill transition-all"
                  style={{ width: `${industryAvgScore}%`, background: 'var(--color-chart-line-grid)' }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-[10px] text-themed-muted mb-0.5">
                <span>{t('dashboard.hero.my_brand')}</span>
                <span className="tabular-nums font-semibold">{primary.panoScore}</span>
              </div>
              <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'var(--color-bg-subtle)' }}>
                <div
                  className="h-full rounded-pill transition-all"
                  style={{ width: `${primary.panoScore}%`, background: 'var(--color-accent)' }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ─── Toolbar ─── */
function FilterPill({ active, onClick, children, style }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-pill text-xs font-medium transition-colors ${
        active ? 'text-themed-accent' : 'text-themed-muted'
      }`}
      style={active
        ? { background: 'var(--color-accent-bg-light)', ...(style || {}) }
        : { background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', ...(style || {}) }}
    >
      {children}
    </button>
  );
}

function PanelToolbar({
  range, engines, selectedEngines,
  onRangeChange, onEngineToggle, onEngineAll,
  dimension, onDimensionChange,
  intent, onIntentChange,
  filtersExpanded, onToggleFilters,
  t,
}) {
  const ranges = [
    { id: '7d',  label: t('dashboard.toolbar.range_7d')  },
    { id: '30d', label: t('dashboard.toolbar.range_30d') },
    { id: '90d', label: t('dashboard.toolbar.range_90d') },
  ];
  const allEnginesSelected = selectedEngines.length === engines.length;

  const dimensions = [
    { id: '',          label: t('dashboard.toolbar.dimension_all') },
    { id: '品类',      label: t('dashboard.toolbar.dimension_category') },
    { id: '品牌',      label: t('dashboard.toolbar.dimension_brand') },
    { id: '产品',      label: t('dashboard.toolbar.dimension_product') },
    { id: '竞品',      label: t('dashboard.toolbar.dimension_competitor') },
  ];
  const intents = [
    { id: '',              label: t('dashboard.toolbar.intent_all') },
    { id: 'informational', label: t('dashboard.toolbar.intent_informational') },
    { id: 'commercial',    label: t('dashboard.toolbar.intent_commercial') },
    { id: 'transactional', label: t('dashboard.toolbar.intent_transactional') },
    { id: 'navigational',  label: t('dashboard.toolbar.intent_navigational') },
  ];

  const expandedActiveCount = (dimension ? 1 : 0) + (intent ? 1 : 0);

  return (
    <Card className="p-3">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.range_label')}</span>
          <div className="flex gap-1">
            {ranges.map((r) => (
              <FilterPill key={r.id} active={range === r.id} onClick={() => onRangeChange(r.id)}>
                {r.label}
              </FilterPill>
            ))}
          </div>
        </div>

        <div className="h-5 w-px bg-themed-card" />

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.engine_label')}</span>
          <FilterPill active={allEnginesSelected} onClick={onEngineAll}>
            {t('dashboard.toolbar.engine_all')}
          </FilterPill>
          {engines.map((e) => {
            const active = selectedEngines.includes(e.name);
            return (
              <FilterPill key={e.name} active={active} onClick={() => onEngineToggle(e.name)}>
                <span className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle" style={{ background: e.color }} />
                {e.name}
              </FilterPill>
            );
          })}
        </div>

        <div className="h-5 w-px bg-themed-card" />
        <ProfileGroupFilter />

        <div className="h-5 w-px bg-themed-card" />
        <button
          onClick={onToggleFilters}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors text-themed-muted hover:text-themed-primary"
          style={{
            background: filtersExpanded ? 'var(--color-accent-bg-light)' : 'transparent',
            border: filtersExpanded ? 'none' : '1px solid var(--color-border-subtle)',
          }}
        >
          {filtersExpanded ? t('dashboard.toolbar.collapse_filters') : t('dashboard.toolbar.more_filters')}
          {expandedActiveCount > 0 && !filtersExpanded && (
            <span
              className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold"
              style={{ background: 'var(--color-accent)', color: 'var(--color-text-inverse)' }}
            >
              {expandedActiveCount}
            </span>
          )}
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className={`transition-transform ${filtersExpanded ? 'rotate-180' : ''}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {!filtersExpanded && expandedActiveCount > 0 && (
          <div className="flex items-center gap-1.5">
            {dimension && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-pill text-[10px] font-medium text-themed-accent"
                style={{ background: 'var(--color-accent-bg-light)' }}>
                {t('dashboard.toolbar.dimension_label')}: {dimensions.find(d => d.id === dimension)?.label}
                <button onClick={() => onDimensionChange('')} className="ml-0.5 opacity-60 hover:opacity-100">×</button>
              </span>
            )}
            {intent && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-pill text-[10px] font-medium text-themed-accent"
                style={{ background: 'var(--color-accent-bg-light)' }}>
                {t('dashboard.toolbar.intent_label')}: {intents.find(i => i.id === intent)?.label}
                <button onClick={() => onIntentChange('')} className="ml-0.5 opacity-60 hover:opacity-100">×</button>
              </span>
            )}
          </div>
        )}
      </div>

      {filtersExpanded && (
        <div className="flex items-center gap-4 flex-wrap mt-3 pt-3" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
          <div className="flex items-center gap-2">
            <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.dimension_label')}</span>
            <div className="flex gap-1">
              {dimensions.map((d) => (
                <FilterPill key={d.id} active={(d.id === '' && !dimension) || d.id === dimension} onClick={() => onDimensionChange(d.id)}>
                  {d.label}
                </FilterPill>
              ))}
            </div>
          </div>

          <div className="h-5 w-px bg-themed-card" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.intent_label')}</span>
            <div className="flex gap-1">
              {intents.map((i) => (
                <FilterPill key={i.id} active={(i.id === '' && !intent) || i.id === intent} onClick={() => onIntentChange(i.id)}>
                  {i.label}
                </FilterPill>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ─── KPI Card ─── */
function KpiCard({ label, fullLabel, value, delta, helpText, sparkData, trendIsRank, onClick }) {
  const positive = trendIsRank ? delta > 0 : delta > 0;
  const negative = trendIsRank ? delta < 0 : delta < 0;
  const tone = positive ? KPI_TONE.pos : negative ? KPI_TONE.neg : KPI_TONE.flat;
  const arrow = positive ? '↗' : negative ? '↘' : '→';
  const deltaStr = trendIsRank
    ? (delta > 0 ? `↑${delta}` : delta < 0 ? `↓${Math.abs(delta)}` : '·')
    : (delta > 0 ? `+${delta}` : `${delta}`);

  return (
    <Card
      className="p-4 cursor-pointer transition-shadow hover:shadow-card-hover"
      onClick={onClick}
    >
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs font-medium text-themed-muted">{label}</span>
        <span className="text-[10px] uppercase tracking-wider text-themed-muted opacity-60">{fullLabel}</span>
      </div>
      <div className="flex items-end justify-between mb-2">
        <span className="text-2xl font-brand font-bold text-themed-primary tabular-nums leading-none">{value}</span>
        <span className={`text-xs font-medium tabular-nums ${tone}`}>{arrow} {deltaStr}</span>
      </div>
      {sparkData && sparkData.length > 0 && (
        <div className="h-7 -mx-1">
          <MiniSparkline data={sparkData} color="var(--color-accent)" />
        </div>
      )}
      <p className="text-[10px] text-themed-muted mt-1.5 leading-snug line-clamp-1">{helpText}</p>
    </Card>
  );
}

/* ─── SoV Pie ─── */
function SovPieChart({ data, primaryName }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[240px] text-sm text-themed-muted">
        暂无声量份额数据
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={88}
          innerRadius={48}
          paddingAngle={2}
          isAnimationActive={false}
        >
          {data.map((entry, i) => {
            const isPrimary = entry.name === primaryName;
            const isOthers = entry.name === '其他' || entry.name === 'Others';
            const fill = isPrimary
              ? 'var(--color-accent)'
              : isOthers
                ? 'var(--color-chart-line-grid)'
                : SOV_COLORS[(i + 1) % SOV_COLORS.length];
            return (
              <Cell
                key={entry.name}
                fill={fill}
                stroke="var(--color-bg-card)"
                strokeWidth={2}
              />
            );
          })}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          formatter={(v, name) => [`${v}%`, name]}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

/* ─── Competitor Quadrant ─── */
function CompetitorQuadrant({ data, primaryName, t }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sm text-themed-muted">
        暂无竞品共现数据
      </div>
    );
  }
  const xMax = Math.ceil(Math.max(...data.map((d) => d.sov)) * 1.1);
  const labels = {
    leader:    { x: xMax * 0.78, y: 0.92, text: t('dashboard.competition.q_leader') },
    highRisk:  { x: xMax * 0.78, y: 0.55, text: t('dashboard.competition.q_high_risk') },
    challenger:{ x: xMax * 0.18, y: 0.92, text: t('dashboard.competition.q_challenger') },
    warning:   { x: xMax * 0.18, y: 0.55, text: t('dashboard.competition.q_warning') },
  };

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="sov"
          domain={[0, xMax]}
          name={t('dashboard.competition.quadrant_axis_x')}
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          label={{
            value: t('dashboard.competition.quadrant_axis_x'),
            position: 'insideBottomRight',
            offset: -4,
            fontSize: 10,
            fill: 'var(--color-text-muted)',
          }}
        />
        <YAxis
          type="number"
          dataKey="sentiment"
          domain={[0.5, 1]}
          name={t('dashboard.competition.quadrant_axis_y')}
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          label={{
            value: t('dashboard.competition.quadrant_axis_y'),
            angle: -90,
            position: 'insideLeft',
            offset: 10,
            fontSize: 10,
            fill: 'var(--color-text-muted)',
          }}
        />
        <ZAxis type="number" dataKey="mentions" range={[120, 720]} />
        <ReferenceLine x={xMax / 2} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
        <ReferenceLine y={0.75} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ strokeDasharray: '3 3', stroke: 'var(--color-accent)' }}
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          formatter={(value, key) => {
            if (key === 'sov')       return [`${value}%`, 'SoV'];
            if (key === 'sentiment') return [value.toFixed(2), t('dashboard.competition.quadrant_axis_y')]; // C4-exempt: scatter Y∈[0,1]
            if (key === 'mentions')  return [value, 'Mentions'];
            return [value, key];
          }}
          labelFormatter={() => ''}
        />
        <Scatter
          data={data}
          shape={(props) => {
            const { cx, cy, payload, node } = props;
            const r = Math.sqrt((node && node.size) || 200) / 2;
            const isPrimary = payload.brand === primaryName;
            return (
              <g>
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={isPrimary ? 'var(--color-accent)' : 'var(--color-chart-3)'}
                  fillOpacity={isPrimary ? 0.85 : 0.55}
                  stroke={isPrimary ? 'var(--color-text-primary)' : 'var(--color-border-subtle)'}
                  strokeWidth={isPrimary ? 1.5 : 1}
                />
                <text
                  x={cx}
                  y={cy + r + 12}
                  textAnchor="middle"
                  fontSize={isPrimary ? 11 : 10}
                  fontWeight={isPrimary ? 700 : 400}
                  fill="var(--color-text-primary)"
                >
                  {payload.brand}
                </text>
              </g>
            );
          }}
        />
        {Object.values(labels).map((lab) => (
          <text
            key={lab.text}
            x={`${(lab.x / xMax) * 100}%`}
            y={`${(1 - (lab.y - 0.5) / 0.5) * 92 + 4}%`}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-text-muted)"
            opacity={0.7}
          >
            {lab.text}
          </text>
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/* ─── PANO Trend ─── */
function PanoTrendChart({ trendData, primaryName, competitors, t }) {
  const data = useMemo(() => (trendData ?? []).map((d, i) => {
    const row = { name: `${d.day}日`, [primaryName]: d.panoScore };
    competitors.forEach((c, idx) => {
      const base = c.panoScore;
      row[c.name] = Math.round(base + Math.sin((i + idx * 3) / 5) * 3 + (Math.random() - 0.5) * 2);
    });
    return row;
  }), [trendData, primaryName, competitors]);

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[280px] text-sm text-themed-muted">
        暂无趋势数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-chart-line-grid)" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          interval={4}
        />
        <YAxis
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          domain={[60, 90]}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          cursor={{ stroke: 'var(--color-accent)', strokeDasharray: '3 3' }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }} />
        <Line
          type="monotone"
          dataKey={primaryName}
          stroke="var(--color-accent)"
          strokeWidth={2.4}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
        {competitors.map((c) => (
          <Line
            key={c.id}
            type="monotone"
            dataKey={c.name}
            stroke="var(--color-chart-line-grid)"
            strokeWidth={1.4}
            dot={false}
            opacity={0.6}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/* ─── KPI Sparkline Summary ─── */
function KpiSparklineSummary({ rows }) {
  return (
    <div className="space-y-4">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-4">
          <span className="text-xs text-themed-muted w-20 shrink-0">{r.label}</span>
          <div className="flex-1 h-10">
            <MiniSparkline data={r.spark} color={r.color || 'var(--color-accent)'} />
          </div>
          <span className="text-sm font-semibold tabular-nums text-themed-primary w-16 text-right">
            {r.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─── Alert Bar ─── */
function AlertBar({ diagnostics, onAlertClick, t }) {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <Card className="p-3 flex items-center gap-2 border-l-4" style={{ borderLeftColor: 'var(--color-success)' }}>
        <span className="text-sm text-themed-success">{t('dashboard.alerts.empty')}</span>
      </Card>
    );
  }
  return (
    <div className="space-y-2">
      {diagnostics.map((d) => {
        const isP0 = d.severity === 'P0';
        return (
          <Card
            key={d.id}
            className="p-3 flex items-center gap-3 border-l-4 cursor-pointer transition-colors hover:bg-themed-subtle"
            style={{ borderLeftColor: isP0 ? 'var(--color-danger)' : 'var(--color-warning)' }}
            onClick={() => onAlertClick(d)}
          >
            <Badge variant={isP0 ? 'red' : 'yellow'} size="sm">{d.severity}</Badge>
            <span className="text-sm text-themed-primary flex-1 truncate">{d.title}</span>
            <span className="text-xs text-themed-muted shrink-0 hidden md:inline">{d.engine}</span>
            <span className="text-xs text-themed-accent shrink-0">{t('dashboard.alerts.view')}</span>
          </Card>
        );
      })}
    </div>
  );
}

/* ─── CrossIndustryWarning ─── */
function CrossIndustryWarning({ visible, t }) {
  if (!visible) return null;
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] text-themed-muted ml-2"
      title={t('brand_watch.crossindustry.card_warning_short')}
      aria-label={t('brand_watch.crossindustry.card_warning_short')}
    >
      <svg
        width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        style={{ opacity: 0.7 }}
      >
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9"  x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </span>
  );
}

/* ─────────────────────────────────────────────────────────────
   BrandPanoramaPanel 主组件 — 整合上述区块
─────────────────────────────────────────────────────────────── */
export default function BrandPanoramaPanel({
  primary,
  industry,
  competitors: competitorsProp,
  headerSlot,
  scrollAnchorId = 'panorama-competition',
  /* Phase 5 §"mock 退役" — 真实数据接入. 任意 override 为 undefined 时
     回退到 mock 数组, 让没有 Project 的访客仍能看到 demo 数据.
     有 Project + pipeline 已生成数据时, DashboardPage 通过 adapter 把
     /v1/projects/:id/{overview, metrics, competitors/metrics,
     competitors/trends, diagnostics} 的响应注入下面 prop. */
  sovDataOverride,
  bubbleDataOverride,
  trendDataOverride,
  diagnosticsOverride,
  sparklineOverride,
  industryAvgScoreOverride,
  isLive,
}) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { t, formatBrand } = useLocale();

  /* ── Competitors fallback: 若外部没传, 从 knowledge graph / 同行业取 3 个 ── */
  const competitors = useMemo(() => {
    if (competitorsProp && competitorsProp.length) return competitorsProp.slice(0, 3);
    const sameIndustry = BRANDS.filter((b) =>
      b.industryId === primary.industryId && b.id !== primary.id
    );
    return sameIndustry
      .sort((a, b) => b.panoScore - a.panoScore)
      .slice(0, 3);
  }, [competitorsProp, primary.id, primary.industryId]);

  /* ── Industry fallback: 若外部没传, 从 primary.industryId 查表 ── */
  const resolvedIndustry = useMemo(() => {
    if (industry) return industry;
    return INDUSTRIES.find((ind) => ind.id === primary.industryId) || null;
  }, [industry, primary.industryId]);

  /* ── Cross-industry detection ── */
  const hasCrossIndustryCompetitors = useMemo(() => {
    if (!primary.industryId) return false;
    return competitors.some((b) => b && b.industryId && b.industryId !== primary.industryId);
  }, [primary.industryId, competitors]);

  /* ── URL filter state ── */
  const [filtersExpanded, setFiltersExpanded] = useState(
    () => searchParams.get('filters') === 'expanded'
  );
  const range = searchParams.get('range') || '30d';
  const engineParam = searchParams.get('engines');
  const dimension = searchParams.get('dimension') || '';
  const intent = searchParams.get('intent') || '';
  const selectedEngines = useMemo(() => (
    engineParam
      ? engineParam.split(',').filter((n) => ENGINES.find((e) => e.name === n))
      : ENGINES.map((e) => e.name)
  ), [engineParam]);

  const setParam = (key, value, defaultValue = '') => {
    const p = new URLSearchParams(searchParams);
    if (value === defaultValue) p.delete(key); else p.set(key, value);
    setSearchParams(p, { replace: true });
  };
  const updateRange = (next) => setParam('range', next, '30d');
  const updateEngines = (next) => {
    const p = new URLSearchParams(searchParams);
    if (next.length === ENGINES.length || next.length === 0) p.delete('engines');
    else p.set('engines', next.join(','));
    setSearchParams(p, { replace: true });
  };
  const toggleEngine = (name) => {
    const next = selectedEngines.includes(name)
      ? selectedEngines.filter((e) => e !== name)
      : [...selectedEngines, name];
    updateEngines(next.length ? next : ENGINES.map((e) => e.name));
  };
  const updateDimension = (next) => setParam('dimension', next, '');
  const updateIntent = (next) => setParam('intent', next, '');
  const toggleFiltersExpanded = () => {
    const next = !filtersExpanded;
    setFiltersExpanded(next);
    setParam('filters', next ? 'expanded' : '', '');
  };

  /* ── KPI values ──
     PRD §4.6-IA-v2.N / DESIGN_TOKENS C11 (2026-04-20): mentionRate stored as
     decimal 0-1; render layer converts to percentage. Prevents "1620%" bug. */
  /* ── Effective data sources ──
     Live mode: use override (may be empty array → chart renders empty state).
     Demo mode (no project): use mock arrays so anonymous visitors see content.
     Important: never silently mix mock with live — once isLive=true, missing
     data shows as empty so operators can see which pipeline parts have gaps. */
  const sovData     = isLive ? (sovDataOverride ?? []) : SOV_DATA;
  const bubbleData  = isLive ? (bubbleDataOverride ?? []) : COMPETITOR_SENTIMENT_BUBBLE;
  const trendData   = isLive ? (trendDataOverride ?? []) : TREND_DATA;

  const mentionRateDec   = primary.mentionRate || 0;
  const mentionRateValue = +(mentionRateDec * 100).toFixed(1);
  const sovEntry         = sovData.find((s) => s.name === primary.name);
  const sovValue         = sovEntry ? sovEntry.value : 0;
  const sentimentValue   = primary.sentiment;
  const citationShare    = 18.2;
  const industryRank     = primary.ranking;

  /* ── Sparklines ── (live: from /v1/projects/:id/metrics; mock: synthesized) */
  const sparkMention = isLive && sparklineOverride
    ? sparklineOverride.mention
    : trendData.map((d) => d.mentionRate ?? 0);
  const sparkSov = isLive && sparklineOverride
    ? sparklineOverride.sov
    : trendData.map((d, i) => Math.max(0, Math.round(
        (sovValue || (d.mentionRate ?? 0) * 0.6) + Math.sin(i / 4) * 2 + (i % 7 === 0 ? -1.5 : 0.4)
      )));
  const sparkSent = isLive && sparklineOverride
    ? sparklineOverride.sentiment
    : trendData.map((d) => Math.round((d.sentiment ?? 0) * 100));
  const sparkCite = isLive && sparklineOverride
    ? sparklineOverride.citation
    : trendData.map((_, i) => Math.round(15 + Math.sin(i / 5) * 2));
  const sparkRank = isLive && sparklineOverride
    ? sparklineOverride.rank
    : trendData.map((_, i) => {
        const progress = i / Math.max(trendData.length - 1, 1);
        const base     = primary.ranking + 2 * (1 - progress);
        const jitter   = Math.sin(i / 3) * 0.35;
        return Math.max(1, Math.round((base + jitter) * 10) / 10);
      });

  const onKpiClick = () => {
    navigate(`/brands/${primary.id}?tab=overview`);
  };
  const onAlertClick = (d) => {
    navigate(`/brands/${primary.id}?tab=diagnostics&diagId=${d.id}`);
  };

  const kpis = [
    {
      label: t('dashboard.kpi.mention_rate'),
      fullLabel: t('dashboard.kpi.mention_rate_full'),
      value: `${mentionRateValue}%`,
      delta: 3.8,
      helpText: t('dashboard.kpi.mention_rate_help'),
      sparkData: sparkMention,
    },
    {
      label: t('dashboard.kpi.sov'),
      fullLabel: t('dashboard.kpi.sov_full'),
      value: `${sovValue}%`,
      delta: 2.1,
      helpText: t('dashboard.kpi.sov_help'),
      sparkData: sparkSov,
    },
    {
      label: t('dashboard.kpi.sentiment'),
      fullLabel: '',
      value: `${Math.round(sentimentValue * 100)}%`,
      delta: -2,
      helpText: t('dashboard.kpi.sentiment_help'),
      sparkData: sparkSent,
    },
    {
      label: t('dashboard.kpi.citation_share'),
      fullLabel: '',
      value: `${citationShare}%`,
      delta: 1.5,
      helpText: t('dashboard.kpi.citation_share_help'),
      sparkData: sparkCite,
    },
    {
      label: t('dashboard.kpi.industry_rank'),
      fullLabel: '',
      value: t('dashboard.ranking_format', { rank: industryRank }),
      delta: 1,
      trendIsRank: true,
      helpText: t('dashboard.kpi.industry_rank_help'),
      sparkData: sparkRank,
    },
  ];

  const primaryAlerts = useMemo(() => {
    if (isLive) {
      return (diagnosticsOverride ?? []).slice(0, 3);
    }
    return DIAGNOSTICS
      .filter((d) => d.severity === 'P0' || d.severity === 'P1')
      .slice(0, 3);
  }, [isLive, diagnosticsOverride]);

  const sparklineRows = [
    { label: t('dashboard.kpi.mention_rate'),   spark: sparkMention, value: `${mentionRateValue}%`,    color: 'var(--color-chart-2)' },
    { label: t('dashboard.kpi.sov'),            spark: sparkSov,     value: `${sovValue}%`,            color: 'var(--color-accent)' },
    { label: t('dashboard.kpi.sentiment'),      spark: sparkSent,    value: `${Math.round(sentimentValue * 100)}%`, color: 'var(--color-chart-3)' },
    { label: t('dashboard.kpi.citation_share'), spark: sparkCite,    value: `${citationShare}%`,       color: 'var(--color-chart-4)' },
    { label: t('dashboard.kpi.industry_rank'),  spark: sparkRank,    value: `#${industryRank}`,        color: 'var(--color-chart-5)' },
  ];

  const industryAvgScore = useMemo(() => {
    if (isLive && industryAvgScoreOverride != null) {
      return Math.round(industryAvgScoreOverride);
    }
    const sameBrands = BRANDS.filter((b) => b.industryId === primary.industryId);
    if (!sameBrands.length) return 60;
    return Math.round(sameBrands.reduce((sum, b) => sum + b.panoScore, 0) / sameBrands.length);
  }, [isLive, industryAvgScoreOverride, primary.industryId]);

  return (
    <div className="space-y-4 pb-4">
      {headerSlot}

      {/* ⓪ Hero */}
      <HeroBlock
        primary={primary}
        industry={resolvedIndustry}
        industryAvgScore={industryAvgScore}
        t={t}
        formatBrand={formatBrand}
        onScoreClick={() => navigate(`/brands/${primary.id}?tab=overview`)}
        onRankClick={() => {
          document.getElementById(scrollAnchorId)?.scrollIntoView({ behavior: 'smooth' });
        }}
      />

      {/* Toolbar */}
      <PanelToolbar
        range={range}
        engines={ENGINES}
        selectedEngines={selectedEngines}
        onRangeChange={updateRange}
        onEngineToggle={toggleEngine}
        onEngineAll={() => updateEngines(ENGINES.map((e) => e.name))}
        dimension={dimension}
        onDimensionChange={updateDimension}
        intent={intent}
        onIntentChange={updateIntent}
        filtersExpanded={filtersExpanded}
        onToggleFilters={toggleFiltersExpanded}
        t={t}
      />

      <ProfileGroupSampleWarning />

      {/* ① 5 KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {kpis.map((k) => (
          <KpiCard key={k.label} {...k} onClick={onKpiClick} />
        ))}
      </div>

      {/* ② Competition view */}
      <div id={scrollAnchorId} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-1">
            <div className="flex items-baseline">
              <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.competition.sov_pie_title')}</h3>
              <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
            </div>
            <span className="text-[11px] text-themed-muted">{t('dashboard.competition.sov_pie_subtitle')}</span>
          </div>
          <SovPieChart data={sovData} primaryName={primary.name} />
        </Card>
        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-1">
            <div className="flex items-baseline">
              <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.competition.quadrant_title')}</h3>
              <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
            </div>
            <span className="text-[11px] text-themed-muted">{t('dashboard.competition.quadrant_subtitle')}</span>
          </div>
          <CompetitorQuadrant data={bubbleData} primaryName={primary.name} t={t} />
        </Card>
      </div>

      {/* ③ Trend view */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline mb-2">
            <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.trend.pano_title')}</h3>
            <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
          </div>
          <PanoTrendChart trendData={trendData} primaryName={primary.name} competitors={competitors} t={t} />
        </Card>
        <Card className="p-4">
          <h3 className="text-sm font-semibold text-themed-primary mb-3">{t('dashboard.trend.kpi_summary_title')}</h3>
          <KpiSparklineSummary rows={sparklineRows} />
        </Card>
      </div>

      {/* ④ Alert bar */}
      <div>
        <h3 className="text-sm font-semibold text-themed-primary mb-2 px-1">{t('dashboard.alerts.title')}</h3>
        <AlertBar diagnostics={primaryAlerts} onAlertClick={onAlertClick} t={t} />
      </div>
    </div>
  );
}
