/*
 * DiagnosticCard — PRD §4.7.0-a 洞察 Stack × 三读者视角 卡片
 * ──────────────────────────────────────────────────────────────
 * 渲染顺序 (固化, 不得调整):
 *   Header  — Severity + Title + meta (type / engine / detected / priority)
 *   Layer 1 — Observation (description + evidence + responseSamples)
 *   Layer 2 — Explanation (causalChain + industryBenchmark + priorityScore + timeSeries)
 *   Layer 3 — Direction   (focusArea + direction + anchorQuestions + ifUntreated + decisionPrompt)
 *   CTA     — 联系 GEO 顾问 (Lead form 入口, 由父组件传入 onContactConsultant)
 *
 * 🚫 严禁渲染 (PRD §4.8.6):
 *   ✗ optimizationSteps (playbook, 属付费咨询业务边界)
 *   ✗ "执行步骤 1-2-3" "发布 X 篇内容" 等剧本式建议
 *   ✗ 自由文本 benchmarkReference (使用结构化 industryBenchmark)
 */
import { Badge, Button } from '../ui';

const READER_LABELS = {
  operator: 'Operator',
  manager: 'Manager',
  branding: 'Branding',
};

const READER_LABELS_ZH = {
  operator: '执行',
  manager: '管理',
  branding: '品牌',
};

const TYPE_LABELS = { brand: '品牌', product: '产品', industry: '行业' };

const TREND_LABELS = {
  new: '新增',
  growing: '加剧',
  persisting: '持续',
  improving: '好转',
  resolved: '已解',
};

const CONFIDENCE_LABELS = { high: '高置信', medium: '中等', low: '低置信' };

const sevColor = (s) => ({ P0: 'red', P1: 'orange', P2: 'accent', P3: 'default' }[s] || 'default');

const sevBorderClass = (s) =>
  ({ P0: 'border-l-4', P1: 'border-l-4', P2: 'border-l-4', P3: 'border-l-2' }[s] || '');

const sevBorderColor = (s) =>
  ({
    P0: 'var(--color-danger)',
    P1: 'var(--color-warning)',
    P2: 'var(--color-accent)',
    P3: 'var(--color-border)',
  }[s] || 'var(--color-border)');

const confidenceColor = (c) =>
  ({ high: 'var(--color-success)', medium: 'var(--color-warning)', low: 'var(--color-danger)' }[c] || 'var(--color-border)');

const formatPercent = (v) => (v > 0 ? `+${v}%` : `${v}%`);

/* ─────────────────────────── Layer Section Header ─────────────────────────── */
function StackSectionHeader({ layer, title, hint }) {
  const layerColor = {
    1: 'var(--color-text-muted)',
    2: 'var(--color-accent)',
    3: 'var(--color-success)',
  }[layer];

  return (
    <div className="flex items-baseline gap-2 mb-3">
      <span
        className="inline-flex items-center justify-center w-6 h-6 rounded-md text-[10px] font-bold tabular-nums"
        style={{ background: `${layerColor}1A`, color: layerColor }}
      >
        L{layer}
      </span>
      <span className="text-xs font-semibold text-themed-primary">{title}</span>
      {hint && <span className="text-[11px] text-themed-faint">{hint}</span>}
    </div>
  );
}

/* ─────────────────────────── L1 · Observation ─────────────────────────── */
function ObservationBlock({ diag }) {
  const ev = diag.evidence || {};
  return (
    <section>
      <StackSectionHeader layer={1} title="观察 · Observation" hint="What changed" />
      <p className="text-sm text-themed-secondary leading-relaxed mb-3">{diag.description}</p>

      {/* Evidence pills */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="rounded-lg border border-themed-card p-3 bg-themed-subtle">
          <div className="text-[11px] text-themed-muted mb-1">{ev.metric || '—'}</div>
          <div className="flex items-baseline gap-2">
            <span className="text-base font-semibold text-themed-primary tabular-nums">{ev.currentValue ?? '—'}</span>
            <span className="text-[11px] text-themed-faint">vs prev {ev.previousValue ?? '—'}</span>
            <span
              className="text-[11px] font-semibold tabular-nums"
              style={{ color: ev.changePercent < 0 ? 'var(--color-danger-text)' : 'var(--color-success-text)' }}
            >
              {ev.changePercent != null ? formatPercent(ev.changePercent) : ''}
            </span>
          </div>
          <div className="text-[11px] text-themed-faint mt-1">{ev.timeRange}</div>
        </div>

        <div className="rounded-lg border border-themed-card p-3 bg-themed-subtle">
          <div className="text-[11px] text-themed-muted mb-1.5">影响范围</div>
          <div className="text-[11px] text-themed-secondary mb-1">
            <span className="text-themed-faint">引擎: </span>
            {(ev.affectedEngines || []).join(' · ') || '—'}
          </div>
          <div className="text-[11px] text-themed-secondary line-clamp-2">
            <span className="text-themed-faint">命中查询: </span>
            {(ev.affectedQueries || []).slice(0, 3).join(' / ') || '—'}
          </div>
        </div>
      </div>

      {/* Response samples */}
      {diag.responseSamples?.length > 0 && (
        <details className="rounded-lg border border-themed-card p-3 bg-themed-card">
          <summary className="text-[11px] font-medium text-themed-muted cursor-pointer hover:text-themed-primary">
            原始 Response 样本 ({diag.responseSamples.length})
          </summary>
          <div className="mt-3 space-y-2">
            {diag.responseSamples.map((s) => (
              <div key={s.responseId} className="rounded-md border border-themed-subtle p-2.5 bg-themed-subtle">
                <div className="flex items-center justify-between mb-1">
                  <Badge variant="default" size="xs">{s.engine}</Badge>
                  <span className="text-[10px] text-themed-faint tabular-nums">{s.capturedAt}</span>
                </div>
                <p className="text-[11px] text-themed-secondary leading-relaxed">"{s.snippet}"</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

/* ─────────────────────────── L2 · Explanation ─────────────────────────── */
function ExplanationBlock({ diag }) {
  const cc = diag.causalChain || {};
  const ib = diag.industryBenchmark || {};
  const ps = diag.priorityScore || {};
  const ts = diag.timeSeries || {};
  const confColor = confidenceColor(cc.confidenceLevel);

  return (
    <section className="rounded-lg border border-themed-card p-4" style={{ background: 'rgba(96,91,255,0.03)' }}>
      <StackSectionHeader layer={2} title="解释 · Explanation" hint="Why it happened" />

      {/* Causal chain */}
      {cc.hypothesizedMechanism && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[11px] font-semibold text-themed-primary">假设机制</span>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
              style={{ background: `${confColor}1A`, color: confColor }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: confColor }} />
              {CONFIDENCE_LABELS[cc.confidenceLevel] || '—'}
            </span>
          </div>
          <p className="text-[12px] text-themed-secondary leading-relaxed">{cc.hypothesizedMechanism}</p>
          {cc.alternativeHypotheses?.length > 0 && (
            <div className="mt-2 pl-2 border-l-2 border-themed-subtle">
              <span className="text-[10px] font-medium text-themed-muted">备选假设: </span>
              <span className="text-[11px] text-themed-secondary">{cc.alternativeHypotheses.join(' · ')}</span>
            </div>
          )}
        </div>
      )}

      {/* Industry benchmark */}
      {ib.metric && (
        <div className="mb-4 rounded-lg border border-themed-card bg-themed-card p-3">
          <div className="text-[11px] font-semibold text-themed-primary mb-2">行业对标 · {ib.metric}</div>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div>
              <div className="text-[10px] text-themed-muted mb-0.5">我方</div>
              <div className="text-base font-semibold text-themed-primary tabular-nums">{ib.myValue}</div>
            </div>
            <div>
              <div className="text-[10px] text-themed-muted mb-0.5">行业中位</div>
              <div className="text-base font-medium text-themed-secondary tabular-nums">{ib.industryMedian}</div>
            </div>
            <div>
              <div className="text-[10px] text-themed-muted mb-0.5">Top 10 均值</div>
              <div className="text-base font-medium text-themed-secondary tabular-nums">{ib.industryTop10Avg}</div>
            </div>
          </div>
          {ib.topCompetitor && (
            <div className="rounded-md p-2.5 bg-themed-subtle border border-themed-subtle">
              <div className="flex items-baseline justify-between mb-1">
                <span className="text-[11px] font-semibold text-themed-primary">
                  标杆: {ib.topCompetitor.brandName}
                </span>
                <span className="text-sm font-bold tabular-nums text-themed-accent">{ib.topCompetitor.value}</span>
              </div>
              <ul className="space-y-0.5">
                {(ib.topCompetitor.keyCharacteristics || []).map((k, i) => (
                  <li key={i} className="text-[11px] text-themed-secondary leading-relaxed">· {k}</li>
                ))}
              </ul>
            </div>
          )}
          {ib.gapAnalysis && (
            <div className="flex items-center gap-3 mt-2 text-[11px] text-themed-faint">
              <span>距中位 <span className="text-themed-secondary tabular-nums">{ib.gapAnalysis.gapToMedian}</span></span>
              <span>距 Top <span className="text-themed-secondary tabular-nums">{ib.gapAnalysis.gapToTop}</span></span>
              <span>分位 <span className="text-themed-secondary tabular-nums">{ib.gapAnalysis.percentileRank}%</span></span>
            </div>
          )}
        </div>
      )}

      {/* Priority + Trend */}
      <div className="grid grid-cols-2 gap-3">
        {ps.composite != null && (
          <div className="rounded-lg border border-themed-card bg-themed-card p-3">
            <div className="text-[11px] font-semibold text-themed-primary mb-2">优先级评分</div>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-2xl font-bold tabular-nums text-themed-accent">{ps.composite}</span>
              <span className="text-[10px] text-themed-faint">/ 10</span>
              {ps.rankWithinPeriod && (
                <span className="ml-auto text-[10px] text-themed-muted">本周期排名 #{ps.rankWithinPeriod}</span>
              )}
            </div>
            <div className="space-y-1">
              {[
                { label: '影响 Impact', v: ps.impact },
                { label: '难易 Ease', v: ps.ease },
                { label: '紧迫 Urgency', v: ps.urgency },
              ].map((row) => (
                <div key={row.label} className="flex items-center gap-2">
                  <span className="text-[10px] text-themed-muted w-20 shrink-0">{row.label}</span>
                  <div className="flex-1 h-1 rounded-full bg-themed-subtle overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${(row.v || 0) * 10}%`, background: 'var(--color-accent)' }}
                    />
                  </div>
                  <span className="text-[10px] tabular-nums text-themed-secondary w-4 text-right">{row.v}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {ts.firstObservedAt && (
          <div className="rounded-lg border border-themed-card bg-themed-card p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-themed-primary">趋势</span>
              <Badge variant={ts.trendStatus === 'growing' ? 'red' : ts.trendStatus === 'persisting' ? 'orange' : 'default'} size="xs">
                {TREND_LABELS[ts.trendStatus] || ts.trendStatus}
              </Badge>
            </div>
            <div className="text-[10px] text-themed-muted mb-1">
              首次观察 <span className="text-themed-secondary tabular-nums">{ts.firstObservedAt}</span>
            </div>
            <div className="text-[10px] text-themed-muted mb-2">
              已存在 <span className="text-themed-secondary tabular-nums">{ts.ageInDays}</span> 天
            </div>
            {/* Severity timeline */}
            {ts.severityHistory?.length > 0 && (
              <div className="flex items-center gap-1">
                {ts.severityHistory.map((h, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full h-1.5 rounded-full"
                      style={{ background: sevBorderColor(h.severity) }}
                      title={`${h.date} · ${h.severity}`}
                    />
                    <span className="text-[9px] text-themed-faint tabular-nums">{h.severity}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/* ─────────────────────────── L3 · Direction ─────────────────────────── */
function DirectionBlock({ diag, onContactConsultant }) {
  const iu = diag.ifUntreated || {};
  const pi = diag.predictedImpact || {};

  return (
    <section
      className="rounded-lg border p-4"
      style={{ borderColor: 'var(--color-success)', background: 'rgba(10,187,135,0.04)' }}
    >
      <StackSectionHeader layer={3} title="方向 · Direction" hint="Where to focus · 不含执行剧本" />

      {/* Focus area + direction */}
      {diag.focusArea && (
        <div className="mb-3">
          <div className="text-[11px] font-semibold text-themed-success mb-1">焦点区</div>
          <div className="text-sm font-semibold text-themed-primary mb-1.5">{diag.focusArea}</div>
          {diag.direction && (
            <p className="text-[12px] text-themed-secondary leading-relaxed">{diag.direction}</p>
          )}
        </div>
      )}

      {/* Anchor questions */}
      {diag.anchorQuestions?.length > 0 && (
        <div className="mb-3 rounded-md p-3 bg-themed-card border border-themed-card">
          <div className="text-[11px] font-semibold text-themed-primary mb-2">
            锚点问题 · Anchor Questions
            <span className="text-[10px] text-themed-faint ml-2 font-normal">事实探查型, 不是执行步骤</span>
          </div>
          <ol className="space-y-1.5">
            {diag.anchorQuestions.map((q, i) => (
              <li key={i} className="flex gap-2">
                <span
                  className="shrink-0 inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold mt-0.5"
                  style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
                >
                  {i + 1}
                </span>
                <p className="text-[12px] text-themed-secondary leading-relaxed">{q}</p>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* If untreated */}
      {iu.scenarioDescription && (
        <div
          className="rounded-md p-3 mb-3 border flex items-start gap-2.5"
          style={{ borderColor: 'var(--color-danger)', background: 'var(--color-danger-bg)' }}
        >
          <span className="text-themed-danger text-sm mt-0.5">⚠</span>
          <div className="flex-1">
            <div className="text-[11px] font-semibold text-themed-danger mb-1">不干预后果 · If Untreated</div>
            <p className="text-[12px] text-themed-secondary leading-relaxed mb-1.5">{iu.scenarioDescription}</p>
            <div className="flex items-center gap-2 text-[10px] text-themed-muted">
              <span className="tabular-nums">
                {iu.metric}: <span className="text-themed-secondary">{iu.projectedValue}</span>
              </span>
              <span>·</span>
              <span>{iu.timeframe}</span>
              <span>·</span>
              <span>{CONFIDENCE_LABELS[iu.confidence] || iu.confidence}</span>
            </div>
          </div>
        </div>
      )}

      {/* Decision prompt (manager) */}
      {diag.decisionPrompt && (
        <div className="rounded-md p-3 mb-3 border border-themed-card bg-themed-card">
          <div className="text-[11px] font-semibold text-themed-primary mb-1">决策提示 · For Manager</div>
          <p className="text-[12px] text-themed-secondary leading-relaxed">{diag.decisionPrompt}</p>
        </div>
      )}

      {/* Predicted impact */}
      {pi.scoreChange && (
        <div className="flex items-center gap-3 text-[11px] text-themed-muted mb-3">
          <span>处理后预期: </span>
          <span className="font-semibold text-themed-accent tabular-nums">{pi.scoreChange}</span>
          <span>·</span>
          <span>{pi.timeframe}</span>
          <span>·</span>
          <span>{CONFIDENCE_LABELS[pi.confidence] || pi.confidence}</span>
        </div>
      )}

      {/* CTA */}
      <div
        className="rounded-md p-3 flex items-center justify-between border"
        style={{ background: 'var(--color-accent-subtle)', borderColor: 'var(--color-accent)' }}
      >
        <div>
          <div className="text-[12px] font-semibold text-themed-accent">需要执行方案?</div>
          <div className="text-[11px] text-themed-secondary mt-0.5">
            执行剧本由 GEO 专业咨询团队提供 · 30 分钟免费诊断咨询
          </div>
        </div>
        <Button variant="accent" size="sm" onClick={() => onContactConsultant?.(diag.id)}>
          联系 GEO 顾问
        </Button>
      </div>
    </section>
  );
}

/* ─────────────────────────── Card Wrapper ─────────────────────────── */
export default function DiagnosticCard({ diag, expanded, onToggle, onContactConsultant }) {
  const ps = diag.priorityScore || {};

  return (
    <div
      className={`t-card overflow-hidden ${sevBorderClass(diag.severity)}`}
      style={{ borderLeftColor: sevBorderColor(diag.severity) }}
    >
      {/* Header */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left flex items-start justify-between"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Badge variant={sevColor(diag.severity)} size="sm">{diag.severity}</Badge>
            <h3 className="text-sm font-semibold text-themed-primary">{diag.title}</h3>
          </div>
          <div className="flex gap-1.5 flex-wrap items-center">
            <Badge variant="default" size="xs">{TYPE_LABELS[diag.type] || diag.type}</Badge>
            <Badge variant="default" size="xs">{diag.engine}</Badge>
            <Badge variant="default" size="xs">{diag.detected}</Badge>
            {ps.composite != null && (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-themed-muted">
                <span>优先级</span>
                <span className="font-semibold tabular-nums text-themed-accent">{ps.composite}</span>
              </span>
            )}
            {(diag.readerHints || []).map((r) => (
              <span
                key={r}
                className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
                style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent-text)' }}
                title={`Primary reader: ${READER_LABELS[r]}`}
              >
                {READER_LABELS_ZH[r] || r}
              </span>
            ))}
          </div>
        </div>
        <div
          className={`text-themed-muted text-sm transition-transform shrink-0 ml-3 ${expanded ? 'rotate-180' : ''}`}
        >
          ▼
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-themed-card mt-4 pt-4 space-y-4">
          <ObservationBlock diag={diag} />
          <ExplanationBlock diag={diag} />
          <DirectionBlock diag={diag} onContactConsultant={onContactConsultant} />
        </div>
      )}
    </div>
  );
}
