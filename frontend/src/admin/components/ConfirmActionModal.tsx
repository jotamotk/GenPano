import React, { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AdminApiError } from '../lib/adminApi.js';

/**
 * ConfirmActionModal — wired confirmation for Module A actions
 * (freeze · force-password-reset · soft-delete). Uses Radix Dialog
 * primitives directly; we are not pulling in the shadcn CLI for one
 * component (decision: package.json already has @radix-ui/react-dialog).
 *
 * The action runner is injected so we don't bake `adminUsersApi` knowledge
 * into the modal — UserDetailPage passes the right shaped function.
 */

export interface ConfirmActionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Localized verb for the primary CTA, e.g. "冻结" / "强制改密" / "软删" */
  cta: string;
  /** Optional: tells the modal whether `reason` is required (most are required). */
  reasonRequired?: boolean;
  /** The work to do once the user confirms. Resolves on success. */
  onConfirm: (args: { reason: string }) => Promise<unknown>;
  /** Tone control for the CTA — destructive by default. */
  destructive?: boolean;
}

export default function ConfirmActionModal({
  open,
  onOpenChange,
  title,
  description,
  cta,
  reasonRequired = true,
  onConfirm,
  destructive = true,
}: ConfirmActionModalProps) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reasonOk = !reasonRequired || reason.trim().length > 0;

  const handleConfirm = async () => {
    if (!reasonOk || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({ reason: reason.trim() });
      setReason('');
      onOpenChange(false);
    } catch (err) {
      if (err instanceof AdminApiError) {
        const code = err.body?.detail?.reason ?? err.body?.error ?? `http_${err.status}`;
        setError(String(code));
      } else {
        setError('network_error');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0"
          style={{ background: 'rgba(0, 0, 0, 0.45)', zIndex: 50 }}
        />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-card p-5"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            zIndex: 51,
          }}
        >
          <Dialog.Title
            className="text-[15px] font-bold mb-1.5"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {title}
          </Dialog.Title>
          <Dialog.Description
            className="text-xs mb-4"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {description}
          </Dialog.Description>

          <label
            className="block text-[12px] font-medium mb-1.5"
            style={{ color: 'var(--color-text-primary)' }}
          >
            原因 {reasonRequired && <span style={{ color: '#ef4444' }}>*</span>}
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="请填写操作原因 (审计日志会记录)"
            className="w-full px-3 py-2 rounded text-[13px] resize-none"
            style={{
              background: 'var(--color-bg-page)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          />

          {error && (
            <div
              className="mt-2 text-xs px-2.5 py-1.5 rounded"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                color: '#dc2626',
                border: '1px solid rgba(239, 68, 68, 0.25)',
              }}
            >
              操作失败: <code>{error}</code>
            </div>
          )}

          <div className="flex justify-end gap-2 mt-5">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
              className="h-9 px-3.5 rounded text-[13px]"
              style={{
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
                background: 'transparent',
              }}
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!reasonOk || submitting}
              className="h-9 px-3.5 rounded text-[13px] font-semibold disabled:opacity-50"
              style={{
                background: destructive ? '#dc2626' : 'var(--color-accent)',
                color: '#fff',
              }}
            >
              {submitting ? '提交中…' : cta}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
