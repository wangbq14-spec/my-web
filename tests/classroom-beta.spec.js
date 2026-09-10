import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const FIXTURE = JSON.parse(readFileSync(fileURLToPath(new URL('fixtures/classroom-codes.json', import.meta.url)), 'utf8'))
const API = 'http://127.0.0.1:8011/api'

const stamp = Date.now()
const student = {
  email: `student-${stamp}@example.com`,
  username: `student_${stamp}`,
  password: 'secret123',
}

function tokenFrom(page) {
  return page.evaluate(() => localStorage.getItem('access_token') || '')
}

async function apiBalance(page) {
  const token = await tokenFrom(page)
  const res = await page.request.get(`${API}/me/balance`, { headers: { Authorization: `Bearer ${token}` } })
  expect(res.ok()).toBeTruthy()
  return (await res.json()).balance
}

async function logout(page) {
  await page.locator('.user-footer-btn').click()
  await page.locator('.user-menu .logout-btn').click()
}

// The composer disables file upload while isStreaming is true (correct product
// behavior). Wait for the stop-generation button to disappear so the next image
// upload never races an in-flight stream.
async function waitForStreamEnd(page) {
  await expect(page.locator('button[aria-label="停止生成"]')).toHaveCount(0, { timeout: 20000 })
}

test.describe.configure({ mode: 'serial' })

test('classroom beta golden path (real frontend/backend/mysql/redis/worker/billing)', async ({ page }) => {
  test.setTimeout(180000)

  // ---------- 1. Landing ----------
  await page.goto('/')
  await expect(page.locator('.brand-name', { hasText: 'Omnixa' })).toBeVisible()
  await page.getByText('开始使用').first().click()
  await expect(page).toHaveURL(/\/register$/)

  // ---------- 2. Register with invite code ----------
  await page.locator('#email').fill(student.email)
  await page.locator('#username').fill(student.username)
  await page.locator('#password').fill(student.password)
  await page.locator('#inviteCode').fill(FIXTURE.beta)
  await page.getByRole('button', { name: '注册' }).click()
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  await expect(page.locator('.composer-input')).toBeVisible()

  // ---------- 3. Beta credits visible ----------
  const initialBalance = await apiBalance(page)
  expect(initialBalance).toBeGreaterThan(0)
  await page.goto('/usage')
  await expect(page).toHaveURL(/\/settings\/usage$/)
  await expect(page.getByText('积分', { exact: false }).first()).toBeVisible()

  // ---------- 4. Create a learning project (template) ----------
  await page.goto('/projects')
  await page.getByRole('button', { name: '模板 / 更多选项' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.locator('.template-list').getByRole('button', { name: '课程知识库' }).click()
  const projectName = `课堂项目-${stamp}`
  await page.getByRole('textbox', { name: '项目名称', exact: true }).fill(projectName)
  await page.getByRole('button', { name: '保存项目' }).click()
  await expect(page.getByText(projectName).first()).toBeVisible({ timeout: 15000 })

  // project id via API
  const token = await tokenFrom(page)
  const projectsRes = await page.request.get(`${API}/projects`, { headers: { Authorization: `Bearer ${token}` } })
  expect(projectsRes.ok()).toBeTruthy()
  const project = (await projectsRes.json()).find((p) => p.name === projectName)
  expect(project).toBeTruthy()

  // ---------- 5. Knowledge upload (real worker: queued -> processing -> ready) ----------
  await page.goto('/knowledge')
  await page.locator('#document-upload').setInputFiles({
    name: '课程笔记.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('第一章 线性代数基础：向量、矩阵与线性变换。\n第二章 概率论：条件概率与贝叶斯公式。', 'utf8'),
  })
  await page.locator('.upload-btn').click()
  const docRow = page.locator('.document-item').filter({ hasText: '课程笔记.txt' })
  await expect(docRow).toBeVisible()
  await expect(docRow.locator('.document-status')).toHaveText(/可用|处理中|排队中/, { timeout: 30000 })

  // ---------- 6. RAG chat against the project (upload doc attached to project via API) ----------
  const uploadRes = await page.request.post(`${API}/documents`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      project_id: String(project.id),
      file: {
        name: '项目资料.md',
        mimeType: 'text/markdown',
        buffer: Buffer.from('# 项目说明\nRAG 检索测试内容：向量检索与嵌入。', 'utf8'),
      },
    },
  })
  expect(uploadRes.status()).toBe(202)
  const projectDoc = await uploadRes.json()
  await expect
    .poll(async () => {
      const r = await page.request.get(`${API}/documents/${projectDoc.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      return (await r.json()).status
    }, { timeout: 30000 })
    .toBe('ready')

  await page.goto(`/chat?project_id=${project.id}`)
  await page.locator('.capability-trigger').click()
  await page.locator('.capability-option[data-mode="rag"]').click()
  await page.locator('.composer-input').fill('根据项目资料总结 RAG 检索')
  await page.locator('.send-btn').first().click()
  await expect(page.locator('.assistant-message').last()).toContainText('[mock]', { timeout: 20000 })

  // ---------- 7. Agent capability ----------
  await page.locator('.capability-trigger').click()
  await page.locator('.capability-option[data-mode="agent"]').click()
  await page.locator('.composer-input').fill('制定一周学习计划')
  await page.locator('.send-btn').first().click()
  await expect(page.locator('.assistant-message').last()).toContainText('[mock]', { timeout: 20000 })

  // ---------- 8. Model tier switch ----------
  await page.locator('.model-trigger').click()
  await page.locator('.model-option[data-tier="fast"]').click()
  await page.locator('.composer-input').fill('切换档位后的提问')
  await page.locator('.send-btn').first().click()
  await expect(page.locator('.assistant-message').last()).toContainText('[mock]', { timeout: 20000 })
  await waitForStreamEnd(page)

  // ---------- 9. Vision: upload image -> multimodal mock reply ----------
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  )
  // Vision requires the plain chat capability (agent/stream rejects images).
  await page.locator('.capability-trigger').click()
  await page.locator('.capability-option[data-mode="chat"]').click()
  await page.locator('input[aria-label="上传图片"]').setInputFiles({
    name: 'chart.png', mimeType: 'image/png', buffer: png,
  })
  await expect(page.locator('.composer-attachments')).toBeVisible()
  await page.locator('.composer-input').fill('这张图里有什么？')
  await page.locator('.send-btn').first().click()
  await expect(page.locator('.assistant-message', { hasText: '[mock-vision]' }).last()).toBeVisible({ timeout: 20000 })
  await waitForStreamEnd(page)

  // ---------- 9b. Vision: image-only (no text) -> multimodal mock reply ----------
  await page.locator('input[aria-label="上传图片"]').setInputFiles({
    name: 'chart.png', mimeType: 'image/png', buffer: png,
  })
  await expect(page.locator('.composer-attachments')).toBeVisible()
  await page.locator('.send-btn').first().click()
  await expect(page.locator('.assistant-message', { hasText: '[mock-vision]' }).last()).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.attachment-thumbnail:not(.attachment-lost)').last()).toBeVisible({ timeout: 10000 })
  await expect(page.locator('[aria-label^="图片已失效"]')).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.assistant-message', { hasText: '[mock-vision]' }).last()).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.attachment-thumbnail:not(.attachment-lost)').last()).toBeVisible({ timeout: 10000 })
  await expect(page.locator('[aria-label^="图片已失效"]')).toHaveCount(0)

  // ---------- 10. Usage: records exist and credits decreased ----------
  await page.goto('/usage')
  await expect(page.locator('.usage-page')).toBeVisible()
  await expect(page.locator('.usage-card').first()).toContainText(/\d/, { timeout: 15000 })
  const spent = await apiBalance(page)
  expect(spent).toBeLessThan(initialBalance)

  // ---------- 11. Feedback ----------
  await page.goto('/chat')
  await page.locator('.feedback-nav-item').click()
  await expect(page.getByLabel('意见反馈')).toBeVisible()
  await page.locator('#feedback-message').fill('课程学习体验很好，希望能导出对话记录。')
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByText('感谢反馈')).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: '关闭' }).click()

  // ---------- 12. Recharge request (manual review flow) ----------
  await page.goto('/pricing')
  const customInput = page.getByLabel('自定义充值金额')
  await expect(customInput).toBeVisible()
  await customInput.fill('50')
  await page.locator('.custom-submit').click()
  await expect(page.getByText('充值申请已提交', { exact: false })).toBeVisible({ timeout: 15000 })

  // ---------- 13. Admin: see + approve the request ----------
  await logout(page)
  await page.goto('/login')
  await page.locator('#username').fill(FIXTURE.admin.username)
  await page.locator('#password').fill(FIXTURE.admin.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })

  await page.goto('/admin')
  await expect(page.locator('.admin-tabs')).toBeVisible()
  await page.locator('.admin-tab', { hasText: 'Recharge' }).click()
  const requestRow = page.locator('tr', { hasText: student.username }).first()
  await expect(requestRow).toBeVisible({ timeout: 15000 })
  await requestRow.getByRole('button', { name: '批准' }).click()
  await requestRow.getByRole('button', { name: '确认批准' }).click()
  // Approved requests leave the pending list after the server-side transaction.
  await expect(requestRow).toHaveCount(0, { timeout: 15000 })

  // Admin also sees the student's feedback.
  await page.locator('.admin-tab', { hasText: 'Feedback' }).click()
  await expect(page.locator('tr', { hasText: '希望能导出对话记录' }).first()).toBeVisible({ timeout: 15000 })

  // ---------- 14. Student balance increased after approval ----------
  await logout(page)
  await page.goto('/login')
  await page.locator('#username').fill(student.username)
  await page.locator('#password').fill(student.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  const afterTopup = await apiBalance(page)
  expect(afterTopup).toBeGreaterThan(spent)

  // ---------- 15. Persistence: reload keeps conversation; re-login keeps project ----------
  await page.goto('/chat')
  await expect(page.locator('.conversation-list')).not.toBeEmpty({ timeout: 15000 })
  await logout(page)
  await page.goto('/login')
  await page.locator('#username').fill(student.username)
  await page.locator('#password').fill(student.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  await page.goto('/projects')
  await expect(page.getByText(projectName).first()).toBeVisible({ timeout: 15000 })
})
