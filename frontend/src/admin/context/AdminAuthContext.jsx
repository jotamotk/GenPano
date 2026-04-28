import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { adminAuthApi, AdminApiError } from '../lib/adminApi.js';

/* ─────────────────────────────────────────────────────────────
   AdminAuthContext — Provider implementation (CLAUDE.md #24.D)

   Responsibilities:
     1. Track current admin identity: { user, status }
        status ∈ 'initializing' | 'authenticated' | 'anonymous' | 'expired'
     2. Schedule a silent-refresh timer ACCESS_TOKEN_TTL - SILENT_REFRESH_LEAD
        (~14min) after every successful auth event. Failure → status='expired'.
     3. Cross-tab sync via BroadcastChannel('genpano-admin-auth'):
          login   → other tabs adopt new user, cancel any expired modal
          logout  → other tabs go anonymous + hard-navigate /admin/login
          refresh → other tabs reschedule their timer
          expire  → other tabs also show modal
     4. Expose `sessionExpired` boolean that <SessionExpiredModal /> consumes.

   What this provider does NOT do:
     - Render any UI itself (modal is a sibling in AdminAuthShell).
     - Read the JWT (it's HttpOnly). Expiry is inferred from timer, not cookie
       inspection. The backend is the real authority via /refresh response.
     - Store the access token in memory. Cookies do the job.

   URL guard behavior:
     The provider just maintains state; AdminRouteGuard.jsx reads `status`
     and decides whether to render children or redirect.
   ───────────────────────────────────────────────────────────── */

/* Silent refresh: 14min interval (token TTL 15min, lead 60s).
 * MVP 客观选择: 客户端常量调度, 不消费 accessExpiresAt 的服务端时钟。
 * 时钟漂移 >60s 的低概率分支兜底是 SessionExpiredModal (用户重登)。
 * 升级路径: 改用 accessExpiresAt 动态调度待 Session A1' 或会话健壮性批次。
 * 后端 mirror: app/admin/auth/constants.py · ACCESS_TOKEN_TTL_SECONDS=900. */
const ACCESS_TOKEN_TTL_SECONDS = 15 * 60;
const SILENT_REFRESH_LEAD_SECONDS = 60;
const SILENT_REFRESH_INTERVAL_MS =
  (ACCESS_TOKEN_TTL_SECONDS - SILENT_REFRESH_LEAD_SECONDS) * 1000;

const BROADCAST_CHANNEL_NAME = 'genpano-admin-auth';

const AdminAuthContext = createContext(null);

export function useAdminAuth() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) {
    throw new Error(
      'useAdminAuth() must be called inside <AdminAuthProvider>. ' +
        'Check that the route is wrapped by <AdminAuthShell />.',
    );
  }
  return ctx;
}

export function AdminAuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('initializing');
  const [sessionExpired, setSessionExpired] = useState(false);

  const refreshTimerRef = useRef(null);
  const channelRef = useRef(null);
  const mountedRef = useRef(true);

  /* ── Timer helpers ────────────────────────────────────────── */

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current != null) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    clearRefreshTimer();
    refreshTimerRef.current = setTimeout(() => {
      void silentRefresh();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, SILENT_REFRESH_INTERVAL_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearRefreshTimer]);

  /* ── Broadcast helpers ────────────────────────────────────── */

  const broadcast = useCallback((msg) => {
    try {
      channelRef.current?.postMessage(msg);
    } catch {
      // BroadcastChannel can throw if the channel was closed mid-flight.
      // Not worth surfacing — cross-tab sync is best-effort.
    }
  }, []);

  /* ── Core auth operations ─────────────────────────────────── */

  const silentRefresh = useCallback(async () => {
    try {
      const res = await adminAuthApi.refresh();
      if (!mountedRef.current) return;
      setUser(res?.user ?? null);
      setStatus('authenticated');
      setSessionExpired(false);
      scheduleRefresh();
      broadcast({ type: 'refresh', user: res?.user ?? null });
    } catch (err) {
      if (!mountedRef.current) return;
      // Any failure = session no longer usable. Backend already cleared
      // cookies on 401 path.
      clearRefreshTimer();
      setUser(null);
      setStatus('expired');
      setSessionExpired(true);
      broadcast({ type: 'expire' });
      // Swallow non-AdminApiError (e.g. offline) so one flaky tick doesn't
      // throw out of a timer callback.
      if (!(err instanceof AdminApiError)) {
        // eslint-disable-next-line no-console
        console.warn('[admin-auth] silent refresh failed (network?)', err);
      }
    }
  }, [broadcast, clearRefreshTimer, scheduleRefresh]);

  const login = useCallback(
    async ({ email, password }) => {
      const res = await adminAuthApi.login({ email, password });
      if (!mountedRef.current) return res;
      setUser(res?.user ?? null);
      setStatus('authenticated');
      setSessionExpired(false);
      scheduleRefresh();
      broadcast({ type: 'login', user: res?.user ?? null });
      return res;
    },
    [broadcast, scheduleRefresh],
  );

  const logout = useCallback(
    async ({ silent = false } = {}) => {
      clearRefreshTimer();
      try {
        await adminAuthApi.logout();
      } catch {
        // Always swallow — user intent is "get me out". Cookie-path cleanup
        // happens server-side on 200 or via cookie expiry.
      }
      if (!mountedRef.current) return;
      setUser(null);
      setStatus('anonymous');
      setSessionExpired(false);
      if (!silent) broadcast({ type: 'logout' });
    },
    [broadcast, clearRefreshTimer],
  );

  const dismissExpiredModal = useCallback(() => {
    setSessionExpired(false);
  }, []);

  /* ── Mount: probe session + set up BroadcastChannel ───────── */

  useEffect(() => {
    mountedRef.current = true;

    // Set up cross-tab channel FIRST so an immediate login/logout in another
    // tab while we're probing doesn't get lost.
    let ch = null;
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        ch = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
        ch.onmessage = (evt) => {
          const msg = evt?.data;
          if (!msg || typeof msg !== 'object') return;
          switch (msg.type) {
            case 'login':
            case 'refresh': {
              setUser(msg.user ?? null);
              setStatus('authenticated');
              setSessionExpired(false);
              scheduleRefresh();
              break;
            }
            case 'logout': {
              clearRefreshTimer();
              setUser(null);
              setStatus('anonymous');
              setSessionExpired(false);
              break;
            }
            case 'expire': {
              clearRefreshTimer();
              setUser(null);
              setStatus('expired');
              setSessionExpired(true);
              break;
            }
            default:
              break;
          }
        };
        channelRef.current = ch;
      } catch {
        // Older browsers / private mode may throw; proceed without sync.
        channelRef.current = null;
      }
    }

    // Probe: hit /refresh once. If a valid refresh cookie exists, we get a
    // fresh pair of cookies and the user payload; otherwise we go anonymous
    // quietly (no modal, because user hasn't done anything yet).
    (async () => {
      try {
        const res = await adminAuthApi.refresh();
        if (!mountedRef.current) return;
        setUser(res?.user ?? null);
        setStatus('authenticated');
        scheduleRefresh();
      } catch {
        if (!mountedRef.current) return;
        setUser(null);
        setStatus('anonymous');
      }
    })();

    return () => {
      mountedRef.current = false;
      clearRefreshTimer();
      try {
        channelRef.current?.close();
      } catch {
        /* no-op */
      }
      channelRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      sessionExpired,
      login,
      logout,
      refreshNow: silentRefresh,
      dismissExpiredModal,
    }),
    [user, status, sessionExpired, login, logout, silentRefresh, dismissExpiredModal],
  );

  return (
    <AdminAuthContext.Provider value={value}>
      {children}
    </AdminAuthContext.Provider>
  );
}
