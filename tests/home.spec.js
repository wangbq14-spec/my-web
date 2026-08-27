import { test, expect } from '@playwright/test'

test('首页可以正常打开并点击开始体验', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveTitle(/智行 AI|Vite/)

  const button = page.getByText('开始体验')
  await expect(button).toBeVisible()

  await button.click()

  await expect(page).toHaveURL(/#experience/)
})