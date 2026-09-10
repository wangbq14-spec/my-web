import http from '../http'

export function submitFeedback(payload) {
  return http.post('/feedback', payload)
}
