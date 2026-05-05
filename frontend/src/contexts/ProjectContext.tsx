/*
 * ProjectContext — PRD §4.1.2 / §4.1.2a
 * ─────────────────────────────────────────────────
 * Holds the active Project + auth state + WatchBrand operations.
 *
 * Hybrid mode (post-Phase-FE切mock):
 *   - useProjects() pulls /v1/projects/ on mount.
 *   - When backend returns >= 1 project, those become the source of
 *     truth (transformed to the legacy mock shape so all 20+ existing
 *     consumers keep working without rewrites).
 *   - When backend returns empty / errors, the static SEED_PROJECTS
 *     (mock.js) is used — useful for unauthenticated visitors and
 *     dev-without-backend.
 *   - Mutations: in live mode, call POST/DELETE /v1/projects/.../competitors
 *     + invalidate the React Query cache. In mock mode, optimistic
 *     in-memory update with rollback (legacy behaviour).
 *
 * ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
 *   This module is shared infra for header buttons and Brand Detail
 *   3-state. It must not produce user-facing copy by itself; it only
 *   exposes structured state. UI strings live in messages.js
 *   (`brand_watch.*`, `formatBrand` / `formatProject`).
 */
import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PROJECTS as SEED_PROJECTS, BRANDS, INDUSTRIES } from '../data/mock';
import { useLocale } from './LocaleContext';
import { useProjects, PROJECTS_QUERY_KEY, type ProjectOut } from '../hooks/useProjects';
import { projectsApi } from '../api/projects';

/** Convert backend ProjectOut to the legacy mock shape (str ids, camelCase). */
function toMockShape(p: ProjectOut): {
  id: string;
  name: string;
  industryId: string | null;
  primaryBrandId: string | null;
  competitorBrandIds: string[];
} {
  return {
    id: p.id,
    name: p.name,
    industryId: p.industry_id != null ? String(p.industry_id) : null,
    primaryBrandId: p.primary_brand_id != null ? String(p.primary_brand_id) : null,
    competitorBrandIds: (p.competitors ?? []).map((c) => String(c.brand_id)),
  };
}

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
  const qc = useQueryClient();
  // Live backend projects (null when the user is not authenticated /
  // backend is offline / no projects exist). When >= 1 project lands,
  // we treat live mode as authoritative.
  const { data: liveProjectsRaw } = useProjects();
  const liveProjects = useMemo(
    () => (liveProjectsRaw ?? []).map(toMockShape),
    [liveProjectsRaw],
  );
  const isLiveMode = liveProjects.length > 0;

  // Local state — used as the source of truth in mock mode, and as a
  // mutable mirror of live data so optimistic updates render
  // immediately (we still call the backend behind the scenes).
  const [mockProjects, setMockProjects] = useState(() =>
    SEED_PROJECTS.map((p) => ({ ...p, competitorBrandIds: [...p.competitorBrandIds] }))
  );
  // When live mode flips on (or live projects update), sync mockProjects
  // to the latest live snapshot so consumers always see fresh state
  // without reading liveProjects directly.
  useEffect(() => {
    if (isLiveMode) {
      setMockProjects(liveProjects.map((p) => ({ ...p, competitorBrandIds: [...p.competitorBrandIds] })));
    }
  }, [isLiveMode, liveProjects]);
  const projects = mockProjects;

  const [activeProjectId, setActiveProjectIdState] = useState(() => SEED_PROJECTS[0]?.id);
  // When live data loads, jump to first live project if no active set.
  useEffect(() => {
    if (isLiveMode && liveProjects.length > 0) {
      const stillExists = liveProjects.some((p) => p.id === activeProjectId);
      if (!stillExists) {
        setActiveProjectIdState(liveProjects[0].id);
      }
    }
  }, [isLiveMode, liveProjects, activeProjectId]);
  const setActiveProjectId = setActiveProjectIdState;

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
      setMockProjects((prev) =>
        prev.map((p) =>
          p.id === projectId
            ? { ...p, competitorBrandIds: [...p.competitorBrandIds, brandId] }
            : p
        )
      );

      try {
        if (isLiveMode) {
          // Live mode — brand IDs are int strings ("101"); convert back
          // to int for the backend POST. Mock IDs ('estee-lauder') won't
          // pass Number() validation, but in live mode every brandId
          // came from a live project so should be numeric.
          const brandIdInt = Number(brandId);
          if (!Number.isFinite(brandIdInt)) {
            throw new Error('non-numeric brandId in live mode');
          }
          await projectsApi.addCompetitor(projectId, brandIdInt);
          qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
        } else {
          // Mock mode — local state is the source of truth; nothing
          // to call. Microtask resolution preserves the original
          // optimistic-success contract from the mock prototype.
          await Promise.resolve();
        }
        return { ok: true };
      } catch (err) {
        // Rollback optimistic local state
        setMockProjects((prev) =>
          prev.map((p) =>
            p.id === projectId
              ? { ...p, competitorBrandIds: p.competitorBrandIds.filter((b) => b !== brandId) }
              : p
          )
        );
        return { ok: false, reason: 'api_error' };
      }
    },
    [projects, isDebounced, stampDebounce, isLiveMode, qc]
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
      setMockProjects((prev) =>
        prev.map((p) =>
          p.id === projectId
            ? { ...p, competitorBrandIds: p.competitorBrandIds.filter((b) => b !== brandId) }
            : p
        )
      );

      try {
        if (isLiveMode) {
          const brandIdInt = Number(brandId);
          if (!Number.isFinite(brandIdInt)) {
            throw new Error('non-numeric brandId in live mode');
          }
          await projectsApi.removeCompetitor(projectId, brandIdInt);
          qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
        } else {
          await Promise.resolve();
        }
        return { ok: true };
      } catch (err) {
        // Rollback to previous state
        setMockProjects((prev) =>
          prev.map((p) =>
            p.id === projectId
              ? { ...p, competitorBrandIds: previous }
              : p
          )
        );
        return { ok: false, reason: 'api_error' };
      }
    },
    [projects, isDebounced, stampDebounce, isLiveMode, qc]
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
