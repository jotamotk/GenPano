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

export async function adminFetch(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body != null ? { 'Content-Type': 'application/json' } : undefined,
    body: body != null ? JSON.stringify(body) : undefined,
    signal,
  });
  const parsed = await parseBody(res);
  if (!res.ok) throw new AdminApiError(res.status, parsed);
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
