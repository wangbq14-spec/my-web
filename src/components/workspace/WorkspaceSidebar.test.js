import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import WorkspaceSidebar from './WorkspaceSidebar.vue'
import { useWorkspaceStore } from '../../stores/workspace'

const authStore = vi.hoisted(() => ({
  user: { username: 'alice' },
  logout: vi.fn(),
}))
const routeMock = vi.hoisted(() => ({
  fullPath: '/chat',
  name: 'chat',
  params: {},
  query: {},
}))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
const conversationApi = vi.hoisted(() => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  listConversations: vi.fn(),
  updateConversation: vi.fn(),
}))
const projectApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  updateProject: vi.fn(),
}))

vi.mock('../../stores/auth', () => ({ useAuthStore: () => authStore }))
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => routerMock,
}))
vi.mock('../../api/modules/conversation', () => conversationApi)
vi.mock('../../api/modules/project', () => projectApi)

const conversations = [
  { id: 1, title: '项目计划', project_id: 7, pinned: false, updated_at: '2026-08-30T08:00:00Z' },
  { id: 2, title: '置顶会话', project_id: null, pinned: true, updated_at: '2026-08-29T08:00:00Z' },
]
const projects = [
  { id: 7, name: '产品发布', pinned: false, conversation_count: 3, document_count: 2 },
  { id: 8, name: '置顶项目', pinned: true, conversation_count: 1, document_count: 1 },
]

async function mountSidebar({ activeConversationId = null, attachTo } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useWorkspaceStore()
  store.activeConversationId = activeConversationId
  const wrapper = mount(WorkspaceSidebar, {
    attachTo,
    global: {
      plugins: [pinia],
      stubs: {
        BrandIdentity: { template: '<span class="brand-stub">Omnixa</span>' },
      },
    },
  })
  wrapper.workspaceStore = store
  await flushPromises()
  return wrapper
}

describe('WorkspaceSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    authStore.user = { username: 'alice' }
    routeMock.fullPath = '/chat'
    routeMock.name = 'chat'
    routeMock.params = {}
    routeMock.query = {}
    conversationApi.listConversations.mockResolvedValue(conversations.map((conversation) => ({ ...conversation })))
    conversationApi.createConversation.mockResolvedValue({ id: 3, title: '新对话', pinned: false })
    conversationApi.updateConversation.mockResolvedValue({})
    conversationApi.deleteConversation.mockResolvedValue()
    projectApi.listProjects.mockResolvedValue(projects.map((project) => ({ ...project })))
    projectApi.updateProject.mockResolvedValue({})
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
  })

  it.each([
    ['chat', {}, 1, '.conversation-item.active', 'true'],
    ['chat', {}, null, '.new-btn.active', 'page'],
    ['projects', {}, null, '.project-section-toggle.active', 'page'],
    ['project-detail', { id: '7' }, null, '.recent-project-link.active', 'page'],
    ['knowledge', {}, null, '.knowledge-nav-item', 'page'],
    ['task-detail', { id: '12' }, null, '.tasks-nav-item', 'page'],
    ['settings', {}, null, '.settings-footer-item', 'page'],
    ['settings-account', {}, null, '.settings-footer-item', 'page'],
    ['settings-usage', {}, null, '.settings-footer-item', 'page'],
    ['settings-billing', {}, null, '.settings-footer-item', 'page'],
  ])('marks the active navigation for %s', async (name, params, activeId, selector, ariaCurrent) => {
    routeMock.name = name
    routeMock.params = params
    const wrapper = await mountSidebar({ activeConversationId: activeId })

    expect(wrapper.get(selector).attributes('aria-current')).toBe(ariaCurrent)
  })

  it('shows projects, Knowledge, Tasks / Workflow, and recent information architecture', async () => {
    const wrapper = await mountSidebar()

    expect(wrapper.get('[data-sidebar-section-toggle="projects"]').text()).toContain('项目')
    expect(wrapper.get('.knowledge-nav-item').text()).toBe('知识库')
    expect(wrapper.get('.tasks-nav-item').text()).toBe('任务 / Workflow')
    expect(wrapper.get('[data-sidebar-section-toggle="conversations"]').text()).toContain('最近')
    expect(wrapper.get('.recent-project-link').text()).toContain('3 会话 · 2 资料')
  })

  it('keeps Usage and Pricing out of the main navigation and out of the footer', async () => {
    const wrapper = await mountSidebar()

    expect(wrapper.find('.usage-nav-item').exists()).toBe(false)
    expect(wrapper.find('.pricing-nav-item').exists()).toBe(false)
    expect(wrapper.find('.theme-toggle').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('定价 / 充值')
    expect(wrapper.text()).not.toContain('用量 / Usage')
  })

  it('navigates through project, Knowledge, and Tasks entries', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('[aria-label="更多项目"]').trigger('click')
    await wrapper.get('.knowledge-nav-item').trigger('click')
    await wrapper.get('.tasks-nav-item').trigger('click')

    expect(routerMock.push).toHaveBeenNthCalledWith(1, '/projects')
    expect(routerMock.push).toHaveBeenNthCalledWith(2, '/knowledge')
    expect(routerMock.push).toHaveBeenNthCalledWith(3, '/tasks')
  })

  it('navigates to Settings from the footer and via the user menu', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('.settings-footer-item').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/settings')

    routerMock.push.mockClear()
    await wrapper.get('.user-footer-btn').trigger('click')
    expect(wrapper.get('.user-menu').exists()).toBe(true)
    expect(wrapper.get('.user-menu').text()).toContain('账号设置')
    expect(wrapper.get('.user-menu').text()).toContain('用量')
    expect(wrapper.get('.user-menu').text()).toContain('退出登录')

    await wrapper.get('.user-menu button').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/settings/account')
  })

  it('routes the project plus action to quick create', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('[aria-label="快速新建项目"]').trigger('click')

    expect(routerMock.push).toHaveBeenCalledWith({ name: 'projects', query: { create: '1' } })
  })

  it('renders pinned conversations and projects outside the recent conversation list', async () => {
    const wrapper = await mountSidebar()
    const pinned = wrapper.get('.pinned-section')

    expect(pinned.text()).toContain('置顶会话')
    expect(pinned.text()).toContain('置顶项目')
    expect(wrapper.get('.conversation-list').text()).toContain('项目计划')
    expect(wrapper.get('.conversation-list').text()).not.toContain('置顶会话')
  })

  it('shows a loading skeleton while the first conversation request is pending', async () => {
    conversationApi.listConversations.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountSidebar()

    expect(wrapper.find('.skeleton-list').exists()).toBe(true)
  })

  it('shows an empty state after loading no conversations', async () => {
    conversationApi.listConversations.mockResolvedValue([])
    const wrapper = await mountSidebar()

    expect(wrapper.get('.sidebar-hint').text()).toBe('还没有对话')
  })

  it('shows a load error and retries the conversation request', async () => {
    conversationApi.listConversations
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(conversations)
    const wrapper = await mountSidebar()

    expect(wrapper.get('.sidebar-load-error').text()).toContain('会话加载失败')
    await wrapper.get('.conversation-list-retry').trigger('click')
    await flushPromises()

    expect(conversationApi.listConversations).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('项目计划')
  })

  it('keeps existing conversations visible when a refresh fails', async () => {
    const wrapper = await mountSidebar()
    conversationApi.listConversations.mockRejectedValue(new Error('network'))

    await wrapper.workspaceStore.loadConversations().catch(() => {})
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.sidebar-refresh-error').text()).toContain('刷新会话失败')
    expect(wrapper.text()).toContain('项目计划')
  })

  it('filters recent conversations locally and shows a no-result message', async () => {
    const wrapper = await mountSidebar()
    const search = wrapper.get('#conversation-search')

    await search.setValue('项目')
    expect(wrapper.get('.conversation-list').text()).toContain('项目计划')
    await search.setValue('不存在')
    expect(wrapper.get('.sidebar-hint').text()).toBe('没有找到相关对话')
    expect(conversationApi.listConversations).toHaveBeenCalledOnce()
  })

  it('persists collapse state and restores it in a new sidebar', async () => {
    const wrapper = await mountSidebar()
    const toggle = wrapper.get('[data-sidebar-section-toggle="projects"]')

    await toggle.trigger('click')

    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(JSON.parse(localStorage.getItem('omnixa.sidebar.collapsed')).projects).toBe(true)
    wrapper.unmount()

    const restored = await mountSidebar()
    expect(restored.get('[data-sidebar-section-toggle="projects"]').attributes('aria-expanded')).toBe('false')
  })

  it('shows the current user and a Settings entry, and logs out from the user menu', async () => {
    const wrapper = await mountSidebar()
    const footer = wrapper.get('.sidebar-footer')

    expect(footer.get('.settings-footer-item').text()).toContain('设置')
    expect(footer.get('.user-footer-name').text()).toBe('alice')
    expect(footer.find('.logout-btn').exists()).toBe(false)

    await wrapper.get('.user-footer-btn').trigger('click')
    await wrapper.get('.user-menu .logout-btn').trigger('click')

    expect(authStore.logout).toHaveBeenCalledOnce()
    expect(routerMock.replace).toHaveBeenCalledWith('/login')
  })

  it('selects a conversation and carries its project context into Chat', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('.conversation-item').trigger('click')
    await flushPromises()

    expect(wrapper.workspaceStore.activeConversationId).toBe(1)
    expect(routerMock.push).toHaveBeenCalledWith({
      name: 'chat',
      query: { conversation_id: 1, project_id: 7 },
    })
  })

  it('creates a new conversation and navigates to Chat from another route', async () => {
    routeMock.name = 'knowledge'
    const wrapper = await mountSidebar()

    await wrapper.get('.new-btn').trigger('click')
    await flushPromises()

    expect(conversationApi.createConversation).toHaveBeenCalledWith({ title: '新对话' })
    expect(routerMock.push).toHaveBeenCalledWith({ name: 'chat', query: { conversation_id: 3 } })
  })

  it('renames a conversation from its menu', async () => {
    conversationApi.updateConversation.mockResolvedValue({ id: 1, title: '发布计划' })
    const wrapper = await mountSidebar()

    await wrapper.get('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[0].trigger('click')
    const input = wrapper.get('.conversation-rename-input')
    await input.setValue('发布计划')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(conversationApi.updateConversation).toHaveBeenCalledWith(1, { title: '发布计划' })
    expect(wrapper.get('.conversation-title').text()).toBe('发布计划')
  })

  it('pins and unpins a conversation through the operation menu and pinned section', async () => {
    conversationApi.updateConversation
      .mockResolvedValueOnce({ id: 1, title: '项目计划', pinned: true })
      .mockResolvedValueOnce({ id: 1, title: '项目计划', pinned: false })
    const wrapper = await mountSidebar()

    await wrapper.get('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[2].trigger('click')
    await flushPromises()
    expect(wrapper.get('.pinned-section').text()).toContain('项目计划')

    await wrapper.get('[aria-label="取消置顶会话：项目计划"]').trigger('click')
    await flushPromises()
    expect(conversationApi.updateConversation).toHaveBeenLastCalledWith(1, { pinned: false })
  })

  it('pins a recent project and exposes it in the pinned section', async () => {
    projectApi.updateProject.mockResolvedValue({ id: 7, name: '产品发布', pinned: true })
    const wrapper = await mountSidebar()

    await wrapper.get('.project-pin-toggle').trigger('click')
    await flushPromises()

    expect(projectApi.updateProject).toHaveBeenCalledWith(7, { pinned: true })
    expect(wrapper.get('.pinned-section').text()).toContain('产品发布')
  })

  it('opens a pinned project detail', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('.pinned-project-entry').trigger('click')

    expect(routerMock.push).toHaveBeenCalledWith({ name: 'project-detail', params: { id: 8 } })
  })

  it('opens a conversation menu and moves focus to its first action', async () => {
    const wrapper = await mountSidebar({ attachTo: document.body })

    await wrapper.get('.conversation-more').trigger('click')
    await flushPromises()

    expect(wrapper.get('.conversation-menu').attributes('role')).toBe('menu')
    expect(document.activeElement).toBe(wrapper.findAll('.conversation-menu button')[0].element)
    wrapper.unmount()
  })

  it('closes an open conversation menu on an outside click', async () => {
    const wrapper = await mountSidebar({ attachTo: document.body })
    await wrapper.get('.conversation-more').trigger('click')

    document.body.click()
    await flushPromises()

    expect(wrapper.find('.conversation-menu').exists()).toBe(false)
    wrapper.unmount()
  })

  it('cancels an inline rename with Escape', async () => {
    const wrapper = await mountSidebar()
    await wrapper.get('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[0].trigger('click')

    const input = wrapper.get('.conversation-rename-input')
    await input.setValue('不要保存')
    await input.trigger('keydown', { key: 'Escape' })

    expect(conversationApi.updateConversation).not.toHaveBeenCalled()
    expect(wrapper.get('.conversation-title').text()).toBe('项目计划')
  })

  it('requires confirmation before deleting a conversation', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    const dialog = wrapper.get('.confirm-modal')
    expect(dialog.attributes('role')).toBe('dialog')
    expect(dialog.text()).toContain('删除后，该对话及其消息将无法恢复。')
    await dialog.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(conversationApi.deleteConversation).toHaveBeenCalledWith(1)
    expect(wrapper.text()).not.toContain('项目计划')
  })

  it('cancels deletion and restores focus to the operation trigger', async () => {
    const wrapper = await mountSidebar({ attachTo: document.body })
    const trigger = wrapper.get('.conversation-more')
    await trigger.trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')

    await wrapper.get('.confirm-actions button').trigger('click')
    await flushPromises()

    expect(conversationApi.deleteConversation).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('replaces an active deleted conversation with the next available conversation', async () => {
    routeMock.query = { conversation_id: '1' }
    const wrapper = await mountSidebar({ activeConversationId: 1 })
    await wrapper.get('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')

    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(routerMock.replace).toHaveBeenCalledWith({ name: 'chat', query: { conversation_id: 2 } })
  })

  it('opens the menu upward only when below is insufficient and above is sufficient', async () => {
    const wrapper = await mountSidebar()
    const row = wrapper.get('.conversation-row').element
    const list = wrapper.get('.conversation-list').element
    vi.spyOn(row, 'getBoundingClientRect').mockReturnValue({ top: 300, bottom: 340 })
    vi.spyOn(list, 'getBoundingClientRect').mockReturnValue({ top: 100, bottom: 400 })

    await wrapper.get('.conversation-more').trigger('click')
    await flushPromises()

    expect(wrapper.get('.conversation-menu').classes()).toContain('menu-up')
  })

  it('keeps the menu below when there is not enough space above', async () => {
    const wrapper = await mountSidebar()
    const row = wrapper.get('.conversation-row').element
    const list = wrapper.get('.conversation-list').element
    vi.spyOn(row, 'getBoundingClientRect').mockReturnValue({ top: 150, bottom: 190 })
    vi.spyOn(list, 'getBoundingClientRect').mockReturnValue({ top: 100, bottom: 220 })

    await wrapper.get('.conversation-more').trigger('click')
    await flushPromises()

    expect(wrapper.get('.conversation-menu').classes()).not.toContain('menu-up')
  })

  it('disables rename, delete, and pin actions while a conversation is locked', async () => {
    const wrapper = await mountSidebar()
    wrapper.workspaceStore.conversationLocked = true

    await wrapper.get('.conversation-more').trigger('click')

    expect(wrapper.findAll('.conversation-menu button').every((button) => button.element.disabled)).toBe(true)
  })

  it('exposes the mobile drawer as a modal, inerts it while closed, traps focus, and restores focus', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
    const wrapper = await mountSidebar({ attachTo: document.body })
    const trigger = wrapper.get('.workspace-menu-btn')
    const sidebar = wrapper.get('.sidebar')

    expect(sidebar.attributes()).toHaveProperty('inert')
    await trigger.trigger('click')
    await flushPromises()

    expect(sidebar.attributes('role')).toBe('dialog')
    expect(sidebar.attributes('aria-modal')).toBe('true')
    expect(sidebar.attributes()).not.toHaveProperty('inert')
    expect(document.activeElement).toBe(wrapper.get('.new-btn').element)

    wrapper.get('.user-footer-btn').element.focus()
    await sidebar.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(wrapper.get('.new-btn').element)

    await wrapper.get('.backdrop').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })
})
