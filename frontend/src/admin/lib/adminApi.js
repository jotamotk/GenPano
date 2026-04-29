/**
 * Session A0 · Thin fetch wrapper for /admin/api/v1/** calls.
 *
 * Centralizes:
 *   - credentials: 'include' (admin_access_token + admin_refresh_token cookies
 *     are HttpOnly + Path=/admin so the browser attaches them automatically).
 *   - JSON encode/decode.
 *   - Error normalization: every non-2xx becomes AdminApiError with
 *     { status, body }. Consumers map status+body.error to UI copy.
 *
 * Session A1' · T1 closure (decision #30 / SESSION_A1_PRIME_PROMPT.md §0.5):
 *   When a *user-initiated* call returns 401 (the silent-refresh probe in
 *   AdminAuthContext is itself an auth endpoint and is exempt), the wrapper
 *   notifies a registered expire-handler so AdminAuthContext can flip
 *   `sessionExpired = true` + cancel the refresh timer + broadcast across
 *   tabs. SessionExpiredModal then renders by reacting to that state and
 *   the user's "重新登录" CTA does the actual /admin/login redirect (the
 *   redirect chain is the A0' contract — we do not hard-navigate from the
 *   fetch wrapper because that would race with React render and lose the
 *   `?redirect=<current>` capture point).
 *
 * Auth endpoints (login / refresh / forgot-password / reset-password /
 * change-password) are exempt from the interceptor: a 401 there is an
 * expected business outcome (wrong password, expired refresh cookie) and
 * the relevant flow already handles it locally (login form shows error;
 * silent-refresh's own catch flips state directly). Firing the interceptor
 * on auth-endpoint 401 would either double-flip (refresh) or wrongly
 * "expire" an anonymous user mid-login (login).
 *
 * We deliberately do NOT bake a base URL here — in dev vite proxies
 * /admin/api/* to http://localhost:4000, in prod the backend is served
 * from the same origin. Either way, relative paths work.
 */

export class AdminApiError extends Error {
  constructor(status, body) {
    super(body?.error ?? `admin_api_error_${status}`);
    this.name = 'AdminApiError';
    this.status = status;
    this.body = body ?? null;
  }
}

async function parseBody(res) {
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/* ── 401 interceptor · module-level handler registry ─────────────
 *
 * AdminAuthProvider registers a single callback at mount and unregisters
 * on unmount. The registry is intentionally a single slot (not a list):
 * only one provider should be alive per page; replacing the slot under
 * StrictMode double-invoke is the correct behavior.
 */

let expireHandler = null;
const AUTH_ENDPOINT_PREFIX = '/admin/api/v1/auth/';

export function registerExpireHandler(fn) {
  expireHandler = typeof fn === 'function' ? fn : null;
}

function isAuthEndpoint(path) {
  if (typeof path !== 'string') return false;
  return path.startsWith(AUTH_ENDPOINT_PREFIX);
}

/**
 * @param {string} path
 * @param {{ method?: string, body?: any, signal?: AbortSignal }} [options]
 * @returns {Promise<any>}
 */
export async function adminFetch(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body != null ? { 'Content-Type': 'application/json' } : undefined,
    body: body != null ? JSON.stringify(body) : undefined,
    signal,
  });
  const parsed = await parseBody(res);
  if (!res.ok) {
    if (res.status === 401 && !isAuthEndpoint(path) && expireHandler) {
      try {
        expireHandler({ status: 401, body: parsed, path });
      } catch {
        // Handler must never throw out of the fetch path. Swallow.
      }
    }
    throw new AdminApiError(res.status, parsed);
  }
  return parsed;
}

/* ── Typed helpers per endpoint ───────────────────────────────── */

export const adminAuthApi = {
  login({ email, password }) {
    return adminFetch('/admin/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
    });
  },
  logout() {
    return adminFetch('/admin/api/v1/auth/logout', { method: 'POST' });
  },
  refresh() {
    return adminFetch('/admin/api/v1/auth/refresh', { method: 'POST' });
  },
  forgotPassword({ email }) {
    return adminFetch('/admin/api/v1/auth/forgot-password', {
      method: 'POST',
      body: { email },
    });
  },
  resetPassword({ token, newPassword }) {
    return adminFetch('/admin/api/v1/auth/reset-password', {
      method: 'POST',
      body: { token, newPassword },
    });
  },
  changePassword({ currentPassword, newPassword }) {
    return adminFetch('/admin/api/v1/auth/change-password', {
      method: 'POST',
      body: { currentPassword, newPassword },
    });
  },
};

/* ── Module A · admin user-management endpoints (Step 3 Y1-Y5) ── */

export const adminUsersApi = {
  list({ limit = 50, offset = 0, signal } = {}) {
    const qs = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    }).toString();
    return adminFetch(`/admin/api/v1/users?${qs}`, { signal });
  },
  detail(userId, { signal } = {}) {
    return adminFetch(`/admin/api/v1/users/${encodeURIComponent(userId)}`, {
      signal,
    });
  },
  /**
   * @param {string} userId
   * @param {{ reason: string, expiresAt?: string | null }} args
   */
  freeze(userId, { reason, expiresAt }) {
    return adminFetch(
      `/admin/api/v1/users/${encodeURIComponent(userId)}/freeze`,
      { method: 'POST', body: { reason, expires_at: expiresAt ?? null } },
    );
  },
  /**
   * @param {string} userId
   * @param {{ reason?: string | null }} args
   */
  forcePasswordReset(userId, { reason }) {
    return adminFetch(
      `/admin/api/v1/users/${encodeURIComponent(userId)}/force-password-reset`,
      { method: 'POST', body: { reason: reason ?? null } },
    );
  },
  /**
   * @param {string} userId
   * @param {{ reason: string }} args
   */
  softDelete(userId, { reason }) {
    return adminFetch(`/admin/api/v1/users/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
      body: { reason },
    });
  },
};
