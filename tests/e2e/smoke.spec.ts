import { test, expect } from '@playwright/test'
import path from 'node:path'

const SAMPLE_CSV = path.join(__dirname, 'sample.csv')

test.describe('Personal Data Analysis Agent — Phase 1 smoke', () => {
  test('upload → ask → real answer with full transparency', async ({ page }) => {
    // 1) Page loads and is STYLED (heading visible, empty state guidance shown).
    await page.goto('./')

    const heading = page.getByRole('heading', { name: /Personal Data Analysis Agent/i })
    await expect(heading).toBeVisible()

    // Styled check: the heading uses a real (non-default) computed font size.
    const fontSize = await heading.evaluate(el => parseFloat(getComputedStyle(el).fontSize))
    expect(fontSize).toBeGreaterThan(18)

    // Empty state guidance renders before any upload.
    await expect(page.getByTestId('empty-no-dataset')).toBeVisible()
    await expect(page.getByText(/Upload a dataset to begin/i)).toBeVisible()

    // At least one labelled "Coming soon" stub is visible from the start.
    await expect(page.getByTestId('stub-badge').first()).toBeVisible()

    // 2) Upload a small CSV via the hidden file input.
    await page.getByTestId('file-input').setInputFiles(SAMPLE_CSV)

    // Dataset-loaded state appears (summary with row count + sample preview).
    await expect(page.getByTestId('dataset-summary')).toBeVisible({ timeout: 30_000 })

    // 3) The question box becomes enabled; type a question and Ask.
    const questionInput = page.getByTestId('question-input')
    await expect(questionInput).toBeEnabled()
    await questionInput.fill('What were total sales by month?')

    const askButton = page.getByTestId('ask-button')
    await expect(askButton).toBeEnabled()
    await askButton.click()

    // 4) The real answer panel appears with non-empty prose (real Gemini run).
    const answerPanel = page.getByTestId('answer-panel')
    await expect(answerPanel).toBeVisible({ timeout: 60_000 })

    const prose = page.getByTestId('answer-prose')
    await expect(prose).toBeVisible()
    const proseText = (await prose.innerText()).trim()
    expect(proseText.length).toBeGreaterThan(10)

    // 5) The cost line appears with real token/cost figures.
    const costLine = page.getByTestId('cost-line')
    await expect(costLine).toBeVisible()
    await expect(costLine).toContainText('tokens')

    // 6) The code panel toggles open and reveals code.
    await page.getByTestId('code-toggle').click()
    await expect(page.getByTestId('code-body')).toBeVisible()

    // 7) The transparency panel toggles open and proves privacy.
    await page.getByTestId('transparency-toggle').click()
    await expect(page.getByTestId('transparency-body')).toBeVisible()
    await expect(page.getByTestId('transparency-body')).toContainText(/no bulk rows/i)

    // 8) At least one labelled "Coming soon" stub remains visible alongside the result.
    await expect(page.getByTestId('stub-badge').first()).toBeVisible()
  })
})
