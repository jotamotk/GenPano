import React from 'react'
import { isDemoActive } from '../../lib/demoMode'

/**
 * DemoModeBadge — small pill rendered in the topbar when `?demo=1` is
 * active. Reminds the presenter that the dashboards are reading from
 * frontend mock fixtures (bestcoffer-scoped) rather than backend data.
 *
 * Renders nothing when demo mode is off.
 */
export default function DemoModeBadge() {
  if (!isDemoActive()) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-pill text-[11px] font-semibold uppercase tracking-wider bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
      title="URL contains ?demo=1 — BestCoffer mock data active. Append ?demo=0 to disable."
      aria-label="Demo mode active"
      data-testid="demo-mode-badge"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      Demo
    </span>
  )
}
