import { test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

test('screenshot hand 0 turn 0', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?hand=0&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/hand0-turn0.png', fullPage: false })
})

test('screenshot hand 2 turn 5', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?hand=2&turn=5')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/hand2-turn5.png', fullPage: false })
})

test('screenshot hand 5 last turn (showdown reveals)', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?hand=5&turn=99')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/hand5-last.png', fullPage: false })
})

test('screenshot dev mode god-view hand 0 turn 0', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?hand=0&turn=0&dev=1')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/hand0-turn0-dev.png', fullPage: false })
})

test('screenshot session summary modal', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?hand=0&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.getByLabel('open session summary').click()
  await page.waitForSelector('text=session summary', { timeout: 5_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/session-summary.png', fullPage: false })
})

test('screenshot all-bot baseline session', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-bots&hand=20&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/demo-bots.png', fullPage: false })
})

test('screenshot tournament hand 0', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-tournament&hand=0&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/tournament-hand0.png', fullPage: false })
})

test('screenshot tournament last hand showdown', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-tournament&hand=29&turn=99')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/tournament-last.png', fullPage: false })
})

test('screenshot 6-LLM smoke hand 0', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-6llm-smoke&hand=0&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/6llm-hand0.png', fullPage: false })
})

test('screenshot 6-LLM smoke last hand showdown', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-6llm-smoke&hand=5&turn=99')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  // Wait for the lazy-loaded PnL chart to hydrate so the leaderboard
  // is in the screenshot.
  await page.waitForSelector('text=standings', { timeout: 5_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/6llm-last.png', fullPage: false })
})

test('screenshot mobile portrait', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })  // iPhone 14
  await page.goto('/?hand=0&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/mobile.png', fullPage: false })
})
