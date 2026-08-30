import { expect, test } from '@playwright/test'

test('侧边栏工作区导航可用', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })

  await page.route('**/api/conversations**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname

    if (request.method() === 'GET' && pathname === '/api/conversations') {
      await route.fulfill({
        json: [{ id: 1, title: '验收会话', updated_at: '2026-08-28T08:00:00Z' }],
      })
      return
    }

    await route.fallback()
  })

  await page.route('**/api/projects**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: [] })
      return
    }

    await route.fallback()
  })

  await page.route('**/api/documents**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: [] })
      return
    }

    await route.fallback()
  })

  await page.goto('/chat')

  const workspaceNav = page.locator('.workspace-nav[aria-label="工作区"]')
  const projectsNavigation = workspaceNav.getByRole('button', { name: '项目', exact: true })
  const knowledgeNavigation = workspaceNav.getByRole('button', { name: '知识库', exact: true })

  await expect(workspaceNav).toBeVisible()
  await expect(projectsNavigation).toBeVisible()
  await expect(knowledgeNavigation).toBeVisible()
  await expect(workspaceNav.getByRole('button', { name: '对话', exact: true })).toHaveCount(0)
  await expect(page.locator('.conversation-list')).toContainText('验收会话')

  await projectsNavigation.click()
  await expect(page).toHaveURL(/\/projects$/)
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '返回 Chat', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)

  await expect(workspaceNav.getByRole('button', { name: '项目', exact: true })).toBeVisible()
  await expect(workspaceNav.getByRole('button', { name: '知识库', exact: true })).toBeVisible()

  await workspaceNav.getByRole('button', { name: '知识库', exact: true }).click()
  await expect(page).toHaveURL(/\/knowledge$/)
})
