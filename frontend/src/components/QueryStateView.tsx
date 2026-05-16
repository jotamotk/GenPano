import React, { useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { ApiError } from '../lib/apiClient';
import { formatApiError } from '../lib/showApiError';

/**
 * QueryStateView — unified loading / error / empty / data renderer for
 * TanStack Query results.
 *
 * Why this exists:
 *   The brand subpages used to do `productsQ.data ?? []` and then render
 *   "暂无产品数据" whenever data was missing — collapsing loading, error,
 *   and empty into the same blank surface. A 502 from the backend looked
 *   identical to "this brand truly has no products" (issue #1031).
 *
 * Contract:
 *   • `query.isLoading` → skeleton with `loadingLabel`
 *   • `query.isError`   → structured inline panel with code, request_id,
 *                          retry button (calls `query.refetch`), and a
 *                          "show details" disclosure with copy-to-clipboard.
 *                          When `query.error` is an ApiError we surface its
 *                          stable RFC 7807 code so support can grep for it.
 *   • `isEmpty(data)`   → muted `emptyLabel` line. Defaults to never-empty.
 *   • otherwise         → `children(data)`.
 *
 * The component intentionally renders inside whatever container the caller
 * provides (Card, plain div, etc.) so it composes with existing layouts
 * without forcing a wrapper.
 */

type QueryLike<TData> = {
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  data?: TData;
  refetch?: () => unknown;
  isFetching?: boolean;
};

interface QueryStateViewProps<TData> {
  query: QueryLike<TData>;
  children: (data: TData) => React.ReactNode;
  isEmpty?: (data: TData) => boolean;
  loadingLabel?: string;
  emptyLabel?: string;
  errorTitle?: string;
  /** Minimum height for the state surfaces so layout doesn't jump. */
  minHeight?: number | string;
}

export default function QueryStateView<TData>({
  query,
  children,
  isEmpty,
  loadingLabel,
  emptyLabel,
  errorTitle,
  minHeight = 160,
}: QueryStateViewProps<TData>) {
  if (query.isLoading) {
    return <LoadingState label={loadingLabel} minHeight={minHeight} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        title={errorTitle}
        onRetry={query.refetch}
        retrying={Boolean(query.isFetching)}
        minHeight={minHeight}
      />
    );
  }
  if (query.data === undefined || query.data === null) {
    return <EmptyState label={emptyLabel} minHeight={minHeight} />;
  }
  if (isEmpty && isEmpty(query.data)) {
    return <EmptyState label={emptyLabel} minHeight={minHeight} />;
  }
  return <>{children(query.data)}</>;
}

function LoadingState({
  label,
  minHeight,
}: {
  label?: string;
  minHeight: number | string;
}) {
  const { t } = useLanguage();
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center text-themed-muted text-sm"
      style={{ minHeight }}
    >
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block w-3 h-3 rounded-full border-2 border-themed-accent border-t-transparent animate-spin"
        />
        {label || t.errors?.loading || 'Loading...'}
      </span>
    </div>
  );
}

function EmptyState({
  label,
  minHeight,
}: {
  label?: string;
  minHeight: number | string;
}) {
  return (
    <div
      className="flex items-center justify-center text-themed-muted text-sm"
      style={{ minHeight }}
    >
      {label || '暂无数据'}
    </div>
  );
}

function ErrorState({
  error,
  title,
  onRetry,
  retrying,
  minHeight,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => unknown;
  retrying: boolean;
  minHeight: number | string;
}) {
  const { t } = useLanguage();
  const labels = t.errors || ({} as Partial<typeof t.errors>);
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const formatted = formatApiError(error);
  const codeLabel =
    (error instanceof ApiError && labels.codes && labels.codes[formatted.code]) ||
    formatted.title;
  const headline = title || labels.failedToLoad || 'Failed to load';

  const onCopy = async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(formatted.copyText);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }
    } catch {
      /* clipboard unavailable; user can still read the expanded block */
    }
  };

  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-2 p-4 text-center"
      style={{ minHeight }}
    >
      <div className="flex flex-wrap items-baseline justify-center gap-2">
        <span
          className="font-mono text-[11px] px-1.5 py-0.5 rounded"
          style={{
            background: 'var(--color-bg-subtle, rgba(220,38,38,0.08))',
            color: 'var(--color-danger, #dc2626)',
          }}
        >
          {formatted.code}
        </span>
        <span className="text-sm font-semibold text-themed-primary">
          {headline}
        </span>
      </div>
      <div className="text-xs text-themed-muted max-w-md">{codeLabel}</div>
      {formatted.requestId ? (
        <div className="text-[11px] font-mono text-themed-muted break-all">
          {labels.requestId || 'request_id'}: {formatted.requestId}
        </div>
      ) : null}
      <div className="flex items-center gap-2 mt-1 flex-wrap justify-center">
        {onRetry ? (
          <button
            type="button"
            onClick={() => {
              if (!retrying) onRetry();
            }}
            disabled={retrying}
            className="t-btn-primary py-1.5 px-3 text-xs disabled:opacity-50"
          >
            {retrying ? labels.retrying || 'Retrying...' : labels.retry || 'Retry'}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onCopy}
          className="text-xs px-2 py-1 rounded border text-themed-muted"
          style={{ borderColor: 'var(--color-border-subtle)' }}
        >
          {copied ? labels.copied || 'Copied' : labels.copy || 'Copy details'}
        </button>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs px-2 py-1 rounded text-themed-muted"
        >
          {labels.showMore || 'Show full details'}
        </button>
      </div>
      {expanded ? (
        <pre className="mt-2 text-[11px] font-mono whitespace-pre-wrap break-words p-2 rounded bg-themed-subtle text-themed-muted max-h-48 overflow-auto select-all w-full max-w-md text-left">
          {formatted.copyText}
        </pre>
      ) : null}
    </div>
  );
}
