import { test, expect } from '@playwright/test'
import path from 'path'

// This suite assumes the app is ALREADY BUILT AND RUNNING at
// http://localhost:8001/app/ before this file executes. It does not start
// or stop the server itself. Before running:
//
//   cd frontend && pnpm build
//   cd .. && uv run python -m src
//
// Then, from the repo root:
//
//   npx playwright test tests/e2e/ --reporter=line

const SAMPLE_CSV = path.join(__dirname, 'fixtures', 'sample.csv')

test.describe('Phase 1 — upload, ask, get a real answer', () => {
  test('page loads and is styled', async ({ page }) => {
    await page.goto('/app/')
    await expect(page.getByRole('heading', { name: 'Data Analysis Agent' })).toBeVisible()

    const dropzone = page.getByTestId('upload-dropzone')
    await expect(dropzone).toBeVisible()
    const borderStyle = await dropzone.evaluate(el => getComputedStyle(el).borderStyle)
    expect(borderStyle).toBe('dashed')
  })

  test('full journey: upload, ask, follow-up, and stub visibility', async ({ page }) => {
    await page.goto('/app/')

    // --- Upload flow ---
    const fileInput = page.getByTestId('file-input')
    await fileInput.setInputFiles(SAMPLE_CSV)

    await expect(page.getByTestId('dataset-profile-card')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('dataset-counts')).toContainText('30 rows')
    await expect(page.getByTestId('dataset-counts')).toContainText('3 columns')
    await expect(page.getByTestId('dataset-columns')).toContainText('amount')
    await expect(page.getByTestId('dataset-columns')).toContainText('category')

    // --- First question: real LLM call + real sandboxed execution ---
    const questionInput = page.getByTestId('question-input')
    const sendButton = page.getByTestId('send-button')

    await questionInput.fill('what is the average of the amount column?')
    await sendButton.click()

    await expect(questionInput).toBeDisabled()

    const firstTurn = page.getByTestId('qa-turn').first()
    await expect(firstTurn.getByTestId('query-status')).toBeVisible()

    await expect(firstTurn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })
    await expect(firstTurn.getByTestId('answer-text')).not.toBeEmpty()
    await expect(firstTurn.getByTestId('answer-text')).toContainText('15.5')

    // Token usage badge — real numbers from the Gemini response
    const tokenBadge = firstTurn.getByTestId('token-usage')
    await expect(tokenBadge).toBeVisible()
    await expect(tokenBadge).toContainText('tokens')
    const tokenText = (await tokenBadge.textContent()) ?? ''
    expect(tokenText).toMatch(/\d+ \+ \d+ = \d+ tokens/)

    // Collapsed code panel — expands to reveal non-empty generated code
    const codeToggle = firstTurn.getByTestId('toggle-code')
    await expect(codeToggle).toBeVisible()
    await expect(firstTurn.getByTestId('generated-code')).toHaveCount(0)
    await codeToggle.click()
    const codePanel = firstTurn.getByTestId('generated-code')
    await expect(codePanel).toBeVisible()
    const codeText = (await codePanel.textContent()) ?? ''
    expect(codeText.trim().length).toBeGreaterThan(0)

    // --- Stub surfaces: visible, labelled, and non-interactive ---
    const chartStub = firstTurn.getByTestId('chart-stub')
    await expect(chartStub).toBeVisible()
    await expect(chartStub).toContainText('Interactive chart — coming in Phase 2')

    const followupStub = firstTurn.getByTestId('followup-stub')
    await expect(followupStub).toBeVisible()
    await expect(followupStub).toContainText('Suggested follow-ups — coming in Phase 2')

    const exportStub = firstTurn.getByTestId('export-stub')
    await expect(exportStub).toBeVisible()
    await expect(exportStub).toBeDisabled()
    await expect(exportStub).toContainText('coming in Phase 2')

    // --- Second, follow-up question in the same session ---
    await expect(questionInput).toBeEnabled({ timeout: 30_000 })
    await questionInput.fill('and what about the max of that same column?')
    await sendButton.click()

    const allTurns = page.getByTestId('qa-turn')
    await expect(allTurns).toHaveCount(2)

    const secondTurn = allTurns.nth(1)
    await expect(secondTurn.getByTestId('answer-card')).toBeVisible({ timeout: 60_000 })
    await expect(secondTurn.getByTestId('answer-text')).not.toBeEmpty()
  })
})
