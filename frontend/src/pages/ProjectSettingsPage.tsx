import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import { useLocale } from '../contexts/LocaleContext';
import {
  useProjects,
  useUpdateProject,
  useDeleteProject,
} from '../hooks/useProjects';
import { isLiveProjectId } from '../hooks/useReports';

/* Phase 5 §"mock 退役" — 整页 100% 后端;
   project 名 / 主品牌 / 行业 / 竞品都来自 GET /v1/projects/.
   Save / Delete 调 PATCH/DELETE /v1/projects/:id. */
export default function ProjectSettingsPage() {
  const { t, formatDate } = useLocale();
  const navigate = useNavigate();
  const projectsQ = useProjects();
  const project = projectsQ.data && projectsQ.data.length > 0
    ? projectsQ.data[0]
    : null;
  const liveProjectId = isLiveProjectId(project?.id ?? null) ? project!.id : null;
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();

  const [projectName, setProjectName] = useState('');
  const [saved, setSaved] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (project) setProjectName(project.name);
  }, [project?.id, project?.name]);

  if (projectsQ.isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  if (!project || !liveProjectId) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">⚙️</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          还没有 Project
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          先 onboarding 创建第一个 Project 后再来设置它.
        </p>
        <Button variant="primary" size="sm" onClick={() => navigate('/onboarding')}>
          开始引导
        </Button>
      </Card>
    );
  }

  const handleSave = () => {
    updateProject.mutate(
      { id: liveProjectId, payload: { name: projectName } },
      {
        onSuccess: () => {
          setSaved(true);
          setTimeout(() => setSaved(false), 2000);
        },
      },
    );
  };

  const handleDelete = () => {
    deleteProject.mutate(liveProjectId, {
      onSuccess: () => navigate('/onboarding'),
    });
  };

  return (
    <div className="min-h-screen bg-white">
      <div className="border-b border-border px-8 py-6">
        <h1 className="text-3xl font-semibold text-ink mb-1">
          {t('project_settings.page_title')}
        </h1>
        <div className="flex items-center gap-2 mt-1">
          <Badge variant="default">LIVE</Badge>
          <p className="text-sm text-ink-secondary">
            {project.name} · {project.competitors?.length ?? 0} 竞品
          </p>
        </div>
      </div>

      <div className="px-8 py-8">
        <div className="max-w-2xl space-y-6">
          {/* Project info */}
          <Card>
            <div className="border-b border-border pb-4 mb-6">
              <h2 className="text-lg font-semibold text-ink">项目信息</h2>
            </div>
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-ink mb-2">
                  项目名
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md text-sm"
                />
              </div>

              <Row label="行业" value={`#${project.industry_id ?? '—'}`} />
              <Row label="主品牌" value={`#${project.primary_brand_id ?? '—'}`} />
              <Row label="是否活跃" value={project.is_active ? '是' : '否'} />
              <Row
                label="偏好引擎"
                value={
                  project.preferred_engines && project.preferred_engines.length > 0
                    ? project.preferred_engines.join(', ')
                    : '默认'
                }
              />
              <Row label="创建时间" value={formatDate(project.created_at)} />
            </div>
          </Card>

          {/* Competitors */}
          <Card>
            <div className="border-b border-border pb-4 mb-6">
              <h2 className="text-lg font-semibold text-ink">竞品</h2>
              <p className="text-xs text-ink-muted mt-1">
                共 {project.competitors?.length ?? 0} 个 (上限 10)
              </p>
            </div>
            {project.competitors && project.competitors.length > 0 ? (
              <ul className="space-y-2">
                {project.competitors.map((c) => (
                  <li
                    key={c.brand_id}
                    className="flex items-center justify-between p-3 bg-bg-subtle rounded-md text-sm"
                  >
                    <span className="text-ink">Brand #{c.brand_id}</span>
                    <span className="text-xs text-ink-muted">
                      {formatDate(c.pinned_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-ink-muted">
                还没有 pin 任何竞品. 在 brand picker 中添加.
              </p>
            )}
          </Card>

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <Button
              onClick={handleSave}
              variant="primary"
              disabled={updateProject.isPending}
            >
              {updateProject.isPending ? '保存中…' : saved ? '已保存 ✓' : '保存'}
            </Button>
            <Button variant="outline" onClick={() => navigate('/dashboard')}>
              返回面板
            </Button>
          </div>

          {/* Danger zone */}
          <Card>
            <div className="border-b border-border pb-4 mb-4">
              <h2 className="text-lg font-semibold text-ink">危险区</h2>
            </div>
            {!showDeleteConfirm ? (
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="w-full px-3 py-2 bg-red-50 text-red-600 text-sm font-medium rounded-md hover:bg-red-100"
              >
                删除 Project
              </button>
            ) : (
              <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                <p className="text-sm text-red-800 mb-3">
                  删除后所有该 Project 的报告 / 诊断 / 引用归属都会丢失. 不可恢复.
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowDeleteConfirm(false)}
                    className="flex-1 px-2 py-1 bg-white border border-red-300 text-red-600 text-xs font-medium rounded"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteProject.isPending}
                    className="flex-1 px-2 py-1 bg-red-600 text-white text-xs font-medium rounded disabled:opacity-50"
                  >
                    {deleteProject.isPending ? '删除中…' : '确认删除'}
                  </button>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-themed-subtle last:border-b-0">
      <span className="text-sm text-ink-secondary">{label}</span>
      <span className="text-sm font-medium text-ink">{value}</span>
    </div>
  );
}
