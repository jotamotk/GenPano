/*
 * BrandPicker — sidebar dropdown so the user can switch the active brand.
 * ────────────────────────────────────────────────────────────────────────
 * Replaces the stub button in DashboardLayout's sidebar that previously
 * showed `activeProject.primaryBrandName` but had no click handler.
 *
 * Three sections, in this priority order:
 *   1. 我的项目 — list of the user's projects, click → setActiveProjectId
 *      so the dashboard re-renders for that project's primary brand.
 *      The currently active project is highlighted with a check mark.
 *   2. 当前项目竞品 — pinned competitors of the active project, click →
 *      navigate to /brand/overview?brandId=X so dashboards / brand pages
 *      render with that brand as the override (DashboardPage reads
 *      `brandId` from the URL).
 *   3. 搜索其他品牌 — text input wired to /v1/brands/search; lets the
 *      user pick any brand across industries (the user's "我需要从不同的
 *      行业里选品牌" requirement). Click → navigate to /brand/overview?
 *      brandId=X. If the brand is already a project's primary brand, we
 *      switch the active project instead.
 *
 * Pure popover — no portal/Radix dependency, click-outside closes via a
 * mousedown listener (mirrors AdminFilterPopover style elsewhere in the
 * SPA).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProject } from '../../contexts/ProjectContext';
import { useLocale } from '../../contexts/LocaleContext';
import { brandsApi, type BrandSearchHit } from '../../api/brands';
import { BRANDS } from '../../data/mock';

interface BrandPickerProps {
  ariaLabel?: string;
  onAfterSelect?: () => void;
}

interface ProjectOption {
  projectId: string;
  brandId: string | null;
  brandName: string;
  isActive: boolean;
}

interface CompetitorOption {
  brandId: string;
  brandName: string;
}

function BrandAvatar({ name }: { name: string }) {
  const initial = (name || 'B').slice(0, 1).toUpperCase();
  return (
    <div
      className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0"
      style={{ background: 'var(--color-accent, #635bff)' }}
    >
      {initial}
    </div>
  );
}

const ICON_CHEVRON = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M3.5 5L7 8.5L10.5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ICON_CHECK = (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M2.5 6.5L5 9L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ICON_SEARCH = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.4" />
    <path d="M9.5 9.5L12 12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

export default function BrandPicker({ ariaLabel, onAfterSelect }: BrandPickerProps) {
  const navigate = useNavigate();
  const { projects, activeProject, setActiveProjectId } = useProject();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<BrandSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  /* ── Project list (each project = one primary brand) ───────────── */
  const projectOptions: ProjectOption[] = useMemo(
    () =>
      (projects || []).map((p) => {
        const brandId = p.primaryBrandId ?? null;
        const mockBrand = brandId ? BRANDS.find((b) => String(b.id) === String(brandId)) : null;
        const brandName =
          (p as { primaryBrandName?: string }).primaryBrandName ||
          mockBrand?.nameZh ||
          mockBrand?.name ||
          p.name;
        return {
          projectId: p.id,
          brandId: brandId != null ? String(brandId) : null,
          brandName,
          isActive: !!activeProject && activeProject.id === p.id,
        };
      }),
    [projects, activeProject],
  );

  /* ── Competitors of the active project ────────────────────────── */
  const competitorOptions: CompetitorOption[] = useMemo(() => {
    const ids = (activeProject?.competitorBrandIds || []) as string[];
    return ids
      .map((id) => {
        const b = BRANDS.find((x) => String(x.id) === String(id));
        return b
          ? { brandId: String(b.id), brandName: b.nameZh || b.name }
          : null;
      })
      .filter((x): x is CompetitorOption => x !== null);
  }, [activeProject]);

  /* ── Click-outside + Esc ──────────────────────────────────────── */
  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  /* ── Debounced brand search ───────────────────────────────────── */
  useEffect(() => {
    if (!open) return;
    const q = search.trim();
    if (q.length < 2) {
      setSearchResults(null);
      setSearchError(null);
      return;
    }
    let cancelled = false;
    setSearching(true);
    setSearchError(null);
    const handle = setTimeout(() => {
      brandsApi
        .search(q, 8)
        .then((res) => {
          if (cancelled) return;
          setSearchResults(res.items || []);
        })
        .catch((err) => {
          if (cancelled) return;
          setSearchError(err?.message || '搜索失败');
          setSearchResults([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [search, open]);

  const close = () => {
    setOpen(false);
    setSearch('');
    setSearchResults(null);
    onAfterSelect?.();
  };

  const handlePickProject = (projectId: string) => {
    setActiveProjectId(projectId);
    close();
  };

  const handlePickBrandId = (brandId: string | number) => {
    /* If the picked brand is already a project's primary brand, switch
       active project. Otherwise route to /brand/overview?brandId=X so
       DashboardPage applies the brand override. */
    const matchedProject = projectOptions.find(
      (p) => p.brandId != null && String(p.brandId) === String(brandId),
    );
    if (matchedProject) {
      setActiveProjectId(matchedProject.projectId);
    } else {
      navigate(`/brand/overview?brandId=${encodeURIComponent(String(brandId))}`);
    }
    close();
  };

  const triggerLabel =
    activeProject?.primaryBrandName ||
    activeProject?.name ||
    projectOptions[0]?.brandName ||
    '选择品牌';

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        className="w-full flex items-center justify-between h-10 pl-2 pr-3 rounded-pill bg-themed-subtle hover:border-themed-strong transition-colors"
        style={{
          background: 'var(--color-bg-subtle-2)',
          border: '0.5px solid var(--color-accent-alpha-27)',
        }}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <BrandAvatar name={triggerLabel} />
          <span className="text-sm font-brand font-semibold text-themed-primary truncate">
            {triggerLabel}
          </span>
        </div>
        <span className="text-themed-muted shrink-0">{ICON_CHEVRON}</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="切换品牌"
          /* Anchored to the trigger button (left:0) but stretches RIGHT
             past the sidebar so brand names + section labels don't get
             clipped by the narrow sidebar column. ~360px is wide enough
             for full-width Chinese brand names + industry hint. */
          className="absolute left-0 mt-2 z-50 rounded-lg border border-themed-card shadow-lg overflow-hidden"
          style={{
            background: 'var(--color-surface, #fff)',
            width: 360,
            maxWidth: 'calc(100vw - 32px)',
            maxHeight: '70vh',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Search */}
          <div className="px-3 py-2.5 border-b border-themed-card">
            <div className="flex items-center gap-2 px-2.5 h-9 rounded-md bg-themed-subtle text-themed-muted">
              <span className="shrink-0">{ICON_SEARCH}</span>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索品牌（任意行业）"
                className="bg-transparent flex-1 text-sm text-themed-primary outline-none"
                autoFocus
              />
            </div>
          </div>

          <div className="overflow-y-auto" style={{ maxHeight: 'calc(70vh - 60px)' }}>
            {/* Search results — only visible while searching. We surface
                error and "no match" exclusively, never both, so the
                502/empty-result case isn't visually noisy. */}
            {search.trim().length >= 2 && (
              <Section label="搜索结果">
                {searching && (
                  <div className="px-4 py-2 text-xs text-themed-muted">搜索中…</div>
                )}
                {!searching && searchError && (
                  <div className="px-4 py-2 text-xs text-themed-danger">
                    {searchError === 'Bad Gateway'
                      ? '后台暂时不可用，请稍后重试'
                      : searchError}
                  </div>
                )}
                {!searching && !searchError && searchResults && searchResults.length === 0 && (
                  <div className="px-4 py-2 text-xs text-themed-muted leading-relaxed">
                    没有找到匹配的品牌。请检查拼写（例如 雅<b>诗</b>兰黛 而不是 雅<b>思</b>兰黛），或<button
                      type="button"
                      className="text-themed-accent underline"
                      onClick={() => {
                        navigate('/onboarding');
                        close();
                      }}
                    >前往「添加品牌」</button>
                  </div>
                )}
                {!searching && !searchError && searchResults?.map((hit) => (
                  <Row
                    key={hit.brandId}
                    name={hit.brandName}
                    hint={hit.industry || ''}
                    onClick={() => handlePickBrandId(hit.brandId)}
                  />
                ))}
              </Section>
            )}

            {/* My projects */}
            {search.trim().length < 2 && projectOptions.length > 0 && (
              <Section label="我的项目">
                {projectOptions.map((p) => (
                  <Row
                    key={p.projectId}
                    name={p.brandName}
                    hint={p.brandName !== triggerLabel ? '切换至此项目' : '当前项目'}
                    active={p.isActive}
                    onClick={() => handlePickProject(p.projectId)}
                  />
                ))}
              </Section>
            )}

            {/* Competitors */}
            {search.trim().length < 2 && competitorOptions.length > 0 && (
              <Section label="当前项目竞品">
                {competitorOptions.map((c) => (
                  <Row
                    key={c.brandId}
                    name={c.brandName}
                    hint="查看该品牌"
                    onClick={() => handlePickBrandId(c.brandId)}
                  />
                ))}
              </Section>
            )}

            {/* Onboarding hint */}
            {search.trim().length < 2 && projectOptions.length === 0 && (
              <div className="px-4 py-6 text-center text-xs text-themed-muted">
                还没有项目。<button
                  type="button"
                  className="text-themed-accent underline"
                  onClick={() => {
                    navigate('/onboarding');
                    close();
                  }}
                >前往设置</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-1.5">
      <div className="px-4 py-1 text-[10px] uppercase tracking-wider text-themed-muted">
        {label}
      </div>
      <div className="flex flex-col">{children}</div>
    </div>
  );
}

function Row({
  name,
  hint,
  active,
  onClick,
}: {
  name: string;
  hint?: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center justify-between gap-3 w-full px-4 py-2 text-left transition-colors ${
        active
          ? 'text-themed-accent font-medium'
          : 'text-themed-primary hover:bg-themed-subtle'
      }`}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <BrandAvatar name={name} />
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{name}</div>
          {hint && (
            <div className="text-[11px] text-themed-muted truncate">{hint}</div>
          )}
        </div>
      </div>
      {active && (
        <span className="text-themed-accent shrink-0">{ICON_CHECK}</span>
      )}
    </button>
  );
}
