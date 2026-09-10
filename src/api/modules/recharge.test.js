import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  cancelRechargeRequest,
  getPaymentInfo,
  getRechargeQuote,
  listRechargeRequests,
  submitCustomRecharge,
  submitRecharge,
} from './recharge'

vi.mock('../http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('recharge API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads payment info and recharge requests', () => {
    getPaymentInfo()
    listRechargeRequests()

    expect(http.get).toHaveBeenNthCalledWith(1, '/me/payment-info')
    expect(http.get).toHaveBeenNthCalledWith(2, '/me/recharge-requests')
  })

  it('submits a recharge request with the provided payload', () => {
    submitRecharge({ package_code: 'p1', credits_requested: 1000, note: '已付款' })

    expect(http.post).toHaveBeenNthCalledWith(1, '/me/recharge-requests', {
      package_code: 'p1',
      credits_requested: 1000,
      note: '已付款',
    })
  })

  it('quotes a custom amount for server-side pricing', () => {
    getRechargeQuote('10')

    expect(http.post).toHaveBeenNthCalledWith(1, '/me/recharge-quote', { amount_cny: '10' })
  })

  it('submits a custom recharge request without client-side credits', () => {
    submitCustomRecharge('12')

    expect(http.post).toHaveBeenNthCalledWith(1, '/me/recharge-requests', { amount_cny: '12' })
  })

  it('cancels a recharge request by id', () => {
    cancelRechargeRequest(42)

    expect(http.post).toHaveBeenNthCalledWith(1, '/me/recharge-requests/42/cancel')
  })
})
