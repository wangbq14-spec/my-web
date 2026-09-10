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

  it('redirects an authenticated user from /register to /chat', async () => {
    authStore.isAuthenticated = true

    await router.push('/register')

    expect(router.currentRoute.value.name).toBe('chat')
  })

  it('keeps public routes public for unauthenticated users', async () => {
    for (const path of ['/', '/login', '/register']) {
      await router.push(path)
      expect(router.currentRoute.value.path).toBe(path)
    }
  })

  it('marks chat, knowledge, project, and task routes as requiring authentication', () => {
    expect(router.getRoutes().find((route) => route.name === 'chat')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'knowledge')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'projects')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'project-detail')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'tasks')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'task-detail')?.meta.requiresAuth).toBe(true)
    expect(router.getRoutes().find((route) => route.name === 'login')?.meta.requiresAuth).toBeUndefined()
    expect(router.getRoutes().find((route) => route.name === 'register')?.meta.requiresAuth).toBeUndefined()
  })

  it('redirects an unauthenticated user from /chat to /login', async () => {
    authStore.isAuthenticated = false

    await router.push('/chat')

    expect(router.currentRoute.value.name).toBe('login')
  })

  it('marks settings routes as protected inside the app shell', () => {
    for (const name of ['settings', 'settings-account', 'settings-appearance', 'settings-usage', 'settings-billing']) {
      expect(router.getRoutes().find((candidate) => candidate.name === name)?.meta.requiresAuth).toBe(true)
    }
  })

  it('redirects legacy /usage and /pricing links into Settings', async () => {
    authStore.isAuthenticated = true

    await router.push('/usage')
    expect(router.currentRoute.value.path).toBe('/settings/usage')
    await router.push('/pricing')
    expect(router.currentRoute.value.path).toBe('/settings/billing')
  })

  it('redirects an unauthenticated user from usage to login', async () => {
    await router.push('/usage')
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/settings/usage')
  })

  it('keeps the protected conversation path as the post-login redirect target', async () => {
    authStore.isAuthenticated = false

    await router.push('/chat')

    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/chat')
  })

  it('redirects an unauthenticated user from /knowledge to /login', async () => {
    authStore.isAuthenticated = false

    await router.push('/knowledge')

    expect(router.currentRoute.value.name).toBe('login')
  })

  it('redirects an unauthenticated user from a project detail route to /login', async () => {
    authStore.isAuthenticated = false

    await router.push('/projects/7')

    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/projects/7')
  })

  it('redirects an unauthenticated user from a task detail route to /login', async () => {
    authStore.isAuthenticated = false

    await router.push('/tasks/12')

    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/tasks/12')
  })
})
