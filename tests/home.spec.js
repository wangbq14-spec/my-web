import { test, expect } from '@playwright/test'

test('首页展示 Omnixa，并提供注册和登录入口', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveTitle(/Omnixa|Vite/)
  await expect(page.locator('.brand-name', { hasText: 'Omnixa' })).toBeVisible()

  const startButton = page.getByRole('link', { name: '开始使用', exact: true })
  await expect(startButton).toBeVisible()

  await startButton.click()

  await expect(page).toHaveURL(/\/register$/)

  await page.goto('/')
  const loginButton = page.locator('.actions').getByRole('link', { name: '登录', exact: true })
  await expect(loginButton).toBeVisible()
  await loginButton.click()

  await expect(page).toHaveURL(/\/login$/)
})
