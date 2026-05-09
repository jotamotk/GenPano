import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['github']] : [['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixels: 100,
    },
  },
  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /tests\/e2e\/.*\.spec\.(ts|tsx)$/,
    },
    {
      name: 'chromium-mobile',
      use: { ...devices['Pixel 7'] },
      testMatch: /tests\/e2e\/.*\.spec\.(ts|tsx)$/,
    },
    {
      name: 'visual',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /tests\/visual\/.*\.spec\.(ts|tsx)$/,
    },
  ],
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
