import { test, expect } from '@playwright/test'

test('首页可以正常打开并点击开始体验', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveTitle(/智行 AI|Vite/)

  const button = page.getByText('开始体验')
  await expect(button).toBeVisible()

  await button.click()

  // 未登录点击「开始体验」→ 进入受保护的 /dashboard → 守卫重定向到 /login
  await expect(page).toHaveURL(/\/login\?redirect=/)
})