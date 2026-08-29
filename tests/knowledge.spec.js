import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

test('unauthenticated users are redirected from /knowledge to /login', async ({ page }) => {
  await page.goto('/knowledge')

  await expect(page).toHaveURL(/\/login/)
})

test('知识库可以上传并删除文档', async ({ page }) => {
  const documents = []

  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })
  await page.route(/\/documents(?:\/\d+)?$/, async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ json: documents })
      return
    }
    if (method === 'POST') {
      const contentType = route.request().headers()['content-type']
      expect(contentType).toContain('multipart/form-data')
      expect(contentType).toContain('boundary=')
      const document = {
        id: 1,
        original_filename: 'notes.txt',
        file_size: 5,
        status: 'ready',
        error_message: null,
        created_at: '2026-08-29T08:30:00Z',
      }
      documents.push(document)
      await route.fulfill({ status: 201, json: document })
      return
    }
    if (method === 'DELETE') {
      documents.splice(0, documents.length)
      await route.fulfill({ status: 204 })
      return
    }
    await route.fallback()
  })

  await page.goto('/knowledge')
  await expect(page.getByText('知识库还是空的')).toBeVisible()

  await page.locator('input[type="file"]').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('hello'),
  })
  await page.locator('.upload-area .upload-btn').click()

  await expect(page.getByText('notes.txt')).toBeVisible()
  await expect(page.getByText('可用', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '删除文档' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '删除', exact: true }).click()

  await expect(page.getByText('知识库还是空的')).toBeVisible()
})
