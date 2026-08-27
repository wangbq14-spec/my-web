import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

const authApi = vi.hoisted(() => ({
  login: vi.fn(),
  getCurrentUser: vi.fn(),
}))

vi.mock('../api/modules/auth', () => authApi)

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    authApi.login.mockReset()
    authApi.getCurrentUser.mockReset()
  })

  it('登录成功后保存 token 并获取当前用户', async () => {
    authApi.login.mockResolvedValue({ access_token: 'token-123' })
    authApi.getCurrentUser.mockResolvedValue({
      username: 'alice',
      email: 'alice@example.com',
    })

    const store = useAuthStore()

    await store.login({ username: 'alice', password: 'secret' })

    expect(store.token).toBe('token-123')
    expect(store.isAuthenticated).toBe(true)
    expect(store.user).toEqual({ username: 'alice', email: 'alice@example.com' })
    expect(localStorage.getItem('access_token')).toBe('token-123')
  })

  it('登录响应缺少 token 时抛错且不进入已登录状态', async () => {
    authApi.login.mockResolvedValue({ message: 'ok' })

    const store = useAuthStore()

    await expect(
      store.login({ username: 'alice', password: 'x' }),
    ).rejects.toThrow()

    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('fetchCurrentUser 失败时清除认证状态', async () => {
    authApi.getCurrentUser.mockRejectedValue({ status: 401, message: 'unauthorized' })

    const store = useAuthStore()
    store.token = 'stale-token'
    localStorage.setItem('access_token', 'stale-token')

    await expect(store.fetchCurrentUser()).rejects.toBeTruthy()

    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('logout 清理 token 和 user', async () => {
    authApi.login.mockResolvedValue({ access_token: 'token-123' })
    authApi.getCurrentUser.mockResolvedValue({ username: 'alice' })

    const store = useAuthStore()
    await store.login({ username: 'alice', password: 'x' })

    store.logout()

    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
  })
})
