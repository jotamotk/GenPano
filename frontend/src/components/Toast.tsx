/**
 * Compatibility shim — historical `showToast(message, type)` callers route
 * through the unified ProjectContext toast system so error toasts get the
 * sticky/copyable treatment without each caller needing changes.
 *
 * Rendering is owned by `components/ui/ToastViewport.tsx`; this module no
 * longer mounts a viewport of its own.
 */
import { showApiError, getToastPusher } from '../lib/showApiError'

export type ToastType = 'success' | 'error' | 'info'

export function showToast(message: string, type: ToastType = 'info'): void {
  if (type === 'error') {
    // Route through showApiError so the sticky/copyable error layout fires
    // even for legacy string-only callers.
    showApiError(new Error(message))
    return
  }
  const pusher = getToastPusher()
  if (pusher) {
    pusher({ kind: type, message })
    return
  }
  // Pre-mount fallback so missed-bootstrap order is at least visible.
  console.log(`[toast:${type}]`, message)
}

export function ToastContainer() {
  // Rendering moved to <ToastViewport />, mounted at the app root.
  return null
}
