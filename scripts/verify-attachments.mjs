// Real-browser verification for the image attachment lifecycle (P0-A), driven
// against the live dev stack: Vite 5173 -> API 8010 (real backend, real DB).
//
// Usage:
//   $env:TOKEN = <jwt for a real user>
//   node scripts/verify-attachments.mjs
//
// Covers: file-select thumbnail, Ctrl+V paste thumbnail, delete, send with
// image (real vision), and thumbnail persistence after a full page reload.

import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173'
const TOKEN = process.env.TOKEN
if (!TOKEN) throw new Error('TOKEN env var is required')

// 1x1 red PNG (enough for a visible thumbnail).
const PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
const PNG_BYTES = Buffer.from(PNG_B64, 'base64')

const results = []
function check(name, ok, extra = '') {
  results.push({ name, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()

try {
  await page.addInitScript((token) => {
    localStorage.setItem('access_token', token)
  }, TOKEN)

  await page.goto(`${BASE}/chat`)
  await page.locator('.composer-input').waitFor({ timeout: 15000 })

  // 1. File select -> thumbnail (NOT "图片已失效").
  await page.locator('input[aria-label="上传图片"]').setInputFiles({
    name: 'selected.png', mimeType: 'image/png', buffer: PNG_BYTES,
  })
  const selThumb = page.locator('.composer-attachments .attachment-thumbnail').first()
  await selThumb.waitFor({ timeout: 15000 })
  const selLost = await page.locator('.attachment-lost').count()
  const selImg = await selThumb.locator('img').count()
  check('file-select shows thumbnail', selLost === 0 && selImg === 1, `lost=${selLost} img=${selImg}`)

  // 2. Ctrl+V paste -> second thumbnail.
  await page.evaluate((b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const file = new File([bytes], 'pasted.png', { type: 'image/png' })
    const dt = new DataTransfer()
    dt.items.add(file)
    const event = new ClipboardEvent('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'clipboardData', { value: dt })
    document.querySelector('.composer').dispatchEvent(event)
  }, PNG_B64)
  await page.waitForFunction(() => {
    const items = document.querySelectorAll('.composer-attachments .attachment-thumbnail')
    return items.length >= 2
  }, { timeout: 15000 })
  const pasteLost = await page.locator('.attachment-lost').count()
  check('paste shows second thumbnail', pasteLost === 0, `lost=${pasteLost}`)

  // 3. Delete the pasted image -> back to one.
  await page.locator('.composer-attachment').nth(1).locator('button[aria-label^="删除附件"]').click()
  await page.waitForFunction(() => {
    return document.querySelectorAll('.composer-attachments .attachment-thumbnail').length === 1
  }, { timeout: 10000 })
  check('delete removes attachment', true)

  // 4. Send the remaining image (real vision via kimi-k3). Wait for the stream
  // to fully finish (assistant text present AND no longer `.is-streaming`) so
  // the server commits the message before we reload.
  await page.locator('.composer-input').fill('这张图里有什么？')
  await page.locator('.send-btn').first().click()
  await page.waitForFunction(() => {
    const el = [...document.querySelectorAll('.assistant-message')].pop()
    return Boolean(el && el.innerText.trim().length > 0 && !el.classList.contains('is-streaming'))
  }, { timeout: 150000 })
  await page.waitForTimeout(1500)
  const asstText = await page.locator('.assistant-message').last().innerText()
  check('assistant replied after image send', asstText.trim().length > 0)

  // 5. Reload -> the URL carries ?conversation_id=..., so the route watcher
  // re-selects the conversation and reloads messages (incl. the attachment).
  await page.reload()
  await page.locator('.messages .message').first().waitFor({ timeout: 15000 })
  const histThumb = page.locator('.message .attachment-thumbnail').first()
  await histThumb.waitFor({ timeout: 15000 })
  const histLost = await page.locator('.attachment-lost').count()
  const histImg = await histThumb.locator('img').count()
  check('thumbnail persists after reload', histLost === 0 && histImg === 1, `lost=${histLost} img=${histImg}`)
} catch (err) {
  console.error('SCRIPT ERROR:', err.message)
  results.push({ name: 'script', ok: false, error: err.message })
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
