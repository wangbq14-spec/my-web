<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import BrandIdentity from '../BrandIdentity.vue'
import FeedbackDialog from './FeedbackDialog.vue'
import { useAuthStore } from '../../stores/auth'
import { useWorkspaceStore } from '../../stores/workspace'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const {
  activeConversationId,
  collapsedSections,
  conversationListError,
  conversationListLoading,
  conversations,
  creatingConversation,
  conversationLocked,
  drawerMode,
  drawerOpen,
  filteredConversations,
  hasPinnedItems,
  pinnedConversations,
  pinnedProjects,
  pinningConversationId,
  pinningProjectId,
  recentConversations,
  recentProjects,
  search,
} = storeToRefs(workspaceStore)

const sidebarFirstControlRef = ref(null)
const sidebarTriggerRef = ref(null)
const openConversationMenuId = ref(null)
const conversationMenuOpensUp = ref(false)
const menuTriggerRef = ref(null)
const editingConversationId = ref(null)
const renameTitle = ref('')
const originalRenameTitle = ref('')
const isRenaming = ref(false)
const confirmDeleteId = ref(null)
const isDeleting = ref(false)
const deleteTriggerRef = ref(null)
const cancelDeleteButton = ref(null)
const feedbackOpen = ref(false)
const userMenuOpen = ref(false)

function getFocusableElements(container) {
  if (!container) return []
  return [...container.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hasAttribute('hidden'))
}

function updateDrawerMode() {
  workspaceStore.setDrawerMode(window.matchMedia?.('(max-width: 768px)').matches ?? false)
}

function toggleDrawer(event) {
  if (drawerOpen.value) {
    closeDrawer()
    return
  }
  sidebarTriggerRef.value = event?.currentTarget ?? null
  workspaceStore.openDrawer()
  nextTick(() => sidebarFirstControlRef.value?.focus())
}

function closeDrawer({ restoreFocus = true } = {}) {
  if (!drawerOpen.value) return
  workspaceStore.closeDrawer()
  const trigger = sidebarTriggerRef.value
  sidebarTriggerRef.value = null
  if (restoreFocus && trigger?.isConnected) nextTick(() => trigger.focus())
}

function navigateFromSidebar(location) {
  closeDrawer({ restoreFocus: false })
  router.push(location)
}

async function createNewConversation() {
  try {
    const shouldMoveFocus = drawerMode.value && drawerOpen.value
    const conversation = await workspaceStore.createNewConversation()
    if (!conversation) return
    closeDrawer({ restoreFocus: false })
    if (route.name !== 'chat') {
      await router.push({ name: 'chat', query: { conversation_id: conversation.id } })
    }
    if (shouldMoveFocus) nextTick(() => document.querySelector('.composer-input')?.focus())
  } catch {
    // The store exposes the product-safe error in the sidebar.
  }
}

async function selectConversation(id) {
  const shouldMoveFocus = drawerMode.value && drawerOpen.value
  const conversation = conversations.value.find((item) => String(item.id) === String(id))
  workspaceStore.selectConversation(conversation?.id ?? id)
  closeConversationMenu({ restoreFocus: false })
  closeDrawer({ restoreFocus: false })
  await router.push({
    name: 'chat',
    query: {
      conversation_id: conversation?.id ?? id,
      ...(conversation?.project_id == null ? {} : { project_id: conversation.project_id }),
    },
  })
  if (shouldMoveFocus) nextTick(() => document.querySelector('.composer-input')?.focus())
}

function conversationProjectName(conversation) {
  if (conversation?.project_id == null) return ''
  return workspaceStore.projects.find(
    (project) => String(project.id) === String(conversation.project_id),
  )?.name || ''
}

function isConversationActive(id) {
  return route.name === 'chat' && String(activeConversationId.value) === String(id)
}

function isNewChatActive() {
  return route.name === 'chat'
    && (activeConversationId.value == null || String(activeConversationId.value).trim() === '')
}

function isProjectActive(projectId) {
  return route.name === 'project-detail' && String(route.params.id) === String(projectId)
}

function isProjectsActive() {
  return route.name === 'projects'
}

function isSettingsActive() {
  return typeof route.name === 'string' && route.name.startsWith('settings')
}

function openProject(projectId) {
  navigateFromSidebar({ name: 'project-detail', params: { id: projectId } })
}

function openProjectQuickCreate() {
  navigateFromSidebar({ name: 'projects', query: { create: '1' } })
}

async function togglePin(type, item) {
  closeConversationMenu({ restoreFocus: false })
  try {
    await workspaceStore.togglePin(type, item)
  } catch {
    // The store exposes the product-safe error in the sidebar.
  }
}

function toggleConversationMenu(id, event) {
  if (openConversationMenuId.value === id) {
    closeConversationMenu()
    return
  }

  const trigger = event?.currentTarget ?? null
  menuTriggerRef.value = trigger
  conversationMenuOpensUp.value = false
  openConversationMenuId.value = id
  nextTick(() => {
    if (openConversationMenuId.value !== id) return
    const row = trigger?.closest('.conversation-row')
    const list = row?.closest('.conversation-list')
    if (row && list) {
      const rowRect = row.getBoundingClientRect()
      const listRect = list.getBoundingClientRect()
      const spaceBelow = listRect.bottom - rowRect.bottom
      const spaceAbove = rowRect.top - listRect.top
      conversationMenuOpensUp.value = spaceBelow < 120 && spaceAbove >= 120
    }
    document.querySelector('.conversation-menu [role="menuitem"]')?.focus()
  })
}

function closeConversationMenu({ restoreFocus = true } = {}) {
  const trigger = menuTriggerRef.value
  openConversationMenuId.value = null
  conversationMenuOpensUp.value = false
  menuTriggerRef.value = null
  if (restoreFocus && trigger?.isConnected) nextTick(() => trigger.focus())
}

function startRename(conversation) {
  if (conversationLocked.value) return
  closeConversationMenu({ restoreFocus: false })
  editingConversationId.value = conversation.id
  originalRenameTitle.value = conversation.title
  renameTitle.value = conversation.title
  nextTick(() => document.querySelector('.conversation-rename-input')?.focus())
}

function cancelRename() {
  if (isRenaming.value) return
  editingConversationId.value = null
  renameTitle.value = ''
  originalRenameTitle.value = ''
}

async function saveRename() {
  if (editingConversationId.value === null || isRenaming.value) return
  const id = editingConversationId.value
  const title = renameTitle.value.trim()
  if (title === originalRenameTitle.value) {
    cancelRename()
    return
  }

  isRenaming.value = true
  try {
    await workspaceStore.renameConversation(id, title)
    editingConversationId.value = null
    renameTitle.value = ''
    originalRenameTitle.value = ''
  } catch (error) {
    if (!workspaceStore.actionError) workspaceStore.actionError = error?.message || '重命名会话失败，请稍后重试'
    editingConversationId.value = null
    renameTitle.value = ''
    originalRenameTitle.value = ''
  } finally {
    isRenaming.value = false
  }
}

function onRenameKeydown(event) {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveRename()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancelRename()
  }
}

function requestDelete(conversationId) {
  if (conversationLocked.value) return
  const trigger = menuTriggerRef.value
  closeConversationMenu({ restoreFocus: false })
  deleteTriggerRef.value = trigger
  confirmDeleteId.value = conversationId
  nextTick(() => cancelDeleteButton.value?.focus())
}

function restoreDeleteTriggerFocus() {
  const trigger = deleteTriggerRef.value
  deleteTriggerRef.value = null
  nextTick(() => {
    if (trigger?.isConnected) trigger.focus()
    else document.querySelector('.conversation-item.active')?.focus()
  })
}

function closeDeleteConfirmation() {
  if (isDeleting.value) return
  confirmDeleteId.value = null
  restoreDeleteTriggerFocus()
}

async function confirmDelete() {
  if (confirmDeleteId.value === null || isDeleting.value) return
  isDeleting.value = true
  try {
    const deletedId = confirmDeleteId.value
    await workspaceStore.deleteConversation(deletedId)
    confirmDeleteId.value = null
    restoreDeleteTriggerFocus()
    if (route.name === 'chat' && String(route.query.conversation_id) === String(deletedId)) {
      const nextId = activeConversationId.value
      await router.replace(nextId ? { name: 'chat', query: { conversation_id: nextId } } : { name: 'chat' })
    }
  } catch {
    // The store exposes the product-safe error in the sidebar.
  } finally {
    isDeleting.value = false
  }
}

function onDocumentClick(event) {
  if (!event.target.closest('.conversation-actions')) closeConversationMenu()
  if (!event.target.closest('.user-footer')) closeUserMenu()
}

function onDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  if (confirmDeleteId.value !== null) closeDeleteConfirmation()
  else if (drawerMode.value && drawerOpen.value) closeDrawer()
  else if (editingConversationId.value !== null) cancelRename()
  else if (userMenuOpen.value) closeUserMenu()
  else closeConversationMenu()
}

function trapFocus(event) {
  if (event.key !== 'Tab') return
  const focusable = getFocusableElements(event.currentTarget)
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function toggleUserMenu() {
  userMenuOpen.value = !userMenuOpen.value
}

function closeUserMenu() {
  userMenuOpen.value = false
}

function goFromUserMenu(path) {
  closeUserMenu()
  navigateFromSidebar(path)
}

function handleLogout() {
  closeUserMenu()
  authStore.logout()
  router.replace('/login')
}

watch(() => route.fullPath, () => closeDrawer({ restoreFocus: false }))

onMounted(() => {
  updateDrawerMode()
  window.addEventListener('resize', updateDrawerMode)
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
  workspaceStore.loadConversations().catch(() => {})
  workspaceStore.loadProjects().catch(() => {})
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateDrawerMode)
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <button
    type="button"
    class="menu-btn workspace-menu-btn"
    aria-controls="chat-sidebar"
    :aria-expanded="drawerOpen ? 'true' : 'false'"
    aria-label="打开菜单"
    @click="toggleDrawer"
  >
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
    ><path d="M4 6h16M4 12h16M4 18h16" /></svg>
  </button>

  <button
    v-if="drawerOpen"
    type="button"
    class="backdrop"
    aria-label="关闭侧边栏"
    @click="closeDrawer"
  />

  <aside
    id="chat-sidebar"
    class="sidebar"
    :class="{ open: drawerOpen }"
    :role="drawerMode ? 'dialog' : undefined"
    :aria-modal="drawerMode && drawerOpen ? 'true' : undefined"
    :aria-label="drawerMode ? '导航侧边栏' : undefined"
    :inert="(drawerMode && !drawerOpen) || confirmDeleteId !== null ? '' : undefined"
    :aria-hidden="drawerMode && !drawerOpen ? 'true' : undefined"
    @keydown="trapFocus"
  >
    <div class="sidebar-header">
      <div class="brand">
        <BrandIdentity variant="compact" />
      </div>
      <button
        ref="sidebarFirstControlRef"
        type="button"
        class="new-btn"
        :class="{ active: isNewChatActive() }"
        :aria-current="isNewChatActive() ? 'page' : undefined"
        :disabled="creatingConversation"
        @click="createNewConversation"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
        ><path d="M12 5v14M5 12h14" /></svg>
        {{ creatingConversation ? '正在新建…' : '新建对话' }}
      </button>
    </div>

    <div class="sidebar-search">
      <label for="conversation-search">搜索对话</label>
      <input
        id="conversation-search"
        v-model="search"
        class="conversation-search-input"
        type="search"
        placeholder="搜索对话"
        autocomplete="off"
      >
    </div>

    <div class="sidebar-primary">
      <section class="sidebar-group pinned-section">
        <button
          type="button"
          class="sidebar-section-toggle"
          data-sidebar-section-toggle="pinned"
          aria-controls="sidebar-pinned-items"
          :aria-expanded="collapsedSections.pinned ? 'false' : 'true'"
          @click="workspaceStore.toggleCollapse('pinned')"
        >
          <span>置顶</span>
          <svg
            class="section-chevron"
            :class="{ collapsed: collapsedSections.pinned }"
            viewBox="0 0 20 20"
            aria-hidden="true"
          ><path d="m6 8 4 4 4-4" /></svg>
        </button>
        <Transition name="sidebar-collapse">
          <div
            v-show="!collapsedSections.pinned"
            id="sidebar-pinned-items"
            class="pinned-list sidebar-collapsible"
          >
            <div
              v-if="!hasPinnedItems"
              class="sidebar-empty-hint"
            >
              暂无置顶
            </div>
            <div
              v-for="conv in pinnedConversations"
              :key="`pinned-conversation-${conv.id}`"
              class="pinned-entry-row"
            >
              <button
                type="button"
                class="pinned-entry pinned-conversation-entry"
                :class="{ active: isConversationActive(conv.id) }"
                :aria-current="isConversationActive(conv.id) ? 'true' : undefined"
                @click="selectConversation(conv.id)"
              >
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                ><path d="M5 5h14v10H9l-4 4Z" /></svg>
                <span class="pinned-entry-copy"><span class="pinned-entry-title">{{ conv.title }}</span><small>会话</small></span>
              </button>
              <button
                type="button"
                class="sidebar-pin-toggle"
                :aria-label="`取消置顶会话：${conv.title}`"
                :disabled="pinningConversationId !== null || conversationLocked"
                @click="togglePin('conversation', conv)"
              >
                <span aria-hidden="true">★</span>
              </button>
            </div>
            <div
              v-for="project in pinnedProjects"
              :key="`pinned-project-${project.id}`"
              class="pinned-entry-row"
            >
              <button
                type="button"
                class="pinned-entry pinned-project-entry"
                :class="{ active: isProjectActive(project.id) }"
                :aria-current="isProjectActive(project.id) ? 'page' : undefined"
                @click="openProject(project.id)"
              >
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                ><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5Z" /><path d="M4 9h16" /></svg>
                <span class="pinned-entry-copy"><span class="pinned-entry-title">{{ project.name }}</span><small>项目</small></span>
              </button>
              <button
                type="button"
                class="sidebar-pin-toggle"
                :aria-label="`取消置顶项目：${project.name}`"
                :disabled="pinningProjectId !== null"
                @click="togglePin('project', project)"
              >
                <span aria-hidden="true">★</span>
              </button>
            </div>
          </div>
        </Transition>
      </section>

      <section class="sidebar-group recent-projects-section">
        <div class="project-section-heading">
          <button
            type="button"
            class="sidebar-section-toggle project-section-toggle"
            :class="{ active: isProjectsActive() }"
            data-sidebar-section-toggle="projects"
            aria-controls="sidebar-recent-projects"
            :aria-current="isProjectsActive() ? 'page' : undefined"
            :aria-expanded="collapsedSections.projects ? 'false' : 'true'"
            @click="workspaceStore.toggleCollapse('projects')"
          >
            <svg
              class="section-chevron"
              :class="{ collapsed: collapsedSections.projects }"
              viewBox="0 0 20 20"
              aria-hidden="true"
            ><path d="m6 8 4 4 4-4" /></svg><span>项目</span>
          </button>
          <div class="project-section-actions">
            <button
              type="button"
              class="project-section-action"
              aria-label="更多项目"
              @click="navigateFromSidebar('/projects')"
            >
              ⋯
            </button>
            <button
              type="button"
              class="project-section-action"
              aria-label="快速新建项目"
              @click="openProjectQuickCreate"
            >
              +
            </button>
          </div>
        </div>
        <Transition name="sidebar-collapse">
          <div
            v-show="!collapsedSections.projects"
            id="sidebar-recent-projects"
            class="recent-projects sidebar-collapsible"
            aria-label="最近项目"
          >
            <div
              v-for="project in recentProjects"
              :key="project.id"
              class="recent-project-row"
            >
              <button
                type="button"
                class="recent-project-link"
                :class="{ active: isProjectActive(project.id) }"
                :aria-current="isProjectActive(project.id) ? 'page' : undefined"
                @click="openProject(project.id)"
              >
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                ><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5Z" /><path d="M4 9h16" /></svg>
                <span class="recent-project-copy"><span class="recent-project-name">{{ project.name }}</span><small>{{ project.conversation_count || 0 }} 会话 · {{ project.document_count || 0 }} 资料</small></span>
              </button>
              <button
                type="button"
                class="sidebar-pin-toggle project-pin-toggle"
                :aria-label="`${project.pinned ? '取消置顶' : '置顶'}项目：${project.name}`"
                :disabled="pinningProjectId !== null"
                @click="togglePin('project', project)"
              >
                <span aria-hidden="true">{{ project.pinned ? '★' : '☆' }}</span>
              </button>
            </div>
            <button
              type="button"
              class="more-projects-link"
              @click="navigateFromSidebar('/projects')"
            >
              更多项目 <span aria-hidden="true">→</span>
            </button>
          </div>
        </Transition>
      </section>

      <nav aria-label="主导航">
        <button
          type="button"
          class="workspace-nav-item knowledge-nav-item"
          :aria-current="route.name === 'knowledge' ? 'page' : undefined"
          @click="navigateFromSidebar('/knowledge')"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          ><path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v17.5H7.5A2.5 2.5 0 0 0 5 22Z" /><path d="M5 4.5v15" /><path d="M9 6h6M9 10h6" /></svg><span>知识库</span>
        </button>
        <button
          type="button"
          class="workspace-nav-item tasks-nav-item"
          :aria-current="route.name === 'tasks' || route.name === 'task-detail' ? 'page' : undefined"
          @click="navigateFromSidebar('/tasks')"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          ><path d="M6 3h12v18H6Z" /><path d="m9 8 1.5 1.5L14 6M9 14h6M9 18h6" /></svg><span>任务 / Workflow</span>
        </button>
        <button
          type="button"
          class="workspace-nav-item feedback-nav-item"
          @click="feedbackOpen = true"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" /></svg><span>意见反馈</span>
        </button>
        <button
          v-if="authStore.user?.role === 'admin'"
          type="button"
          class="workspace-nav-item admin-nav-item"
          :aria-current="route.name === 'admin' ? 'page' : undefined"
          @click="navigateFromSidebar('/admin')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M3 9h18M8 21h8M12 17v4" /></svg><span>运营中心</span>
        </button>
      </nav>
    </div>

    <section class="recent-conversations">
      <button
        type="button"
        class="sidebar-section-toggle recent-conversations-title"
        data-sidebar-section-toggle="conversations"
        aria-controls="sidebar-recent-conversations"
        :aria-expanded="collapsedSections.conversations ? 'false' : 'true'"
        @click="workspaceStore.toggleCollapse('conversations')"
      >
        <span>最近</span><svg
          class="section-chevron"
          :class="{ collapsed: collapsedSections.conversations }"
          viewBox="0 0 20 20"
          aria-hidden="true"
        ><path d="m6 8 4 4 4-4" /></svg>
      </button>
      <Transition name="sidebar-collapse">
        <div
          v-show="!collapsedSections.conversations"
          id="sidebar-recent-conversations"
          class="conversation-list sidebar-collapsible"
        >
          <div
            v-if="conversationListLoading && conversations.length === 0"
            class="skeleton-list"
          >
            <div
              v-for="i in 4"
              :key="i"
              class="skeleton-item"
            />
          </div>
          <div
            v-else-if="conversationListError && conversations.length === 0"
            class="sidebar-load-error sidebar-hint error"
            role="alert"
          >
            <strong>会话加载失败</strong><span>{{ conversationListError }}</span><button
              type="button"
              class="conversation-list-retry"
              @click="workspaceStore.loadConversations().catch(() => {})"
            >
              重试
            </button>
          </div>
          <div
            v-else-if="recentConversations.length === 0"
            class="sidebar-hint"
          >
            还没有对话
          </div>
          <div
            v-if="conversationListError && recentConversations.length > 0"
            class="sidebar-refresh-error"
            role="alert"
          >
            <span>刷新会话失败</span><button
              type="button"
              class="conversation-list-retry"
              @click="workspaceStore.loadConversations().catch(() => {})"
            >
              重试
            </button>
          </div>
          <div
            v-if="recentConversations.length > 0 && filteredConversations.length === 0"
            class="sidebar-hint"
          >
            没有找到相关对话
          </div>
          <div
            v-for="conv in filteredConversations"
            :key="conv.id"
            class="conversation-row"
          >
            <button
              v-if="editingConversationId !== conv.id"
              type="button"
              class="conversation-item"
              :class="{ active: isConversationActive(conv.id) }"
              :aria-current="isConversationActive(conv.id) ? 'true' : undefined"
              @click="selectConversation(conv.id)"
            >
              <svg
                class="conversation-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              ><path d="M5 5h14v10H9l-4 4Z" /></svg>
              <span class="conversation-copy"><span
                class="conversation-title"
                @dblclick.stop="startRename(conv)"
              >{{ conv.title }}</span><span
                v-if="conversationProjectName(conv)"
                class="conversation-project-tag"
              >{{ conversationProjectName(conv) }}</span></span>
            </button>
            <input
              v-else
              v-model="renameTitle"
              class="conversation-rename-input"
              type="text"
              maxlength="200"
              aria-label="重命名会话"
              :aria-busy="isRenaming"
              :disabled="isRenaming"
              @keydown="onRenameKeydown"
              @blur="saveRename"
            >
            <div class="conversation-actions">
              <button
                type="button"
                class="conversation-more"
                aria-label="会话操作"
                aria-haspopup="menu"
                :aria-expanded="openConversationMenuId === conv.id ? 'true' : 'false'"
                @click.stop="toggleConversationMenu(conv.id, $event)"
              >
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                ><path d="M5 12h.01M12 12h.01M19 12h.01" /></svg>
              </button>
              <div
                v-if="openConversationMenuId === conv.id"
                class="conversation-menu"
                :class="{ 'menu-up': conversationMenuOpensUp }"
                role="menu"
                @click.stop
              >
                <button
                  type="button"
                  role="menuitem"
                  :disabled="conversationLocked"
                  @click="startRename(conv)"
                >
                  重命名
                </button>
                <button
                  type="button"
                  role="menuitem"
                  class="danger"
                  :disabled="conversationLocked"
                  @click="requestDelete(conv.id)"
                >
                  删除
                </button>
                <button
                  type="button"
                  role="menuitem"
                  :disabled="conversationLocked || pinningConversationId !== null"
                  @click="togglePin('conversation', conv)"
                >
                  {{ conv.pinned ? '取消置顶' : '置顶' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </section>

    <p
      v-if="workspaceStore.actionError"
      class="sidebar-action-error"
      role="alert"
    >
      {{ workspaceStore.actionError }}
    </p>
    <div class="sidebar-footer">
      <button
        type="button"
        class="workspace-nav-item settings-footer-item"
        :class="{ active: isSettingsActive() }"
        :aria-current="isSettingsActive() ? 'page' : undefined"
        @click="navigateFromSidebar('/settings')"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
        ><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></svg><span>设置</span>
      </button>
      <div class="user-footer">
        <button
          type="button"
          class="user-footer-btn"
          aria-haspopup="menu"
          :aria-expanded="userMenuOpen ? 'true' : 'false'"
          @click="toggleUserMenu"
        >
          <span
            class="user-avatar"
            aria-hidden="true"
          >{{ (authStore.user?.username || '?').slice(0, 1).toUpperCase() }}</span>
          <span class="user-footer-name">{{ authStore.user?.username || '已登录' }}</span>
          <svg
            class="user-chevron"
            :class="{ open: userMenuOpen }"
            viewBox="0 0 20 20"
            aria-hidden="true"
          ><path d="m6 8 4 4 4-4" /></svg>
        </button>
        <div
          v-if="userMenuOpen"
          class="user-menu"
          role="menu"
          @click.stop
        >
          <button
            type="button"
            role="menuitem"
            @click="goFromUserMenu('/settings/account')"
          >
            账号设置
          </button>
          <button
            type="button"
            role="menuitem"
            @click="goFromUserMenu('/settings/usage')"
          >
            用量
          </button>
          <button
            type="button"
            role="menuitem"
            class="logout-btn danger"
            @click="handleLogout"
          >
            退出登录
          </button>
        </div>
      </div>
    </div>
  </aside>

  <div
    v-if="confirmDeleteId !== null"
    class="confirm-modal-backdrop"
    @click.self="closeDeleteConfirmation"
  >
    <section
      class="confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      aria-describedby="delete-dialog-description"
      @keydown="trapFocus"
    >
      <h2 id="delete-dialog-title">
        删除对话
      </h2>
      <p id="delete-dialog-description">
        删除后，该对话及其消息将无法恢复。<span class="legacy-delete-copy">删除后无法恢复</span>
      </p>
      <div class="confirm-actions">
        <button
          ref="cancelDeleteButton"
          type="button"
          :disabled="isDeleting"
          @click="closeDeleteConfirmation"
        >
          取消
        </button>
        <button
          type="button"
          class="danger"
          :disabled="isDeleting"
          @click="confirmDelete"
        >
          {{ isDeleting ? '正在删除…' : '删除' }}
        </button>
      </div>
    </section>
  </div>
  <FeedbackDialog v-model="feedbackOpen" />
</template>

<style scoped>
.sidebar,
.workspace-menu-btn,
.confirm-modal-backdrop {
  --chat-focus-width: 2px;
  --chat-focus-offset: 2px;
  --chat-space-tight: 3px;
  --chat-space-1-25: 5px;
  --chat-space-2-5: 10px;
  --chat-icon-sm: 14px;
  --chat-menu-min-width: 104px;
}

.sidebar {
  width: 280px;
  flex: 0 0 280px;
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow-x: hidden;
  border-right: 1px solid var(--color-border-subtle);
  background: var(--color-surface-sunken);
  color: var(--color-text-primary);
}

.sidebar :is(button, input):focus-visible,
.workspace-menu-btn:focus-visible {
  outline: var(--chat-focus-width) solid var(--color-focus-ring);
  outline-offset: var(--chat-focus-offset);
  box-shadow: 0 0 0 var(--chat-focus-width) color-mix(in srgb, var(--color-focus-ring) 28%, transparent);
}

.sidebar-header { display: flex; flex: 0 0 auto; align-items: center; justify-content: space-between; padding: var(--space-4); }
.brand { display: flex; align-items: center; gap: var(--space-2); color: var(--color-secondary-identity); font-size: var(--text-md); font-weight: 700; }
.new-btn { display: flex; align-items: center; min-height: var(--space-11); gap: var(--space-1); border: 0; border-radius: var(--radius-xl); padding: var(--space-2) var(--space-3); background: transparent; color: var(--color-secondary-identity); font: inherit; font-size: var(--text-sm); cursor: pointer; transition: background var(--duration-fast) var(--ease-standard); }
.new-btn:hover, .new-btn:focus-visible { background: var(--color-accent-soft); }
.new-btn.active { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); font-weight: 600; }
.new-btn:disabled, .sidebar button:disabled { opacity: .55; cursor: not-allowed; }
.new-btn svg { width: var(--chat-icon-sm); height: var(--chat-icon-sm); fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }

.sidebar-search { display: grid; flex: 0 0 auto; gap: var(--space-1); padding: 0 var(--space-4) var(--space-2); }
.sidebar-search label { color: var(--color-text-secondary); font-size: var(--text-xs); }
.sidebar-search input { width: 100%; min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-2) var(--chat-space-2-5); background: var(--color-surface); color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); }
.sidebar-primary { position: relative; z-index: 1; display: grid; flex: 0 0 auto; gap: var(--space-1); padding: 0 var(--space-2) var(--space-1); }
.sidebar-group { min-width: 0; }
.sidebar-section-toggle { display: flex; width: 100%; min-height: var(--space-8); align-items: center; justify-content: space-between; gap: var(--space-2); border: 0; border-radius: var(--radius-md); padding: var(--space-1) var(--space-2); background: transparent; color: var(--color-text-secondary); font: inherit; font-size: var(--text-xs); font-weight: 600; letter-spacing: .04em; text-align: left; cursor: pointer; }
.sidebar-section-toggle:hover, .sidebar-section-toggle:focus-visible { background: var(--color-surface-hover); color: var(--color-text-primary); }
.section-chevron { width: var(--space-4); height: var(--space-4); flex: 0 0 auto; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.7; transition: transform var(--duration-normal) var(--ease-standard); }
.section-chevron.collapsed { transform: rotate(-90deg); }
.sidebar-collapse-enter-active, .sidebar-collapse-leave-active { transform-origin: top; transition: opacity var(--duration-normal) var(--ease-standard), transform var(--duration-normal) var(--ease-standard); }
.sidebar-collapse-enter-from, .sidebar-collapse-leave-to { opacity: 0; transform: scaleY(.96) translateY(-4px); }
.sidebar-collapsible { transform-origin: top; }

.project-section-heading { display: flex; min-width: 0; align-items: center; gap: var(--space-1); }
.project-section-toggle { flex: 1; min-width: 0; justify-content: flex-start; }
.project-section-toggle.active { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); color: var(--color-text-primary); font-weight: 650; }
.project-section-actions { display: flex; flex: 0 0 auto; gap: 1px; }
.project-section-action { width: var(--space-8); height: var(--space-8); border: 0; border-radius: var(--radius-md); padding: 0; background: transparent; color: var(--color-text-secondary); font: inherit; font-size: var(--text-md); line-height: 1; cursor: pointer; }
.project-section-action:hover, .project-section-action:focus-visible { background: var(--color-surface-hover); color: var(--color-text-primary); }

.workspace-nav-item { display: flex; width: 100%; min-height: var(--space-11); align-items: center; gap: var(--space-3); border: 0; border-radius: var(--radius-md); padding: var(--space-2); background: transparent; color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); text-align: left; cursor: pointer; transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard); }
.workspace-nav-item svg { width: var(--space-4); height: var(--space-4); flex: 0 0 auto; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }
.workspace-nav-item:hover, .workspace-nav-item:focus-visible { background: var(--color-surface-hover); color: var(--color-accent); }
.workspace-nav-item[aria-current="page"] { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); color: var(--color-text-primary); font-weight: 650; }

.sidebar-empty-hint { padding: var(--space-1) var(--space-2) var(--space-2); color: var(--color-text-tertiary); font-size: var(--text-xs); }
.pinned-list { display: grid; gap: 1px; }
.pinned-entry-row, .recent-project-row { display: flex; min-width: 0; align-items: center; gap: 1px; }
.pinned-entry { display: flex; flex: 1; min-width: 0; min-height: var(--space-9); align-items: center; gap: var(--space-2); border: 0; border-radius: var(--radius-lg); padding: var(--space-1) var(--space-2); overflow: hidden; background: transparent; color: var(--color-text-primary); font: inherit; text-align: left; cursor: pointer; }
.pinned-entry > svg, .recent-project-link > svg { width: var(--space-4); height: var(--space-4); flex: 0 0 auto; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }
.pinned-conversation-entry > svg { color: var(--color-accent); }
.pinned-project-entry > svg { color: var(--color-secondary-identity); }
.pinned-entry-copy, .recent-project-copy { display: grid; min-width: 0; gap: 1px; }
.pinned-entry-title, .recent-project-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pinned-entry small, .recent-project-link small { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: 400; }
.pinned-entry:hover, .pinned-entry:focus-visible { background: var(--color-surface-hover); }
.pinned-entry.active { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); font-weight: 650; }
.sidebar-pin-toggle { width: var(--space-9); min-width: var(--space-9); height: var(--space-9); border: 0; border-radius: var(--radius-lg); padding: 0; background: transparent; color: var(--color-accent); font: inherit; cursor: pointer; }
.sidebar-pin-toggle:hover:not(:disabled), .sidebar-pin-toggle:focus-visible:not(:disabled) { background: var(--color-surface-hover); }

.recent-projects { display: grid; min-width: 0; gap: 1px; color: var(--color-text-tertiary); font-size: var(--text-xs); }
.recent-project-link, .more-projects-link { display: flex; flex: 1; min-width: 0; align-items: center; justify-content: space-between; gap: var(--space-2); border: 0; border-radius: var(--radius-md); padding: var(--space-1) var(--space-2); overflow: hidden; background: transparent; color: var(--color-text-secondary); font: inherit; text-align: left; cursor: pointer; }
.recent-project-link { min-height: var(--space-11); justify-content: flex-start; }
.recent-project-link.active { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); color: var(--color-text-primary); font-weight: 650; }
.recent-project-link:hover, .recent-project-link:focus-visible, .more-projects-link:hover, .more-projects-link:focus-visible { background: var(--color-surface-hover); color: var(--color-accent); }
.more-projects-link { margin-left: calc(var(--space-4) + var(--space-2)); color: var(--color-accent); }

.recent-conversations { position: relative; z-index: 2; display: flex; flex: 1; min-height: 0; flex-direction: column; }
.recent-conversations-title { flex: 0 0 auto; margin: 0 var(--space-2); padding: var(--space-2); }
.conversation-list { flex: 1; min-height: 0; overflow: auto; padding: var(--space-1) var(--space-2); scrollbar-gutter: stable; }
.conversation-list:has(.conversation-menu) { overflow: visible; }
.sidebar-hint { padding: var(--space-2) var(--chat-space-2-5); color: var(--color-text-secondary); font-size: var(--text-sm); }
.sidebar-hint.error { color: var(--color-danger); }
.sidebar-load-error, .sidebar-refresh-error { display: grid; gap: var(--space-2); margin: var(--space-1) var(--chat-focus-width); padding: var(--chat-space-2-5); border: 1px solid var(--color-danger); border-radius: var(--radius-md); background: var(--color-danger-soft); color: var(--color-danger); font-size: var(--text-sm); }
.sidebar-refresh-error { display: flex; align-items: center; justify-content: space-between; }
.sidebar-load-error button, .sidebar-refresh-error button { min-height: var(--space-11); width: fit-content; border: 1px solid currentColor; border-radius: var(--radius-sm); padding: var(--space-1) var(--space-2); background: transparent; color: inherit; font: inherit; font-size: var(--text-xs); cursor: pointer; }
.skeleton-list { padding: var(--space-1); }
.skeleton-item { height: var(--space-9); margin-bottom: var(--space-2); border-radius: var(--radius-md); background: var(--color-surface-hover); }

.conversation-row { position: relative; display: flex; align-items: center; gap: var(--chat-space-tight); }
.conversation-item { display: flex; flex: 1; min-width: 0; min-height: var(--space-11); align-items: flex-start; gap: var(--space-2); border: 0; border-radius: var(--radius-xl); padding: var(--space-2) var(--space-3); background: transparent; color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); text-align: left; cursor: pointer; }
.conversation-item:hover, .conversation-item:focus-visible, .conversation-row:hover .conversation-item { background: var(--color-surface-hover); }
.conversation-item.active { box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent); background: var(--color-surface-hover); font-weight: 600; }
.conversation-icon { width: var(--space-4); height: var(--space-4); flex: 0 0 auto; margin-top: 2px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }
.conversation-copy { display: block; min-width: 0; }
.conversation-title { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conversation-project-tag { display: block; width: fit-content; max-width: 100%; margin-top: 2px; border-radius: var(--radius-pill); padding: 1px var(--space-2); overflow: hidden; background: color-mix(in srgb, var(--color-secondary-identity) 10%, transparent); color: var(--color-text-secondary); font-size: var(--text-xs); line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.conversation-rename-input { flex: 1; width: 100%; min-width: 0; border: 1px solid var(--color-accent); border-radius: var(--radius-xl); padding: var(--chat-space-tight) var(--chat-space-1-25); background: var(--color-surface); color: var(--color-text-primary); font: inherit; }
.conversation-more { min-width: var(--space-11); min-height: var(--space-11); border: 0; border-radius: var(--radius-lg); padding: var(--space-2); background: transparent; color: var(--color-text-secondary); cursor: pointer; opacity: 0; }
.conversation-row:hover .conversation-more, .conversation-row:focus-within .conversation-more { opacity: 1; }
.conversation-more:hover, .conversation-more:focus-visible { background: var(--color-surface-hover); color: var(--color-text-primary); }
.conversation-more svg { width: var(--space-4); height: var(--space-4); fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; }
.conversation-menu { position: absolute; top: calc(100% - var(--chat-space-tight)); right: 0; z-index: 50; min-width: var(--chat-menu-min-width); border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-1); background: var(--color-surface); box-shadow: var(--shadow-float); }
.conversation-menu.menu-up { top: auto; bottom: calc(100% - 3px); }
.conversation-menu button { display: block; width: 100%; min-height: var(--space-11); border: 0; border-radius: var(--radius-lg); padding: var(--space-2); background: transparent; color: var(--color-text-primary); text-align: left; cursor: pointer; }
.conversation-menu button:hover:not(:disabled), .conversation-menu button:focus-visible:not(:disabled) { background: var(--color-surface-hover); }
.danger { color: var(--color-danger); }

.sidebar-action-error { margin: 0 var(--space-3) var(--space-2); color: var(--color-danger); font-size: var(--text-xs); }
.sidebar-footer { position: relative; display: grid; flex: 0 0 auto; gap: var(--space-2); border-top: 1px solid var(--color-border-subtle); padding: var(--space-3) var(--space-4); color: var(--color-text-secondary); font-size: var(--text-sm); }

.user-footer { position: relative; }
.user-footer-btn { display: flex; width: 100%; min-height: var(--space-11); align-items: center; gap: var(--space-2); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-xl); padding: var(--space-1) var(--space-2); background: color-mix(in srgb, var(--color-surface) 74%, transparent); color: var(--color-text-primary); font: inherit; cursor: pointer; transition: border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard); }
.user-footer-btn:hover, .user-footer-btn:focus-visible { border-color: var(--color-border); background: var(--color-surface-hover); }
.user-avatar { display: grid; width: var(--space-8); height: var(--space-8); flex: 0 0 auto; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--color-accent) 16%, transparent); color: var(--color-accent); font-size: var(--text-sm); font-weight: 700; }
.user-footer-name { flex: 1; min-width: 0; overflow: hidden; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.user-chevron { width: var(--space-4); height: var(--space-4); flex: 0 0 auto; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.5; transition: transform var(--duration-fast) var(--ease-standard); }
.user-chevron.open { transform: rotate(180deg); }

.user-menu { position: absolute; right: 0; bottom: calc(100% + var(--space-2)); z-index: 30; display: grid; min-width: 180px; gap: 2px; border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-1); background: var(--color-surface); box-shadow: var(--shadow-overlay); }
.user-menu button { display: block; width: 100%; min-height: var(--space-11); border: 0; border-radius: var(--radius-lg); padding: var(--space-2); background: transparent; color: var(--color-text-primary); font: inherit; text-align: left; cursor: pointer; }
.user-menu button:hover:not(:disabled), .user-menu button:focus-visible:not(:disabled) { background: var(--color-surface-hover); }
.user-menu .danger { color: var(--color-danger); }

.workspace-menu-btn { display: none; border: 0; background: var(--color-surface); color: var(--color-text-primary); cursor: pointer; }
.workspace-menu-btn svg { width: var(--space-5); height: var(--space-5); fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.backdrop { display: none; }

.confirm-modal-backdrop { position: fixed; inset: 0; z-index: 40; display: flex; align-items: center; justify-content: center; padding: var(--space-5); background: color-mix(in srgb, var(--color-text-primary) 32%, transparent); }
.confirm-modal { width: min(100%, 360px); border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-6); background: var(--color-surface); color: var(--color-text-primary); box-shadow: var(--shadow-overlay); }
.confirm-modal h2, .confirm-modal p { margin: 0; }
.confirm-modal p { margin-top: var(--space-2); color: var(--color-text-secondary); }
.legacy-delete-copy { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.confirm-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-5); }
.confirm-actions button { min-height: var(--space-11); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); cursor: pointer; }
.confirm-actions button:hover:not(:disabled), .confirm-actions button:focus-visible:not(:disabled) { background: var(--color-surface-hover); }
.confirm-actions .danger { border-color: var(--color-danger); background: var(--color-danger); color: var(--color-surface); }

@media (hover: none) { .conversation-more { opacity: 1; } }

@media (max-width: 768px) {
  .sidebar { position: fixed; inset: 0 auto 0 0; z-index: 30; width: min(280px, 92vw); transform: translateX(-100%); transition: transform var(--duration-normal) var(--ease-standard); }
  .sidebar.open { transform: translateX(0); }
  .backdrop { position: fixed; inset: 0; z-index: 20; display: block; border: 0; padding: 0; background: color-mix(in srgb, var(--color-text-primary) 32%, transparent); cursor: pointer; }
  .workspace-menu-btn { position: fixed; top: var(--space-2); left: var(--space-2); z-index: 15; display: grid; width: var(--space-11); height: var(--space-11); place-items: center; border-radius: var(--radius-lg); box-shadow: var(--shadow-float); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
