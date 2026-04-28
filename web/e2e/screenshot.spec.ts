/**
 * Screenshot regeneration for README + USAGE docs.
 *
 * Targets the shipped `demo-6llm` session only (other ids were retired
 * from the Pages deploy on 2026-04-27). Outputs go straight into
 * `docs/images/` so a `npm run test:e2e -- --grep screenshot` is the
 * one-shot way to refresh the README hero + screenshots.
 *
 * Hand picks (from the 30-hand demo-6llm run after Reasoning Visibility
 * Overhaul — commit de05812):
 *   - hand 18 turn 11 → 17-action grind ending in a GPT-5 win,
 *     turn street, GPT-5 actively acting → reasoning summary visible
 *     on the right panel (this is the hero shot for the README).
 *   - hand 18 last turn → all 5 community cards + Claude's fold to
 *     GPT-5's river call → 'showdown' frame with the standings panel.
 *   - hand 3 turn 11 → Gemini acting on the river with its full
 *     <thought>-extracted reasoning summary visible (this is the
 *     dev-mode shot — also showcases the summary kind).
 *   - summary modal — UI-state shot, not session-specific.
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

test('hero — GPT-5 reasoning visible mid-game (hand 18 turn 11)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=18&turn=11`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  // Wait for GPT-5's reasoning summary block to render (markdown-parsed,
  // appears as a blue-bordered panel). Without this the screenshot can
  // race the lazy markdown chunk and ship a half-loaded panel.
  await page.waitForSelector('[data-reasoning-artifact]', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/hero.png`, fullPage: false })
})

test('showdown — river end with leaderboard (hand 18 last turn)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=18&turn=99`)
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

test('dev mode — Gemini reasoning summary + dev badges (hand 3 turn 11 dev=1)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${SESSION}&hand=3&turn=11&dev=1`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('[data-reasoning-artifact]', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/dev-mode.png`, fullPage: false })
})

// ---------------------------------------------------------------------------
// flagship companion (102-hand, claude-sonnet-4-6 swapped for haiku-4-5).
// Separate file names so README can show the controlled-experiment delta
// (mini Haiku came last → Sonnet came first) side-by-side without
// overwriting the baseline screenshots.
// ---------------------------------------------------------------------------

const FLAGSHIP = 'demo-6llm-flagship'

test('flagship hero — Sonnet acting mid-hand (hand 53 turn 6)', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${FLAGSHIP}&hand=53&turn=6`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/flagship-hero.png`, fullPage: false })
})

test('flagship summary — final P&L modal across 102 hands', async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await page.goto(`/?session=${FLAGSHIP}&hand=0&turn=0`)
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.getByLabel('open session summary').click()
  await page.waitForSelector('text=session summary', { timeout: 5_000 })
  await page.screenshot({ path: `${DOCS_IMAGES}/flagship-summary.png`, fullPage: false })
})
