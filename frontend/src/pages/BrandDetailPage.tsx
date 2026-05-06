import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import { isLiveProjectId } from '../hooks/useReports';
import BrandOverviewLiveView from '../components/dashboard/BrandOverviewLiveView';
import BrandVisibilityPage from './brand/BrandVisibilityPage';
import BrandSentimentPage from './brand/BrandSentimentPage';
import BrandCitationsPage from './brand/BrandCitationsPage';
import BrandProductsPage from './brand/BrandProductsPage';

/* ─────────────────────────────────────────────────────────────
   BrandDetailPage — PRD §4.6.1b 单品牌深度视角 (Phase 5 mock 退役)
   ─────────────────────────────────────────────────────────────
   IA: /brands/:id?tab=overview|diagnostics|products|engines

   重写要点:
   - 整页数据来自后端; 不再 import data/mock.
   - 没有 Project: 显示引导 (跳 /onboarding).
   - 有 Project: 各 Tab 使用对应 live 端点
       overview     → /v1/projects/:id/overview
       diagnostics  → 跳 /brand/diagnostics (DiagnosticsPage 是 live)
       products     → BrandProductsPage live tab
       engines      → BrandVisibilityPage live tab
       citations    → BrandCitationsPage live tab
   - 旧版 5 tab + ContentGap + AuthorityRadar 等 mock-heavy 视图退役;
     这些指标在新页面 (Brand sub-pages) 里有 live 对应, 此处仅做 deep
     view 入口.
*/

const TAB_IDS = ['overview', 'visibility', 'sentiment', 'citations', 'products'] as const;
type TabId = (typeof TAB_IDS)[number];

export default function BrandDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { t } = useLocale();
  const { data: liveProjects, isLoading } = useProjects();

  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;

  const tabParam = params.get('tab');
  const activeTab: TabId = (TAB_IDS as readonly string[]).includes(tabParam ?? '')
    ? (tabParam as TabId)
    : 'overview';

  const setTab = (tabId: TabId) => {
    const next = new URLSearchParams(params);
    next.set('tab', tabId);
    setParams(next);
  };

  if (isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  if (!isLiveProjectId(liveProjectId)) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🏷️</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          先创建 Project
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          单品牌深度视图需要 Project 上下文 (主品牌 + 时间窗口 + 引擎).
        </p>
        <Button variant="primary" size="sm" onClick={() => navigate('/onboarding')}>
          开始引导
        </Button>
      </Card>
    );
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: 'overview', label: '概览' },
    { id: 'visibility', label: '可见度' },
    { id: 'sentiment', label: '情感' },
    { id: 'citations', label: '引用' },
    { id: 'products', label: '产品' },
  ];

  return (
    <div className="space-y-5">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/brands')}
            className="text-sm text-themed-muted hover:text-themed-primary transition-colors"
          >
            ← 品牌矩阵
          </button>
          <div className="h-4 w-px bg-themed-card" />
          <Badge variant="default">LIVE</Badge>
          <span className="text-sm text-themed-primary font-medium">
            Brand #{id}
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div className="t-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`t-tab ${activeTab === tab.id ? 't-tab-active' : ''}`}
            onClick={() => setTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'overview' && (
          <BrandOverviewLiveView projectId={liveProjectId as string} />
        )}
        {activeTab === 'visibility' && <BrandVisibilityPage />}
        {activeTab === 'sentiment' && <BrandSentimentPage />}
        {activeTab === 'citations' && <BrandCitationsPage />}
        {activeTab === 'products' && <BrandProductsPage />}
      </div>
    </div>
  );
}
