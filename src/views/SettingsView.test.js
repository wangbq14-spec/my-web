import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from './SettingsView.vue'
import { useAuthStore } from '../stores/auth'

const routeMock = vi.hoisted(() => ({ path: '/settings', name: 'settings', params: {}, query: {} }))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => routerMock,
}))

const USER = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  role: 'admin',
  created_at: '2026-08-28T08:00:00Z',
}

function mountSettings() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore()
  authStore.user = { ...USER }
  const logoutSpy = vi.spyOn(authStore, 'logout')
  const wrapper = mount(SettingsView, {
    global: {
      plugins: [pinia],
      stubs: {
        UsageView: { template: '<div class="usage-stub">Usage content</div>' },
        PricingView: { template: '<div class="pricing-stub">Pricing content</div>' },
      },
    },
  })
  wrapper.authStore = authStore
  wrapper.logoutSpy = logoutSpy
  return wrapper
}

describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    routeMock.path = '/settings'
    routeMock.name = 'settings'
    routeMock.params = {}
    routeMock.query = {}
    delete document.documentElement.dataset.theme
  })

  it('renders the four settings categories', () => {
    const wrapper = mountSettings()

    const tabs = wrapper.findAll('.settings-tab').map((tab) => tab.text())
    expect(tabs).toEqual(['账号', '外观', '用量', '定价与充值'])
  })

  it('shows the account panel by default with real user data', () => {
    const wrapper = mountSettings()

    const fields = wrapper.find('.account-fields').text()
    expect(fields).toContain('alice')
    expect(fields).toContain('alice@example.com')
    expect(fields).toContain('管理员')
    expect(fields).toContain('2026')
  })

  it('navigates to a category when a tab is clicked', async () => {
    const wrapper = mountSettings()

    await wrapper.findAll('.settings-tab')[1].trigger('click')

    expect(routerMock.push).toHaveBeenCalledWith('/settings/appearance')
  })

  it('does not push when already on the target category', async () => {
    routeMock.name = 'settings-account'
    routeMock.path = '/settings/account'
    const wrapper = mountSettings()

    await wrapper.findAll('.settings-tab')[0].trigger('click')

    expect(routerMock.push).not.toHaveBeenCalled()
  })

  it('renders the embedded Usage view on /settings/usage', () => {
    routeMock.name = 'settings-usage'
    routeMock.path = '/settings/usage'
    const wrapper = mountSettings()

    expect(wrapper.find('.usage-stub').exists()).toBe(true)
    expect(wrapper.find('.pricing-stub').exists()).toBe(false)
  })

  it('renders the embedded Pricing view on /settings/billing', () => {
    routeMock.name = 'settings-billing'
    routeMock.path = '/settings/billing'
    const wrapper = mountSettings()

    expect(wrapper.find('.pricing-stub').exists()).toBe(true)
    expect(wrapper.find('.usage-stub').exists()).toBe(false)
  })

  it('switches the theme immediately and persists it', async () => {
    routeMock.name = 'settings-appearance'
    routeMock.path = '/settings/appearance'
    const wrapper = mountSettings()
    const [light, dark] = wrapper.findAll('.theme-option')

    await dark.trigger('click')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('omnixa-theme')).toBe('dark')

    await light.trigger('click')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('omnixa-theme')).toBe('light')
  })

  it('logs out from the account panel and goes to /login', async () => {
    const wrapper = mountSettings()

    await wrapper.get('.logout-btn').trigger('click')

    expect(wrapper.logoutSpy).toHaveBeenCalledOnce()
    expect(wrapper.authStore.user).toBeNull()
    expect(routerMock.replace).toHaveBeenCalledWith('/login')
  })
})
