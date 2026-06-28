import { test, expect } from '@playwright/test'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// These run against the LIVE app served by the backend at http://localhost:8001/app/.
// The orchestrator/qa starts the backend before running `pnpm exec playwright test`.

const SAMPLE_CSV = `month,region,revenue,units
2024-01,North,1200.5,30
2024-01,South,980.0,21
2024-02,North,1500.0,40
2024-02,South,,18
2024-03,North,1750.25,52
`

test.describe('Phase 1 — static render (no backend required for these assertions)', () => {
  test('page loads, is styled, shows upload UI + privacy line + labelled stubs', async ({
    page,
  }) => {
    await page.goto('./')

    // styled: heading visible and laid out
    const heading = page.getByRole('heading', {
      name: /privacy-preserving data analysis/i,
    })
    await expect(heading).toBeVisible()

    // privacy reassurance line
    await expect(
      page.getByText(/raw data never leaves this machine/i),
    ).toBeVisible()

    // primary upload control
    await expect(
      page.getByRole('button', { name: /choose csv file/i }),
    ).toBeVisible()

    // question input exists and is disabled until a dataset is loaded
    const questionInput = page.getByLabel(/your question about the data/i)
    await expect(questionInput).toBeVisible()
    await expect(questionInput).toBeDisabled()

    // empty-state guidance for the answer area
    await expect(page.getByText(/ask a question above to see a streamed answer/i)).toBeVisible()

    // labelled, non-functional stubs render and are marked "Coming soon"
    const stubs = page.locator('[data-stub="true"]')
    await expect(stubs.first()).toBeVisible()
    expect(await stubs.count()).toBeGreaterThanOrEqual(8)
    await expect(page.getByText('Coming soon').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Charts' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Audit-trail browser' })).toBeVisible()

    // styling sanity: body has a non-default background (Tailwind applied)
    const bg = await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    )
    expect(bg).not.toBe('rgba(0, 0, 0, 0)')
  })
})

// FULL PRIMARY JOURNEY — requires the LIVE backend (POST /datasets + SSE query).
// qa runs this against the running server. It uploads a real CSV, asserts the
// auto-profile renders, asks a question, and asserts streamed answer + shown code.
test.describe('Phase 1 — full journey (REQUIRES live backend)', () => {
  test('upload CSV -> profile -> ask -> streamed answer -> show code', async ({
    page,
  }) => {
    await page.goto('./')

    // upload a real CSV via the hidden file input
    const dir = mkdtempSync(join(tmpdir(), 'pw-csv-'))
    const csvPath = join(dir, 'sales.csv')
    writeFileSync(csvPath, SAMPLE_CSV)
    await page.locator('input[type="file"]').setInputFiles(csvPath)

    // profile table appears (column headers + at least one column row)
    await expect(page.getByRole('cell', { name: 'revenue' })).toBeVisible({
      timeout: 30_000,
    })
    await expect(page.getByText(/columns/i).first()).toBeVisible()

    // ask a question
    const questionInput = page.getByLabel(/your question about the data/i)
    await expect(questionInput).toBeEnabled()
    await questionInput.fill('What is the total revenue by month?')
    await page.getByRole('button', { name: /^ask$/i }).click()

    // a live step badge appears
    await expect(page.getByLabel('Analysis progress')).toBeVisible({
      timeout: 30_000,
    })

    // streamed answer eventually has non-empty content
    await expect
      .poll(
        async () => {
          const txt = await page
            .locator('section:has(h2:has-text("Answer"))')
            .innerText()
          return txt.trim().length
        },
        { timeout: 90_000 },
      )
      .toBeGreaterThan('3. Answer'.length + 5)

    // "Show code" discloses the pandas that ran
    const showCode = page.getByRole('button', { name: /show code/i })
    await expect(showCode).toBeVisible({ timeout: 90_000 })
    await showCode.click()
    await expect(page.getByText(/your data rows stayed local/i)).toBeVisible()
  })
})
