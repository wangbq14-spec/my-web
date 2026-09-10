import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  approveRecharge,
  createInviteCode,
  disableInviteCode,
  getAdminOverview,
  getAnalytics,
  getUserDetail,
  getUserFeedback,
  getUserLedger,
  getUserRecharges,
  getUserUsage,
  grantCredits,
  listFeedback,
  listInviteCodes,
  listRechargeRequests,
  listUsers,
  rejectRecharge,
  updateFeedbackStatus,
} from './admin'

vi.mock('../http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('admin API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads the operations overview', () => {
    getAdminOverview()
    expect(http.get).toHaveBeenCalledWith('/admin/overview')
  })

  it('lists users with search and filter params', () => {
    listUsers({ search: 'alice', filter: 'new', limit: 30 })
    expect(http.get).toHaveBeenCalledWith('/admin/users', {
      params: { search: 'alice', filter: 'new', limit: 30, offset: 0 },
    })
  })

  it('loads user detail, usage, ledger, feedback and recharges', () => {
    getUserDetail(7)
    getUserUsage(7)
    getUserLedger(7)
    getUserFeedback(7)
    getUserRecharges(7)

    expect(http.get).toHaveBeenNthCalledWith(1, '/admin/users/7')
    expect(http.get).toHaveBeenNthCalledWith(2, '/admin/users/7/usage', { params: { limit: 20 } })
    expect(http.get).toHaveBeenNthCalledWith(3, '/admin/users/7/ledger', { params: { limit: 50 } })
    expect(http.get).toHaveBeenNthCalledWith(4, '/admin/users/7/feedback', { params: { limit: 20 } })
    expect(http.get).toHaveBeenNthCalledWith(5, '/admin/users/7/recharge-requests', { params: { limit: 20 } })
  })

  it('grants credits with reason and optional idempotency key', () => {
    grantCredits(7, { amount: 50, reason: '奖励', request_id: 'r-1' })
    expect(http.post).toHaveBeenCalledWith('/admin/users/7/grant-credits', {
      amount: 50,
      reason: '奖励',
      request_id: 'r-1',
    })
  })

  it('manages invite codes', () => {
    listInviteCodes()
    createInviteCode({ channel: 'classroom', max_uses: 20 })
    disableInviteCode(3)

    expect(http.get).toHaveBeenCalledWith('/admin/invite-codes', { params: { limit: 50, offset: 0 } })
    expect(http.post).toHaveBeenCalledWith('/admin/invite-codes', {
      channel: 'classroom',
      max_uses: 20,
    })
    expect(http.post).toHaveBeenCalledWith('/admin/invite-codes/3/disable')
  })

  it('lists recharge requests with optional status', () => {
    listRechargeRequests({ status: 'pending' })
    expect(http.get).toHaveBeenCalledWith('/admin/recharge-requests', {
      params: { status: 'pending', limit: 50, offset: 0 },
    })
  })

  it('approves or rejects a recharge request', () => {
    approveRecharge(9, '已到账')
    rejectRecharge(9, null)

    expect(http.post).toHaveBeenCalledWith('/admin/recharge-requests/9/approve', { note: '已到账' })
    expect(http.post).toHaveBeenCalledWith('/admin/recharge-requests/9/reject', null)
  })

  it('lists feedback and updates its status', () => {
    listFeedback({ status: 'new' })
    updateFeedbackStatus(5, 'reviewed')

    expect(http.get).toHaveBeenCalledWith('/admin/feedback', {
      params: { status: 'new', type: undefined, limit: 50, offset: 0 },
    })
    expect(http.post).toHaveBeenCalledWith('/admin/feedback/5/status', { status: 'reviewed' })
  })

  it('loads analytics for a range', () => {
    getAnalytics('30d')
    expect(http.get).toHaveBeenCalledWith('/admin/analytics', { params: { range: '30d' } })
  })
})
