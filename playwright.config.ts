import { defineConfig, devices } from '@playwright/test'

// This suite runs against the live, already-built, already-running app.
// Operator must start the server before running this suite:
//   cd frontend && pnpm build
//   cd .. && uv run python -m src
// Then, from the repo root:
//   npx playwright test tests/e2e/ --reporter=line

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:8001',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
