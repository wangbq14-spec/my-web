import http from '../http'

// POST /auth/login —— 约定返回 { access_token: string }（或 { token }），可选附带 user
export function login(credentials) {
  return http.post('/auth/login', credentials)
}

export function register(payload) {
  return http.post('/auth/register', payload)
}

// GET /auth/me —— 约定返回当前用户对象
export function getCurrentUser() {
  return http.get('/auth/me')
}
