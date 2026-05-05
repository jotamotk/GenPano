import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';

/* ─────────────────────────────────────────────────────────────
   AuthPromptModal — PRD §4.1.1c T1-T9 delayed auth wall framework
   ─────────────────────────────────────────────────────────────
   A generic, hook-aware modal that any CTA can fire when it needs
   to gate an action behind sign-up/login. The consumer passes:

     hookKey    — matches `auth.hook.<key>` i18n namespace
                  (e.g. 'quick_create_project' for T9)
     returnTo   — where the user should land after auth succeeds
                  (serialized into /register?return_to=...)
     action     — optional secondary intent like 'create_project' or
                  'monitor_brand' that upstream pages can read off
                  the URL after the auth wizard completes

   Each hook advertises 3 fixed value bullets + a primary + secondary
   CTA. Uses Radix Dialog rather than a hand-rolled modal —
   this gets us focus trap, ESC, ARIA out of the box).

   Wire-up note (PRD §4.11 #44-46): callers should also fire the
   corresponding Mixpanel event (e.g. `auth_prompt_shown` with
   hook=<key>, entry_source=<source>) before mounting. Instrumentation
   lives in the caller, not here, so we stay presentational.
*/
export default function AuthPromptModal({
  open,
  onOpenChange,
  hookKey = 'quick_create_project',
  returnTo = '',
  action = '',
  entrySource = '',
}) {
  const navigate = useNavigate();
  const { t } = useLocale();

  const k = (suffix) => `auth.hook.${hookKey}.${suffix}`;

  const handlePrimary = () => {
    const qs = new URLSearchParams();
    if (returnTo) qs.set('return_to', returnTo);
    if (action) qs.set('action', action);
    if (entrySource) qs.set('entry_source', entrySource);
    const tail = qs.toString();
    onOpenChange?.(false);
    navigate(`/register${tail ? `?${tail}` : ''}`);
  };

  const handleSecondary = () => {
    onOpenChange?.(false);
    // Secondary path keeps the user in data-exploration mode without
    // forcing auth (PRD §4.1.1 "Data-Before-Auth"). Sends them to the
    // industry list — they can still sign up later from any hook.
    navigate('/industry');
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50"
          style={{ background: 'rgba(3, 11, 29, 0.48)', backdropFilter: 'blur(2px)' }}
        />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-card-lg p-8"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            boxShadow: '0 24px 64px rgba(3, 11, 29, 0.18)',
          }}
        >
          <Dialog.Title
            className="text-xl font-brand font-bold mb-1.5"
            style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
          >
            {t(k('title'))}
          </Dialog.Title>
          <Dialog.Description
            className="text-sm mb-5"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t(k('subtitle'))}
          </Dialog.Description>

          {/* Three fixed value bullets (PRD §4.1.1c) */}
          <ul className="space-y-2.5 mb-6">
            {['bullet_1', 'bullet_2', 'bullet_3'].map((b) => (
              <li
                key={b}
                className="flex items-start gap-2.5 text-sm"
                style={{ color: 'var(--color-text-body)' }}
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="flex-shrink-0 mt-0.5"
                  style={{ color: 'var(--color-accent)' }}
                  aria-hidden="true"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span>{t(k(b))}</span>
              </li>
            ))}
          </ul>

          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={handlePrimary}
              className="t-btn-primary w-full h-11 text-sm font-semibold"
            >
              {t(k('cta_primary'))}
            </button>
            <button
              type="button"
              onClick={handleSecondary}
              className="w-full h-10 text-sm font-medium transition-colors"
              style={{ color: 'var(--color-text-muted)' }}
            >
              {t(k('cta_secondary'))}
            </button>
          </div>

          <Dialog.Close
            className="absolute top-4 right-4 w-8 h-8 rounded-btn flex items-center justify-center transition-colors"
            style={{ color: 'var(--color-text-muted)' }}
            aria-label={t('common.cancel')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
