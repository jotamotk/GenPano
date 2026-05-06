import { Card } from '../components/ui';
import DashboardEmptyState from '../components/empty/DashboardEmptyState';
import BrandPanoramaPanelLive from '../components/dashboard/BrandPanoramaPanelLive';
import { useProjects } from '../hooks/useProjects';

/* ─────────────────────────────────────────────────────────────
   DashboardPage ("我的品牌") — PRD §4.6.1a 市场宏观视角
   ─────────────────────────────────────────────────────────────
   全部数据来自后端 (Phase 5 §"mock 退役"). 渲染 BrandPanoramaPanelLive,
   保留原 PRD 的丰富可视化布局: Hero + 5 KPI 卡 + SoV 饼图 + 4 象限气泡
   + 30 天趋势 + Top 诊断条. 所有图表都由 /v1/projects/:id/overview +
   /v1/projects/:id/competitors/metrics + /v1/projects/:id/diagnostics
   驱动.
*/
export default function DashboardPage() {
  const { data: liveProjects, isLoading } = useProjects();

  if (isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  if (!liveProjects || liveProjects.length === 0) {
    return <DashboardEmptyState />;
  }

  const projectId = liveProjects[0].id;

  return <BrandPanoramaPanelLive projectId={projectId} />;
}
