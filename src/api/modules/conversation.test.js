import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  updateConversation,
} from './conversation'

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('conversation API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listConversations URL 正确', () => {
    listConversations()

    expect(http.get).toHaveBeenCalledWith('/conversations')
  })

  it('createConversation URL 正确', () => {
    createConversation({ title: 'x' })

    expect(http.post).toHaveBeenCalledWith('/conversations', { title: 'x' })
  })

  it('getConversation URL 正确', () => {
    getConversation(2)

    expect(http.get).toHaveBeenCalledWith('/conversations/2')
  })

  it('deleteConversation sends the correct URL', () => {
    deleteConversation(2)

    expect(http.delete).toHaveBeenCalledWith('/conversations/2')
  })

  it('updateConversation sends the correct URL and body', () => {
    updateConversation(2, { title: 'new title' })

    expect(http.patch).toHaveBeenCalledWith('/conversations/2', { title: 'new title' })
  })

  it('returns the list response so callers can sort and filter it client-side', async () => {
    const conversations = [{ id: 2, title: '最新对话', updated_at: '2026-08-29T08:00:00Z' }]
    http.get.mockResolvedValue(conversations)

    await expect(listConversations()).resolves.toBe(conversations)
  })

  it('returns the created conversation so the caller can make it active immediately', async () => {
    const conversation = { id: 3, title: '新建对话' }
    http.post.mockResolvedValue(conversation)

    await expect(createConversation({ title: '新建对话' })).resolves.toBe(conversation)
  })
})
