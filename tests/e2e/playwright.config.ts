import { defineConfig, devices } from '@playwright/test'

/**
 * E2E config for the Personal Data Analysis Agent.
 *
 * Runs against the LIVE app served at http://localhost:8001/app/ — the gate
 * starts the server (FastAPI serving the static export + real Gemini via .env).
 * We do NOT start a server here.
 */
export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8001/app/',
    trace: 'retain-on-failure',
    actionTimeout: 20_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
