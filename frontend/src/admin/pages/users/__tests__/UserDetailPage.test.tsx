import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import UserDetailPage from '../UserDetailPage';

/**
 * UserDetailPage · 4-tab Detail + Y3 freeze action wiring.
 *
 * The detail probe and the freeze POST share the global fetch mock; we
 * sequence responses in the order the page issues them.
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const DETAIL_BODY = {
  id: 'u-1',
  email: 'alice@example.com',
  name_zh: '艾莉丝',
  name_en: null,
  email_verified_at: null,
  preferences: {},
  created_at: '2026-04-01T08:00:00Z',
  updated_at: '2026-04-01T08:00:00Z',
  deletion_requested_at: null,
  is_frozen: false,
  recent_moderation: [],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/users/u-1']}>
      <Routes>
        <Route path="/admin/users/:userId" element={<UserDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('UserDetailPage (Module A · Y2 + Y3)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders header + basic-tab fields after detail GET', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, DETAIL_BODY));

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'alice@example.com' }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText('艾莉丝')).toBeInTheDocument();
    expect(screen.getByText('正常')).toBeInTheDocument();
  });

  it('opens freeze modal then POSTs to /freeze with reason', async () => {
    // 1. initial GET
    fetchMock.mockResolvedValueOnce(jsonResponse(200, DETAIL_BODY));
    // 2. POST /freeze
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { user_id: 'u-1', action: 'freeze' }),
    );
    // 3. refetch after success
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { ...DETAIL_BODY, is_frozen: true }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '冻结' })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: '冻结' }));

    await waitFor(() =>
      expect(screen.getByText('冻结此用户')).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByPlaceholderText(/请填写操作原因/), {
      target: { value: '违反社区准则' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认冻结' }));

    await waitFor(() => {
      const freezeCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).endsWith('/freeze'),
      );
      expect(freezeCall).toBeDefined();
    });

    const freezeCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).endsWith('/freeze'),
    );
    expect(freezeCall).toBeDefined();
    expect(String(freezeCall![0])).toBe('/admin/api/v1/users/u-1/freeze');
    const init = freezeCall![1] as RequestInit;
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body as string);
    expect(body.reason).toBe('违反社区准则');
  });
});
