import React from 'react'

/**
 * InfoTooltip — small "i" icon that reveals a description on hover/focus.
 *
 * Replaces inline metric subtitles displayed alongside card titles, so the
 * card header stays compact while the description is still discoverable.
 *
 * Usage:
 *   <h3>SoV 分布 <InfoTooltip text="全行业品牌声量占比" /></h3>
 */

export interface InfoTooltipProps {
  /** Description text shown inside the tooltip bubble. */
  text?: React.ReactNode
  /** Optional aria-label override (defaults to "info"). */
  label?: string
  /** Tooltip placement relative to the icon. */
  placement?: 'top' | 'bottom'
  className?: string
}

export default function InfoTooltip({
  text,
  label = 'info',
  placement = 'top',
  className = '',
}: InfoTooltipProps) {
  if (text == null || text === '') return null

  const positionClass =
    placement === 'bottom'
      ? 'top-full mt-1.5'
      : 'bottom-full mb-1.5'

  return (
    <span
      className={`group relative inline-flex items-center align-middle ${className}`.trim()}
      tabIndex={0}
      role="button"
      aria-label={label}
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 12 12"
        fill="none"
        aria-hidden="true"
        className="shrink-0 text-themed-secondary hover:text-themed-primary transition-colors"
      >
        <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.25" fill="none" />
        <circle cx="6" cy="3.4" r="0.7" fill="currentColor" />
        <rect x="5.4" y="5" width="1.2" height="4" rx="0.6" fill="currentColor" />
      </svg>
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 -translate-x-1/2 ${positionClass} z-20 hidden group-hover:block group-focus-within:block whitespace-normal min-w-[140px] max-w-[260px] px-2.5 py-1.5 rounded-btn text-[11px] leading-snug font-normal normal-case tracking-normal shadow-md`}
        style={{
          background: 'var(--color-tooltip-bg, var(--color-bg-card))',
          color: 'var(--color-text-body, var(--color-text-primary))',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        {text}
      </span>
    </span>
  )
}
