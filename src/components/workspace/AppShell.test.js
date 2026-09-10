import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import AppShell from './AppShell.vue'
import { useWorkspaceStore } from '../../stores/workspace'

const routeMock = vi.hoisted(() => ({ fullPath: '/chat', name: 'chat', params: {}, query: {} }))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
const conversationApi = vi.hoisted(() => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  listConversations: vi.fn(),
  updateConversation: vi.fn(),
}))
const projectApi = vi.hoisted(() => ({ listProjects: vi.fn(), updateProject: vi.fn() }))

vi.mock('vue-router', () => ({
  RouterView: { template: '<main class="routed-content">Nested route content</main>' },
  useRoute: () => routeMock,
  useRouter: () => routerMock,
}))
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({ user: { username: 'alice' }, logout: vi.fn() }),
}))
vi.mock('../../api/modules/conversation', () => conversationApi)
vi.mock('../../api/modules/project', () => projectApi)

async function mountShell() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useWorkspaceStore()
  store.activeConversationId = 1
  const wrapper = mount(AppShell, {
    global: {
      plugins: [pinia],
      stubs: {
        BrandIdentity: { template: '<span>Omnixa</span>' },
        ThemeToggle: { template: '<button>主题</button>' },
      },
    },
  })
  wrapper.workspaceStore = store
  await flushPromises()
  return wrapper
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    routeMock.fullPath = '/chat'
    routeMock.name = 'chat'
    routeMock.params = {}
    routeMock.query = {}
    conversationApi.listConversations.mockResolvedValue([
      { id: 1, title: '当前会话', pinned: false, updated_at: '2026-08-30T08:00:00Z' },
    ])
    projectApi.listProjects.mockResolvedValue([{ id: 7, name: '产品发布', pinned: false }])
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
  })

  it('renders the shared WorkspaceSidebar and nested RouterView content', async () => {
    const wrapper = await mountShell()

    expect(wrapper.find('.sidebar').exists()).toBe(true)
    expect(wrapper.get('.routed-content').text()).toBe('Nested route content')
  })

  it('keeps active navigation highlighting inside the shared shell', async () => {
    routeMock.name = 'project-detail'
    routeMock.params = { id: '7' }
    const wrapper = await mountShell()

    expect(wrapper.get('.recent-project-link').attributes('aria-current')).toBe('page')
  })

  it('inerts routed content while the mobile navigation drawer is open', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
    const wrapper = await mountShell()

    await wrapper.get('.workspace-menu-btn').trigger('click')

    expect(wrapper.get('.workspace-main').attributes()).toHaveProperty('inert')
    expect(wrapper.get('.sidebar').attributes('aria-modal')).toBe('true')
  })
})
