import { defineConfig, devices } from '@playwright/test'

// The app is served by the backend at http://localhost:8001/app/.
// webServer is DISABLED on purpose — the orchestrator/qa starts the backend
// (uv run python -m src) before running these tests.
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8001/app/',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
