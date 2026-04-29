import { Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import LandingPage from './pages/LandingPage'
import AuthPage from './pages/AuthPage'
import OnboardingPage from './pages/OnboardingPage'

/* ── Existing pages (re-used directly at new canonical routes) ── */
import DashboardPage from './pages/DashboardPage'         // becomes BrandOverviewPage (T2')
/* IndustryPage (legacy Plan S v1 5-段) superseded by IndustryOverviewPage v2 8-段 —
   see PRD §4.6.1e v2 扩展记录 (2026-04-20) and SESSIONS Session T3' task #1 */
import IndustryOverviewPage from './pages/industry/IndustryOverviewPage'
import BrandsPage from './pages/BrandsPage'               // kept as "品牌集市" grid
import BrandProductDetailPage from './pages/BrandProductDetailPage'
import BrandSimulatorPage from './pages/BrandSimulatorPage'
import DiagnosticsPage from './pages/DiagnosticsPage'     // to be cut down to single-brand in T2'
import TopicsPage from './pages/TopicsPage'
import ReportsPage from './pages/ReportsPage'
import KnowledgeGraphPage from './pages/KnowledgeGraphPage'
import SettingsPage from './pages/SettingsPage'
import ProjectSettingsPage from './pages/ProjectSettingsPage'
import ToastViewport from './components/ui/ToastViewport'

/* ── NEW distinct sub-view pages (Brand/Industry Mode IA v2.0, Sessions T2'/T3') ──
   Each page owns a differentiated content shape; App.jsx mounts them at the
   canonical /brand/* and /industry/* routes so the sidebar nav surfaces real
   distinct views rather than every tab rendering Overview. */
import BrandVisibilityPage from './pages/brand/BrandVisibilityPage'
import BrandSentimentPage from './pages/brand/BrandSentimentPage'
import BrandCitationsPage from './pages/brand/BrandCitationsPage'
import BrandProductsPage from './pages/brand/BrandProductsPage'
import BrandCompetitorsPage from './pages/brand/BrandCompetitorsPage'
import IndustryRankingPage from './pages/industry/IndustryRankingPage'
import IndustryTopicsPage from './pages/industry/IndustryTopicsPage'

/* Admin Console pages.
   Admin surfaces live under /admin/* and are gated by a separate Next.js
   middleware (Step 8). For Phase Gate A0 only the three auth-front pages
   are mounted; the authenticated /admin/dashboard target is a Step 8 stub. */
import AdminLoginPage from './admin/pages/AdminLoginPage'
import AdminChangePasswordPage from './admin/pages/AdminChangePasswordPage'
import AdminForgotPasswordPage from './admin/pages/AdminForgotPasswordPage'
import AdminDashboardPage from './admin/pages/AdminDashboardPage'
import AdminAuthShell from './admin/components/AdminAuthShell'
import AdminRouteGuard from './admin/components/AdminRouteGuard'

/* ─────────────────────────────────────────────────────────────
   Legacy-path redirect helpers
   §4.6-IA-v2.D — 301 map from pre-2026-04-20 paths to Brand/Industry Mode
   ─────────────────────────────────────────────────────────────
   These are client-side Navigate fallbacks so the SPA never 404s on old
   deep links. Session T4' adds Next.js middleware for SSR-layer 301s so
   search engines see the real redirects, not a flash of content. */

function RedirectBrandDetail() {
  const { id } = useParams()
  return <Navigate to={`/brand/overview?brandId=${id}`} replace />
}

function RedirectBrandProduct() {
  const { id, productId } = useParams()
  return <Navigate to={`/brand/products/${productId}?brandId=${id}`} replace />
}

function RedirectBrandSimulator() {
  const { id } = useParams()
  return <Navigate to={`/brand/citations?sub=simulator&brandId=${id}`} replace />
}

function RedirectIndustryDetail() {
  const { id } = useParams()
  return <Navigate to={`/industry/overview?industryId=${id}`} replace />
}

/* Preserve any pre-existing query string when redirecting to a canonical mode path */
function RedirectWithQuery({ to }) {
  const location = useLocation()
  return <Navigate to={`${to}${location.search}`} replace />
}

export default function App() {
  return (
    <>
      <Routes>
        {/* ── Anonymous routes (§4.1.1-gate: the only anon surfaces) ── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<AuthPage type="login" />} />
        <Route path="/auth" element={<AuthPage type="login" />} />
        <Route path="/register" element={<AuthPage type="register" />} />
        <Route path="/onboarding" element={<OnboardingPage />} />

        {/* ── Admin Console (Session A0) ──
             Admin routes are wrapped by <AdminAuthShell /> which mounts
             AdminAuthProvider (silent refresh + BroadcastChannel) and the
             global SessionExpiredModal. Inside the shell, gated pages sit
             behind <AdminRouteGuard /> (Step 8) which enforces the
             authenticated + force-password-change state machine. */}
        <Route element={<AdminAuthShell />}>
          {/* Anonymous-allowed admin routes */}
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="/admin/forgot-password" element={<AdminForgotPasswordPage />} />

          {/* Gated admin routes (require valid session) */}
          <Route element={<AdminRouteGuard />}>
            <Route path="/admin/change-password" element={<AdminChangePasswordPage />} />
            <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
          </Route>
        </Route>

        {/* ══════════════════════════════════════════════════════════
            Authenticated app shell (Brand/Industry Mode IA v2.0)
            §4.6-IA-v2. Route Guard wiring lands in Session T4'.
            ══════════════════════════════════════════════════════════ */}
        <Route element={<DashboardLayout />}>
          {/* ── Brand Mode sub-views (§4.6-IA-v2.C.2) ── */}
          <Route path="/brand/overview"            element={<DashboardPage />} />
          <Route path="/brand/visibility"          element={<BrandVisibilityPage />} />
          <Route path="/brand/topics"              element={<TopicsPage />} />
          <Route path="/brand/sentiment"           element={<BrandSentimentPage />} />
          <Route path="/brand/citations"           element={<BrandCitationsPage />} />
          <Route path="/brand/products"            element={<BrandProductsPage />} />
          <Route path="/brand/products/:productId" element={<BrandProductDetailPage />} />
          <Route path="/brand/competitors"         element={<BrandCompetitorsPage />} />
          <Route path="/brand/diagnostics"         element={<DiagnosticsPage />} />
          <Route path="/brand/reports"             element={<ReportsPage />} />

          {/* ── Industry Mode sub-views (§4.6-IA-v2.C.3) ── */}
          <Route path="/industry/overview"         element={<IndustryOverviewPage />} />
          <Route path="/industry/ranking"          element={<IndustryRankingPage />} />
          <Route path="/industry/topics"           element={<IndustryTopicsPage />} />
          <Route path="/industry/knowledge-graph"  element={<KnowledgeGraphPage />} />

          {/* ── Orthogonal authenticated pages ── */}
          <Route path="/brands"          element={<BrandsPage />} />
          <Route path="/settings"        element={<SettingsPage />} />
          <Route path="/project-settings" element={<ProjectSettingsPage />} />

          {/* ── Legacy 301 redirects (§4.6-IA-v2.D) ── */}
          <Route path="/dashboard"       element={<RedirectWithQuery to="/brand/overview" />} />
          <Route path="/topics"          element={<RedirectWithQuery to="/brand/topics" />} />
          <Route path="/industry"        element={<RedirectWithQuery to="/industry/overview" />} />
          <Route path="/industries"      element={<RedirectWithQuery to="/industry/overview" />} />
          <Route path="/industries/:id"  element={<RedirectIndustryDetail />} />
          <Route path="/knowledge-graph" element={<RedirectWithQuery to="/industry/knowledge-graph" />} />
          <Route path="/diagnostics"     element={<RedirectWithQuery to="/brand/diagnostics" />} />
          <Route path="/reports"         element={<RedirectWithQuery to="/brand/reports" />} />
          <Route path="/brands/:id"      element={<RedirectBrandDetail />} />
          <Route path="/brands/:id/simulator" element={<RedirectBrandSimulator />} />
          <Route path="/brands/:id/products/:productId" element={<RedirectBrandProduct />} />
        </Route>

        {/* ── Catch-all: unknown paths go home (SSR will 404 properly via middleware in T4') ── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastViewport />
    </>
  )
}
