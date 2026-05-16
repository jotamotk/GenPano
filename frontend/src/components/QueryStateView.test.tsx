import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../contexts/LanguageContext'
import QueryStateView from './QueryStateView'
import { ApiError } from '../lib/apiClient'

function renderWithLocale(ui: React.ReactElement, lang: 'zh' | 'en' = 'en') {
  window.localStorage.setItem('genpano_lang', lang)
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('QueryStateView', () => {
  it('renders a loading state while the query is pending', () => {
    renderWithLocale(
      <QueryStateView query={{ isLoading: true }}>
        {() => <div data-testid="content">should-not-render</div>}
      </QueryStateView>,
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByTestId('content')).not.toBeInTheDocument()
  })

  it('shows the structured error panel with code + request_id + retry on error', () => {
    const apiError = new ApiError(
      {
        type: 'about:blank',
        title: 'Bad Gateway',
        status: 502,
        code: 'bad_gateway',
      },
      { requestId: 'req-abc-123', path: '/v1/projects/xx/products' },
    )
    const refetch = vi.fn()

    renderWithLocale(
      <QueryStateView
        query={{ isError: true, error: apiError, refetch }}
      >
        {() => <div data-testid="content">should-not-render</div>}
      </QueryStateView>,
    )

    // Error code is shown verbatim so support can grep for it.
    expect(screen.getByText('bad_gateway')).toBeInTheDocument()
    // Request id is surfaced.
    expect(screen.getByText(/req-abc-123/)).toBeInTheDocument()
    // The localized message for bad_gateway should be visible (en-US).
    expect(
      screen.getByText(/Upstream service is temporarily unavailable/i),
    ).toBeInTheDocument()
    // Retry button invokes refetch.
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }))
    expect(refetch).toHaveBeenCalledTimes(1)
    // Children must not be rendered while in the error state.
    expect(screen.queryByTestId('content')).not.toBeInTheDocument()
  })

  it('renders the empty label when isEmpty returns true', () => {
    renderWithLocale(
      <QueryStateView
        query={{ data: { items: [] } }}
        isEmpty={(d) => (d as { items: unknown[] }).items.length === 0}
        emptyLabel="No products yet"
      >
        {() => <div data-testid="content">should-not-render</div>}
      </QueryStateView>,
    )
    expect(screen.getByText('No products yet')).toBeInTheDocument()
    expect(screen.queryByTestId('content')).not.toBeInTheDocument()
  })

  it('renders children with the data when query succeeds and is not empty', () => {
    renderWithLocale(
      <QueryStateView
        query={{ data: { items: [{ id: 1, name: 'Product A' }] } }}
        isEmpty={(d) => (d as { items: unknown[] }).items.length === 0}
      >
        {(d) => (
          <ul>
            {(d as { items: { id: number; name: string }[] }).items.map((it) => (
              <li key={it.id}>{it.name}</li>
            ))}
          </ul>
        )}
      </QueryStateView>,
    )
    expect(screen.getByText('Product A')).toBeInTheDocument()
  })

  it('shows the empty label when data is undefined (no isEmpty callback)', () => {
    renderWithLocale(
      <QueryStateView query={{ data: undefined }} emptyLabel="Nothing here">
        {() => <div data-testid="content">should-not-render</div>}
      </QueryStateView>,
    )
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.queryByTestId('content')).not.toBeInTheDocument()
  })
})
