import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from './index'

const authStore = vi.hoisted(() => ({
  isAuthenticated: false,
}))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => authStore,
}))

describe('router authentication guard', () => {
  beforeEach(async () => {
    authStore.isAuthenticated = false
    await router.push('/')
  })

  it('redirects an authenticated user from /login to /chat', async () => {
    authStore.isAuthenticated = true

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('chat')
  })

  it('redirects an unauthenticated user from /chat to /login', async () => {
    authStore.isAuthenticated = false

    await router.push('/chat')

    expect(router.currentRoute.value.name).toBe('login')
  })
})
