import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UsersListPage from '../UsersListPage';

/**
 * UsersListPage · GET /admin/api/v1/users wiring + render
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('UsersListPage (Module A · Y1)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders table rows from a 200 response', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        items: [
          {
            id: 'u-1',
            email: 'alice@example.com',
            name_zh: '艾莉丝',
            name_en: null,
            created_at: '2026-04-01T08:00:00Z',
            is_frozen: false,
            is_deleted: false,
          },
          {
            id: 'u-2',
            email: 'bob@example.com',
            name_zh: null,
            name_en: 'Bob',
            created_at: '2026-04-02T08:00:00Z',
            is_frozen: true,
            is_deleted: false,
          },
        ],
        total: 2,
      }),
    );

    render(
      <MemoryRouter>
        <UsersListPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('alice@example.com')).toBeInTheDocument(),
    );
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(screen.getByText('已冻结')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/admin/api/v1/users');
    expect(url).toContain('limit=25');
    expect(url).toContain('offset=0');
  });

  it('shows error block when backend returns 500', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, { detail: { reason: 'internal' } }),
    );

    render(
      <MemoryRouter>
        <UsersListPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText(/请求失败/)).toBeInTheDocument(),
    );
  });
});
