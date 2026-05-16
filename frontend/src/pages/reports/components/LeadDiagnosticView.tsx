import { useMemo } from 'react';
import { Badge, Card } from '../../../components/ui';
import { DIAGNOSTICS } from '../../../data/mock';
import type { ReportData, TFn } from '../lib/types';
import { LeadLayerCard, LEAD_LAYER_META, classifyDiagnosticsForLead } from './LeadLayerCard';

export function LeadDiagnosticView({
  report,
  brandName,
  t,
  onContactConsultant,
}: {
  report: ReportData;
  brandName: string;
  t: TFn;
  onContactConsultant?: () => void;
}) {
  // 该品牌相关诊断: industry 类全收 + 按品牌 ID 匹配.
  // Mock REPORTS.brand.id 形如 'brand-estee-lauder', DIAGNOSTICS[].brandId
  // 形如 'estee-lauder' — 比较前去掉 'brand-' 前缀做规范化.
  // 真实 lead_diagnostic payload 应通过 backend 返回 linked_diagnostic_ids
  // (PRD §4.7.4a, audit #1044 F4-4) — 这里先以 brand 维度做收敛, F4-3 详情
  // 适配器落地时改为消费 payload 自带的 linked diagnostics.
  const relevantDiags = useMemo(() => {
    const key = report.brand.id.replace(/^brand-/, '');
    return DIAGNOSTICS.filter(
      (d) => d.type === 'industry' || d.brandId === key,
    );
  }, [report.brand.id]);

  const layers = useMemo(() => classifyDiagnosticsForLead(relevantDiags), [relevantDiags]);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-baseline gap-3 mb-2 flex-wrap">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('reports.lead.architecture_title')}
          </h3>
          <Badge variant="orange" size="sm">{t('reports.sections.variant.strengthened')}</Badge>
        </div>
        <p className="text-xs text-themed-muted leading-relaxed">
          {t('reports.lead.architecture_subtitle', { brand: brandName })}
        </p>
        <div className="mt-3 grid grid-cols-4 gap-2">
          {[
            { k: 'quickWins', n: layers.quickWins.length },
            { k: 'strategicBets', n: layers.strategicBets.length },
            { k: 'brandingRisks', n: layers.brandingRisks.length },
            { k: 'consultingAccelerators', n: layers.consultingAccelerators.length },
          ].map((row) => {
            const m = LEAD_LAYER_META[row.k];
            return (
              <div
                key={row.k}
                className="rounded-md p-2.5 border"
                style={{ borderColor: m.borderColor, background: m.bg }}
              >
                <div className="text-[10px] font-medium" style={{ color: m.color }}>
                  {t(`reports.lead.layer.${row.k}.title`)}
                </div>
                <div className="text-lg font-bold tabular-nums text-themed-primary mt-0.5">{row.n}</div>
              </div>
            );
          })}
        </div>
      </Card>

      <LeadLayerCard layerKey="quickWins" items={layers.quickWins} t={t} />
      <LeadLayerCard layerKey="strategicBets" items={layers.strategicBets} t={t} />
      <LeadLayerCard layerKey="brandingRisks" items={layers.brandingRisks} t={t} />
      <LeadLayerCard
        layerKey="consultingAccelerators"
        items={layers.consultingAccelerators}
        t={t}
        onContactConsultant={onContactConsultant}
      />
    </div>
  );
}
