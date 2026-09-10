import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from './workspace'

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

vi.mock('../api/modules/conversation', () => conversationApi)
vi.mock('../api/modules/project', () => projectApi)

describe('workspace store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
    conversationApi.listConversations.mockResolvedValue([])
    projectApi.listProjects.mockResolvedValue([])
  })

  it('loads and sorts conversations by updated time and id', async () => {
    conversationApi.listConversations.mockResolvedValue([
      { id: 1, title: '较早', updated_at: '2026-08-01T08:00:00Z' },
      { id: 2, title: '同时间较小 id', updated_at: '2026-08-30T08:00:00Z' },
      { id: 3, title: '同时间较大 id', updated_at: '2026-08-30T08:00:00Z' },
    ])
    const store = useWorkspaceStore()

    await store.loadConversations()

    expect(store.conversations.map(({ id }) => id)).toEqual([3, 2, 1])
    expect(store.conversationListLoading).toBe(false)
  })

  it('keeps the newest conversation request when responses finish out of order', async () => {
    let resolveFirst
    conversationApi.listConversations
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce([{ id: 2, title: '最新' }])
    const store = useWorkspaceStore()

    const first = store.loadConversations()
    await store.loadConversations()
    resolveFirst([{ id: 1, title: '过期' }])
    await first

    expect(store.conversations).toEqual([{ id: 2, title: '最新' }])
  })

  it('exposes a safe load error and resets loading', async () => {
    conversationApi.listConversations.mockRejectedValue(new Error('network details'))
    const store = useWorkspaceStore()

    await expect(store.loadConversations()).rejects.toThrow('network details')

    expect(store.conversationListError).toBe('会话加载失败，请稍后重试')
    expect(store.conversationListLoading).toBe(false)
  })

  it('normalizes a non-array conversation response to an empty list', async () => {
    conversationApi.listConversations.mockResolvedValue({ items: [] })
    const store = useWorkspaceStore()

    await store.loadConversations()

    expect(store.conversations).toEqual([])
  })

  it('loads projects', async () => {
    projectApi.listProjects.mockResolvedValue([{ id: 7, name: '产品发布' }])
    const store = useWorkspaceStore()

    await store.loadProjects()

    expect(store.projects).toEqual([{ id: 7, name: '产品发布' }])
    expect(store.projectsLoading).toBe(false)
  })

  it('exposes a safe project load error', async () => {
    projectApi.listProjects.mockRejectedValue(new Error('private backend error'))
    const store = useWorkspaceStore()

    await expect(store.loadProjects()).rejects.toThrow('private backend error')

    expect(store.projectsError).toBe('项目加载失败，请稍后重试')
    expect(store.projectsLoading).toBe(false)
  })

  it('selects and clears the active conversation', () => {
    const store = useWorkspaceStore()

    store.selectConversation(7)
    expect(store.activeConversationId).toBe(7)
    store.selectConversation(null)
    expect(store.activeConversationId).toBeNull()
  })

  it('creates and activates one conversation while a request is pending', async () => {
    let resolveCreate
    conversationApi.createConversation.mockReturnValue(new Promise((resolve) => { resolveCreate = resolve }))
    const store = useWorkspaceStore()

    const first = store.createNewConversation({ project_id: 7 })
    const second = await store.createNewConversation()
    resolveCreate({ id: 9, title: '新对话', project_id: 7 })
    await first

    expect(second).toBeNull()
    expect(conversationApi.createConversation).toHaveBeenCalledWith({ title: '新对话', project_id: 7 })
    expect(store.activeConversationId).toBe(9)
    expect(store.conversations[0].id).toBe(9)
  })

  it('can create without changing the active conversation', async () => {
    conversationApi.createConversation.mockResolvedValue({ id: 2, title: '后台创建' })
    const store = useWorkspaceStore()
    store.activeConversationId = 1

    await store.createNewConversation({}, { activate: false })

    expect(store.activeConversationId).toBe(1)
  })

  it('reports a safe create error and unlocks the create action', async () => {
    conversationApi.createConversation.mockRejectedValue(new Error('database detail'))
    const store = useWorkspaceStore()

    await expect(store.createNewConversation()).rejects.toThrow('database detail')

    expect(store.actionError).toBe('新建会话失败，请稍后重试')
    expect(store.creatingConversation).toBe(false)
  })

  it('renames a conversation with a trimmed title', async () => {
    conversationApi.updateConversation.mockResolvedValue({ id: 1, title: '新标题' })
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '旧标题', project_id: 7 }]

    await store.renameConversation(1, '  新标题  ')

    expect(conversationApi.updateConversation).toHaveBeenCalledWith(1, { title: '新标题' })
    expect(store.conversations[0]).toEqual({ id: 1, title: '新标题', project_id: 7 })
  })

  it.each(['', '   '])('rejects an empty rename (%j)', async (title) => {
    const store = useWorkspaceStore()

    await expect(store.renameConversation(1, title)).rejects.toThrow('会话标题不能为空')
    expect(conversationApi.updateConversation).not.toHaveBeenCalled()
  })

  it('rejects a conversation title longer than 200 characters', async () => {
    const store = useWorkspaceStore()

    await expect(store.renameConversation(1, 'a'.repeat(201))).rejects.toThrow('会话标题不能超过 200 个字符')
    expect(conversationApi.updateConversation).not.toHaveBeenCalled()
  })

  it('removes a missing conversation and refreshes after a 404 rename', async () => {
    conversationApi.updateConversation.mockRejectedValue({ status: 404 })
    conversationApi.listConversations.mockResolvedValue([{ id: 2, title: '服务端列表' }])
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '已删除' }, { id: 2, title: '旧列表' }]

    await expect(store.renameConversation(1, '新标题')).rejects.toEqual({ status: 404 })

    expect(store.conversations).toEqual([{ id: 2, title: '服务端列表' }])
    expect(conversationApi.listConversations).toHaveBeenCalledOnce()
  })

  it('keeps a conversation and reports a safe rename error on non-404 failures', async () => {
    conversationApi.updateConversation.mockRejectedValue(new Error('network'))
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '原标题' }]

    await expect(store.renameConversation(1, '新标题')).rejects.toThrow('network')

    expect(store.conversations[0].title).toBe('原标题')
    expect(store.actionError).toBe('重命名会话失败，请稍后重试')
  })

  it('deletes an active conversation and selects the next item', async () => {
    conversationApi.deleteConversation.mockResolvedValue()
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '当前' }, { id: 2, title: '下一条' }]
    store.activeConversationId = 1

    const result = await store.deleteConversation(1)

    expect(result).toEqual({ wasActive: true, nextConversationId: 2 })
    expect(store.conversations.map(({ id }) => id)).toEqual([2])
  })

  it('treats a 404 delete as already deleted', async () => {
    conversationApi.deleteConversation.mockRejectedValue({ status: 404 })
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '已不存在' }]

    await expect(store.deleteConversation(1)).resolves.toEqual({
      wasActive: false,
      nextConversationId: null,
    })
    expect(store.conversations).toEqual([])
  })

  it('keeps a conversation when deletion fails', async () => {
    conversationApi.deleteConversation.mockRejectedValue(new Error('network'))
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '保留' }]

    await expect(store.deleteConversation(1)).rejects.toThrow('network')

    expect(store.conversations).toHaveLength(1)
    expect(store.actionError).toBe('删除会话失败，请稍后重试')
  })

  it('pins and unpins conversations', async () => {
    conversationApi.updateConversation
      .mockResolvedValueOnce({ id: 1, pinned: true })
      .mockResolvedValueOnce({ id: 1, pinned: false })
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '计划', pinned: false }]

    await store.togglePin('conversation', store.conversations[0])
    await store.togglePin('conversation', store.conversations[0])

    expect(conversationApi.updateConversation).toHaveBeenNthCalledWith(1, 1, { pinned: true })
    expect(conversationApi.updateConversation).toHaveBeenNthCalledWith(2, 1, { pinned: false })
    expect(store.conversations[0].pinned).toBe(false)
  })

  it('pins a project', async () => {
    projectApi.updateProject.mockResolvedValue({ id: 7, pinned: true })
    const store = useWorkspaceStore()
    store.projects = [{ id: 7, name: '产品发布', pinned: false }]

    await store.togglePin('project', store.projects[0])

    expect(projectApi.updateProject).toHaveBeenCalledWith(7, { pinned: true })
    expect(store.projects[0].pinned).toBe(true)
  })

  it('reports a safe pin error and releases the conversation lock', async () => {
    conversationApi.updateConversation.mockRejectedValue(new Error('network'))
    const store = useWorkspaceStore()
    store.conversations = [{ id: 1, title: '计划', pinned: false }]

    await expect(store.togglePin('conversation', store.conversations[0])).rejects.toThrow('network')

    expect(store.actionError).toBe('置顶会话失败，请稍后重试')
    expect(store.pinningConversationId).toBeNull()
  })

  it('rejects an unsupported pin type', async () => {
    const store = useWorkspaceStore()

    await expect(store.togglePin('document', { id: 1, pinned: false })).rejects.toThrow(
      'Unsupported pin type: document',
    )
  })

  it('filters only unpinned recent conversations by title', () => {
    const store = useWorkspaceStore()
    store.conversations = [
      { id: 1, title: '项目计划', pinned: false },
      { id: 2, title: '读书笔记', pinned: false },
      { id: 3, title: '置顶项目', pinned: true },
    ]
    store.search = '项目'

    expect(store.filteredConversations.map(({ id }) => id)).toEqual([1])
  })

  it('limits recent and pinned project navigation to three entries', () => {
    const store = useWorkspaceStore()
    store.projects = [1, 2, 3, 4].map((id) => ({ id, pinned: true }))

    expect(store.recentProjects.map(({ id }) => id)).toEqual([1, 2, 3])
    expect(store.pinnedProjects.map(({ id }) => id)).toEqual([1, 2, 3])
  })

  it('persists collapsed sections and restores them in a new store', () => {
    const store = useWorkspaceStore()

    store.toggleCollapse('projects')

    expect(JSON.parse(localStorage.getItem('omnixa.sidebar.collapsed'))).toMatchObject({
      pinned: false,
      projects: true,
      conversations: false,
    })
    setActivePinia(createPinia())
    expect(useWorkspaceStore().collapsedSections.projects).toBe(true)
  })

  it('ignores unsupported collapse sections', () => {
    const store = useWorkspaceStore()

    store.toggleCollapse('unknown')

    expect(localStorage.getItem('omnixa.sidebar.collapsed')).toBeNull()
  })

  it('opens the drawer only in drawer mode and closes it when leaving drawer mode', () => {
    const store = useWorkspaceStore()

    store.openDrawer()
    expect(store.drawerOpen).toBe(false)
    store.setDrawerMode(true)
    store.openDrawer()
    expect(store.drawerOpen).toBe(true)
    store.setDrawerMode(false)
    expect(store.drawerOpen).toBe(false)
  })
})
