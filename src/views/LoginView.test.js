import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from './LoginView.vue'

const router = vi.hoisted(() => ({
  replace: vi.fn(),
}))
const authStore = vi.hoisted(() => ({
  loading: false,
  login: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => router,
}))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => authStore,
}))

describe('LoginView', () => {
  beforeEach(() => {
    router.replace.mockReset()
    authStore.login.mockReset()
    authStore.login.mockResolvedValue()
  })

  it('redirects to /chat after a successful login', async () => {
    const wrapper = mount(LoginView)

    await wrapper.find('#username').setValue('alice')
    await wrapper.find('#password').setValue('secret')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(authStore.login).toHaveBeenCalledWith({
      username: 'alice',
      password: 'secret',
    })
    expect(router.replace).toHaveBeenCalledWith('/chat')
  })
})
