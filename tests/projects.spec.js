import { expect, test } from '@playwright/test'

test('登录后可新建、进入并删除项目', async ({ page }) => {
  const projects = []
  const documents = [{ id: 8, original_filename: 'notes.md', status: 'ready', project_id: null, created_at: '2026-08-30T07:00:00Z' }]

  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, username: 'e2e-user', email: 'e2e@example.com' },
  }))
  await page.route(/\/api\/projects(?:\/\d+)?$/, async (route) => {
    const method = route.request().method()
    const url = new URL(route.request().url())
    const id = Number(url.pathname.split('/').at(-1))
    if (method === 'GET' && url.pathname === '/api/projects') {
      await route.fulfill({ json: projects })
      return
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON()
      const project = {
        id: 1,
        name: body.name,
        description: body.description ?? null,
        instructions: null,
        pinned: false,
        created_at: '2026-08-30T08:00:00Z',
        updated_at: '2026-08-30T08:00:00Z',
        last_activity_at: '2026-08-30T08:00:00Z',
        conversation_count: 0,
        document_count: 0,
      }
      projects.unshift(project)
      await route.fulfill({ status: 201, json: project })
      return
    }
    if (method === 'GET') {
      await route.fulfill({ json: projects.find((project) => project.id === id) })
      return
    }
    if (method === 'PATCH') {
      const project = projects.find((project) => project.id === id)
      Object.assign(project, route.request().postDataJSON())
      await route.fulfill({ json: project })
      return
    }
    if (method === 'DELETE') {
      projects.splice(projects.findIndex((project) => project.id === id), 1)
      await route.fulfill({ status: 204 })
      return
    }
    await route.fallback()
  })
  await page.route(/\/api\/projects\/1\/conversations$/, (route) => route.fulfill({ json: [] }))
  await page.route(/\/api\/projects\/1\/documents$/, (route) => route.fulfill({ json: documents.filter((document) => document.project_id === 1) }))
  await page.route(/\/api\/documents(?:\/\d+)?$/, async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ json: documents })
      return
    }
    if (method === 'PATCH') {
      const id = Number(new URL(route.request().url()).pathname.split('/').at(-1))
      const document = documents.find((item) => item.id === id)
      Object.assign(document, route.request().postDataJSON())
      await route.fulfill({ json: document })
      return
    }
    await route.fallback()
  })

  await page.goto('/projects')
  await page.locator('.quick-create input').fill('发布准备')
  await page.locator('.quick-create button[type=submit]').click()

  const allProjects = page.getByRole('region', { name: '全部项目' })
  const projectRow = allProjects.locator('.project-row').filter({ hasText: '发布准备' })

  await expect(projectRow.getByText('发布准备', { exact: true })).toBeVisible()
  await projectRow.getByRole('button', { name: '置顶 发布准备' }).click()
  await expect(projectRow.getByRole('button', { name: '取消置顶 发布准备' })).toBeVisible()
  await projectRow.locator('.project-summary').click()
  await expect(page).toHaveURL(/\/projects\/1$/)
  await expect(page.getByRole('heading', { name: '发布准备' })).toBeVisible()

  await page.getByRole('button', { name: 'Instructions' }).click()
  const instructions = page.getByRole('textbox', { name: '项目 Instructions' })
  await instructions.fill('优先列出风险')
  await page.getByRole('button', { name: '保存说明' }).click()
  await expect.poll(() => projects[0].instructions).toBe('优先列出风险')
  await instructions.fill('')
  await page.getByRole('button', { name: '保存说明' }).click()
  await expect.poll(() => projects[0].instructions).toBe('')

  await page.getByRole('button', { name: 'Knowledge' }).click()
  await page.getByRole('button', { name: '移入本项目' }).click()
  await expect(page.getByRole('button', { name: '移出项目' })).toBeVisible()

  await page.getByRole('button', { name: '返回项目' }).click()
  await projectRow.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '删除项目' }).click()
  await expect(projectRow.getByText('发布准备', { exact: true })).not.toBeVisible()
})
