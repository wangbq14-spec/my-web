import http from '../http'

export function listDocuments() {
  return http.get('/documents')
}

export function getDocument(id) {
  return http.get(`/documents/${id}`)
}

export function deleteDocument(id) {
  return http.delete(`/documents/${id}`)
}

export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  return http.post('/documents', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}
