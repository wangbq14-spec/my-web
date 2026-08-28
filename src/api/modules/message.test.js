import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import { listMessages } from './message'

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('message API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listMessages URL 正确', () => {
    listMessages(3)

    expect(http.get).toHaveBeenCalledWith('/conversations/3/messages')
  })
})
