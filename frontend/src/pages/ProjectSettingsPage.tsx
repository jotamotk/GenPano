import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import { BRANDS, PROJECTS, INDUSTRIES } from '../data/mock';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import { useUpdateProject, useDeleteProject } from '../hooks/useProjects';
import { isLiveProjectId } from '../hooks/useReports';

/* ─────────────────────────────────────────────────────────────
   ProjectSettingsPage — PRD §4.10 全量国际化
   ─────────────────────────────────────────────────────────────
   - 所有 label / placeholder / 按钮文案 → messages.project_settings.*
   - 行业 / 品牌名 → useLocale().formatBrand / industry 按 locale 选字段
   - 日期 → formatDate(locale) 替代 toLocaleDateString('zh-CN')
*/
const MAX_COMPETITORS = 5;

export default function ProjectSettingsPage() {
  const { t, locale, formatBrand, formatDate } = useLocale();
  const navigate = useNavigate();
  // ProjectContext is hybrid live/mock since PR #293 — when the user has
  // a real backend project, activeProject reflects it (toMockShape); else
  // it falls back to the first mock project.
  const { activeProject: liveActiveProject } = useProject();
  const project = liveActiveProject || PROJECTS[0];
  const liveProjectId = isLiveProjectId(project?.id) ? project.id : null;
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();
  // Live projects come through toMockShape() which has competitorBrandIds
  // but lacks the rich preferences object — fall back to mock for those.
  const mockFallback = PROJECTS[0];
  const preferences = project?.preferences || mockFallback?.preferences;
  const industry = INDUSTRIES.find((i) => i.id === project.industryId);
  const primaryBrand = BRANDS.find((b) => b.id === project.primaryBrandId);
  const competitorBrands = (project.competitorBrandIds || [])
    .map((id) => BRANDS.find((b) => b.id === id))
    .filter(Boolean);

  // State
  const [projectName, setProjectName] = useState(project.name);
  const [competitors, setCompetitors] = useState(competitorBrands);
  const [showAddCompetitor, setShowAddCompetitor] = useState(false);
  const [weeklyEnabled, setWeeklyEnabled] = useState(preferences.reportSchedule.weeklyEnabled);
  const [monthlyEnabled, setMonthlyEnabled] = useState(preferences.reportSchedule.monthlyEnabled);
  const [emailRecipients, setEmailRecipients] = useState(
    preferences.reportSchedule.emailRecipients.join(', ')
  );
  const [p0Notify, setP0Notify] = useState(preferences.alertConfig.p0Notify);
  const [p1Notify, setP1Notify] = useState(preferences.alertConfig.p1Notify);
  const [saved, setSaved] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Available brands (same industry, exclude primary + already selected)
  const allIndustryBrands = BRANDS.filter((b) => b.industryId === project.industryId);
  const availableBrands = allIndustryBrands.filter(
    (b) => b.id !== project.primaryBrandId && !competitors.find((c) => c.id === b.id)
  );

  // Industry label localisation (mock has name / nameEn)
  const industryLabel = locale === 'zh-CN' ? industry?.name : industry?.nameEn || industry?.name;
  const industrySub = locale === 'zh-CN' ? industry?.nameEn : industry?.name;

  // Brand positioning / price range localisation via brand_meta dictionary (fallback = raw)
  const localizeBrandMeta = (value, bucket) => {
    if (!value) return '';
    const key = `brand_meta.${bucket}.${value}`;
    const resolved = t(key);
    return resolved === key ? value : resolved;
  };

  const handleAddCompetitor = (brand) => {
    if (competitors.length < MAX_COMPETITORS) {
      setCompetitors([...competitors, brand]);
      setShowAddCompetitor(false);
    }
  };

  const handleRemoveCompetitor = (brandId) => {
    setCompetitors(competitors.filter((c) => c.id !== brandId));
  };

  const handleSave = () => {
    if (liveProjectId) {
      // Persist project name to backend (only field the live API accepts).
      updateProject.mutate(
        { id: liveProjectId, payload: { name: projectName } },
        {
          onSuccess: () => {
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
          },
        },
      );
      return;
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleDelete = () => {
    if (liveProjectId) {
      deleteProject.mutate(liveProjectId, {
        onSuccess: () => {
          navigate('/onboarding');
        },
      });
      return;
    }
    // Mock-only: just close the dialog (no real delete).
    setShowDeleteConfirm(false);
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Page header */}
      <div className="border-b border-border px-8 py-6">
        <h1 className="text-3xl font-semibold text-ink mb-1">{t('project_settings.page_title')}</h1>
        <p className="text-sm text-ink-secondary">{project.name}</p>
      </div>

      {/* Main content */}
      <div className="px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left column - Main settings */}
          <div className="lg:col-span-2 space-y-8">
            {/* Section 1: Project info */}
            <Card>
              <div className="border-b border-border pb-4 mb-6">
                <h2 className="text-lg font-semibold text-ink">
                  {t('project_settings.section.project_info')}
                </h2>
              </div>
              <div className="space-y-6">
                {/* Industry */}
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    {t('project_settings.field.industry')}
                  </label>
                  <div className="flex items-center gap-3 p-3 bg-bg-subtle rounded-md">
                    <span className="text-xl">{industry?.icon}</span>
                    <div>
                      <div className="text-sm font-medium text-ink">{industryLabel}</div>
                      <div className="text-xs text-ink-muted">{industrySub}</div>
                    </div>
                  </div>
                </div>

                {/* Primary brand */}
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    {t('project_settings.field.primary_brand')}
                  </label>
                  <div className="flex items-center justify-between p-3 bg-bg-subtle rounded-md">
                    <div>
                      <div className="text-sm font-medium text-ink">{formatBrand(primaryBrand)}</div>
                      <div className="text-xs text-ink-muted">
                        {locale === 'zh-CN' ? primaryBrand.nameEn : primaryBrand.name}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-bf-400">
                        {t('project_settings.field.pano_score')}
                      </div>
                      <div className="text-lg font-bold text-ink">{primaryBrand.panoScore}</div>
                    </div>
                  </div>
                </div>

                {/* Project name */}
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    {t('project_settings.field.project_name')}
                  </label>
                  <input
                    type="text"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    className="w-full px-3 py-2 border border-border rounded-md text-sm text-ink focus:outline-none focus:ring-2 focus:ring-bf-400"
                    placeholder={t('project_settings.field.project_name_placeholder')}
                  />
                </div>
              </div>
            </Card>

            {/* Section 2: Competitor management */}
            <Card>
              <div className="border-b border-border pb-4 mb-6">
                <h2 className="text-lg font-semibold text-ink">
                  {t('project_settings.section.competitor_management')}
                </h2>
              </div>

              {competitors.length > 0 && (
                <div className="mb-6">
                  <div className="text-sm text-ink-secondary mb-3">
                    {t('project_settings.competitor.current_label', {
                      count: competitors.length,
                      max: MAX_COMPETITORS,
                    })}
                  </div>
                  <div className="space-y-2">
                    {competitors.map((competitor) => (
                      <div
                        key={competitor.id}
                        className="flex items-center justify-between p-3 bg-bg-subtle rounded-md"
                      >
                        <div className="flex-1">
                          <div className="text-sm font-medium text-ink">{formatBrand(competitor)}</div>
                          <div className="text-xs text-ink-muted flex items-center gap-2 mt-1">
                            <span>{locale === 'zh-CN' ? competitor.nameEn : competitor.name}</span>
                            <Badge variant="secondary">
                              {localizeBrandMeta(competitor.positioning, 'positioning')}
                            </Badge>
                            <span className="text-bf-400 font-semibold">
                              {t('project_settings.field.pano_score')} {competitor.panoScore}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleRemoveCompetitor(competitor.id)}
                          className="ml-4 p-1.5 text-ink-muted hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                          title={t('project_settings.competitor.remove_title')}
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {competitors.length < MAX_COMPETITORS && (
                <div className="mb-4">
                  <button
                    onClick={() => setShowAddCompetitor(!showAddCompetitor)}
                    className="w-full px-3 py-2 border-2 border-dashed border-border rounded-md text-sm font-medium text-ink-secondary hover:border-bf-400 hover:text-bf-400 transition-colors"
                  >
                    {t('project_settings.competitor.add_button')}
                  </button>
                </div>
              )}

              {showAddCompetitor && availableBrands.length > 0 && (
                <div className="mb-4 p-4 bg-bg-subtle rounded-md">
                  <div className="text-sm text-ink-secondary mb-3">
                    {t('project_settings.competitor.picker_header', {
                      count: availableBrands.length,
                    })}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {availableBrands.map((brand) => (
                      <button
                        key={brand.id}
                        onClick={() => handleAddCompetitor(brand)}
                        className="text-left p-2 rounded-md hover:bg-white border border-transparent hover:border-bf-400 transition-colors"
                      >
                        <div className="text-sm font-medium text-ink">{formatBrand(brand)}</div>
                        <div className="text-xs text-ink-muted">
                          {(locale === 'zh-CN' ? brand.nameEn : brand.name)} ·{' '}
                          {t('project_settings.field.pano_score')} {brand.panoScore}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {competitors.length === MAX_COMPETITORS && (
                <p className="text-xs text-ink-muted">
                  {t('project_settings.competitor.max_reached', { max: MAX_COMPETITORS })}
                </p>
              )}
            </Card>

            {/* Section 3: Report preferences */}
            <Card>
              <div className="border-b border-border pb-4 mb-6">
                <h2 className="text-lg font-semibold text-ink">
                  {t('project_settings.section.report_preferences')}
                </h2>
              </div>
              <div className="space-y-6">
                {/* Weekly toggle */}
                <div
                  onClick={() => setWeeklyEnabled(!weeklyEnabled)}
                  className="flex items-center gap-3 cursor-pointer"
                >
                  <div
                    className={`w-10 h-5 rounded-full transition-colors relative ${weeklyEnabled ? 'bg-bf-400' : 'bg-gray-200'}`}
                  >
                    <div
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${weeklyEnabled ? 'translate-x-5' : 'translate-x-0.5'}`}
                    />
                  </div>
                  <span className="text-sm text-ink font-medium">
                    {t('project_settings.report.weekly_toggle')}
                  </span>
                </div>

                {/* Monthly toggle */}
                <div
                  onClick={() => setMonthlyEnabled(!monthlyEnabled)}
                  className="flex items-center gap-3 cursor-pointer"
                >
                  <div
                    className={`w-10 h-5 rounded-full transition-colors relative ${monthlyEnabled ? 'bg-bf-400' : 'bg-gray-200'}`}
                  >
                    <div
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${monthlyEnabled ? 'translate-x-5' : 'translate-x-0.5'}`}
                    />
                  </div>
                  <span className="text-sm text-ink font-medium">
                    {t('project_settings.report.monthly_toggle')}
                  </span>
                </div>

                {/* Email recipients */}
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    {t('project_settings.report.email_recipients')}
                  </label>
                  <input
                    type="email"
                    value={emailRecipients}
                    onChange={(e) => setEmailRecipients(e.target.value)}
                    className="w-full px-3 py-2 border border-border rounded-md text-sm text-ink focus:outline-none focus:ring-2 focus:ring-bf-400"
                    placeholder={t('project_settings.report.email_placeholder')}
                  />
                  <p className="text-xs text-ink-muted mt-1">
                    {t('project_settings.report.email_example')}
                  </p>
                </div>
              </div>
            </Card>

            {/* Section 4: Alert settings */}
            <Card>
              <div className="border-b border-border pb-4 mb-6">
                <h2 className="text-lg font-semibold text-ink">
                  {t('project_settings.section.alert_settings')}
                </h2>
              </div>
              <div className="space-y-6">
                <div
                  onClick={() => setP0Notify(!p0Notify)}
                  className="flex items-center gap-3 cursor-pointer"
                >
                  <div
                    className={`w-10 h-5 rounded-full transition-colors relative ${p0Notify ? 'bg-bf-400' : 'bg-gray-200'}`}
                  >
                    <div
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${p0Notify ? 'translate-x-5' : 'translate-x-0.5'}`}
                    />
                  </div>
                  <span className="text-sm text-ink font-medium">
                    {t('project_settings.alert.p0_toggle')}
                  </span>
                </div>

                <div
                  onClick={() => setP1Notify(!p1Notify)}
                  className="flex items-center gap-3 cursor-pointer"
                >
                  <div
                    className={`w-10 h-5 rounded-full transition-colors relative ${p1Notify ? 'bg-bf-400' : 'bg-gray-200'}`}
                  >
                    <div
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${p1Notify ? 'translate-x-5' : 'translate-x-0.5'}`}
                    />
                  </div>
                  <span className="text-sm text-ink font-medium">
                    {t('project_settings.alert.p1_toggle')}
                  </span>
                </div>
              </div>
            </Card>

            {/* Bottom action buttons */}
            <div className="flex items-center gap-3">
              <Button onClick={handleSave} variant="primary" className="relative">
                {saved
                  ? t('project_settings.actions.saved')
                  : t('project_settings.actions.save')}
              </Button>
              <Button variant="outline">{t('project_settings.actions.cancel')}</Button>
            </div>
          </div>

          {/* Right column - Project summary */}
          <div>
            <Card>
              <div className="border-b border-border pb-4 mb-6">
                <h2 className="text-lg font-semibold text-ink">
                  {t('project_settings.section.summary')}
                </h2>
              </div>

              <div className="space-y-6">
                <div>
                  <div className="text-xs text-ink-muted uppercase tracking-wide mb-1">
                    {t('project_settings.summary.created_at')}
                  </div>
                  <div className="text-sm font-medium text-ink">
                    {formatDate(project.createdAt, { year: 'numeric', month: 'long', day: 'numeric' })}
                  </div>
                </div>

                <div>
                  <div className="text-xs text-ink-muted uppercase tracking-wide mb-1">
                    {t('project_settings.summary.industry')}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{industry?.icon}</span>
                    <div className="text-sm font-medium text-ink">{industryLabel}</div>
                  </div>
                </div>

                <div>
                  <div className="text-xs text-ink-muted uppercase tracking-wide mb-1">
                    {t('project_settings.summary.primary_brand')}
                  </div>
                  <div className="text-sm font-medium text-ink">{formatBrand(primaryBrand)}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="text-xs font-semibold text-bf-400">
                      {t('project_settings.field.pano_score')}
                    </div>
                    <div className="text-sm font-bold text-ink">{primaryBrand.panoScore}</div>
                  </div>
                </div>

                <div>
                  <div className="text-xs text-ink-muted uppercase tracking-wide mb-1">
                    {t('project_settings.summary.competitor_count')}
                  </div>
                  <div className="text-2xl font-bold text-ink">
                    {competitors.length}{' '}
                    <span className="text-sm text-ink-secondary">/{MAX_COMPETITORS}</span>
                  </div>
                </div>

                <div>
                  <div className="text-xs text-ink-muted uppercase tracking-wide mb-2">
                    {t('project_settings.summary.report_cadence')}
                  </div>
                  <div className="flex flex-col gap-1">
                    {weeklyEnabled && (
                      <div className="text-sm text-ink flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-bf-400"></span>
                        {t('project_settings.summary.weekly_enabled')}
                      </div>
                    )}
                    {monthlyEnabled && (
                      <div className="text-sm text-ink flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-bf-400"></span>
                        {t('project_settings.summary.monthly_enabled')}
                      </div>
                    )}
                    {!weeklyEnabled && !monthlyEnabled && (
                      <div className="text-sm text-ink-muted">
                        {t('project_settings.summary.none_enabled')}
                      </div>
                    )}
                  </div>
                </div>

                {/* Danger zone */}
                <div className="pt-4 border-t border-border">
                  <button
                    onClick={() => setShowDeleteConfirm(!showDeleteConfirm)}
                    className="w-full px-3 py-2 bg-red-50 text-red-600 text-sm font-medium rounded-md hover:bg-red-100 transition-colors"
                  >
                    {t('project_settings.delete.button')}
                  </button>

                  {showDeleteConfirm && (
                    <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
                      <p className="text-sm text-red-800 mb-3">
                        {t('project_settings.delete.confirm_prompt')}
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setShowDeleteConfirm(false)}
                          className="flex-1 px-2 py-1 bg-white border border-red-300 text-red-600 text-xs font-medium rounded hover:bg-red-50 transition-colors"
                        >
                          {t('project_settings.delete.cancel')}
                        </button>
                        <button
                          onClick={handleDelete}
                          disabled={deleteProject.isPending}
                          className="flex-1 px-2 py-1 bg-red-600 text-white text-xs font-medium rounded hover:bg-red-700 transition-colors disabled:opacity-50"
                        >
                          {deleteProject.isPending
                            ? '删除中…'
                            : t('project_settings.delete.confirm')}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
