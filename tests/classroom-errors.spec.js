import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const FIXTURE = JSON.parse(readFileSync(fileURLToPath(new URL('fixtures/classroom-codes.json', import.meta.url)), 'utf8'))
const API = 'http://127.0.0.1:8011/api'

const stamp = Date.now()
const email = (name) => `${name}-${stamp}@example.com`

async function fillRegister(page, username, inviteCode) {
  await page.goto('/register')
  await page.locator('#email').fill(email(username))
  await page.locator('#username').fill(username)
  await page.locator('#password').fill('secret123')
  if (inviteCode) await page.locator('#inviteCode').fill(inviteCode)
  await page.getByRole('button', { name: '注册' }).click()
}

async function login(page, username, password) {
  await page.goto('/login')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
}

async function apiLogin(page, username, password) {
  const res = await page.request.post(`${API}/auth/login`, {
    data: { username, password },
  })
  return res
}

test.describe.configure({ mode: 'serial' })

test('error paths: invite codes', async ({ page }) => {
  test.setTimeout(120000)

  // 1. invalid invite code
  await fillRegister(page, `err_invalid_${stamp}`, FIXTURE.invalid)
  await expect(page.getByRole('alert')).toContainText('邀请码无效', { timeout: 15000 })

  // 2. expired invite code
  await fillRegister(page, `err_expired_${stamp}`, FIXTURE.expired)
  await expect(page.getByRole('alert')).toContainText('邀请码已过期', { timeout: 15000 })

  // 3. max-used invite code
  await fillRegister(page, `err_maxused_${stamp}`, FIXTURE.one_use)
  await expect(page.getByRole('alert')).toContainText('邀请码已用完', { timeout: 15000 })

  // 4. disabled invite code
  await fillRegister(page, `err_disabled_${stamp}`, FIXTURE.disabled)
  await expect(page.getByRole('alert')).toContainText('邀请码无效', { timeout: 15000 })
})

test('error paths: auth + authorization', async ({ page }) => {
  test.setTimeout(120000)

  // 5. wrong password rejected
  await login(page, FIXTURE.poor.username, 'wrong-password-123')
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 15000 })
  await expect(page).toHaveURL(/\/login$/)

  // 6. normal user cannot open /admin (router guard) and API returns 403
  await login(page, FIXTURE.poor.username, FIXTURE.poor.password)
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  const res = await page.request.get(`${API}/admin/overview`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.status()).toBe(403)
})

test('error paths: 402 insufficient credits', async ({ page }) => {
  test.setTimeout(120000)
  // Dedicated zero-balance user: deterministic 402 regardless of other specs
  // topping up the "poor" fixture user through the recharge flow.
  await login(page, FIXTURE.zero.username, FIXTURE.zero.password)
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  await page.locator('.composer-input').fill('这条消息会触发 402')
  await page.locator('.send-btn').first().click()
  await expect(page.getByText('积分不足，无法继续生成')).toBeVisible({ timeout: 20000 })
})

test('error paths: image validation', async ({ page }) => {
  test.setTimeout(120000)
  await login(page, FIXTURE.poor.username, FIXTURE.poor.password)
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })

  // 7. image too large (>10MB)
  await page.locator('input[aria-label="上传图片"]').setInputFiles({
    name: 'huge.png',
    mimeType: 'image/png',
    buffer: Buffer.alloc(11 * 1024 * 1024, 1),
  })
  await expect(page.getByText('图片太大（>10MB）')).toBeVisible()

  // 8. unsupported image format
  await page.locator('input[aria-label="上传图片"]').setInputFiles({
    name: 'anim.gif',
    mimeType: 'image/gif',
    buffer: Buffer.from('GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'),
  })
  await expect(page.getByText('图片格式不支持')).toBeVisible()
})

test('error paths: failed document can be retried', async ({ page }) => {
  test.setTimeout(120000)
  await login(page, FIXTURE.poor.username, FIXTURE.poor.password)
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15000 })
  await page.goto('/knowledge')
  // A truncated/fake PDF reliably fails parsing on the worker. Unique name per
  // run so accumulated rows from earlier runs never trip strict locators.
  const pdfName = `broken-${Date.now()}.pdf`
  await page.locator('#document-upload').setInputFiles({
    name: pdfName,
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF', 'utf8'),
  })
  await page.locator('.upload-btn').click()
  const row = page.locator('.document-item').filter({ hasText: pdfName })
  await expect(row).toBeVisible()
  await expect(row.locator('.document-status')).toHaveText('处理失败', { timeout: 30000 })
  await expect(row.locator('.retry-btn')).toBeVisible()
  await row.locator('.retry-btn').click()
  await expect(row.locator('.document-status')).toHaveText(/处理失败|排队中/, { timeout: 30000 })
})

test('error paths: recharge double approve is rejected', async ({ page }) => {
  test.setTimeout(120000)
  // Student submits a recharge request via API.
  const loginRes = await apiLogin(page, FIXTURE.poor.username, FIXTURE.poor.password)
  expect(loginRes.ok()).toBeTruthy()
  const studentToken = (await loginRes.json()).access_token
  const reqRes = await page.request.post(`${API}/me/recharge-requests`, {
    headers: { Authorization: `Bearer ${studentToken}` },
    data: { amount_cny: 10 },
  })
  expect(reqRes.ok()).toBeTruthy()
  const requestId = (await reqRes.json()).id

  // Admin approves once, then a second approve must fail (409/400).
  const adminRes = await apiLogin(page, FIXTURE.admin.username, FIXTURE.admin.password)
  const adminToken = (await adminRes.json()).access_token
  const first = await page.request.post(`${API}/admin/recharge-requests/${requestId}/approve`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { note: 'approve once' },
  })
  expect([200, 201]).toContain(first.status())
  const second = await page.request.post(`${API}/admin/recharge-requests/${requestId}/approve`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { note: 'approve twice' },
  })
  expect([400, 409]).toContain(second.status())
})
