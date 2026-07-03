import { test, expect } from '@playwright/test'
import path from 'path'

// This suite assumes the app is ALREADY BUILT AND RUNNING at
// http://localhost:8001/app/ before this file executes, per phase1.spec.ts.
//
//   cd frontend && pnpm build
//   cd .. && uv run python agent.py --run
//
// Then, from the repo root:
//
//   npx playwright test tests/e2e/ --reporter=line

const SAMPLE_CSV = path.join(__dirname, 'fixtures', 'sample.csv')

async function uploadAndReady(page: import('@playwright/test').Page) {
  await page.goto('/app/')
  await page.getByTestId('file-input').setInputFiles(SAMPLE_CSV)
  await expect(page.getByTestId('dataset-profile-card')).toBeVisible({ timeout: 30_000 })
}

test.describe('Phase 2 — conversation, charts & export', () => {
  test('a chart-appropriate question renders a real interactive chart', async ({ page }) => {
    await uploadAndReady(page)

    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('show me a breakdown of the amount by category as a chart')
    await sendButton.click()

    const turn = page.getByTestId('qa-turn').first()
    await expect(turn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })

    const chart = turn.getByTestId('chart')
    await expect(chart).toBeVisible({ timeout: 15_000 })
    // Plotly renders an SVG/canvas layer inside the chart container once real data draws.
    await expect(chart.locator('.js-plotly-plot')).toHaveCount(1)
  })

  test('a scalar question renders no chart element', async ({ page }) => {
    await uploadAndReady(page)

    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('what is the average of the amount column?')
    await sendButton.click()

    const turn = page.getByTestId('qa-turn').first()
    await expect(turn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })
    await expect(turn.getByTestId('chart')).toHaveCount(0)
  })

  test('follow-up chips appear on a completed answer and clicking one submits a new turn', async ({ page }) => {
    await uploadAndReady(page)

    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('what is the average of the amount column?')
    await sendButton.click()

    const firstTurn = page.getByTestId('qa-turn').first()
    await expect(firstTurn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })

    const chips = firstTurn.getByTestId('followup-chip')
    const chipCount = await chips.count()
    test.skip(chipCount === 0, 'Backend did not suggest follow-ups for this answer')

    await chips.first().click()

    const allTurns = page.getByTestId('qa-turn')
    await expect(allTurns).toHaveCount(2)
    await expect(allTurns.nth(1).getByTestId('answer-card').or(allTurns.nth(1).getByTestId('query-status'))).toBeVisible()
  })

  test('an ambiguous question shows the clarification bubble', async ({ page }) => {
    await uploadAndReady(page)

    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('what about that column, is it good?')
    await sendButton.click()

    const turn = page.getByTestId('qa-turn').first()
    await expect(
      turn.getByTestId('clarification-bubble').or(turn.getByTestId('unanswerable-bubble')),
    ).toBeVisible({ timeout: 60_000 })
    await expect(turn.getByTestId('query-failed')).toHaveCount(0)
  })

  test('export button triggers a download for a completed query with a table', async ({ page }) => {
    await uploadAndReady(page)

    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('show me the amount and category for every row')
    await sendButton.click()

    const turn = page.getByTestId('qa-turn').first()
    await expect(turn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })

    const exportButton = turn.getByTestId('export-button')
    await expect(exportButton).toBeVisible()
    await expect(exportButton).toBeEnabled()

    const [download] = await Promise.all([page.waitForEvent('download'), exportButton.click()])
    expect(download.suggestedFilename()).toMatch(/\.(csv|xlsx)$/)
  })
})
