import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE_PATH lets a single codebase produce two builds:
//   - prod build:    base = '/'         (served from https://host/)
//   - preview build: base = '/preview/' (served from https://host/preview/)
// Must end with '/'. Leave unset for local dev.
const basePath = process.env.VITE_BASE_PATH || '/'
const isDockerDev = Boolean(process.env.VITE_ADMIN_BACKEND_URL)
const apiProxyTarget =
  process.env.VITE_API_BACKEND_URL ||
  (isDockerDev ? 'http://host.docker.internal:8000' : 'http://localhost:4000')
// Admin moved into the FastAPI backend in PR #386 — same target as /api.
const adminProxyTarget =
  process.env.VITE_ADMIN_BACKEND_URL || apiProxyTarget

export default defineConfig({
  base: basePath,
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
    // /api/*        - main FastAPI backend on :4000
    // /admin*       - Admin SPA + APIs on the same FastAPI backend (:4000).
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/admin/api': {
        target: adminProxyTarget,
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/admin\/api/, '/api'),
      },
      '/admin': {
        target: adminProxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    // Self-seeded harness violation fixtures must never enter production
    rollupOptions: {
      external: (id) => id.includes('__ci_fixtures__'),
    },
  },
})
