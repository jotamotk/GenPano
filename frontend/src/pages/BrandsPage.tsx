import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Card } from '../components/ui';
import { MiniSparkline } from '../components/charts';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import { BRANDS, PROJECTS, TREND_DATA } from '../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandsPage — PRD §4.6.1b 列表入口
   ─────────────────────────────────────────────────────────────
   职责: 仅列出 Project 范围内的品牌(主品牌 + 竞品), 点击行进入
         /brands/:id 单品牌深度视图.

   🚫 本页不做:
     - 跨品牌 SoV 饼图 / 竞品四象限 / 跨品牌 PANO 趋势对比
       → 回到「面板」
     - 单品牌的 V/S/R/A 子维度展开 / Diagnostics 列表 / 产品明细
       → 进入 /brands/:id
     - 情感分布 / 引用来源 / Top Domains
       → 进入 /brands/:id 概览 Tab

   样式: 颜色全部走 var(--color-*) / .text-themed-* / .bg-themed-*.
*/

export default function BrandsPage() {
  const navigate = useNavigate();
  const { t, formatNumber } = useLocale();
  // ProjectContext is hybrid live/mock since PR #293 — when the user
  // has a real backend project, activeProject reflects it; otherwise
  // it falls back to the first mock project.
  const { activeProject: liveActiveProject } = useProject();
  const activeProject = liveActiveProject || PROJECTS[0];

  // 列表数据 = 主品牌 + 竞品 (不含全行业)
  const rows = useMemo(() => {
    const primaryId = activeProject?.primaryBrandId;
    const competitorIds = activeProject?.competitorBrandIds || [];
    const all = [primaryId, ...competitorIds]
      .map((id) => BRANDS.find((b) => b.id === id))
      .filter(Boolean);
    return all.map((b) => ({
      ...b,
      isPrimary: b.id === primaryId,
      // MiniSparkline expects raw number[], not { value } objects.
      sparkData: TREND_DATA.slice(-14).map((d) => d.panoScore),
    }));
  }, [activeProject]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            {t('brand.list_title')}
          </h2>
          <p className="text-sm text-themed-muted mt-1">
            {t('brand.list_subtitle')}
          </p>
        </div>
      </div>

      {/* LIVE strip — primary + competitors from
          /v1/projects/:id/competitors/metrics */}

      {/* List table */}
      <Card className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full t-table">
            <thead>
              <tr>
                <th className="text-left py-3 px-5 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.brand')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.pano')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.change')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.mention')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.sentiment')}
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  {t('brand.list_col.rank')}
                </th>
                <th className="text-left py-3 px-4 font-medium text-themed-muted text-xs w-40">
                  PANO 14d
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const positive = row.change && row.change.startsWith('+');
                return (
                  <tr
                    key={row.id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer transition-colors"
                    onClick={() => navigate(`/brands/${row.id}?tab=overview`)}
                    style={row.isPrimary ? { background: 'var(--color-accent-subtle)' } : undefined}
                  >
                    <td className="py-3 px-5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-themed-primary">
                          {row.name}
                        </span>
                        <span className="text-[11px] text-themed-muted">
                          {row.nameEn}
                        </span>
                        {row.isPrimary ? (
                          <Badge variant="accent" size="sm">
                            {t('brand.list_col.primary_badge')}
                          </Badge>
                        ) : (
                          <Badge variant="default" size="sm">
                            {t('brand.list_col.competitor_badge')}
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right text-sm font-semibold tabular-nums text-themed-primary">
                      {row.panoScore}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums">
                      <span className={positive ? 'text-themed-success' : 'text-themed-danger'}>
                        {row.change}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {formatNumber(row.mentionRate, { maximumFractionDigits: 1 })}%
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {formatNumber(row.sentiment, { maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      #{row.ranking}
                    </td>
                    <td className="py-3 px-4">
                      <div className="h-7 -mx-1">
                        <MiniSparkline
                          data={row.sparkData}
                          color={row.isPrimary ? 'var(--color-accent)' : 'var(--color-chart-3)'}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
