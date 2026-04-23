import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
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
