import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import AdminRouteGuard from '../AdminRouteGuard';
import { AdminAuthProvider } from '../../context/AdminAuthContext.jsx';

/**
 * AdminRouteGuard · 401 probe → anonymous → login redirect.
 *
 * The provider's mount-time /refresh probe drives the state machine.
 * On 401 we expect the guard to push the visitor to /admin/login.
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('AdminRouteGuard', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('redirects to /admin/login when /refresh returns 401', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'no_session' }),
    );

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminAuthProvider>
          <Routes>
            <Route element={<AdminRouteGuard />}>
              <Route path="/admin/dashboard" element={<div>SECRET</div>} />
            </Route>
            <Route path="/admin/login" element={<div>LOGIN_PAGE</div>} />
          </Routes>
        </AdminAuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('LOGIN_PAGE')).toBeInTheDocument(),
    );
    expect(screen.queryByText('SECRET')).toBeNull();
  });

  it('renders children when /refresh returns a valid session', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        user: { id: 'a-1', email: 'admin@x.com', role: 'super_admin' },
      }),
    );

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminAuthProvider>
          <Routes>
            <Route element={<AdminRouteGuard />}>
              <Route path="/admin/dashboard" element={<div>SECRET</div>} />
            </Route>
            <Route path="/admin/login" element={<div>LOGIN_PAGE</div>} />
          </Routes>
        </AdminAuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('SECRET')).toBeInTheDocument(),
    );
  });
});
