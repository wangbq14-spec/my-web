import http from '../http'

export function getAdminOverview() {
  return http.get('/admin/overview')
}

export function listUsers({ search = '', filter = '', limit = 50, offset = 0 } = {}) {
  return http.get('/admin/users', { params: { search, filter, limit, offset } })
}

export function getUserDetail(userId) {
  return http.get(`/admin/users/${userId}`)
}

export function getUserUsage(userId) {
  return http.get(`/admin/users/${userId}/usage`, { params: { limit: 20 } })
}

export function getUserLedger(userId) {
  return http.get(`/admin/users/${userId}/ledger`, { params: { limit: 50 } })
}

export function getUserFeedback(userId) {
  return http.get(`/admin/users/${userId}/feedback`, { params: { limit: 20 } })
}

export function getUserRecharges(userId) {
  return http.get(`/admin/users/${userId}/recharge-requests`, { params: { limit: 20 } })
}

export function grantCredits(userId, payload) {
  return http.post(`/admin/users/${userId}/grant-credits`, payload)
}

export function listInviteCodes({ limit = 50, offset = 0 } = {}) {
  return http.get('/admin/invite-codes', { params: { limit, offset } })
}

export function createInviteCode(payload) {
  return http.post('/admin/invite-codes', payload)
}

export function disableInviteCode(inviteId) {
  return http.post(`/admin/invite-codes/${inviteId}/disable`)
}

export function listRechargeRequests({ status = '', limit = 50, offset = 0 } = {}) {
  return http.get('/admin/recharge-requests', {
    params: { status: status || undefined, limit, offset },
  })
}

export function approveRecharge(requestId, note = null) {
  return http.post(`/admin/recharge-requests/${requestId}/approve`, note ? { note } : null)
}

export function rejectRecharge(requestId, note = null) {
  return http.post(`/admin/recharge-requests/${requestId}/reject`, note ? { note } : null)
}

export function listFeedback({ status = '', type = '', limit = 50, offset = 0 } = {}) {
  return http.get('/admin/feedback', {
    params: { status: status || undefined, type: type || undefined, limit, offset },
  })
}

export function updateFeedbackStatus(feedbackId, status) {
  return http.post(`/admin/feedback/${feedbackId}/status`, { status })
}

export function getAnalytics(range) {
  return http.get('/admin/analytics', { params: { range } })
}
