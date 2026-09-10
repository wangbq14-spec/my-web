import { defineStore } from 'pinia'
import {
  createConversation as createConversationRequest,
  deleteConversation as deleteConversationRequest,
  listConversations,
  updateConversation,
} from '../api/modules/conversation'
import { listProjects, updateProject } from '../api/modules/project'

const SIDEBAR_COLLAPSED_KEY = 'omnixa.sidebar.collapsed'
const defaultCollapsedSections = {
  pinned: false,
  projects: false,
  conversations: false,
}

function readCollapsedSections() {
  if (typeof window === 'undefined') return { ...defaultCollapsedSections }

  try {
    const saved = JSON.parse(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) || '{}')
    return Object.fromEntries(
      Object.entries(defaultCollapsedSections).map(([section, fallback]) => [
        section,
        typeof saved?.[section] === 'boolean' ? saved[section] : fallback,
      ]),
    )
  } catch {
    return { ...defaultCollapsedSections }
  }
}

function sortConversations(items) {
  return [...items].sort((left, right) => {
    const leftTime = Date.parse(left.updated_at)
    const rightTime = Date.parse(right.updated_at)
    const hasLeftTime = Number.isFinite(leftTime)
    const hasRightTime = Number.isFinite(rightTime)

    if (hasLeftTime && hasRightTime) {
      const timeDifference = rightTime - leftTime
      if (timeDifference) return timeDifference
      return Number(right.id) - Number(left.id)
    }
    if (hasLeftTime) return -1
    if (hasRightTime) return 1
    return 0
  })
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    conversations: [],
    activeConversationId: null,
    projects: [],
    search: '',
    collapsedSections: readCollapsedSections(),
    conversationListLoading: false,
    conversationListError: '',
    conversationRequestSeq: 0,
    projectsLoading: false,
    projectsError: '',
    actionError: '',
    creatingConversation: false,
    conversationLocked: false,
    pinningConversationId: null,
    pinningProjectId: null,
    drawerOpen: false,
    drawerMode: false,
  }),

  getters: {
    recentConversations: (state) => state.conversations.filter((conversation) => !conversation.pinned),
    filteredConversations() {
      const query = this.search.trim().toLocaleLowerCase()
      if (!query) return this.recentConversations
      return this.recentConversations.filter((conversation) =>
        String(conversation.title || '').toLocaleLowerCase().includes(query),
      )
    },
    recentProjects: (state) => state.projects.slice(0, 3),
    pinnedConversations: (state) => state.conversations.filter((conversation) => conversation.pinned).slice(0, 3),
    pinnedProjects: (state) => state.projects.filter((project) => project.pinned).slice(0, 3),
    hasPinnedItems() {
      return this.pinnedConversations.length > 0 || this.pinnedProjects.length > 0
    },
  },

  actions: {
    async loadConversations() {
      const requestId = ++this.conversationRequestSeq
      this.conversationListLoading = true
      this.conversationListError = ''
      try {
        const result = await listConversations()
        if (requestId === this.conversationRequestSeq) {
          this.conversations = Array.isArray(result) ? sortConversations(result) : []
        }
        return this.conversations
      } catch (error) {
        if (requestId === this.conversationRequestSeq) {
          this.conversationListError = '会话加载失败，请稍后重试'
        }
        throw error
      } finally {
        if (requestId === this.conversationRequestSeq) this.conversationListLoading = false
      }
    },

    async loadProjects() {
      this.projectsLoading = true
      this.projectsError = ''
      try {
        const result = await listProjects()
        this.projects = Array.isArray(result) ? result : []
        return this.projects
      } catch (error) {
        this.projectsError = '项目加载失败，请稍后重试'
        throw error
      } finally {
        this.projectsLoading = false
      }
    },

    async createNewConversation(payload = {}, { activate = true } = {}) {
      if (this.creatingConversation) return null
      this.creatingConversation = true
      this.actionError = ''
      try {
        const conversation = await createConversationRequest({ title: '新对话', ...payload })
        this.conversations = [
          conversation,
          ...this.conversations.filter((item) => String(item.id) !== String(conversation.id)),
        ]
        this.conversationRequestSeq += 1
        this.conversationListLoading = false
        if (activate) this.activeConversationId = conversation.id
        return conversation
      } catch (error) {
        this.actionError = '新建会话失败，请稍后重试'
        throw error
      } finally {
        this.creatingConversation = false
      }
    },

    selectConversation(id) {
      this.activeConversationId = id ?? null
    },

    async renameConversation(id, title) {
      const normalizedTitle = title.trim()
      if (!normalizedTitle) throw new Error('会话标题不能为空')
      if (normalizedTitle.length > 200) throw new Error('会话标题不能超过 200 个字符')

      this.actionError = ''
      try {
        const updated = await updateConversation(id, { title: normalizedTitle })
        const index = this.conversations.findIndex((item) => String(item.id) === String(id))
        if (index !== -1) {
          this.conversations[index] = { ...this.conversations[index], ...updated, title: normalizedTitle }
        }
        this.conversationRequestSeq += 1
        this.conversationListLoading = false
        return updated
      } catch (error) {
        if (error?.status === 404) {
          this.conversations = this.conversations.filter((item) => String(item.id) !== String(id))
          await this.loadConversations().catch(() => {})
        } else {
          this.actionError = '重命名会话失败，请稍后重试'
        }
        throw error
      }
    },

    async deleteConversation(id) {
      this.actionError = ''
      try {
        await deleteConversationRequest(id)
      } catch (error) {
        if (error?.status !== 404) {
          this.actionError = '删除会话失败，请稍后重试'
          throw error
        }
      }

      const wasActive = String(this.activeConversationId) === String(id)
      this.conversations = this.conversations.filter((item) => String(item.id) !== String(id))
      this.conversationRequestSeq += 1
      this.conversationListLoading = false
      if (wasActive) this.activeConversationId = this.conversations[0]?.id ?? null
      return { wasActive, nextConversationId: this.activeConversationId }
    },

    async togglePin(type, item) {
      const pinned = !item.pinned
      this.actionError = ''

      if (type === 'conversation') {
        if (this.pinningConversationId !== null) return null
        this.pinningConversationId = item.id
        try {
          const updated = await updateConversation(item.id, { pinned })
          const index = this.conversations.findIndex((candidate) => String(candidate.id) === String(item.id))
          if (index !== -1) this.conversations[index] = { ...this.conversations[index], ...updated, pinned }
          return updated
        } catch (error) {
          this.actionError = pinned ? '置顶会话失败，请稍后重试' : '取消置顶会话失败，请稍后重试'
          throw error
        } finally {
          this.pinningConversationId = null
        }
      }

      if (type === 'project') {
        if (this.pinningProjectId !== null) return null
        this.pinningProjectId = item.id
        try {
          const updated = await updateProject(item.id, { pinned })
          const index = this.projects.findIndex((candidate) => String(candidate.id) === String(item.id))
          if (index !== -1) this.projects[index] = { ...this.projects[index], ...updated, pinned }
          return updated
        } catch (error) {
          this.actionError = pinned ? '置顶项目失败，请稍后重试' : '取消置顶项目失败，请稍后重试'
          throw error
        } finally {
          this.pinningProjectId = null
        }
      }

      throw new Error(`Unsupported pin type: ${type}`)
    },

    toggleCollapse(section) {
      if (!(section in this.collapsedSections)) return
      this.collapsedSections[section] = !this.collapsedSections[section]
      if (typeof window === 'undefined') return
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, JSON.stringify(this.collapsedSections))
      } catch {
        // Navigation remains usable when browser storage is unavailable.
      }
    },

    setDrawerMode(isDrawer) {
      this.drawerMode = isDrawer
      if (!isDrawer) this.drawerOpen = false
    },

    openDrawer() {
      if (this.drawerMode) this.drawerOpen = true
    },

    closeDrawer() {
      this.drawerOpen = false
    },
  },
})
