/*
 * ProjectContext — PRD §4.1.2 / §4.1.2a
 * ─────────────────────────────────────────────────
 * Holds the active Project + auth state + WatchBrand operations.
 *
 * In production this becomes a thin SWR/React Query hook around
 *   GET    /api/v1/projects
 *   POST   /api/v1/projects/:id/competitors
 *   DELETE /api/v1/projects/:id/competitors/:brandId
 * For the prototype, mutations rewrite the in-memory PROJECTS array
 * (mock.js) and broadcast via React state — wired so optimistic
 * updates / rollback / 30s debounce / 10-cap can be exercised.
 *
 * ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
 *   This module is shared infra for header buttons and Brand Detail
 *   3-state. It must not produce user-facing copy by itself; it only
 *   exposes structured state. UI strings live in messages.js
 *   (`brand_watch.*`, `formatBrand` / `formatProject`).
 */
import React, {
  createContext, useCallback, useContext, useMemo, useRef, useState,
} from 'react';
import { PROJECTS as SEED_PROJECTS, BRANDS, INDUSTRIES } from '../data/mock';
import { useLocale } from './LocaleContext';

const COMPETITOR_CAP = 10;
const DEBOUNCE_MS = 30 * 1000;

const ProjectContext = createContext({
  projects: [],
  activeProject: null,
  isAuthenticated: true,
  setActiveProjectId: () => {},
  setIsAuthenticated: () => {},
  addCompetitor: async () => ({ ok: false }),
  removeCompetitor: async () => ({ ok: false }),
  getWatchState: () => ({ kind: 'unknown' }),
  toasts: [],
  pushToast: () => {},
  dismissToast: () => {},
});

export function ProjectProvider({ children, initialAuthenticated = true }) {
  // Deep-clone projects so mutations don't leak back into mock module.
  const [projects, setProjects] = useState(() =>
    SEED_PROJECTS.map((p) => ({ ...p, competitorBrandIds: [...p.competitorBrandIds] }))
  );
  const [activeProjectId, setActiveProjectId] = useState(() => SEED_PROJECTS[0]?.id);
  const [isAuthenticated, setIsAuthenticated] = useState(initialAuthenticated);
  const [toasts, setToasts] = useState([]);
  const debounceMapRef = useRef(new Map()); // key = `${projectId}::${brandId}` → timestamp

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) || projects[0] || null,
    [projects, activeProjectId]
  );

  /* ── Toast plumbing — minimal stand-in, real impl can use Sonner. ── */
  const pushToast = useCallback((toast) => {
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((prev) => [...prev, { id, ...toast }]);
    if (toast.duration !== Infinity) {
      const dur = toast.duration ?? 4000;
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, dur);
    }
  }, []);
  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  /* ── Debounce check — same (project, brand) tuple within 30s blocked. ── */
  const isDebounced = useCallback((projectId, brandId) => {
    const key = `${projectId}::${brandId}`;
    const last = debounceMapRef.current.get(key);
    if (!last) return false;
    return Date.now() - last < DEBOUNCE_MS;
  }, []);
  const stampDebounce = useCallback((projectId, brandId) => {
    debounceMapRef.current.set(`${projectId}::${brandId}`, Date.now());
  }, []);

  /* ── Mutations ───────────────────────────────────────────
     PRD §4.1.2a — optimistic update with rollback on simulated failure.
     For the mock, the "API call" is a microtask that resolves true.
  */
  const addCompetitor = useCallback(
    async (projectId, brandId) => {
      const target = projects.find((p) => p.id === projectId);
      if (!target) return { ok: false, reason: 'project_not_found' };
      if (target.competitorBrandIds.length >= COMPETITOR_CAP) {
        return { ok: false, reason: 'capacity_full' };
      }
      if (target.competitorBrandIds.includes(brandId)) {
        return { ok: true, reason: 'noop' };
      }
      if (target.primaryBrandId === brandId) {
        return { ok: false, reason: 'is_primary' };
      }
      if (isDebounced(projectId, brandId)) {
        return { ok: false, reason: 'debounced' };
      }
      stampDebounce(projectId, brandId);

      // Optimistic add
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId
            ? { ...p, competitorBrandIds: [...p.competitorBrandIds, brandId] }
            : p
        )
      );

      try {
        // Simulated API — always succeeds in mock; real impl does
        //   await fetch(`/api/v1/projects/${projectId}/competitors`, {...})
        await Promise.resolve();
        return { ok: true };
      } catch (err) {
        // Rollback
        setProjects((prev) =>
          prev.map((p) =>
            p.id === projectId
              ? { ...p, competitorBrandIds: p.competitorBrandIds.filter((b) => b !== brandId) }
              : p
          )
        );
        return { ok: false, reason: 'api_error' };
      }
    },
    [projects, isDebounced, stampDebounce]
  );

  const removeCompetitor = useCallback(
    async (projectId, brandId) => {
      const target = projects.find((p) => p.id === projectId);
      if (!target) return { ok: false, reason: 'project_not_found' };
      if (!target.competitorBrandIds.includes(brandId)) {
        return { ok: true, reason: 'noop' };
      }
      if (isDebounced(projectId, brandId)) {
        return { ok: false, reason: 'debounced' };
      }
      stampDebounce(projectId, brandId);

      // Optimistic remove
      const previous = target.competitorBrandIds.slice();
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId
            ? { ...p, competitorBrandIds: p.competitorBrandIds.filter((b) => b !== brandId) }
            : p
        )
      );

      try {
        await Promise.resolve();
        return { ok: true };
      } catch (err) {
        // Rollback
        setProjects((prev) =>
          prev.map((p) =>
            p.id === projectId
              ? { ...p, competitorBrandIds: previous }
              : p
          )
        );
        return { ok: false, reason: 'api_error' };
      }
    },
    [projects, isDebounced, stampDebounce]
  );

  /* ── Watch state classifier — drives WatchBrandButton + Brand Detail banner.
     Returns one of:
       - { kind: 'anonymous' }                          → button #6
       - { kind: 'no_project' }                         → button #5
       - { kind: 'primary', project }                   → button #1
       - { kind: 'watching', project }                  → button #2
       - { kind: 'not_watching_same_industry', project }→ button #3
       - { kind: 'not_watching_cross_industry', project, brandIndustry, projectIndustry } → button #4
       - { kind: 'capacity_full', project }             → button #3 disabled
  */
  const getWatchState = useCallback(
    (brandOrId) => {
      if (!brandOrId) return { kind: 'unknown' };
      const brand = typeof brandOrId === 'string'
        ? BRANDS.find((b) => b.id === brandOrId)
        : brandOrId;
      if (!brand) return { kind: 'unknown' };

      if (!isAuthenticated) return { kind: 'anonymous', brand };
      if (!activeProject) return { kind: 'no_project', brand };

      if (activeProject.primaryBrandId === brand.id) {
        return { kind: 'primary', project: activeProject, brand };
      }
      if (activeProject.competitorBrandIds.includes(brand.id)) {
        return { kind: 'watching', project: activeProject, brand };
      }

      const projectIndustry = INDUSTRIES.find((i) => i.id === activeProject.industryId);
      const brandIndustry = INDUSTRIES.find((i) => i.id === brand.industryId);
      const sameIndustry =
        brand.industryId === activeProject.industryId || !brand.industryId;

      const atCap = activeProject.competitorBrandIds.length >= COMPETITOR_CAP;
      if (atCap) {
        return { kind: 'capacity_full', project: activeProject, brand, projectIndustry, brandIndustry };
      }

      if (sameIndustry) {
        return {
          kind: 'not_watching_same_industry',
          project: activeProject,
          brand,
          projectIndustry,
          brandIndustry,
        };
      }
      return {
        kind: 'not_watching_cross_industry',
        project: activeProject,
        brand,
        projectIndustry,
        brandIndustry,
      };
    },
    [activeProject, isAuthenticated]
  );

  const value = useMemo(
    () => ({
      projects,
      activeProject,
      isAuthenticated,
      setActiveProjectId,
      setIsAuthenticated,
      addCompetitor,
      removeCompetitor,
      getWatchState,
      toasts,
      pushToast,
      dismissToast,
      COMPETITOR_CAP,
    }),
    [
      projects, activeProject, isAuthenticated,
      addCompetitor, removeCompetitor, getWatchState,
      toasts, pushToast, dismissToast,
    ]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  return useContext(ProjectContext);
}

/**
 * Locale-aware project label resolver — single entry point per PRD §4.10.4a.B.
 * Used by the brand_watch namespace to fill {project} placeholder.
 */
export function useFormatProject() {
  const { locale } = useLocale();
  return useCallback(
    (project) => {
      if (!project) return '';
      // mock projects have only `name` (Chinese), no localized fields yet.
      // When we migrate to real Project model with nameZh/nameEn this becomes
      // analogous to formatBrand. For now: return the only available label.
      return project.nameEn && locale === 'en-US'
        ? project.nameEn
        : project.name || project.id;
    },
    [locale]
  );
}
