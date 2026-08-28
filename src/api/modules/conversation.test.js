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
})
