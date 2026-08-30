import http from '../http'

export function listProjects() {
  return http.get('/projects')
}

export function createProject(data) {
  return http.post('/projects', data)
}

export function getProject(id) {
  return http.get(`/projects/${id}`)
}

export function updateProject(id, data) {
  return http.patch(`/projects/${id}`, data)
}

export function deleteProject(id) {
  return http.delete(`/projects/${id}`)
}

export function listProjectConversations(id) {
  return http.get(`/projects/${id}/conversations`)
}

export function listProjectDocuments(id) {
  return http.get(`/projects/${id}/documents`)
}
