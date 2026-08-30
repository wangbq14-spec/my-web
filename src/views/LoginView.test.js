import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from './LoginView.vue'
import RegisterView from './RegisterView.vue'

const router = vi.hoisted(() => ({
  replace: vi.fn(),
}))
const authStore = vi.hoisted(() => ({
  loading: false,
  login: vi.fn(),
  register: vi.fn(),
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
    authStore.register.mockReset()
    authStore.register.mockResolvedValue()
    authStore.loading = false
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

describe('RegisterView', () => {
  beforeEach(() => {
    router.replace.mockReset()
    authStore.register.mockReset()
    authStore.register.mockResolvedValue()
    authStore.loading = false
  })

  it('shows a validation error for an invalid email address', async () => {
    const wrapper = mount(RegisterView)

    await wrapper.find('#email').setValue('not-an-email')
    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.get('[role="alert"]').text()).toBe('请输入有效的邮箱地址')
    expect(authStore.register).not.toHaveBeenCalled()
  })

  it('registers and redirects to /chat after a successful registration', async () => {
    const wrapper = mount(RegisterView)

    await wrapper.find('#email').setValue('alice@example.com')
    await wrapper.find('#username').setValue('alice')
    await wrapper.find('#password').setValue('password-123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(authStore.register).toHaveBeenCalledWith({
      email: 'alice@example.com',
      username: 'alice',
      password: 'password-123',
    })
    expect(router.replace).toHaveBeenCalledWith('/chat')
  })

  it('shows the registration error when registration fails', async () => {
    authStore.register.mockRejectedValue({ message: '该邮箱已被注册' })
    const wrapper = mount(RegisterView)

    await wrapper.find('#email').setValue('alice@example.com')
    await wrapper.find('#username').setValue('alice')
    await wrapper.find('#password').setValue('password-123')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('该邮箱已被注册')
    expect(router.replace).not.toHaveBeenCalled()
  })
})
