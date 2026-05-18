/**
 * Demo mode toggle.
 *
 * Opt-in via URL `?demo=1`. Hydrated to sessionStorage so SPA navigation
 * within the same tab keeps mock data live without re-appending the param.
 * Default off; closing the tab clears it. `?demo=0` clears it explicitly.
 *
 * When active, `apiClient.request()` substitutes a small set of GET
 * responses scoped to the bestcoffer demo (project_id 7380c0e0-…,
 * brand_id 24) so the dashboards used in tomorrow's demo render filled
 * data even where production rows are sparse.
 */

const STORAGE_KEY = 'genpano_demo_mode'

export const DEMO_PROJECT_ID = '7380c0e0-8798-4a5f-998f-42010a7d9caa'
export const DEMO_BRAND_ID = 24

function safeSessionStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null
  } catch {
    return null
  }
}

export function isDemoActive(): boolean {
  const store = safeSessionStorage()
  if (!store) return false
  return store.getItem(STORAGE_KEY) === '1'
}

export function setDemoActive(on: boolean): void {
  const store = safeSessionStorage()
  if (!store) return
  if (on) store.setItem(STORAGE_KEY, '1')
  else store.removeItem(STORAGE_KEY)
}

/**
 * Read `?demo=1` (or `?demo=0`) from the current URL and reflect it into
 * sessionStorage. Call once at app boot.
 */
export function hydrateDemoMode(): void {
  if (typeof window === 'undefined') return
  try {
    const params = new URLSearchParams(window.location.search)
    const raw = params.get('demo')
    if (raw === '1' || raw === 'true' || raw === 'on') setDemoActive(true)
    else if (raw === '0' || raw === 'false' || raw === 'off') setDemoActive(false)
  } catch {
    // window.location unavailable (SSR / sandbox) — no-op
  }
}
