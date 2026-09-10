import { expect, test } from '@playwright/test'

test('登录后通过统一 WorkspaceSidebar 在工作区页面间导航', async ({ page }) => {
  const conversation = {
    id: 1,
    title: '验收会话',
    pinned: false,
    updated_at: '2026-08-30T08:00:00Z',
  }
  const project = {
    id: 7,
    name: '发布项目',
    description: '统一导航验收',
    instructions: '',
    pinned: false,
    conversation_count: 1,
    document_count: 0,
    created_at: '2026-08-30T08:00:00Z',
    updated_at: '2026-08-30T08:00:00Z',
  }

  await page.route('**/api/auth/login', (route) => route.fulfill({
    status: 200,
    json: { access_token: 'workspace-nav-token', token_type: 'bearer' },
  }))
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, username: 'qa-user', email: 'qa@example.com' },
  }))
  await page.route('**/api/conversations', (route) => route.fulfill({ json: [conversation] }))
  await page.route('**/api/conversations/1/messages', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/projects', (route) => route.fulfill({ json: [project] }))
  await page.route('**/api/documents', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/tasks', (route) => route.fulfill({ json: [] }))

  await page.goto('/login')
  await page.getByLabel('用户名 / 邮箱').fill('qa-user')
  await page.getByLabel('密码').fill('secret')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)

  const sidebar = page.locator('.sidebar')
  const projects = sidebar.getByRole('button', { name: '项目', exact: true })
  const knowledge = sidebar.getByRole('button', { name: '知识库', exact: true })
  const tasks = sidebar.getByRole('button', { name: '任务 / Workflow', exact: true })

  await expect(sidebar).toBeVisible()
  await expect(projects).toBeVisible()
  await expect(knowledge).toBeVisible()
  await expect(tasks).toBeVisible()

  await sidebar.getByLabel('更多项目', { exact: true }).click()
  await expect(page).toHaveURL(/\/projects$/)
  await expect(sidebar).toBeVisible()
  await expect(projects).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toHaveCount(0)

  await knowledge.click()
  await expect(page).toHaveURL(/\/knowledge$/)
  await expect(knowledge).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toHaveCount(0)

  await tasks.click()
  await expect(page).toHaveURL(/\/tasks$/)
  await expect(tasks).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toHaveCount(0)

  await sidebar.getByRole('button', { name: '验收会话', exact: true }).click()
  await expect(page).toHaveURL(/\/chat\?conversation_id=1$/)
  await expect(sidebar.locator('.conversation-item.active')).toHaveAttribute('aria-current', 'true')
  await expect(page.getByRole('button', { name: '返回 Chat', exact: true })).toHaveCount(0)
})
