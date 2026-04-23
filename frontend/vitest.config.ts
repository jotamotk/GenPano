import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [fileURLToPath(new URL('./vitest.setup.ts', import.meta.url))],
    include: ['src/**/*.{test,spec}.{ts,tsx,js,jsx}', 'tests/unit/**/*.{test,spec}.{ts,tsx,js,jsx}'],
    exclude: [
      'node_modules/**',
      'dist/**',
      'dist-*/**',
      'src/__ci_fixtures__/**',
      'tests/e2e/**',
      'tests/visual/**',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'node_modules/**',
        'dist*/**',
        'src/__ci_fixtures__/**',
        '**/*.d.ts',
        'vite.config.*',
        'vitest.config.*',
        'playwright.config.*',
      ],
    },
  },
});
