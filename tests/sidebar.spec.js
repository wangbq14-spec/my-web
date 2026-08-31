import { expect, test } from '@playwright/test'

test('侧边栏分组、项目快捷入口和独立知识库导航可用', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, username: 'e2e-user', email: 'e2e@example.com' },
  }))

  await page.route('**/api/conversations**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname

    if (request.method() === 'GET' && pathname === '/api/conversations') {
      await route.fulfill({
        json: [
          { id: 1, title: '置顶会话', pinned: true, updated_at: '2026-08-28T09:00:00Z' },
          { id: 2, title: '验收会话', pinned: false, updated_at: '2026-08-28T08:00:00Z' },
        ],
      })
      return
    }

    await route.fallback()
  })

  await page.route('**/api/projects**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    const project = {
      id: 7,
      name: '发布项目',
      description: '',
      instructions: '',
      pinned: false,
      conversation_count: 3,
      document_count: 2,
      created_at: '2026-08-28T08:00:00Z',
      updated_at: '2026-08-28T08:00:00Z',
    }
    if (route.request().method() === 'GET' && pathname === '/api/projects') {
      await route.fulfill({ json: [project] })
      return
    }
    if (route.request().method() === 'GET' && pathname === '/api/projects/7') {
      await route.fulfill({ json: project })
      return
    }
    if (route.request().method() === 'GET' && pathname.endsWith('/conversations')) {
      await route.fulfill({ json: [] })
      return
    }
    if (route.request().method() === 'GET' && pathname.endsWith('/documents')) {
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

  const sidebar = page.locator('.sidebar')
  const pinnedToggle = sidebar.getByRole('button', { name: '置顶', exact: true })
  const projectsToggle = sidebar.getByRole('button', { name: '项目', exact: true })
  const knowledgeNavigation = sidebar.getByRole('button', { name: '知识库', exact: true })

  await expect(sidebar.getByText('工作区', { exact: true })).toHaveCount(0)
  await expect(pinnedToggle).toHaveAttribute('aria-expanded', 'true')
  await expect(sidebar.locator('.pinned-section')).toContainText('置顶会话')
  await expect(sidebar.locator('.conversation-list')).not.toContainText('置顶会话')
  await expect(sidebar.locator('.conversation-list')).toContainText('验收会话')
  await expect(sidebar.locator('.conversation-icon')).toBeVisible()
  await expect(projectsToggle).toHaveAttribute('aria-expanded', 'true')
  await expect(sidebar.locator('.recent-project-link')).toContainText('3 会话 · 2 资料')
  await expect(sidebar.getByLabel('更多项目', { exact: true })).toBeVisible()
  await expect(sidebar.getByRole('button', { name: '快速新建项目', exact: true })).toBeVisible()
  await expect(knowledgeNavigation).toBeVisible()

  await projectsToggle.click()
  await expect(projectsToggle).toHaveAttribute('aria-expanded', 'false')
  await projectsToggle.click()

  await sidebar.getByRole('button', { name: '快速新建项目', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\?create=1$/)
  await expect(page.locator('.quick-create input')).toBeFocused()
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '返回 Chat', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)

  await sidebar.getByRole('button', { name: '知识库', exact: true }).click()
  await expect(page).toHaveURL(/\/knowledge$/)
})
