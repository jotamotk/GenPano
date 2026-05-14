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
  // 取该品牌相关诊断 (mock: 按 brandId 匹配 + industry 类全收)
  const relevantDiags = useMemo(() => {
    return DIAGNOSTICS.filter((d) => d.type === 'industry' || d.brandId === report.brand.id || true);
    // 当前 mock 数据全是雅诗兰黛, 简化为全选
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
