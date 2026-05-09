import React from 'react'

/**
 * MockDataBadge — small chip rendered alongside a chart card title when the
 * chart is rendering mock fallback data instead of live backend data.
 *
 * Usage:
 *   <h3>Mention Rate {isMock && <MockDataBadge />}</h3>
 *
 * Variants:
 *   - default: amber pill (warning tone) — most charts
 *   - subtle:  thin outline — for dense card grids
 */

export interface MockDataBadgeProps {
  /** Optional reason to show in tooltip / aside (e.g. "no project") */
  reason?: string
  variant?: 'default' | 'subtle'
  className?: string
}

export default function MockDataBadge({
  reason,
  variant = 'default',
  className = '',
}: MockDataBadgeProps) {
  const base =
    'inline-flex items-center gap-1 rounded text-[10px] font-semibold uppercase tracking-wider align-middle'
  const styles =
    variant === 'subtle'
      ? 'px-1.5 py-0.5 border border-themed-card text-themed-muted'
      : 'px-1.5 py-0.5 bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300'
  const label = 'Mock'
  const title = reason
    ? `演示数据 (${reason}) — 接入 live 项目后自动切换`
    : '演示数据 — 接入 live 项目后自动切换'
  return (
    <span className={`${base} ${styles} ${className}`} title={title} aria-label={title}>
      <span className="w-1 h-1 rounded-full bg-current" />
      {label}
      {reason && <span className="opacity-70 normal-case font-normal">· {reason}</span>}
    </span>
  )
}
