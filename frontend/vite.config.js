import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE_PATH lets a single codebase produce two builds:
//   - prod build:    base = '/'         (served from https://host/)
//   - preview build: base = '/preview/' (served from https://host/preview/)
// Must end with '/'. Leave unset for local dev.
const basePath = process.env.VITE_BASE_PATH || '/'

export default defineConfig({
  base: basePath,
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
    // /api/*        — main backend (Node.js on :4000, user/brand/industry APIs)
    // /admin/api/*  — admin console backend (same :4000, Path=/admin cookie scope)
    proxy: {
      '/api': {
        target: 'http://localhost:4000',
        changeOrigin: true,
      },
      '/admin/api': {
        target: 'http://localhost:4000',
        changeOrigin: false,
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
