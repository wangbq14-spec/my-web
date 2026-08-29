import { expect, test } from '@playwright/test'

function sortByUpdatedAt(conversations) {
  return [...conversations].sort((left, right) => (
    new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  ))
}

async function mockConversations(page) {
  let nextId = 3
  const conversations = [
    { id: 1, title: '项目计划', updated_at: '2026-08-28T08:00:00Z' },
    { id: 2, title: '读书笔记', updated_at: '2026-08-27T08:00:00Z' },
  ]

  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-token')
  })

  await page.route('**/conversations**', async (route) => {
    const request = route.request()
    const method = request.method()
    const pathname = new URL(request.url()).pathname
    const apiPath = pathname.replace(/^\/api/, '')
    const match = apiPath.match(/^\/conversations\/(\d+)/)
    const conversationId = match ? Number(match[1]) : null

    if (method === 'GET' && apiPath === '/conversations') {
      await route.fulfill({ json: sortByUpdatedAt(conversations) })
      return
    }

    if (method === 'POST' && apiPath === '/conversations') {
      const conversation = {
        id: nextId,
        title: request.postDataJSON().title,
        updated_at: '2026-08-29T08:00:00Z',
      }
      nextId += 1
      conversations.unshift(conversation)
      await route.fulfill({ status: 201, json: conversation })
      return
    }

    if (method === 'GET' && /\/messages$/.test(apiPath)) {
      await route.fulfill({ json: [] })
      return
    }

    if (method === 'POST' && /\/chat\/stream$/.test(apiPath)) {
      const conversation = conversations.find((item) => item.id === conversationId)
      if (conversation) {
        conversation.title = '周末行程规划'
        conversation.updated_at = '2026-08-30T08:00:00Z'
      }
      await route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
        body: 'event: done\ndata: {"user_message_id": 10, "assistant_message_id": 11, "model": "e2e"}\n\n',
      })
      return
    }

    if (method === 'PATCH' && conversationId !== null) {
      const conversation = conversations.find((item) => item.id === conversationId)
      conversation.title = request.postDataJSON().title
      await route.fulfill({ json: conversation })
      return
    }

    if (method === 'DELETE' && conversationId !== null) {
      const index = conversations.findIndex((item) => item.id === conversationId)
      conversations.splice(index, 1)
      await route.fulfill({ status: 204 })
      return
    }

    await route.fallback()
  })

  return conversations
}

async function openConversationMenu(page, title) {
  const row = page.locator('.conversation-row').filter({ hasText: title })
  await row.locator('.conversation-more').click()
  return row
}

test('creates a new conversation', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')

  await page.getByRole('button', { name: '新建对话' }).click()

  await expect(page.locator('.conversation-item[aria-current="true"]')).toContainText('新对话')
})

test('shows the automatic title after the first message', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: '新建对话' }).click()
  await page.locator('.composer-input').fill('帮我规划周末行程')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByRole('button', { name: '周末行程规划' })).toBeVisible()
})

test('renames a conversation', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')

  await openConversationMenu(page, '项目计划')
  await page.getByRole('menuitem', { name: '重命名' }).click()
  const input = page.getByRole('textbox', { name: '重命名会话' })
  await input.fill('已重命名项目')
  await input.press('Enter')

  await expect(page.getByRole('button', { name: '已重命名项目' })).toBeVisible()
})

test('filters conversations by search title', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')

  await page.getByRole('searchbox', { name: '搜索对话' }).fill('读书')

  await expect(page.locator('.conversation-list')).toContainText('读书笔记')
  await expect(page.locator('.conversation-list')).not.toContainText('项目计划')
})

test('deletes a conversation', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')

  await openConversationMenu(page, '项目计划')
  await page.getByRole('menuitem', { name: '删除' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('删除后，该对话及其消息将无法恢复。')
  await dialog.getByRole('button', { name: '删除', exact: true }).click()

  await expect(page.locator('.conversation-list')).not.toContainText('项目计划')
})

test('keeps conversation changes after a refresh', async ({ page }) => {
  await mockConversations(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: '新建对话' }).click()
  await openConversationMenu(page, '新对话')
  await page.getByRole('menuitem', { name: '重命名' }).click()
  const input = page.getByRole('textbox', { name: '重命名会话' })
  await input.fill('刷新后仍存在')
  await input.press('Enter')
  await page.reload()

  await expect(page.locator('.conversation-list')).toContainText('刷新后仍存在')
})

test('redirects unauthenticated users from the protected conversation page to login', async ({ page }) => {
  await page.goto('/chat')

  await expect(page).toHaveURL(/\/login\?redirect=\/chat/)
})
