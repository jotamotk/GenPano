import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';

/* ─────────────────────────────────────────────────────────────
   ProjectRequiredBanner — PRD §4.1.1d E4
   ─────────────────────────────────────────────────────────────
   Top-of-page banner for pages that depend on a Project
   (/brands/:id?tab=diag, /topics, etc.). Renders only when:

     - user is authenticated
     - projects.length === 0
     - banner not already dismissed for this page (sessionStorage)

   Primary CTA routes to /projects/new with entry_source=gated_banner;
   secondary routes to /industry for data-first browsing. Dismissal
   is scoped to `pathname` so moving to a different gated page will
   surface the banner again (intentional — each gated surface is a
   separate decision point per PRD §4.1.1d).

   Consumer mounts this at the top of the page; no props required.
*/
const DISMISS_PREFIX = 'genpano.gatedBanner.dismissed.';

export default function ProjectRequiredBanner() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useLocale();
  const { projects, isAuthenticated } = useProject();
  const [dismissed, setDismissed] = useState(false);

  const storageKey = `${DISMISS_PREFIX}${location.pathname}`;

  useEffect(() => {
    try {
      const v = sessionStorage.getItem(storageKey);
      setDismissed(v === '1');
    } catch {
      /* sessionStorage unavailable — default to shown */
    }
  }, [storageKey]);

  const onDismiss = () => {
    try {
      sessionStorage.setItem(storageKey, '1');
    } catch {
      /* noop */
    }
    setDismissed(true);
  };

  const onCreate = () => {
    navigate('/projects/new?entry_source=gated_banner');
  };

  const onExplore = () => {
    navigate('/industry');
  };

  // Guard: only show for authenticated zero-Project users
  if (!isAuthenticated) return null;
  if (projects.length > 0) return null;
  if (dismissed) return null;

  return (
    <div
      role="region"
      aria-label={t('project.gatedBanner.title')}
      className="flex items-start gap-4 rounded-card p-4 mb-4"
      style={{
        background: 'var(--color-accent-bg-light, rgba(99, 91, 255, 0.06))',
        border: '1px solid var(--color-accent-soft, rgba(99, 91, 255, 0.18))',
      }}
    >
      <div
        className="w-9 h-9 rounded-btn flex items-center justify-center flex-shrink-0"
        style={{ background: 'var(--color-accent)', color: '#FFFFFF' }}
        aria-hidden="true"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="12" y1="18" x2="12" y2="12" />
          <line x1="9" y1="15" x2="15" y2="15" />
        </svg>
      </div>

      <div className="flex-1 min-w-0">
        <div
          className="text-sm font-semibold mb-1"
          style={{ color: 'var(--color-text-primary)' }}
        >
          {t('project.gatedBanner.title')}
        </div>
        <div
          className="text-xs mb-3 leading-relaxed"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('project.gatedBanner.body')}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center h-8 px-3 text-xs font-semibold rounded-btn transition-colors"
            style={{ background: 'var(--color-accent)', color: '#FFFFFF' }}
          >
            {t('project.gatedBanner.cta_primary')}
          </button>
          <button
            type="button"
            onClick={onExplore}
            className="inline-flex items-center h-8 px-3 text-xs font-medium rounded-btn transition-colors"
            style={{
              color: 'var(--color-text-body)',
              border: '1px solid var(--color-border-subtle)',
              background: 'transparent',
            }}
          >
            {t('project.gatedBanner.cta_secondary')}
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={onDismiss}
        aria-label={t('project.gatedBanner.dismiss_aria')}
        className="w-7 h-7 rounded-btn flex items-center justify-center transition-colors flex-shrink-0"
        style={{ color: 'var(--color-text-muted)' }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}
