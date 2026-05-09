import React from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { Target, Globe } from 'lucide-react';
import { PROJECTS } from '../data/mock';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import { useUnreadAlertCount } from '../hooks/useAlerts';
import UserMenu from '../components/UserMenu';

/* ─────────────────────────────────────────────────────────────
   DashboardLayout — Brand/Industry Mode IA v2.0 (see PRD §4.6-IA-v2)
   ─────────────────────────────────────────────────────────────
   Shell = Topbar (Logo + Mode Toggle + GlobalFilters + 🔍 ⌘K + 🔔 + 👤)
         + Mode-aware Sidebar (240px, renders BrandSidebar or IndustrySidebar)
         + Main (Outlet)

   Mode is derived from URL prefix (/brand/* or /industry/*), NEVER stored
   in localStorage. URL is the single source of truth. See §4.6-IA-v2.H3.

   Sub-view mapping (§4.6-IA-v2.C.2.2 + .C.3.2):
     Brand Mode  /brand/overview /visibility /topics /sentiment /citations
                 /products /products/:id /competitors /diagnostics /reports
     Industry Mode /industry/overview /ranking /topics /knowledge-graph

   Implementation note: this layout is the post-T1' shell. Full sub-view
   components (BrandPicker popover, IndustryPicker, CommandPalette, AlertBell
   with real data, etc.) are implemented in their own files under
   components/topbar/ and components/sidebar/ as those Sessions land.
   The skeleton below renders the nav structure so all new routes mount
   correctly; richer behavior is layered in by T2'/T3'/T4'.

   Style contract: tokens only. Colors via var(--color-*) or .text-themed-*
   / .bg-themed-* / .t-* component classes. No inline hex (except brand logo).
*/

/* ── Lucide-style SVG icons (currentColor-driven) ── */
const Icon = ({ children, size = 20 }) => (
  <svg
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

const icons = {
  /* Brand Mode — analytics */
  overview:   <Icon><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></Icon>,
  visibility: <Icon><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></Icon>,
  topics:     <Icon><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></Icon>,
  sentiment:  <Icon><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01M15 9h.01"/></Icon>,
  citations:  <Icon><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></Icon>,
  products:   <Icon><path d="M20 7l-8-4-8 4v10l8 4 8-4V7z"/><path d="M4 7l8 4 8-4"/><path d="M12 11v10"/></Icon>,
  competitors:<Icon><path d="M6 9l6 6 6-6"/><path d="M6 15l6-6 6 6"/></Icon>,
  /* Brand Mode — ops */
  diagnostics:<Icon><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></Icon>,
  reports:    <Icon><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></Icon>,
  /* Industry Mode */
  industry:   <Icon><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></Icon>,
  ranking:    <Icon><path d="M6 9l6-6 6 6"/><path d="M6 15l6 6 6-6"/></Icon>,
  kg:         <Icon><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8 6h8M6 8v8M18 8v8M8 18h8"/></Icon>,
  /* Tools */
  terminal:   <Icon><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></Icon>,
  /* Topbar */
  search:     <Icon><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></Icon>,
  bell:       <Icon><path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></Icon>,
  user:       <Icon><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></Icon>,
  chevron:    <Icon size={16}><path d="M6 9l6 6 6-6"/></Icon>,
  gear:       <Icon size={16}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06a1.65 1.65 0 001.82.33h0a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51h0a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v0a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></Icon>,
};

/* ─────────────────────────────────────────────────────────────
   Mode derivation from URL (single source of truth)
   §4.6-IA-v2.C: mode = 'brand' | 'industry' | null
   ───────────────────────────────────────────────────────────── */
function useMode() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const mode = path.startsWith('/brand')
    ? 'brand'
    : path.startsWith('/industry')
      ? 'industry'
      : null;

  const switchMode = (newMode) => {
    if (newMode === mode) return;
    // Preserve sub-view name across mode prefix swap where equivalents exist
    // (e.g. /brand/overview ↔ /industry/overview, /brand/topics ↔ /industry/topics).
    // Sub-views that only exist in one mode fall back to 'overview'.
    const INDUSTRY_SUBVIEWS = new Set(['overview', 'ranking', 'topics', 'knowledge-graph']);
    const BRAND_SUBVIEWS = new Set([
      'overview', 'visibility', 'topics', 'sentiment', 'citations',
      'products', 'competitors', 'diagnostics', 'reports',
    ]);
    const rawSub = path.replace(/^\/(brand|industry)\/?/, '').split('?')[0] || 'overview';
    const allowed = newMode === 'industry' ? INDUSTRY_SUBVIEWS : BRAND_SUBVIEWS;
    const subView = allowed.has(rawSub) ? rawSub : 'overview';
    navigate(`/${newMode}/${subView}${location.search}`);
  };

  return { mode, switchMode };
}

/* ─────────────────────────────────────────────────────────────
   ModeToggle (Stripe-style pill) — §4.6-IA-v2.C.1
   ───────────────────────────────────────────────────────────── */
function ModeToggle({ mode, onSwitch, t }) {
  // Default to 'brand' visually for null mode so toggle always has a selected half
  const active = mode || 'brand';
  return (
    <div
      role="tablist"
      className="flex items-center gap-0 rounded-pill p-0.5"
      style={{ background: 'var(--color-bg-subtle-2)' }}
    >
      {['brand', 'industry'].map((m) => {
        const isActive = active === m;
        const Icon = m === 'brand' ? Target : Globe;
        return (
          <button
            key={m}
            role="tab"
            aria-selected={isActive}
            onClick={() => onSwitch(m)}
            className="inline-flex items-center gap-1.5 px-3.5 h-8 text-sm font-medium rounded-pill transition-colors"
            style={
              isActive
                ? {
                    background: 'var(--color-accent-soft)',
                    color: 'var(--color-accent)',
                  }
                : { background: 'transparent', color: 'var(--color-text-muted)' }
            }
          >
            <Icon
              size={14}
              strokeWidth={isActive ? 2.25 : 2}
              aria-hidden="true"
            />
            <span>{t(m === 'brand' ? 'mode.toggle.brand' : 'mode.toggle.industry')}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Topbar (§4.6-IA-v2.C.1)
   ───────────────────────────────────────────────────────────── */
function Topbar({ mode, onSwitchMode, t, locale, setLocale, onNavigate }) {
  // Phase N — bell badge fed by /v1/alerts/unread-count.
  // 30s polling keeps it close-to-fresh; webhook push lands later.
  const { data: unreadCount } = useUnreadAlertCount();
  return (
    <header
      className="h-14 shrink-0 flex items-center gap-4 px-6 bg-themed-card border-b border-themed-card"
    >
      {/* Logo */}
      <button
        onClick={() => onNavigate('/brand/overview')}
        className="flex items-center gap-2.5 shrink-0"
        aria-label="GenPano home"
      >
        <div
          className="w-8 h-8 rounded-card flex items-center justify-center bg-themed-gradient-accent"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="white" fillOpacity="0.95"/>
            <path
              d="M8 12l3 3 5-6"
              stroke="var(--color-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <span className="text-base font-brand font-bold text-themed-primary">GenPano</span>
      </button>

      {/* Mode Toggle */}
      <ModeToggle mode={mode} onSwitch={onSwitchMode} t={t} />

      {/* Global filters slot — filled by pages via context/portal
          (time range, engine, profile group; engine-compare segmented on Brand Mode).
          Implementation deferred to T2'; placeholder keeps layout balance.  */}
      <div className="flex-1 min-w-0" data-slot="topbar-filters" />

      {/* Search ⌘K */}
      <button
        aria-label={t('topbar.search.aria')}
        className="p-2 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle transition-colors"
        title={t('topbar.search.aria')}
      >
        {icons.search}
      </button>

      {/* Alert Bell — count from /v1/alerts/unread-count (Phase N) */}
      <button
        aria-label={t('topbar.alerts.aria')}
        onClick={() => onNavigate('/alerts')}
        className="relative p-2 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle transition-colors"
        title={t('topbar.alerts.aria')}
      >
        {icons.bell}
        {unreadCount !== undefined && unreadCount > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold flex items-center justify-center text-white"
            style={{ background: 'var(--color-danger, #E2434B)' }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Language toggle (moved from sidebar bottom, §4.6-IA-v2.C.1) */}
      <button
        type="button"
        onClick={() => setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN')}
        aria-label={t('lang.toggle_aria')}
        title={t('lang.toggle_aria')}
        className="px-2 h-8 rounded-pill text-xs font-medium text-themed-muted hover:text-themed-primary hover:bg-themed-subtle transition-colors"
      >
        {locale === 'zh-CN' ? 'EN' : '中文'}
      </button>

      {/* User menu — avatar dropdown (Account / API Keys / Notifications / Logout) */}
      <UserMenu />
    </header>
  );
}

/* ─────────────────────────────────────────────────────────────
   Nav primitives
   ───────────────────────────────────────────────────────────── */
function NavItem({ icon, label, path, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 h-10 pl-7 pr-3 text-sm text-left transition-colors ${
        active
          ? 'text-themed-accent font-medium'
          : 'text-themed-muted hover:text-themed-primary hover:bg-themed-subtle'
      }`}
      style={
        active
          ? { background: 'var(--gradient-sidebar-active)' }
          : undefined
      }
    >
      <span className="shrink-0">{icon}</span>
      <span className="font-ui-cn">{label}</span>
    </button>
  );
}

function NavSection({ label, children }) {
  return (
    <div className="pt-4 first:pt-0">
      <div className="px-7 pb-2">
        <span className="text-[11px] uppercase tracking-wider text-themed-muted">{label}</span>
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   BrandSidebar — §4.6-IA-v2.C.2
   ───────────────────────────────────────────────────────────── */
function BrandSidebar({ t, onNavigate, currentPath, activeProject, search }) {
  const analyticsItems = [
    { key: 'overview',    icon: icons.overview,    path: '/brand/overview' },
    { key: 'visibility',  icon: icons.visibility,  path: '/brand/visibility' },
    { key: 'topics',      icon: icons.topics,      path: '/brand/topics' },
    { key: 'sentiment',   icon: icons.sentiment,   path: '/brand/sentiment' },
    { key: 'citations',   icon: icons.citations,   path: '/brand/citations' },
    { key: 'products',    icon: icons.products,    path: '/brand/products' },
    { key: 'competitors', icon: icons.competitors, path: '/brand/competitors' },
  ];
  const opsItems = [
    { key: 'diagnostics', icon: icons.diagnostics, path: '/brand/diagnostics' },
    { key: 'reports',     icon: icons.reports,     path: '/brand/reports' },
  ];

  const isActive = (path) =>
    currentPath === path || currentPath.startsWith(`${path}/`);

  return (
    <>
      {/* BrandPicker slot — real Radix Popover implemented in T2'.
          For now render current brand label (from Project) with chevron affordance. */}
      <div className="px-4 pt-5 pb-3 border-b border-themed-card">
        <button
          type="button"
          className="w-full flex items-center justify-between h-10 pl-2 pr-3 rounded-pill bg-themed-subtle hover:border-themed-strong transition-colors"
          style={{
            background: 'var(--color-bg-subtle-2)',
            border: '0.5px solid var(--color-accent-alpha-27)',
          }}
          aria-label={t('brand_picker.aria')}
        >
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0 bg-themed-gradient-accent">
              {activeProject?.primaryBrandName?.[0] || activeProject?.name?.[0] || 'B'}
            </div>
            <span className="text-sm font-brand font-semibold text-themed-primary truncate">
              {activeProject?.primaryBrandName || activeProject?.name || t('brand_picker.empty')}
            </span>
          </div>
          <span className="text-themed-muted shrink-0">{icons.chevron}</span>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2">
        <NavSection label={t('nav.analytics')}>
          {analyticsItems.map((item) => (
            <NavItem
              key={item.path}
              icon={item.icon}
              label={t(`nav.brand.${item.key}`)}
              path={item.path}
              active={isActive(item.path)}
              onClick={() => onNavigate(item.path + search)}
            />
          ))}
        </NavSection>
        <NavSection label={t('nav.operations')}>
          {opsItems.map((item) => (
            <NavItem
              key={item.path}
              icon={item.icon}
              label={t(`nav.brand.${item.key}`)}
              path={item.path}
              active={isActive(item.path)}
              onClick={() => onNavigate(item.path + search)}
            />
          ))}
        </NavSection>
      </nav>

      {/* Project footer — MVP Project hidden per §4.6-IA-v2.G */}
      <div className="px-4 py-3 border-t border-themed-card">
        <button
          onClick={() => onNavigate('/project-settings')}
          className="w-full flex items-center justify-between gap-2 text-xs text-themed-muted hover:text-themed-primary transition-colors"
        >
          <span className="truncate">
            {t('nav.brand.project_footer', { projectName: activeProject?.name || '' })}
          </span>
          <span className="shrink-0">{icons.gear}</span>
        </button>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────
   IndustrySidebar — §4.6-IA-v2.C.3
   ───────────────────────────────────────────────────────────── */
function IndustrySidebar({ t, onNavigate, currentPath, search, onSwitchMode }) {
  const items = [
    { key: 'overview',        icon: icons.industry, path: '/industry/overview' },
    { key: 'ranking',         icon: icons.ranking,  path: '/industry/ranking' },
    { key: 'topics',          icon: icons.topics,   path: '/industry/topics' },
    { key: 'knowledge_graph', icon: icons.kg,       path: '/industry/knowledge-graph' },
  ];

  const isActive = (path) =>
    currentPath === path || currentPath.startsWith(`${path}/`);

  return (
    <>
      {/* IndustryPicker slot — real Radix Popover in T3' */}
      <div className="px-4 pt-5 pb-3 border-b border-themed-card">
        <button
          type="button"
          className="w-full flex items-center justify-between h-10 pl-3 pr-3 rounded-pill bg-themed-subtle hover:border-themed-strong transition-colors"
          style={{
            background: 'var(--color-bg-subtle-2)',
            border: '0.5px solid var(--color-accent-alpha-27)',
          }}
          aria-label={t('industry_picker.aria')}
        >
          <span className="text-sm font-brand font-semibold text-themed-primary truncate">
            {t('industry_picker.current')}
          </span>
          <span className="text-themed-muted shrink-0">{icons.chevron}</span>
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        <NavSection label={t('nav.analytics')}>
          {items.map((item) => (
            <NavItem
              key={item.path}
              icon={item.icon}
              label={t(`nav.industry.${item.key}`)}
              path={item.path}
              active={isActive(item.path)}
              onClick={() => onNavigate(item.path + search)}
            />
          ))}
        </NavSection>
      </nav>

      {/* Switch-to-brand footer nudge */}
      <div className="px-4 py-4 border-t border-themed-card">
        <button
          onClick={() => onSwitchMode('brand')}
          className="w-full text-left text-xs text-themed-muted hover:text-themed-primary transition-colors leading-relaxed"
        >
          {t('industry_sidebar.switch_to_brand')}
        </button>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────
   DashboardLayout — main shell composition
   ───────────────────────────────────────────────────────────── */
export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { locale, setLocale, t } = useLocale();
  const { mode, switchMode } = useMode();

  const projectCtx = useProject();
  const projects = projectCtx?.projects ?? PROJECTS;
  const activeProject = projectCtx?.activeProject
    ?? (projects.length > 0 ? projects[0] : null);

  // Pass through query string so brandId/industryId persists across sub-view clicks
  const search = location.search || '';

  // Mode fallback: if URL is outside /brand|/industry (e.g. /settings), treat as 'brand'
  // so the sidebar still renders a navigable shell. Non-mode pages can render an inline
  // back-to-app breadcrumb if they prefer.
  const effectiveMode = mode || 'brand';

  return (
    <div className="flex flex-col h-screen bg-themed-page">
      {/* ── Topbar ── */}
      <Topbar
        mode={effectiveMode}
        onSwitchMode={switchMode}
        t={t}
        locale={locale}
        setLocale={setLocale}
        onNavigate={(p) => navigate(p)}
      />

      {/* ── Body: sidebar + main ── */}
      <div className="flex flex-1 min-h-0">
        <aside
          className="w-[240px] shrink-0 flex flex-col t-sidebar border-r border-themed-card"
        >
          {effectiveMode === 'industry' ? (
            <IndustrySidebar
              t={t}
              onNavigate={navigate}
              currentPath={location.pathname}
              search={search}
              onSwitchMode={switchMode}
            />
          ) : (
            <BrandSidebar
              t={t}
              onNavigate={navigate}
              currentPath={location.pathname}
              search={search}
              activeProject={activeProject}
            />
          )}
        </aside>

        <main className="flex-1 overflow-auto bg-themed-page">
          <div className="px-6 py-5">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
