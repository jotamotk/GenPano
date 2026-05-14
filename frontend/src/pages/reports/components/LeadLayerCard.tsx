import { Badge, Button, Card } from '../../../components/ui';
import type { TFn } from '../lib/types';

/* ─────────────────────────────────────────────────────────────
 * 7-pre. LeadDiagnosticView — PRD §4.7.4a 4 层架构
 *
 *   1. Quick Wins              (Operator · 短期可做, 低成本)
 *   2. Strategic Bets          (Manager · 跨季度, 需资源决策)
 *   3. Branding Risks          (Branding · 叙事/人设级风险)
 *   4. Consulting Accelerators (转化 · 适合付费咨询的复杂场景)
 *
 *   ⚠️ 严禁渲染具体执行剧本 (PRD §4.8.6) —
 *      每层只展示: 焦点区 + 锚点问题 + 建议参与团队 + 评估窗口
 *      具体动作清单留给付费咨询业务
 * ─────────────────────────────────────────────────────────── */

/* Lead-diagnostic items mirror DIAGNOSTICS shape from data/mock — kept loose. */
interface LeadDiagItem {
  id: string;
  type?: string;
  brandId?: string;
  severity?: string;
  category?: string;
  title?: string;
  focusArea?: string;
  readerHints?: string[];
  causalChain?: {
    alternativeHypotheses?: unknown[];
    confidenceLevel?: string;
  };
  priorityScore?: { ease?: number; impact?: number; urgency?: number; composite?: number };
  anchorQuestions: string[];
}

export function classifyDiagnosticsForLead(diags: LeadDiagItem[]) {
  const quickWins: LeadDiagItem[] = [];
  const strategicBets: LeadDiagItem[] = [];
  const brandingRisks: LeadDiagItem[] = [];
  const consultingAccelerators: LeadDiagItem[] = [];

  diags.forEach((d) => {
    const ease = d.priorityScore?.ease ?? 5;
    const impact = d.priorityScore?.impact ?? 5;
    const isHighSev = d.severity === 'P0' || d.severity === 'P1';
    const isBranding =
      (d.readerHints || []).includes('branding') || d.category === 'narrative_drift';
    const isComplex =
      (d.causalChain?.alternativeHypotheses || []).length > 0 ||
      d.causalChain?.confidenceLevel === 'low';

    // Branding 优先 (避免 narrative_drift 被分到其他层)
    if (isBranding && isHighSev) {
      brandingRisks.push(d);
      return;
    }
    // Consulting accelerators: 高严重度 + 复杂/低置信
    if (isHighSev && isComplex && impact >= 7) {
      consultingAccelerators.push(d);
      return;
    }
    // Quick wins: 高 ease + 中等以上影响
    if (ease >= 7 && impact >= 5) {
      quickWins.push(d);
      return;
    }
    // Strategic bets: 高影响, 低/中 ease
    if (impact >= 7 || isHighSev) {
      strategicBets.push(d);
      return;
    }
    quickWins.push(d);
  });

  return { quickWins, strategicBets, brandingRisks, consultingAccelerators };
}

export const LEAD_LAYER_META: Record<string, {
  color: string;
  bg: string;
  borderClass: string;
  borderColor: string;
}> = {
  quickWins: {
    color: 'var(--color-success)',
    bg: 'rgba(10,187,135,0.05)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-success)',
  },
  strategicBets: {
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-subtle)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-accent)',
  },
  brandingRisks: {
    color: 'var(--color-warning-text)',
    bg: 'rgba(245,166,35,0.06)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-warning)',
  },
  consultingAccelerators: {
    color: 'var(--color-danger-text)',
    bg: 'rgba(219,55,63,0.05)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-danger)',
  },
};

export function LeadLayerCard({
  layerKey,
  items,
  t,
  onContactConsultant,
}: {
  layerKey: string;
  items: LeadDiagItem[];
  t: TFn;
  onContactConsultant?: () => void;
}) {
  const meta = LEAD_LAYER_META[layerKey];
  const titleKey = `reports.lead.layer.${layerKey}.title`;
  const descKey = `reports.lead.layer.${layerKey}.description`;
  const readerKey = `reports.lead.layer.${layerKey}.reader`;
  const isPaid = layerKey === 'consultingAccelerators';

  return (
    <Card
      className={`p-5 ${meta.borderClass}`}
      style={{ borderLeftColor: meta.borderColor, background: meta.bg }}
    >
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-1 flex-wrap">
            <h3 className="text-sm font-semibold text-themed-primary">{t(titleKey)}</h3>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
              style={{ background: 'rgba(255,255,255,0.6)', color: meta.color }}
            >
              {t(readerKey)}
            </span>
            <Badge variant={isPaid ? 'red' : 'default'} size="xs">
              {items.length} {t('reports.lead.items_label')}
            </Badge>
          </div>
          <p className="text-[12px] text-themed-secondary leading-relaxed">{t(descKey)}</p>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-[11px] text-themed-faint italic mt-2">
          {t('reports.lead.empty')}
        </p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 5).map((d) => (
            <div
              key={d.id}
              className="rounded-md p-3 bg-themed-card border border-themed-card"
            >
              <div className="flex items-start gap-2 mb-1.5 flex-wrap">
                <Badge
                  variant={
                    ({ P0: 'red', P1: 'orange', P2: 'accent', P3: 'default' } as Record<string, string>)[d.severity as string] || 'default'
                  }
                  size="xs"
                >
                  {d.severity}
                </Badge>
                <span className="text-[12px] font-semibold text-themed-primary flex-1 min-w-0">{d.title}</span>
                {d.priorityScore?.composite != null && (
                  <span className="text-[10px] text-themed-muted shrink-0">
                    优先级 <span className="font-semibold tabular-nums text-themed-accent">{d.priorityScore.composite}</span>
                  </span>
                )}
              </div>
              {d.focusArea && (
                <div className="text-[11px] text-themed-secondary mb-1">
                  <span className="text-themed-muted">焦点: </span>
                  {d.focusArea}
                </div>
              )}
              {d.anchorQuestions?.length > 0 && (
                <details>
                  <summary className="text-[11px] font-medium text-themed-accent cursor-pointer hover:opacity-80">
                    {d.anchorQuestions.length} 个锚点问题
                  </summary>
                  <ol className="mt-2 space-y-1 pl-1">
                    {d.anchorQuestions.slice(0, 3).map((q, i) => (
                      <li key={i} className="text-[11px] text-themed-secondary leading-relaxed">
                        <span className="text-themed-faint mr-1.5 tabular-nums">{i + 1}.</span>
                        {q}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          ))}
          {items.length > 5 && (
            <p className="text-[11px] text-themed-faint italic">
              {t('reports.lead.more', { count: items.length - 5 })}
            </p>
          )}
        </div>
      )}

      {isPaid && items.length > 0 && (
        <div
          className="rounded-md p-3 mt-3 flex items-center justify-between border"
          style={{ borderColor: meta.borderColor, background: 'rgba(255,255,255,0.7)' }}
        >
          <div>
            <div className="text-[12px] font-semibold" style={{ color: meta.color }}>
              {t('reports.lead.paid_cta_title')}
            </div>
            <div className="text-[11px] text-themed-secondary mt-0.5">
              {t('reports.lead.paid_cta_subtitle')}
            </div>
          </div>
          <Button variant="accent" size="sm" onClick={onContactConsultant}>
            {t('reports.lead.paid_cta_button')}
          </Button>
        </div>
      )}
    </Card>
  );
}
