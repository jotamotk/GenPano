import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';

/* ─────────────────────────────────────────────────────────────
   DashboardEmptyState — PRD §4.1.1d E1
   ─────────────────────────────────────────────────────────────
   Rendered by DashboardPage when `projects.length === 0`.
   MUST take over the entire page (no `fallback to PROJECTS[0]`,
   no phantom KPI cards with industry data masquerading as "yours").

   Composition:
     1. Title + subtitle explaining why there is nothing to show
     2. Primary CTA  → /projects/new         (T9 expert fast-path)
     3. Secondary CTA → /industry             (data-first exploration)
     4. Three greyed preview cards (PanoScore / 提及率 / 引用份额) —
        placeholders only; PRD forbids mounting Recharts here to keep
        the surface lightweight and avoid simulating data the user
        does not have yet.

   Instrumentation (Mixpanel #44 `empty_state_shown` per §4.11):
     surface='dashboard', authState='authenticated_zero_project'
     — fired by the caller (DashboardPage) because this component
     stays stateless/presentational.
*/
const PREVIEW_CARDS = [
  { id: 'pano', labelKey: 'dashboard.empty.preview_pano_label' },
  { id: 'mention', labelKey: 'dashboard.empty.preview_mention_label' },
  { id: 'citation', labelKey: 'dashboard.empty.preview_citation_label' },
];

export default function DashboardEmptyState() {
  const navigate = useNavigate();
  const { t } = useLocale();

  const onCreate = () => {
    // entry_source=empty_state_dashboard — one of the 6 enums PRD §4.1.1d
    navigate('/projects/new?entry_source=empty_state_dashboard');
  };

  const onExplore = () => {
    navigate('/industry');
  };

  return (
    <div className="flex flex-col items-center justify-center py-16 px-6">
      <div className="max-w-xl w-full text-center">
        {/* Decorative icon (abstract layered squares) */}
        <div
          className="w-16 h-16 mx-auto mb-6 rounded-card-lg flex items-center justify-center"
          style={{
            background: 'var(--color-accent-bg-light, rgba(99, 91, 255, 0.08))',
            color: 'var(--color-accent)',
          }}
          aria-hidden="true"
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
          </svg>
        </div>

        <h1
          className="text-2xl font-brand font-bold mb-3"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
        >
          {t('dashboard.empty.title')}
        </h1>
        <p
          className="text-sm mb-8 leading-relaxed"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('dashboard.empty.subtitle')}
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-12">
          <button
            type="button"
            onClick={onCreate}
            className="t-btn-primary h-11 px-6 text-sm font-semibold w-full sm:w-auto"
          >
            {t('dashboard.empty.cta_primary')}
          </button>
          <button
            type="button"
            onClick={onExplore}
            className="h-11 px-5 text-sm font-medium rounded-btn-lg transition-colors w-full sm:w-auto"
            style={{
              color: 'var(--color-text-body)',
              border: '1px solid var(--color-border-subtle)',
              background: 'transparent',
            }}
          >
            {t('dashboard.empty.cta_secondary')}
          </button>
        </div>

        {/* Greyed preview row — placeholders only, no chart data */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 opacity-70">
          {PREVIEW_CARDS.map((card) => (
            <div
              key={card.id}
              className="rounded-card p-5 text-left"
              style={{
                background: 'var(--color-bg-subtle, #f8fafc)',
                border: '1px dashed var(--color-border-subtle)',
              }}
              aria-hidden="true"
            >
              <div
                className="text-xs font-medium mb-2"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t(card.labelKey)}
              </div>
              <div
                className="h-8 rounded-btn mb-2"
                style={{ background: 'var(--color-border-subtle)' }}
              />
              <div
                className="text-[11px]"
                style={{ color: 'var(--color-text-faint, var(--color-text-muted))' }}
              >
                {t('dashboard.empty.preview_placeholder')}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
