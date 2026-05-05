import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocale } from '../contexts/LocaleContext';

/* ─────────────────────────────────────────────────────────────
   ProjectSelector — sidebar project switcher (PRD §4.1.1d E2)
   ─────────────────────────────────────────────────────────────
   Two visual variants:

     (a) projects.length === 0 (zero-Project state)
         The entire selector morphs into an empty-state CTA:
           Primary  → /projects/new (entry_source=empty_state_sidebar)
           Secondary → /industry
         PRD explicitly forbids rendering `Select Industry` /
         `Select Brand` / `· 主品牌` labels in this state — they
         are misleading when the user literally has no project.

     (b) projects.length > 0
         The classic switcher: active-project summary button →
         expand → list of projects + "+ 新建项目" footer.
*/

const ProjectSelector = ({
  activeProject,
  projects = [],
  brands = [],
  industries = [],
  onSwitch,
  onCreateNew,
}) => {
  const navigate = useNavigate();
  const { t } = useLocale();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  /* ── PRD §4.1.1d E2: zero-Project variant ──
     Must come BEFORE any activeProject lookup — `projects[0]` fallbacks
     produce phantom labels ("Select Industry · Select Brand · 主品牌")
     which PRD bans as misleading in the zero state. */
  if (projects.length === 0) {
    return (
      <div className="w-full space-y-2" aria-label={t('project_selector.empty.aria_label')}>
        <button
          type="button"
          onClick={() => navigate('/projects/new?entry_source=empty_state_sidebar')}
          className="w-full flex items-center justify-center gap-1.5 h-10 rounded-pill text-sm font-semibold transition-colors"
          style={{
            background: 'var(--color-accent)',
            color: '#FFFFFF',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd" />
          </svg>
          {t('project_selector.empty.cta_primary')}
        </button>
        <button
          type="button"
          onClick={() => navigate('/industry')}
          className="w-full flex items-center justify-center h-9 text-xs font-medium transition-colors"
          style={{ color: 'var(--color-sidebar-text, var(--color-text-muted))' }}
        >
          {t('project_selector.empty.cta_secondary')}
        </button>
      </div>
    );
  }

  // Find brand and industry objects for active project
  const activeBrand = brands.find(b => b.id === activeProject?.primaryBrandId);
  const activeIndustry = industries.find(ind => ind.id === activeProject?.industryId);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  const handleProjectSwitch = (projectId) => {
    onSwitch(projectId);
    setIsOpen(false);
  };

  const handleCreateNew = () => {
    onCreateNew();
    setIsOpen(false);
  };

  const getIndustryName = (industryId) => {
    const industry = industries.find(ind => ind.id === industryId);
    return industry?.name || '';
  };

  const getBrandName = (brandId) => {
    const brand = brands.find(b => b.id === brandId);
    return brand?.name || '';
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Collapsed state - selector button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors"
        style={{
          backgroundColor: 'var(--color-sidebar-selector-bg)',
          color: 'var(--color-sidebar-text)',
        }}
      >
        <div className="flex-1 text-left min-w-0">
          {/* Industry name - line 1 */}
          <div
            className="font-medium truncate"
            style={{
              fontSize: '13px',
              color: 'var(--color-sidebar-text)',
            }}
          >
            {activeIndustry?.name || t('project_selector.fallback_industry')}
          </div>
          {/* Brand name + badge - line 2 */}
          <div
            className="truncate"
            style={{
              fontSize: '11px',
              color: 'var(--color-sidebar-text)',
              opacity: 0.8,
            }}
          >
            {activeBrand?.name || t('project_selector.fallback_brand')}
            {activeBrand ? ` · ${t('project_selector.primary_suffix')}` : ''}
          </div>
        </div>

        {/* Chevron icon */}
        <svg
          className={`w-4 h-4 ml-2 flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          style={{ color: 'var(--color-sidebar-text)' }}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 14l-7 7m0 0l-7-7m7 7V3"
          />
        </svg>
      </button>

      {/* Expanded state - dropdown panel */}
      {isOpen && (
        <div
          className="absolute left-0 right-0 mt-2 bg-white border rounded-lg shadow-lg z-50"
          style={{
            borderColor: 'var(--color-sidebar-border)',
            top: '100%',
          }}
        >
          {/* Project list */}
          <div
            className="overflow-y-auto"
            style={{
              maxHeight: '200px',
            }}
          >
            {projects.map((project) => {
              const isActive = project.id === activeProject?.id;
              const projectBrand = brands.find(b => b.id === project.primaryBrandId);

              return (
                <div
                  key={project.id}
                  onClick={() => handleProjectSwitch(project.id)}
                  className="flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors"
                  style={{
                    backgroundColor: isActive ? 'var(--color-sidebar-selector-bg)' : 'transparent',
                    color: isActive ? 'var(--color-sidebar-text-active)' : 'var(--color-sidebar-text)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'var(--color-sidebar-item-hover)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  {/* Industry icon placeholder */}
                  <div
                    className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0"
                    style={{
                      backgroundColor: 'var(--color-sidebar-item-hover)',
                      fontSize: '12px',
                    }}
                  >
                    {getIndustryName(project.industryId).charAt(0) || '◯'}
                  </div>

                  {/* Brand name and panoScore */}
                  <div className="flex-1 min-w-0">
                    <div
                      className="font-medium truncate"
                      style={{
                        fontSize: '12px',
                      }}
                    >
                      {projectBrand?.name || 'Brand'}
                    </div>
                    {project.panoScore !== undefined && (
                      <div
                        style={{
                          fontSize: '10px',
                          opacity: 0.7,
                        }}
                      >
                        Score: {project.panoScore.toFixed(1)}
                      </div>
                    )}
                  </div>

                  {/* Checkmark for active project */}
                  {isActive && (
                    <svg
                      className="w-4 h-4 flex-shrink-0"
                      style={{ color: 'var(--color-sidebar-text-active)' }}
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  )}
                </div>
              );
            })}
          </div>

          {/* Divider */}
          <div
            style={{
              height: '1px',
              backgroundColor: 'var(--color-sidebar-border)',
            }}
          />

          {/* Create new project button */}
          <button
            onClick={handleCreateNew}
            className="w-full flex items-center gap-2 px-3 py-2.5 font-medium transition-colors"
            style={{
              fontSize: '12px',
              color: 'var(--color-sidebar-text)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--color-sidebar-item-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"
                clipRule="evenodd"
              />
            </svg>
            新建项目
          </button>
        </div>
      )}
    </div>
  );
};

export default ProjectSelector;
