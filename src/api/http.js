import axios from 'axios'
import { clearAccessToken, getAccessToken } from '../utils/token'

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 10000,
})

http.interceptors.request.use(
  (config) => {
    const token = getAccessToken()

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    return config
  },
  (error) => Promise.reject(error),
)

http.interceptors.response.use(
  (response) => response.data,

  (error) => {
    const status = error.response?.status

    if (status === 401) {
      clearAccessToken()
      if (unauthorizedHandler) {
        unauthorizedHandler()
      }
    }

    const responseData = error.response?.data
    const detail = responseData?.detail

    const normalizedError = {
      status: status ?? 0,
      message:
        responseData?.message ||
        (typeof detail === 'string' ? detail : null) ||
        error.message ||
        '请求失败，请稍后重试',
      data: responseData ?? null,
    }

    return Promise.reject(normalizedError)
  },
)

export default http
