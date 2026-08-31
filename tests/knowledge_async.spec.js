import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

test('document upload polls to ready and retries a failed document', async ({ page }) => {
  const documents = [
    {
      id: 1,
      original_filename: 'failed.txt',
      file_size: 6,
      status: 'failed',
      error_message: null,
      created_at: '2026-08-29T08:30:00Z',
    },
  ]
  let uploadedDocumentPolls = 0
  let retryRequests = 0

  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, username: 'e2e-user', email: 'e2e@example.com' },
  }))
  await page.route(/\/documents(?:\/\d+(?:\/retry)?)?$/, async (route) => {
    const request = route.request()
    const method = request.method()
    const pathname = new URL(request.url()).pathname.replace(/^\/api/, '')

    if (method === 'GET' && pathname === '/documents') {
      await route.fulfill({ json: documents })
      return
    }
    if (method === 'POST' && pathname === '/documents') {
      expect(route.request().headers()['content-type']).toContain('multipart/form-data')
      const document = {
        id: 2,
        original_filename: 'queued.txt',
        file_size: 5,
        status: 'queued',
        error_message: null,
        created_at: '2026-08-29T08:31:00Z',
      }
      documents.push(document)
      await route.fulfill({ status: 202, json: document })
      return
    }
    if (method === 'GET' && pathname === '/documents/2') {
      uploadedDocumentPolls += 1
      const status = uploadedDocumentPolls === 1 ? 'processing' : 'ready'
      documents[1] = { ...documents[1], status }
      await route.fulfill({ json: documents[1] })
      return
    }
    if (method === 'POST' && pathname === '/documents/1/retry') {
      retryRequests += 1
      documents[0] = { ...documents[0], status: 'queued', error_message: null }
      await route.fulfill({ json: documents[0] })
      return
    }

    await route.fallback()
  })

  await page.goto('/knowledge')
  await expect(page.getByText('failed.txt')).toBeVisible()
  await expect(page.locator('.retry-btn')).toHaveText('重新处理')

  await page.locator('input[type="file"]').setInputFiles({
    name: 'queued.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('hello'),
  })
  await page.locator('.upload-area .upload-btn').click()

  const uploadedStatus = page.locator('.document-item').filter({ hasText: 'queued.txt' }).locator('.document-status')
  await expect(page.getByText('queued.txt')).toBeVisible()
  await expect(uploadedStatus).not.toBeEmpty()
  const processingStatus = await uploadedStatus.textContent()

  await expect.poll(() => uploadedStatus.textContent()).not.toBe(processingStatus)
  await page.waitForTimeout(2200)
  expect(uploadedDocumentPolls).toBe(2)

  await page.locator('.retry-btn').click()
  await expect.poll(() => retryRequests).toBe(1)
})
