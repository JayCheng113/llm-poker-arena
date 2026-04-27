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
  await page.click('text=📊 summary')
  await page.waitForSelector('text=session summary', { timeout: 5_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/session-summary.png', fullPage: false })
})

test('screenshot all-bot baseline session', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?session=demo-bots&hand=20&turn=0')
  await page.waitForSelector('text=is acting', { timeout: 10_000 })
  await page.screenshot({ path: '/tmp/web-dogfood/demo-bots.png', fullPage: false })
})
