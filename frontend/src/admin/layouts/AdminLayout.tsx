import React, { useMemo } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  Users,
  Activity,
  Network,
  DollarSign,
  LogOut,
  ShieldCheck,
} from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';
import { ADMIN_ROUTE_GROUPS } from '../routes/adminRoutes';

interface AdminAuthValue {
  user: { email?: string; role?: string } | null;
  logout: () => Promise<void>;
}

/**
 * AdminLayout — Session A1' Step 9 (decision #29 · 11-Session Python pivot)
 *
 * App shell for the 17 gated admin pages: top navbar (env band + identity +
 * logout) + left rail (4 module groups · A users / B pipeline / C KG /
 * D cost+audit) + content <Outlet />. Sits inside <AdminRouteGuard /> so
 * unauthenticated traffic never reaches this component.
 *
 * The SessionExpiredModal is rendered by AdminAuthShell as a sibling and
 * therefore overlays this layout regardless of which inner route is active.
 */

const MODULE_ICON: Record<string, LucideIcon> = {
  A: Users,
  B: Activity,
  C: Network,
  D: DollarSign,
};

function envBandColor(): { bg: string; label: string } {
  const env = (import.meta as { env?: Record<string, string> }).env?.MODE;
  if (env === 'production') return { bg: '#ef4444', label: 'PROD' };
  if (env === 'staging') return { bg: '#f59e0b', label: 'STAGING' };
  return { bg: '#10b981', label: 'DEV' };
}

export default function AdminLayout() {
  const { user, logout } = useAdminAuth() as AdminAuthValue;
  const navigate = useNavigate();
  const env = useMemo(envBandColor, []);

  const handleLogout = async () => {
    await logout();
    navigate('/admin/login', { replace: true });
  };

  return (
    <div
      className="min-h-screen w-full flex flex-col"
      style={{ background: 'var(--color-bg-page)' }}
    >
      {/* Env band */}
      <div
        className="h-1 w-full"
        style={{ background: env.bg }}
        aria-label={`environment-${env.label}`}
      />

      {/* Top navbar */}
      <header
        className="h-14 flex items-center justify-between px-6 shrink-0"
        style={{
          background: 'var(--color-bg-card)',
          borderBottom: '1px solid var(--color-border-subtle)',
        }}
      >
        <div className="flex items-center gap-3">
          <ShieldCheck size={20} style={{ color: 'var(--color-accent)' }} />
          <span
            className="text-[15px] font-bold"
            style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}
          >
            GENPANO Admin Console
          </span>
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{ background: env.bg, color: '#fff', letterSpacing: '0.05em' }}
          >
            {env.label}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[13px]">
          <span style={{ color: 'var(--color-text-muted)' }}>
            {user?.email ?? '—'} · {user?.role ?? '—'}
          </span>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 h-8 rounded text-[13px] font-medium"
            style={{
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
              background: 'transparent',
            }}
          >
            <LogOut size={14} /> 退出
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Left rail */}
        <nav
          className="w-60 shrink-0 py-4 px-3 overflow-y-auto"
          style={{
            background: 'var(--color-bg-card)',
            borderRight: '1px solid var(--color-border-subtle)',
          }}
        >
          {ADMIN_ROUTE_GROUPS.map((group) => {
            const Icon = MODULE_ICON[group.module] ?? Users;
            return (
              <div key={group.module} className="mb-5">
                <div
                  className="flex items-center gap-2 px-2 mb-1.5 text-[11px] font-bold uppercase"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}
                >
                  <Icon size={12} />
                  Module {group.module} · {group.label}
                </div>
                <ul className="space-y-0.5">
                  {group.routes.map((r) => (
                    <li key={r.path}>
                      <NavLink
                        to={r.path}
                        className={({ isActive }) =>
                          `block px-2 py-1.5 rounded text-[13px] ${
                            isActive ? 'font-semibold' : ''
                          }`
                        }
                        style={({ isActive }) => ({
                          color: isActive
                            ? 'var(--color-accent)'
                            : 'var(--color-text-primary)',
                          background: isActive
                            ? 'var(--color-bg-page)'
                            : 'transparent',
                        })}
                      >
                        {r.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </nav>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
