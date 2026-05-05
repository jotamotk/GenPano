/*
 * WatchBrandButton — PRD §4.1.2a
 * ─────────────────────────────────────────────────
 * 一键加入竞品监控按钮 — 6 状态机, 复用于:
 *   - BrandDetailPage 顶栏
 *   - DashboardPage 卡片菜单 (后续)
 *   - 行业探索 List/Graph 视图 (后续, 当前 PRD 选择直达 Brand Detail)
 *
 * 状态映射 (来自 useProject().getWatchState(brand)):
 *   #1 primary                       → 只读金色徽章 "主品牌 · {project}"
 *   #2 watching                      → 灰底徽章 "已在监控 · {project}", 悬浮出"移除"菜单
 *   #3 not_watching_same_industry    → 主 CTA "加入竞品监控"
 *   #4 not_watching_cross_industry   → 双选 dropdown CTA
 *   #5 no_project                    → CTA "创建项目监控此品牌" → /onboarding?monitor_brand=:id
 *   #6 anonymous                     → CTA "免费注册监控此品牌" → /auth?mode=register&monitor_brand=:id&return_to=...
 *   capacity_full (state #3 变体)    → 主 CTA disabled + tooltip
 *
 * 行为:
 *   - 乐观更新由 ProjectContext.addCompetitor / removeCompetitor 实现
 *   - 30s debounce 同一 (project, brand) 由 Context 拦截, 失败时弹 toast
 *   - capacity_full 时按钮 disabled, 鼠标悬停 tooltip 提示
 *
 * ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
 *   组件本身不写任何"本页只做 / 详情请进入" 这类解释文案,
 *   所有外露 string 必须走 t('brand_watch.*'), 占位符走 formatBrand / formatProject.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject, useFormatProject } from '../../contexts/ProjectContext';

/* ─────────────────────────────────────────────────
   Generic shapes (color-only, depend on var(--color-*))
─────────────────────────────────────────────────── */
const SHAPE_CLASS = {
  // primary CTA pill — accent fill
  primaryCta:
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-sm font-medium ' +
    'transition-colors hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed',
  // secondary outline pill — used for badges (#1 #2)
  badge:
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-sm font-medium ' +
    'transition-colors',
  // outline CTA — used for #5 / #6 (lower visual weight than #3)
  outlineCta:
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-sm font-medium ' +
    'transition-colors hover:bg-themed-subtle',
};

/* Tiny carat / chevron icon (avoid a new dep) */
function CaratIcon({ open }) {
  return (
    <svg
      className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function CrownIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 4l3 5 5-3-2 9H6L4 6l5 3 3-5z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/* ─────────────────────────────────────────────────
   Small confirmation modal (state #2 → 移除确认)
   Lightweight — avoids pulling in Radix Dialog yet.
─────────────────────────────────────────────────── */
function ConfirmModal({ open, title, body, confirmLabel, cancelLabel, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.32)' }}
      onClick={onCancel}
    >
      <div
        className="rounded-card p-5 max-w-sm w-full mx-4"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
          boxShadow: 'var(--shadow-card-hover)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-themed-primary mb-2">{title}</h3>
        <p className="text-xs text-themed-secondary leading-relaxed mb-4">{body}</p>
        <div className="flex justify-end gap-2">
          <button
            className="px-3 py-1.5 rounded-pill text-sm font-medium text-themed-primary hover:bg-themed-subtle transition-colors"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            className="px-3 py-1.5 rounded-pill text-sm font-medium text-white transition-colors hover:opacity-90"
            style={{ background: 'var(--color-danger, #dc2626)' }}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────
   Reusable inline dropdown menu (states #2 / #4)
─────────────────────────────────────────────────── */
function InlineMenu({ open, anchorRef, onClose, children }) {
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (anchorRef.current && !anchorRef.current.contains(e.target)) {
        onClose?.();
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, anchorRef, onClose]);
  if (!open) return null;
  return (
    <div
      className="absolute right-0 top-full mt-1 min-w-[220px] z-30 rounded-card overflow-hidden"
      style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border-subtle)',
        boxShadow: 'var(--shadow-card-hover)',
      }}
    >
      {children}
    </div>
  );
}

function MenuItem({ onClick, children, danger = false }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-themed-subtle ${
        danger ? 'text-themed-primary' : 'text-themed-primary'
      }`}
      style={danger ? { color: 'var(--color-danger, #dc2626)' } : undefined}
    >
      {children}
    </button>
  );
}

/* ─────────────────────────────────────────────────
   Main component
─────────────────────────────────────────────────── */
export default function WatchBrandButton({
  brand,
  /* Optional: caller can choose to render the cross-industry warning
     line under the button. Default true on Brand Detail, false on
     dense list cards. */
  showCrossIndustryHint = true,
  /* Optional className for outer wrapper */
  className = '',
}) {
  const { t, formatBrand } = useLocale();
  const formatProject = useFormatProject();
  const {
    getWatchState,
    addCompetitor,
    removeCompetitor,
    pushToast,
    activeProject,
    COMPETITOR_CAP,
  } = useProject();

  const navigate = useNavigate();
  const location = useLocation();

  const wrapperRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const state = useMemo(() => getWatchState(brand), [getWatchState, brand]);

  /* Derive display strings */
  const projectName = state.project ? formatProject(state.project) : '';
  const brandName = brand ? formatBrand(brand) : '';

  /* ─── Action handlers ─── */

  const handleAddSameIndustry = useCallback(async () => {
    if (!activeProject || !brand) return;
    setBusy(true);
    const res = await addCompetitor(activeProject.id, brand.id);
    setBusy(false);
    if (res.ok) {
      pushToast({
        kind: 'success',
        message: t('brand_watch.toast.added', { project: projectName }),
      });
    } else if (res.reason === 'capacity_full') {
      pushToast({
        kind: 'error',
        message: t('brand_watch.button.capacity_full_tooltip'),
      });
    } else if (res.reason === 'debounced') {
      pushToast({
        kind: 'error',
        message: t('brand_watch.button.debounce_tooltip'),
      });
    } else {
      pushToast({
        kind: 'error',
        message: t('brand_watch.toast.add_failed'),
      });
    }
  }, [activeProject, brand, addCompetitor, pushToast, t, projectName]);

  const handleAddCrossIndustryCurrent = useCallback(async () => {
    setMenuOpen(false);
    if (!activeProject || !brand) return;
    setBusy(true);
    const res = await addCompetitor(activeProject.id, brand.id);
    setBusy(false);
    if (res.ok) {
      pushToast({
        kind: 'success',
        message: t('brand_watch.toast.added_crossindustry', { project: projectName }),
      });
    } else {
      pushToast({
        kind: 'error',
        message:
          res.reason === 'capacity_full'
            ? t('brand_watch.button.capacity_full_tooltip')
            : res.reason === 'debounced'
            ? t('brand_watch.button.debounce_tooltip')
            : t('brand_watch.toast.add_failed'),
      });
    }
  }, [activeProject, brand, addCompetitor, pushToast, t, projectName]);

  const handleCreateNewProjectForBrand = useCallback(() => {
    setMenuOpen(false);
    if (!brand) return;
    // entry_source=brand_detail_cta — one of the 6 enums PRD §4.1.1d
    // Preserved through onboarding → /projects/new so funnel attribution stays intact.
    navigate(
      `/onboarding?monitor_brand=${encodeURIComponent(brand.id)}&entry_source=brand_detail_cta`,
    );
  }, [brand, navigate]);

  const handleConfirmRemove = useCallback(async () => {
    setConfirmOpen(false);
    setMenuOpen(false);
    if (!activeProject || !brand) return;
    setBusy(true);
    const res = await removeCompetitor(activeProject.id, brand.id);
    setBusy(false);
    if (res.ok) {
      pushToast({
        kind: 'success',
        message: t('brand_watch.toast.removed', {
          project: projectName,
          brand: brandName,
        }),
      });
    } else {
      pushToast({
        kind: 'error',
        message:
          res.reason === 'debounced'
            ? t('brand_watch.button.debounce_tooltip')
            : t('brand_watch.toast.remove_failed'),
      });
    }
  }, [activeProject, brand, removeCompetitor, pushToast, t, projectName, brandName]);

  const handleRegisterCta = useCallback(() => {
    if (!brand) return;
    const returnTo = `${location.pathname}${location.search || ''}`;
    const qs = new URLSearchParams();
    qs.set('monitor_brand', brand.id);
    qs.set('return_to', returnTo);
    navigate(`/register?${qs.toString()}`);
  }, [brand, location, navigate]);

  const handleCreateProjectCta = useCallback(() => {
    if (!brand) return;
    // entry_source=brand_detail_cta — carries through onboarding to /projects/new.
    navigate(
      `/onboarding?monitor_brand=${encodeURIComponent(brand.id)}&entry_source=brand_detail_cta`,
    );
  }, [brand, navigate]);

  /* ─── Render by state.kind ─── */

  if (!brand || state.kind === 'unknown') return null;

  /* #1 — primary brand */
  if (state.kind === 'primary') {
    return (
      <span
        className={`${SHAPE_CLASS.badge} ${className}`}
        style={{
          background: 'var(--color-accent-subtle)',
          color: 'var(--color-accent)',
          border: '1px solid var(--color-accent-soft, var(--color-accent))',
        }}
        title={t('brand_watch.button.primary_badge', { project: projectName })}
      >
        <CrownIcon />
        <span>{t('brand_watch.button.primary_badge', { project: projectName })}</span>
      </span>
    );
  }

  /* #2 — already watching, hover dropdown for remove */
  if (state.kind === 'watching') {
    return (
      <div ref={wrapperRef} className={`relative inline-flex ${className}`}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className={SHAPE_CLASS.badge}
          style={{
            background: 'var(--color-bg-subtle-2)',
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-border-subtle)',
          }}
        >
          <CheckIcon />
          <span>{t('brand_watch.button.watching_badge', { project: projectName })}</span>
          <CaratIcon open={menuOpen} />
        </button>
        <InlineMenu open={menuOpen} anchorRef={wrapperRef} onClose={() => setMenuOpen(false)}>
          <MenuItem
            danger
            onClick={() => {
              setMenuOpen(false);
              setConfirmOpen(true);
            }}
          >
            {t('brand_watch.dropdown.watching_remove')}
          </MenuItem>
        </InlineMenu>
        <ConfirmModal
          open={confirmOpen}
          title={t('brand_watch.confirm.remove_title', { brand: brandName })}
          body={t('brand_watch.confirm.remove_body', {
            project: projectName,
            brand: brandName,
          })}
          confirmLabel={t('brand_watch.confirm.remove_confirm')}
          cancelLabel={t('brand_watch.confirm.remove_cancel')}
          onConfirm={handleConfirmRemove}
          onCancel={() => setConfirmOpen(false)}
        />
      </div>
    );
  }

  /* capacity_full — visually like #3 but disabled with tooltip */
  if (state.kind === 'capacity_full') {
    return (
      <div className={`relative inline-flex ${className}`}>
        <button
          disabled
          className={SHAPE_CLASS.primaryCta}
          style={{
            background: 'var(--color-bg-subtle-2)',
            color: 'var(--color-text-muted)',
            border: '1px solid var(--color-border-subtle)',
          }}
          title={t('brand_watch.button.capacity_full_tooltip')}
        >
          <PlusIcon />
          <span>{t('brand_watch.button.watch_cta')}</span>
        </button>
        {showCrossIndustryHint && (
          <span
            className="ml-2 self-center text-[11px] text-themed-muted"
            title={t('brand_watch.button.capacity_full_tooltip')}
          >
            {COMPETITOR_CAP}/{COMPETITOR_CAP}
          </span>
        )}
      </div>
    );
  }

  /* #3 — same-industry, single CTA */
  if (state.kind === 'not_watching_same_industry') {
    return (
      <button
        onClick={handleAddSameIndustry}
        disabled={busy}
        className={`${SHAPE_CLASS.primaryCta} ${className}`}
        style={{
          background: 'var(--color-accent)',
          color: 'var(--color-on-accent, #ffffff)',
        }}
      >
        <PlusIcon />
        <span>
          {busy ? t('brand_watch.button.loading') : t('brand_watch.button.watch_cta')}
        </span>
      </button>
    );
  }

  /* #4 — cross-industry, dropdown with two options */
  if (state.kind === 'not_watching_cross_industry') {
    const projectIndustryName =
      state.projectIndustry?.name ||
      state.projectIndustry?.nameZh ||
      state.projectIndustry?.nameEn ||
      '';
    const targetIndustryName =
      state.brandIndustry?.name ||
      state.brandIndustry?.nameZh ||
      state.brandIndustry?.nameEn ||
      '';

    return (
      <div ref={wrapperRef} className={`relative inline-flex flex-col ${className}`}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          disabled={busy}
          className={SHAPE_CLASS.primaryCta}
          style={{
            background: 'var(--color-accent)',
            color: 'var(--color-on-accent, #ffffff)',
          }}
        >
          <PlusIcon />
          <span>
            {busy ? t('brand_watch.button.loading') : t('brand_watch.button.watch_cta_dropdown')}
          </span>
          <CaratIcon open={menuOpen} />
        </button>
        <InlineMenu open={menuOpen} anchorRef={wrapperRef} onClose={() => setMenuOpen(false)}>
          <MenuItem onClick={handleAddCrossIndustryCurrent}>
            {t('brand_watch.dropdown.crossindustry_add_to_current')}
          </MenuItem>
          <MenuItem onClick={handleCreateNewProjectForBrand}>
            {t('brand_watch.dropdown.crossindustry_create_new')}
          </MenuItem>
        </InlineMenu>
        {showCrossIndustryHint && (
          <span className="mt-1 text-[11px] text-themed-muted leading-snug max-w-xs">
            {t('brand_watch.crossindustry.warning_inline', {
              brand: brandName,
              targetIndustry: targetIndustryName,
              projectIndustry: projectIndustryName,
            })}
          </span>
        )}
      </div>
    );
  }

  /* #5 — logged-in but no project */
  if (state.kind === 'no_project') {
    return (
      <button
        onClick={handleCreateProjectCta}
        className={`${SHAPE_CLASS.outlineCta} ${className}`}
        style={{
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border-subtle)',
          background: 'var(--color-bg-card)',
        }}
      >
        <PlusIcon />
        <span>{t('brand_watch.button.create_project_cta')}</span>
      </button>
    );
  }

  /* #6 — anonymous */
  if (state.kind === 'anonymous') {
    return (
      <button
        onClick={handleRegisterCta}
        className={`${SHAPE_CLASS.primaryCta} ${className}`}
        style={{
          background: 'var(--color-accent)',
          color: 'var(--color-on-accent, #ffffff)',
        }}
      >
        <PlusIcon />
        <span>{t('brand_watch.button.register_cta')}</span>
      </button>
    );
  }

  return null;
}
