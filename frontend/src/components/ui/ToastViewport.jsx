/*
 * ToastViewport — minimal renderer for toasts pushed via
 * ProjectContext.pushToast({ kind, message }).
 *
 * Lives at the app root (mounted from App.jsx). Real impl will swap
 * to Sonner per CLAUDE.md dependency rules.
 *
 * ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
 *   This file owns no copy. All `toast.message` strings are produced by
 *   callers via t() — never hard-code user-facing text here.
 */
import React from 'react';
import { useProject } from '../../contexts/ProjectContext';

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

export default function ToastViewport() {
  const { toasts, dismissToast } = useProject();
  if (!toasts || toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[2000] flex flex-col gap-2 pointer-events-none"
      style={{ maxWidth: '360px' }}
    >
      {toasts.map((toast) => {
        const style = KIND_STYLE[toast.kind] || KIND_STYLE.info;
        return (
          <div
            key={toast.id}
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
              onClick={() => dismissToast(toast.id)}
              className="text-themed-muted hover:text-themed-primary text-xs"
              aria-label="dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
