import http from '../http'

export function listModels() {
  return http.get('/models')
}
