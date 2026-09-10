import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import { getBalance, listUsage } from './usage'

vi.mock('../http', () => ({ default: { get: vi.fn() } }))

describe('usage API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads balance and usage history with query params', () => {
    getBalance()
    listUsage({ limit: 20, offset: 10 })

    expect(http.get).toHaveBeenNthCalledWith(1, '/me/balance')
    expect(http.get).toHaveBeenNthCalledWith(2, '/me/usage', { params: { limit: 20, offset: 10 } })
  })
})
