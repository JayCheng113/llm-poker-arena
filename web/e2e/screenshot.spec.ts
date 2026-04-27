/**
 * Screenshot regeneration for README + USAGE docs.
 *
 * Targets the shipped `demo-6llm` session only (other ids were retired
 * from the Pages deploy on 2026-04-27). Outputs go straight into
 * `docs/images/` so a `npm run test:e2e -- --grep screenshot` is the
 * one-shot way to refresh the README hero + screenshots.
 *
 * Hand picks (from the actual 30-hand demo-6llm run):
 *   - hand 1, turn 10  → a deep multi-way pot, river fully out;
 *                        good for the hero (god-view shows all hole cards)
 *   - hand 1, last turn → river-final state with all 5 community cards
 *                         and the winner banner
 *   - hand 8, turn 5   → mid-game with HUD numbers populated for
 *                         several seats (hand 8 is one of the longest)
 *   - dev mode + summary modal — UI-state shots, not session-specific
 */
import { test } from '@playwright/test'

import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

test.describe.configure({ mode: 'serial' })

// ESM equivalent of CommonJS __dirname (Playwright + ESM project).
const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const DOCS_IMAGES = resolve(__dirname, '../../docs/images')
mkdirSync(DOCS_IMAGES, { recursive: true })

const VIEWPORT = { width: 1440, height: 900 }
const SESSION = 'demo-6llm'

test('hero — mid-game god-view (hand 1 turn 10)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=1&turn=10`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/hero.png`, fullPage: false })
})

test('showdown — river end with leaderboard (hand 1 last turn)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=1&turn=99`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/showdown.png`, fullPage: false })
})

test('session summary — full P&L modal (hand 0)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=0&turn=0`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.getByLabel('open session summary').click()
  await page.waitForSelector('text=session summary', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/summary.png`, fullPage: false })
})

test('dev mode — raw JSON + retry badges (hand 8 turn 5 dev=1)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=8&turn=5&dev=1`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/dev-mode.png`, fullPage: false })
})
