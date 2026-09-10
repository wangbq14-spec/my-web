import http from '../http'

export function getBalance() {
  return http.get('/me/balance')
}

export function listUsage(params = {}) {
  return http.get('/me/usage', { params })
}
