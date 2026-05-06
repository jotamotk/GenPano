import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import DashboardEmptyState from '../components/empty/DashboardEmptyState';
import BrandPanoramaPanel from '../components/dashboard/BrandPanoramaPanel';
import { BRANDS, INDUSTRIES } from '../data/mock';
import { useProjects } from '../hooks/useProjects';

/* ─────────────────────────────────────────────────────────────
   DashboardPage ("我的品牌") — PRD §4.6.1a 市场宏观视角
   ─────────────────────────────────────────────────────────────
   ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
     本页是 Project.primaryBrand 的快捷入口, 沿用 BrandPanoramaPanel 渲染
     与 /brands/:id?tab=overview 完全相同的单品牌全景视图. 此文件保留
     为 legacy 路由兼容 (/dashboard), 未来可改为 301 重定向到
     /brands/:primaryBrandId?tab=overview.
*/
export default function DashboardPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { projects, activeProject } = useProject();
  const { data: liveProjects } = useProjects();

  /* ── PRD §4.1.1d E1: Zero-Project early-return (MANDATORY) ──
     Skip the empty state when the user has at least one real project
     in the backend (just signed up + onboarded but mock context
     hasn't been wired yet). */
  if (projects.length === 0 && (!liveProjects || liveProjects.length === 0)) {
    return <DashboardEmptyState />;
  }

  const project = activeProject;
  const primary = BRANDS.find((b) => b.id === project?.primaryBrandId) || BRANDS[1];
  const industry = INDUSTRIES.find((ind) => ind.id === project?.industryId);
  const competitors = (project?.competitorBrandIds || [])
    .map((id) => BRANDS.find((b) => b.id === id))
    .filter(Boolean)
    .slice(0, 3);

  const header = (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-baseline gap-3">
        <span className="text-sm text-themed-muted">{t('dashboard.page_subtitle')}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => navigate('/project-settings')}>
          {t('dashboard.toolbar.project_settings')}
        </Button>
        <Button variant="primary" size="sm" onClick={() => navigate(`/brands/${primary.id}?tab=diagnostics`)}>
          {t('dashboard.toolbar.share_pdf')}
        </Button>
      </div>
    </div>
  );

  return (
    <>
      <BrandPanoramaPanel
        primary={primary}
        industry={industry}
        competitors={competitors}
        headerSlot={header}
        scrollAnchorId="dashboard-competition"
      />
    </>
  );
}
