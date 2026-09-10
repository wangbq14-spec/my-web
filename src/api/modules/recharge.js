import http from '../http'

export function getPaymentInfo() {
  return http.get('/me/payment-info')
}

export function submitRecharge(payload) {
  return http.post('/me/recharge-requests', payload)
}

// Custom-amount recharge: the server computes credits from amount_cny; the
// client never sends credits for custom orders.
export function getRechargeQuote(amountCny) {
  return http.post('/me/recharge-quote', { amount_cny: amountCny })
}

export function submitCustomRecharge(amountCny) {
  return http.post('/me/recharge-requests', { amount_cny: amountCny })
}

export function listRechargeRequests() {
  return http.get('/me/recharge-requests')
}

export function cancelRechargeRequest(id) {
  return http.post(`/me/recharge-requests/${id}/cancel`)
}
