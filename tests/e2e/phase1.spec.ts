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
    // Some providers (e.g. Gemini thinking models) report a non-zero
    // thinking_tokens component, added as a labelled third addend so the
    // sum is literally correct (see AnswerCard's honest token display).
    expect(tokenText).toMatch(/\d+ \+ \d+( \+ \d+ \(thinking\))? = \d+ tokens/)

    // Collapsed code panel — expands to reveal non-empty generated code
    const codeToggle = firstTurn.getByTestId('toggle-code')
    await expect(codeToggle).toBeVisible()
    await expect(firstTurn.getByTestId('generated-code')).toHaveCount(0)
    await codeToggle.click()
    const codePanel = firstTurn.getByTestId('generated-code')
    await expect(codePanel).toBeVisible()
    const codeText = (await codePanel.textContent()) ?? ''
    expect(codeText.trim().length).toBeGreaterThan(0)

    // --- Phase 2 surfaces: real, not stubs (see tests/e2e/phase2.spec.ts for
    // full chart/follow-up/export coverage) ---
    // A purely scalar average has no chart_spec, so no chart panel renders.
    await expect(firstTurn.getByTestId('chart')).toHaveCount(0)

    const exportButton = firstTurn.getByTestId('export-button')
    await expect(exportButton).toBeVisible()
    await expect(exportButton).toBeEnabled()
    await expect(exportButton).toContainText('Export cleaned data')

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
