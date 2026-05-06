import { useNavigate } from 'react-router-dom';
import { Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import DashboardEmptyState from '../components/empty/DashboardEmptyState';
import BrandOverviewLiveView from '../components/dashboard/BrandOverviewLiveView';
import { useProjects } from '../hooks/useProjects';

/* ─────────────────────────────────────────────────────────────
   DashboardPage ("我的品牌") — PRD §4.6.1a 市场宏观视角
   ─────────────────────────────────────────────────────────────
   Phase 5 §"mock 退役" — 整页数据来自后端 (GET /v1/projects/:id/overview).
   - 用户没有 Project: 显示 onboarding 引导 (DashboardEmptyState)
   - 有 Project 但还没采集数据: 显示 "首批数据采集中" 空状态 + 重试按钮
   - 有 Project + 有数据: 渲染 KPI / 趋势 / Top prompts / 同集团共享域
   不再 import mock; mock.js 在 Phase 5 末整体迁出 pages/**.
*/
export default function DashboardPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { data: liveProjects, isLoading } = useProjects();

  if (isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  // No project yet — guide to onboarding (Phase 1 entry).
  if (!liveProjects || liveProjects.length === 0) {
    return <DashboardEmptyState />;
  }

  // Use the first project. Multi-project picker is on /project-settings.
  const projectId = liveProjects[0].id;

  return (
    <BrandOverviewLiveView projectId={projectId} />
  );
}
