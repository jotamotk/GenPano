/*
 * ToastViewport — renders toasts pushed via ProjectContext.pushToast.
 *
 * Two layouts:
 *   • compact (success/info)  — same minimal card as before, auto-dismiss.
 *   • error                   — sticky red-bordered panel showing the error
 *                               code, title, optional detail, request_id, a
 *                               Copy-details button, and a "show full" block
 *                               so users can manually select the entire
 *                               diagnostic block. Errors do not auto-dismiss.
 *
 * Copy-to-clipboard falls back to a temporary <textarea> + execCommand when
 * `navigator.clipboard` is unavailable (e.g. plain-HTTP admin previews).
 */
import React, { useState } from 'react';
import { useProject } from '../../contexts/ProjectContext';
import { useLanguage } from '../../contexts/LanguageContext';

const KIND_STYLE = {
  success: {
    background: 'var(--color-bg-card)',
    color: 'var(--color-text-primary)',
    border: '1px solid var(--color-success, #16a34a)',
    accent: 'var(--color-success, #16a34a)',
  },
  error: {
    background: 'var(--color-bg-card)',
    color: 'var(--color-text-primary)',
    border: '1px solid var(--color-danger, #dc2626)',
    accent: 'var(--color-danger, #dc2626)',
  },
  info: {
    background: 'var(--color-bg-card)',
    color: 'var(--color-text-primary)',
    border: '1px solid var(--color-border-subtle)',
    accent: 'var(--color-accent)',
  },
};

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_err) {
    /* fall through to legacy path */
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand && document.execCommand('copy');
    document.body.removeChild(ta);
    return Boolean(ok);
  } catch (_err) {
    return false;
  }
}

interface ToastShape {
  id: string;
  kind?: string;
  message?: string;
  title?: string;
  code?: string;
  detail?: string;
  requestId?: string;
  copyText?: string;
  count?: number;
  duration?: number;
}

interface ToastCardProps {
  toast: ToastShape;
  onDismiss: () => void;
}

function ErrorToastCard({ toast, onDismiss }: ToastCardProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const { t } = useLanguage();
  const labels = (t && t.errors) || {};
  const localizedTitle = (labels.codes && toast.code && labels.codes[toast.code]) || toast.title || toast.message;
  const onCopy = async () => {
    const ok = await copyText(toast.copyText || toast.message || '');
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };
  const style = KIND_STYLE.error;
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-card pointer-events-auto p-3 shadow-md text-sm flex gap-2"
      style={{
        background: style.background,
        color: style.color,
        border: style.border,
        boxShadow: 'var(--shadow-card-hover)',
      }}
    >
      <span
        className="w-1.5 self-stretch rounded-full flex-shrink-0"
        style={{ background: style.accent }}
      />
      <div className="flex-1 leading-snug min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          {toast.code ? (
            <span
              className="font-mono text-[11px] px-1.5 py-0.5 rounded"
              style={{ background: 'var(--color-bg-subtle, rgba(220,38,38,0.08))', color: style.accent }}
            >
              {toast.code}
            </span>
          ) : null}
          <span className="font-semibold break-words">{localizedTitle}</span>
          {toast.count && toast.count > 1 ? (
            <span className="text-[11px] text-themed-muted">× {toast.count}</span>
          ) : null}
        </div>
        {toast.detail ? (
          <div className="mt-1 text-themed-muted text-xs break-words whitespace-pre-wrap">
            {toast.detail}
          </div>
        ) : null}
        {toast.requestId ? (
          <div className="mt-1.5 text-[11px] font-mono text-themed-muted break-all">
            {(labels.requestId || 'request_id')}: {toast.requestId}
          </div>
        ) : null}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={onCopy}
            className="text-xs px-2 py-1 rounded border"
            style={{ borderColor: 'var(--color-border-subtle)' }}
          >
            {copied ? (labels.copied || 'Copied') : (labels.copy || 'Copy details')}
          </button>
          {toast.copyText ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="text-xs px-2 py-1 rounded text-themed-muted"
            >
              {labels.showMore || 'Show full details'}
            </button>
          ) : null}
        </div>
        {expanded && toast.copyText ? (
          <pre className="mt-2 text-[11px] font-mono whitespace-pre-wrap break-words p-2 rounded bg-themed-subtle text-themed-muted max-h-48 overflow-auto select-all">
            {toast.copyText}
          </pre>
        ) : null}
      </div>
      <button
        onClick={onDismiss}
        className="text-themed-muted hover:text-themed-primary text-xs flex-shrink-0"
        aria-label="dismiss"
      >
        ✕
      </button>
    </div>
  );
}

function CompactToastCard({ toast, onDismiss }: ToastCardProps) {
  const style = (toast.kind && (KIND_STYLE as Record<string, typeof KIND_STYLE.info>)[toast.kind]) || KIND_STYLE.info;
  return (
    <div
      className="rounded-card pointer-events-auto flex items-start gap-2 p-3 shadow-md text-sm"
      style={{
        background: style.background,
        color: style.color,
        border: style.border,
        boxShadow: 'var(--shadow-card-hover)',
      }}
    >
      <span
        className="w-1.5 self-stretch rounded-full flex-shrink-0"
        style={{ background: style.accent }}
      />
      <div className="flex-1 leading-snug">{toast.message}</div>
      <button
        onClick={onDismiss}
        className="text-themed-muted hover:text-themed-primary text-xs"
        aria-label="dismiss"
      >
        ✕
      </button>
    </div>
  );
}

export default function ToastViewport() {
  const { toasts, dismissToast } = useProject();
  if (!toasts || toasts.length === 0) return null;

  // Dedupe identical errors by code+detail, attaching a count badge — keeps
  // a flurry of repeated failures from drowning the viewport.
  const deduped: ToastShape[] = [];
  const errorIndex = new Map<string, number>();
  for (const toast of (toasts as unknown as ToastShape[])) {
    if (toast.kind === 'error') {
      const key = `${toast.code || ''}::${toast.detail || ''}::${toast.title || ''}`;
      const idx = errorIndex.get(key);
      if (idx != null) {
        const existing = deduped[idx];
        deduped[idx] = { ...existing, count: (existing.count || 1) + 1 };
        continue;
      }
      errorIndex.set(key, deduped.length);
    }
    deduped.push(toast);
  }

  // Cap visible items so a stuck-open error stack does not eat the screen.
  const visible = deduped.slice(-4);

  return (
    <div
      className="fixed bottom-4 right-4 z-[2000] flex flex-col gap-2 pointer-events-none"
      style={{ maxWidth: '420px', width: 'calc(100% - 2rem)' }}
    >
      {visible.map((toast) =>
        toast.kind === 'error' ? (
          <ErrorToastCard
            key={toast.id}
            toast={toast}
            onDismiss={() => dismissToast(toast.id)}
          />
        ) : (
          <CompactToastCard
            key={toast.id}
            toast={toast}
            onDismiss={() => dismissToast(toast.id)}
          />
        )
      )}
    </div>
  );
}
