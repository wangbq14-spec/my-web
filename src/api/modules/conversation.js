import http from '../http'

export function listConversations() {
  return http.get('/conversations')
}

export function createConversation(data) {
  return http.post('/conversations', data)
}

export function getConversation(id) {
  return http.get(`/conversations/${id}`)
}

export function deleteConversation(id) {
  return http.delete(`/conversations/${id}`)
}

export function updateConversation(id, data) {
  return http.patch(`/conversations/${id}`, data)
}
