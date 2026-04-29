/**
 * Session A1' · T1 closure tests
 *
 * Validates the 401 interceptor in adminApi.adminFetch:
 *   1. 2xx path is unchanged (handler not invoked, parsed body returned).
 *   2. 401 on a non-auth endpoint invokes the registered expire-handler.
 *   3. 401 on a non-auth endpoint still throws AdminApiError after the
 *      handler runs (caller's `try/catch` semantics preserved).
 *   4. 401 on an /admin/api/v1/auth/* endpoint does NOT invoke the
 *      handler (login/refresh failures are local business outcomes).
 *   5. Non-401 errors (e.g. 500) never invoke the handler.
 *
 * The wrapper deliberately does not navigate or render — those concerns
 * live in AdminAuthContext + SessionExpiredModal. We assert the
 * interceptor invocation contract; downstream effects are covered by the
 * provider integration tests in T6.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  adminFetch,
  AdminApiError,
  registerExpireHandler,
} from '../adminApi.js';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('adminFetch · 401 interceptor (Session A1 T1)', () => {
  let handler: ReturnType<typeof vi.fn>;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    handler = vi.fn();
    registerExpireHandler(handler);
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    registerExpireHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('case 1: 200 passthrough returns parsed body and does NOT invoke handler', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { items: [{ id: 'u-1' }], total: 1 }),
    );

    const out = await adminFetch('/admin/api/v1/users');

    expect(out).toEqual({ items: [{ id: 'u-1' }], total: 1 });
    expect(handler).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/api/v1/users',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('case 2: 401 on non-auth endpoint invokes the registered expire handler', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'unauthorized' }),
    );

    await expect(adminFetch('/admin/api/v1/users')).rejects.toBeInstanceOf(
      AdminApiError,
    );

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 401,
        path: '/admin/api/v1/users',
        body: { error: 'unauthorized' },
      }),
    );
  });

  it('case 3: 401 still throws AdminApiError after handler runs (caller chain preserved)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'unauthorized' }),
    );

    let caught: unknown = null;
    try {
      await adminFetch('/admin/api/v1/kg/industries');
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(AdminApiError);
    expect((caught as AdminApiError).status).toBe(401);
    expect((caught as AdminApiError).body).toEqual({ error: 'unauthorized' });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('case 4: 401 on /admin/api/v1/auth/login does NOT invoke handler (auth endpoint exempt)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'invalid_credentials' }),
    );

    await expect(
      adminFetch('/admin/api/v1/auth/login', {
        method: 'POST',
        body: { email: 'x@y.z', password: 'wrong' },
      }),
    ).rejects.toBeInstanceOf(AdminApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it('case 5: 500 (non-401) error never invokes handler', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, { error: 'internal_server_error' }),
    );

    await expect(adminFetch('/admin/api/v1/users')).rejects.toBeInstanceOf(
      AdminApiError,
    );

    expect(handler).not.toHaveBeenCalled();
  });
});

describe('adminFetch · handler registry lifecycle', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    registerExpireHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('unregistered (null) handler: 401 throws but no handler is called', async () => {
    registerExpireHandler(null);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'unauthorized' }),
    );

    await expect(adminFetch('/admin/api/v1/users')).rejects.toBeInstanceOf(
      AdminApiError,
    );
    // No throw because no handler. Test reaches this line = success.
  });
});
