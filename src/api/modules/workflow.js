import http from '../http'

export function listTasks(status) {
  if (status) return http.get('/tasks', { params: { status } })
  return http.get('/tasks')
}

export function createTask(data) {
  return http.post('/tasks', data)
}

export function getTask(id) {
  return http.get(`/tasks/${id}`)
}

export function startTask(id) {
  return http.post(`/tasks/${id}/start`, undefined, { timeout: 120000 })
}

export function cancelTask(id) {
  return http.post(`/tasks/${id}/cancel`)
}

export function retryTask(id) {
  return http.post(`/tasks/${id}/retry`)
}

export function approveTask(id, data = {}) {
  return http.post(`/tasks/${id}/approve`, data)
}

export function rejectTask(id, data = {}) {
  return http.post(`/tasks/${id}/reject`, data)
}

export function listArtifacts(id) {
  return http.get(`/tasks/${id}/artifacts`)
}
