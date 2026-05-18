import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { hydrateDemoMode, isDemoActive, setDemoActive } from './demoMode'

describe('demoMode toggle', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  afterEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  test('default state is off', () => {
    expect(isDemoActive()).toBe(false)
  })

  test('setDemoActive(true) persists to sessionStorage', () => {
    setDemoActive(true)
    expect(isDemoActive()).toBe(true)
    expect(window.sessionStorage.getItem('genpano_demo_mode')).toBe('1')
  })

  test('setDemoActive(false) clears the flag', () => {
    setDemoActive(true)
    setDemoActive(false)
    expect(isDemoActive()).toBe(false)
    expect(window.sessionStorage.getItem('genpano_demo_mode')).toBeNull()
  })

  test('hydrateDemoMode reads ?demo=1 from URL', () => {
    const originalSearch = window.location.search
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, search: '?demo=1' },
    })
    hydrateDemoMode()
    expect(isDemoActive()).toBe(true)
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, search: originalSearch },
    })
  })

  test('hydrateDemoMode honors ?demo=0 to disable', () => {
    setDemoActive(true)
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, search: '?demo=0' },
    })
    hydrateDemoMode()
    expect(isDemoActive()).toBe(false)
  })

  test('hydrateDemoMode leaves state untouched when ?demo is absent', () => {
    setDemoActive(true)
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...window.location, search: '?other=1' },
    })
    hydrateDemoMode()
    expect(isDemoActive()).toBe(true)
  })
})
