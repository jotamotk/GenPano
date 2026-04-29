import React from 'react'
import { Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import LandingPage from './pages/LandingPage'
import AuthPage from './pages/AuthPage'
import OnboardingPage from './pages/OnboardingPage'
import EmailSentPage from './pages/EmailSentPage'
import SetupPage from './pages/SetupPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import ResetPasswordSuccessPage from './pages/ResetPasswordSuccessPage'
import { useAuth } from './context/AuthContext'
import { authApi } from './api/auth'

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

function isSafeRedirectTarget(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')
}

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-themed-page">
      <svg className="animate-spin w-7 h-7 text-themed-accent" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>
  )
}

function RequireAuth({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingScreen />
  if (!user) {
    const redirect = `${location.pathname}${location.search}`
    return <Navigate to={`/register?redirect=${encodeURIComponent(redirect)}`} replace />
  }
  return children
}

function PublicOnly({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingScreen />
  if (user) {
    const params = new URLSearchParams(location.search)
    const redirect = params.get('redirect') || params.get('return_to')
    return <Navigate to={isSafeRedirectTarget(redirect) ? redirect : '/brand/overview'} replace />
  }
  return children
}

function AuthCallback() {
  const { setTokenAndUser } = useAuth()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const token = params.get('token')

  React.useEffect(() => {
    let cancelled = false
    async function hydrate() {
      if (!token) {
        window.location.replace('/login?error=oauth_failed')
        return
      }
      try {
        const user = await authApi.getMe(token)
        if (!cancelled) {
          setTokenAndUser(token, user)
          window.history.replaceState({}, '', '/brand/overview')
          window.location.replace('/brand/overview')
        }
      } catch {
        window.location.replace('/login?error=oauth_failed')
      }
    }
    hydrate()
    return () => { cancelled = true }
  }, [setTokenAndUser, token])

  return <LoadingScreen />
}

export default function App() {
  return (
    <>
      <Routes>
        {/* ── Anonymous routes (§4.1.1-gate: the only anon surfaces) ── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<PublicOnly><AuthPage type="login" /></PublicOnly>} />
        <Route path="/auth" element={<PublicOnly><AuthPage type="login" /></PublicOnly>} />
        <Route path="/register" element={<PublicOnly><AuthPage type="register" /></PublicOnly>} />
        <Route path="/forgot" element={<PublicOnly><AuthPage type="login" initialStep="forgot" /></PublicOnly>} />
        <Route path="/forgot-password" element={<PublicOnly><AuthPage type="login" initialStep="forgot" /></PublicOnly>} />
        <Route path="/email-sent" element={<PublicOnly><EmailSentPage /></PublicOnly>} />
        <Route path="/setup" element={<PublicOnly><SetupPage /></PublicOnly>} />
        <Route path="/reset-password" element={<PublicOnly><ResetPasswordPage /></PublicOnly>} />
        <Route path="/reset-password-success" element={<PublicOnly><ResetPasswordSuccessPage /></PublicOnly>} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/onboarding" element={<RequireAuth><OnboardingPage /></RequireAuth>} />

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
        <Route element={<RequireAuth><DashboardLayout /></RequireAuth>}>
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
