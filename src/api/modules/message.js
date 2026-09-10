import http from '../http'

export function listMessages(conversationId) {
  return http.get(`/conversations/${conversationId}/messages`)
}
