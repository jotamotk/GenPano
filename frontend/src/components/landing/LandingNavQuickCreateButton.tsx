import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import AuthPromptModal from '../auth/AuthPromptModal';

/* ─────────────────────────────────────────────────────────────
   LandingNavQuickCreateButton — PRD §4.1.1d E3
   ─────────────────────────────────────────────────────────────
   A small top-right nav button on the Landing page that morphs
   by auth + project state:

     Anonymous              → opens <AuthPromptModal hookKey=
                              "quick_create_project"/> (T9)
     Authenticated, 0 Project → navigates to /projects/new
                                (entry_source=landing_nav_quick)
     Authenticated, has Project → navigates to /projects/new
                                 with label "+ New project"

   The button must stay small and sit in the nav corner — it is
   deliberately not the hero CTA. The Landing hero still owns the
   primary conversion funnel (Sign up free); this button is a
   fast-path for users who already know what they want.
*/
export default function LandingNavQuickCreateButton({ className = '', style = {} }) {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { projects, isAuthenticated } = useProject();
  const [modalOpen, setModalOpen] = useState(false);

  const hasProject = isAuthenticated && projects.length > 0;
  const zeroProject = isAuthenticated && projects.length === 0;

  let labelKey;
  if (!isAuthenticated) labelKey = 'nav.quickCreate.anonymous';
  else if (zeroProject) labelKey = 'nav.quickCreate.authenticated_zero';
  else labelKey = 'nav.quickCreate.authenticated_has';

  const handleClick = () => {
    if (!isAuthenticated) {
      // T9 expert fast-path — open modal so the user sees the value prop
      // before committing to the signup flow.
      setModalOpen(true);
      return;
    }
    // Both authenticated states go to /projects/new; the page itself can
    // decide whether to show a "first project" vs "additional project"
    // variant based on projects.length.
    navigate('/projects/new?entry_source=landing_nav_quick');
  };

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-btn transition-all duration-200 ${className}`}
        style={{
          background: hasProject ? 'transparent' : '#030303',
          color: hasProject ? '#030B1D' : '#FFFFFF',
          border: hasProject ? '1.5px solid #E2E8F0' : '1.5px solid #030303',
          ...style,
        }}
      >
        {!hasProject && (
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M8 0a.5.5 0 01.5.5v2a.5.5 0 01-1 0v-2A.5.5 0 018 0zm0 11a.5.5 0 01.5.5v2a.5.5 0 01-1 0v-2A.5.5 0 018 11zm5-3a.5.5 0 01-.5.5h-2a.5.5 0 010-1h2a.5.5 0 01.5.5zM5 8a.5.5 0 01-.5.5h-2a.5.5 0 010-1h2A.5.5 0 015 8zm6.354-3.354a.5.5 0 010 .708l-1.414 1.414a.5.5 0 01-.708-.708l1.414-1.414a.5.5 0 01.708 0zM6.768 9.232a.5.5 0 010 .708l-1.414 1.414a.5.5 0 01-.708-.708l1.414-1.414a.5.5 0 01.708 0zm4.586 2.122a.5.5 0 01-.708 0L9.232 9.94a.5.5 0 01.708-.708l1.414 1.414a.5.5 0 010 .708zM6.06 6.768a.5.5 0 01-.708 0L3.938 5.354a.5.5 0 01.708-.708L6.06 6.06a.5.5 0 010 .708z" />
          </svg>
        )}
        {t(labelKey)}
      </button>

      <AuthPromptModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        hookKey="quick_create_project"
        returnTo="/projects/new"
        action="create_project"
        entrySource="landing_nav_quick"
      />
    </>
  );
}
