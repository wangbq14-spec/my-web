<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createConversation,
  deleteConversation,
  listConversations,
  updateConversation,
} from '../api/modules/conversation'
import { listMessages } from '../api/modules/message'
import { streamAgent, streamChat, streamRegenerate } from '../api/stream'
import AssistantMessage from '../components/chat/AssistantMessage.vue'
import { useAuthStore } from '../stores/auth'

const MAX_TEXTAREA_HEIGHT = 200

const router = useRouter()
const authStore = useAuthStore()

const conversations = ref([])
const conversationListLoading = ref(false)
const conversationListError = ref(null)
const conversationSearch = ref('')
const filteredConversations = computed(() => {
  const query = conversationSearch.value.trim().toLocaleLowerCase()
  if (!query) return conversations.value

  return conversations.value.filter((conversation) =>
    String(conversation.title || '').toLocaleLowerCase().includes(query),
  )
})

const activeConversationId = ref(null)
const activeConversationTitle = computed(() => {
  const current = conversations.value.find((c) => c.id === activeConversationId.value)
  return current?.title || '新对话'
})

const messages = ref([])
const messagesLoading = ref(false)
const messagesError = ref(null)

const inputContent = ref('')
const mode = ref('chat')
const isStreaming = ref(false)
const error = ref(null)
const retryContext = ref(null)
const showRegenerate = computed(() => {
  const lastMessage = messages.value.at(-1)
  return lastMessage?.role === 'assistant' && !lastMessage.stopped
})
const canRegenerate = computed(() => {
  const lastMessage = messages.value.at(-1)
  return Boolean(
    !isStreaming.value &&
      lastMessage?.role === 'assistant' &&
      lastMessage.id != null &&
      !lastMessage.isStreaming &&
      !lastMessage.stopped,
  )
})

const isSidebarOpen = ref(false)
const isCreating = ref(false)
const openConversationMenuId = ref(null)
const editingConversationId = ref(null)
const renameTitle = ref('')
const originalRenameTitle = ref('')
const isRenaming = ref(false)
const confirmDeleteId = ref(null)
const isDeleting = ref(false)
const deleteTriggerRef = ref(null)
const cancelDeleteButton = ref(null)
const menuTriggerRef = ref(null)

const messagesContainer = ref(null)
const textareaRef = ref(null)
const shouldAutoScroll = ref(true)
const showScrollToBottom = ref(false)

let activeController = null
let listRequestSeq = 0
let messageRequestSeq = 0
let isMounted = true

const suggestions = [
  '帮我解释一段代码',
  '帮我规划一个项目',
  '总结一段内容',
  '帮我解决一个报错',
]

function sortConversations(items) {
  return [...items].sort((left, right) => {
    const leftTime = Date.parse(left.updated_at)
    const rightTime = Date.parse(right.updated_at)
    const hasLeftTime = Number.isFinite(leftTime)
    const hasRightTime = Number.isFinite(rightTime)

    if (hasLeftTime && hasRightTime) {
      const timeDifference = rightTime - leftTime
      if (timeDifference) return timeDifference
      return right.id - left.id
    }
    if (hasLeftTime) return -1
    if (hasRightTime) return 1
    return 0
  })
}

async function loadConversations() {
  const seq = ++listRequestSeq
  if (isMounted) {
    conversationListLoading.value = true
    conversationListError.value = null
  }

  try {
    const result = await listConversations()
    if (isMounted && seq === listRequestSeq) {
      conversations.value = Array.isArray(result) ? sortConversations(result) : []
      conversationListError.value = null
    }
  } catch {
    if (isMounted && seq === listRequestSeq) {
      conversationListError.value = '会话加载失败，请稍后重试'
    }
  } finally {
    if (isMounted && seq === listRequestSeq) {
      conversationListLoading.value = false
    }
  }
}

function invalidateConversationListRequests() {
  listRequestSeq += 1
}

async function selectConversation(id) {
  closeConversationMenu({ restoreFocus: false })
  const isSwitchingConversation = activeConversationId.value !== id
  activeConversationId.value = id
  if (isSwitchingConversation && activeController) {
    activeController.abort()
    isStreaming.value = false
    activeController = null
  }
  const requestId = ++messageRequestSeq
  isSidebarOpen.value = false
  messages.value = []
  error.value = null
  messagesLoading.value = true
  messagesError.value = null
  try {
    const loadedMessages = await listMessages(id)
    if (!isMounted || requestId !== messageRequestSeq || activeConversationId.value !== id) return
    messages.value = loadedMessages
  } catch (err) {
    if (!isMounted || requestId !== messageRequestSeq || activeConversationId.value !== id) return
    messagesError.value = err?.message || '加载消息失败'
  } finally {
    if (isMounted && requestId === messageRequestSeq && activeConversationId.value === id) {
      messagesLoading.value = false
    }
  }
  if (!isMounted || requestId !== messageRequestSeq || activeConversationId.value !== id) return
  await nextTick()
  if (!isMounted || requestId !== messageRequestSeq || activeConversationId.value !== id) return
  scrollToBottom()
}

function toggleConversationMenu(id, event) {
  if (openConversationMenuId.value === id) {
    closeConversationMenu()
    return
  }

  menuTriggerRef.value = event?.currentTarget ?? null
  openConversationMenuId.value = id
  nextTick(() => document.querySelector('.conversation-menu [role="menuitem"]')?.focus())
}

function closeConversationMenu({ restoreFocus = true } = {}) {
  const trigger = menuTriggerRef.value
  openConversationMenuId.value = null
  menuTriggerRef.value = null
  if (restoreFocus && trigger?.isConnected) {
    nextTick(() => trigger.focus())
  }
}

function startRename(conversation) {
  if (isStreaming.value) return
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

  const title = renameTitle.value.trim()
  const conversationId = editingConversationId.value
  if (!title) {
    error.value = '会话标题不能为空'
    cancelRename()
    return
  }
  if (title.length > 200) {
    error.value = '会话标题不能超过 200 个字符'
    cancelRename()
    return
  }
  if (title === originalRenameTitle.value) {
    cancelRename()
    return
  }

  isRenaming.value = true
  try {
    const updated = await updateConversation(conversationId, { title })
    const index = conversations.value.findIndex((conversation) => conversation.id === conversationId)
    if (index !== -1) {
      conversations.value[index] = { ...conversations.value[index], ...updated, title }
    }
    invalidateConversationListRequests()
    editingConversationId.value = null
    renameTitle.value = ''
    originalRenameTitle.value = ''
  } catch (err) {
    const index = conversations.value.findIndex((conversation) => conversation.id === conversationId)
    if (index !== -1) conversations.value[index].title = originalRenameTitle.value
    editingConversationId.value = null
    renameTitle.value = ''
    originalRenameTitle.value = ''
    if (err?.status === 404) {
      conversations.value = conversations.value.filter((conversation) => conversation.id !== conversationId)
      await loadConversations()
      return
    }
    error.value = '重命名会话失败，请稍后重试'
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

function requestDelete(conversationId, event) {
  if (isStreaming.value) return
  closeConversationMenu({ restoreFocus: false })
  deleteTriggerRef.value = event?.currentTarget ?? null
  confirmDeleteId.value = conversationId
  nextTick(() => cancelDeleteButton.value?.focus())
}

function restoreDeleteTriggerFocus() {
  const trigger = deleteTriggerRef.value
  deleteTriggerRef.value = null
  nextTick(() => {
    if (trigger?.isConnected) {
      trigger.focus()
      return
    }
    document.querySelector('.conversation-item.active')?.focus()
  })
}

function closeDeleteConfirmation() {
  if (!isDeleting.value) {
    confirmDeleteId.value = null
    restoreDeleteTriggerFocus()
  }
}

async function confirmDelete() {
  const conversationId = confirmDeleteId.value
  if (conversationId === null || isDeleting.value) return

  isDeleting.value = true
  try {
    await deleteConversation(conversationId)
    const wasActive = activeConversationId.value === conversationId
    conversations.value = conversations.value.filter((conversation) => conversation.id !== conversationId)
    invalidateConversationListRequests()
    confirmDeleteId.value = null
    restoreDeleteTriggerFocus()

    if (wasActive) {
      messages.value = []
      messagesError.value = null
      const nextConversation = conversations.value[0]
      if (nextConversation) {
        await selectConversation(nextConversation.id)
      } else {
        activeConversationId.value = null
      }
    }
  } catch (err) {
    if (err?.status === 404) {
      const wasActive = activeConversationId.value === conversationId
      conversations.value = conversations.value.filter((conversation) => conversation.id !== conversationId)
      confirmDeleteId.value = null
      restoreDeleteTriggerFocus()
      await loadConversations()

      if (wasActive) {
        messages.value = []
        messagesError.value = null
        const nextConversation = conversations.value[0]
        if (nextConversation) {
          await selectConversation(nextConversation.id)
        } else {
          activeConversationId.value = null
        }
      }
      return
    }
    error.value = '删除会话失败，请稍后重试'
  } finally {
    isDeleting.value = false
  }
}

async function createNewConversation() {
  if (isCreating.value) return

  if (activeController) activeController.abort()
  isStreaming.value = false
  activeController = null
  retryContext.value = null
  isCreating.value = true
  error.value = null
  try {
    const conversation = await createConversation({ title: '新对话' })
    if (!isMounted) return
    conversations.value = [
      conversation,
      ...conversations.value.filter((item) => item.id !== conversation.id),
    ]
    invalidateConversationListRequests()
    messageRequestSeq += 1
    activeConversationId.value = conversation.id
    messages.value = []
    messagesLoading.value = false
    messagesError.value = null
    isSidebarOpen.value = false
    await nextTick()
    textareaRef.value?.focus()
  } catch {
    if (isMounted) error.value = '新建会话失败，请稍后重试'
  } finally {
    if (isMounted) isCreating.value = false
  }
}

function toggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
}

function handleLogout() {
  authStore.logout()
  router.replace('/login')
}

function fillSuggestion(text) {
  inputContent.value = text
  nextTick(() => {
    textareaRef.value?.focus()
    autoResize()
  })
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
}

function isNearBottom() {
  const el = messagesContainer.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom(smooth = false) {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function onScroll() {
  const nearBottom = isNearBottom()
  shouldAutoScroll.value = nearBottom
  showScrollToBottom.value = !nearBottom
}

function handleScrollToBottom() {
  scrollToBottom(true)
  shouldAutoScroll.value = true
  showScrollToBottom.value = false
}

function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    sendMessage()
  }
}

async function executeStreaming({
  stream,
  mode: streamMode,
  conversationId,
  content,
  userMessage,
  assistantMessage,
  removeOnError,
}) {
  const streamConversationId = conversationId
  const streamController = new AbortController()
  isStreaming.value = true
  activeController = streamController
  let streamTerminal = false
  const selectedStream = stream || (streamMode === 'agent' ? streamAgent : streamChat)

  const callbacks = {
    conversationId,
    ...(content === undefined ? {} : { content }),
    ...(selectedStream === streamChat ? { useRag: streamMode === 'rag' } : {}),
    signal: streamController.signal,
    onDelta({ content: delta }) {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      assistantMessage.content += delta
      if (shouldAutoScroll.value) nextTick(() => scrollToBottom())
    },
    onSources(data) {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      assistantMessage.sources = data?.sources || []
    },
    onDone(data) {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      streamTerminal = true
      if (userMessage) userMessage.id = data.user_message_id
      assistantMessage.id = data.assistant_message_id
      assistantMessage.model = data.model
      assistantMessage.isStreaming = false
      assistantMessage.agentStatus = null
      assistantMessage.activeTool = null
      retryContext.value = null
      void loadConversations()
    },
    onError(err) {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      streamTerminal = true
      assistantMessage.isStreaming = false
      assistantMessage.agentStatus = null
      assistantMessage.activeTool = null
      if (err?.type === 'abort') {
        assistantMessage.stopped = true
        return
      }

      if (removeOnError) {
        const index = messages.value.indexOf(assistantMessage)
        if (index !== -1) messages.value.splice(index, 1)
      } else {
        retryContext.value = { mode: streamMode, conversationId, content, userMessage, assistantMessage }
      }
      error.value = '生成失败，请重试'
    },
  }

  if (streamMode === 'agent') {
    callbacks.onAgentStep = () => {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      assistantMessage.agentStatus = 'thinking'
      assistantMessage.activeTool = null
    }
    callbacks.onToolStart = ({ name }) => {
      if (!isMounted || activeController !== streamController) return
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      assistantMessage.agentStatus = 'using_tool'
      assistantMessage.activeTool = name
    }
    callbacks.onToolResult = () => {
      if (!isMounted || activeController !== streamController) return
      // Tool inputs and results are intentionally not exposed in the UI.
    }
  }

  await selectedStream(callbacks)

  if (activeConversationId.value === streamConversationId && activeController === streamController) {
    isStreaming.value = false
    activeController = null
  }
}

async function sendMessage() {
  const content = inputContent.value.trim()
  if (!content || isStreaming.value || !activeConversationId.value) return

  inputContent.value = ''
  resetTextarea()
  error.value = null
  retryContext.value = null

  const userMessage = reactive({ id: null, role: 'user', content })
  const assistantMessage = reactive({
    id: null,
    role: 'assistant',
    content: '',
    model: null,
    sources: [],
    isStreaming: true,
    stopped: false,
    agentStatus: null,
    activeTool: null,
  })
  messages.value.push(userMessage, assistantMessage)
  await nextTick()
  scrollToBottom()

  await executeStreaming({
    mode: mode.value,
    conversationId: activeConversationId.value,
    content,
    userMessage,
    assistantMessage,
    removeOnError: false,
  })
}

async function retry() {
  if (isStreaming.value || !retryContext.value) return

  const context = retryContext.value
  if (context.conversationId !== activeConversationId.value) return
  error.value = null
  retryContext.value = null
  context.assistantMessage.content = ''
  context.assistantMessage.sources = []
  context.assistantMessage.isStreaming = true
  context.assistantMessage.stopped = false
  context.assistantMessage.agentStatus = null
  context.assistantMessage.activeTool = null

  await executeStreaming({ ...context, removeOnError: false })
}

async function regenerate() {
  if (!canRegenerate.value || !activeConversationId.value) return
  if (retryContext.value && retryContext.value.conversationId !== activeConversationId.value) return

  const conversationId = activeConversationId.value
  error.value = null
  retryContext.value = null
  const assistantMessage = reactive({
    id: null,
    role: 'assistant',
    content: '',
    model: null,
    sources: [],
    isStreaming: true,
    stopped: false,
    agentStatus: null,
    activeTool: null,
  })
  messages.value.push(assistantMessage)
  await nextTick()
  scrollToBottom()

  await executeStreaming({
    stream: streamRegenerate,
    conversationId,
    assistantMessage,
    removeOnError: true,
  })
}

function dismissError() {
  error.value = null
  retryContext.value = null
}

function resetTextarea() {
  const el = textareaRef.value
  if (el) {
    el.style.height = 'auto'
  }
}

function stopGeneration() {
  if (activeController) {
    activeController.abort()
  }
}

function onDocumentClick(event) {
  if (!event.target.closest('.conversation-actions')) {
    closeConversationMenu()
  }
}

function onDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  if (confirmDeleteId.value !== null) {
    closeDeleteConfirmation()
  } else if (editingConversationId.value !== null) {
    cancelRename()
  } else {
    closeConversationMenu()
  }
}

onMounted(() => {
  loadConversations()
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  isMounted = false
  listRequestSeq += 1
  activeController?.abort()
  activeController = null
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div class="chat-page">
    <div
      v-if="isSidebarOpen"
      class="backdrop"
      @click="toggleSidebar"
    />

    <aside
      class="sidebar"
      :class="{ open: isSidebarOpen }"
    >
      <div class="sidebar-header">
        <div class="brand">
          <span class="brand-mark">✦</span>
          <span class="brand-name">智行 AI</span>
        </div>
        <button
          type="button"
          class="new-btn"
          :disabled="isCreating"
          @click="createNewConversation"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          {{ isCreating ? '正在新建…' : '新建对话' }}
        </button>
      </div>

      <div class="sidebar-search">
        <label for="conversation-search">搜索对话</label>
        <input
          id="conversation-search"
          v-model="conversationSearch"
          class="conversation-search-input"
          type="search"
          placeholder="搜索对话"
          autocomplete="off"
        >
      </div>

      <div class="conversation-list">
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
          <strong>会话加载失败</strong>
          <span>{{ conversationListError }}</span>
          <button
            type="button"
            class="conversation-list-retry"
            @click="loadConversations"
          >
            Retry
          </button>
        </div>
        <div
          v-else-if="conversations.length === 0"
          class="sidebar-hint"
        >
          还没有对话
        </div>
        <div
          v-if="conversationListError && conversations.length > 0"
          class="sidebar-refresh-error"
          role="alert"
        >
          <span>刷新会话失败</span>
          <button
            type="button"
            class="conversation-list-retry"
            @click="loadConversations"
          >
            Retry
          </button>
        </div>
        <div
          v-if="conversations.length > 0 && filteredConversations.length === 0"
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
            :class="{ active: conv.id === activeConversationId }"
            :aria-current="conv.id === activeConversationId ? 'true' : undefined"
            @click="selectConversation(conv.id)"
          >
            <span
              class="conversation-title"
              @dblclick.stop="startRename(conv)"
            >{{ conv.title }}</span>
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
              ...
            </button>
            <div
              v-if="openConversationMenuId === conv.id"
              class="conversation-menu"
              role="menu"
              @click.stop
            >
              <button
                type="button"
                role="menuitem"
                :disabled="isStreaming"
                @click="startRename(conv)"
              >
                重命名
              </button>
              <button
                type="button"
                role="menuitem"
                class="danger"
                :disabled="isStreaming"
                @click="requestDelete(conv.id, $event)"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="sidebar-footer">
        <button
          type="button"
          class="knowledge-nav-btn"
          aria-label="知识库"
          @click="router.push('/knowledge')"
        >
          知识库
        </button>
        <div class="footer-user">
          <span class="footer-dot" />
          <span class="footer-username">{{ authStore.user?.username || '已登录' }}</span>
        </div>
        <button
          type="button"
          class="logout-btn"
          aria-label="退出登录"
          @click="handleLogout"
        >
          退出登录
        </button>
      </div>
    </aside>

    <section class="main">
      <header class="chat-header">
        <button
          type="button"
          class="menu-btn"
          aria-label="打开菜单"
          @click="toggleSidebar"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span class="header-title">{{ activeConversationTitle }}</span>
        <span class="header-badge">AI Chat</span>
      </header>

      <div
        v-if="messagesLoading"
        class="messages"
      >
        <div
          v-for="i in 3"
          :key="i"
          class="skeleton-message"
          :class="i % 2 === 0 ? 'right' : 'left'"
        />
      </div>
      <div
        v-else-if="messagesError"
        class="messages"
      >
        <div class="empty-state error">
          {{ messagesError }}
        </div>
      </div>
      <div
        v-else-if="!activeConversationId"
        class="messages"
      >
        <div class="empty-state">
          <div class="empty-mark">
            ✦
          </div>
          <h2 class="empty-title">
            选择或新建一个会话
          </h2>
          <p class="empty-subtitle">
            开始你的 AI 对话之旅
          </p>
        </div>
      </div>
      <div
        v-else
        ref="messagesContainer"
        class="messages"
        @scroll="onScroll"
      >
        <div
          v-if="messages.length === 0"
          class="empty-state"
        >
          <div class="empty-mark">
            ✦
          </div>
          <h2 class="empty-title">
            有什么可以帮你？
          </h2>
          <p class="empty-subtitle">
            选择下面一个问题，或直接输入你的想法
          </p>
          <div class="suggestions">
            <button
              v-for="s in suggestions"
              :key="s"
              type="button"
              class="suggestion-card"
              @click="fillSuggestion(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="message"
          :class="msg.role"
        >
          <AssistantMessage
            v-if="msg.role === 'assistant'"
            :message="msg"
          />
          <div
            v-else
            class="message-body"
          >
            <div class="bubble">
              {{ msg.content }}
            </div>
          </div>
        </div>
      </div>

      <button
        v-if="showScrollToBottom"
        type="button"
        class="scroll-bottom-btn"
        aria-label="回到底部"
        @click="handleScrollToBottom"
      >
        ↓
      </button>

      <div
        v-if="error"
        class="error-banner"
      >
        <span>{{ error }}</span>
        <button
          v-if="retryContext"
          type="button"
          class="retry-btn"
          @click="retry"
        >
          Retry
        </button>
        <button
          type="button"
          class="error-close"
          aria-label="关闭"
          @click="dismissError"
        >
          ×
        </button>
      </div>

      <div
        v-if="activeConversationId"
        class="composer-wrap"
      >
        <div class="composer">
          <textarea
            ref="textareaRef"
            v-model="inputContent"
            class="composer-input"
            rows="1"
            placeholder="给 AI 发消息…"
            @input="autoResize"
            @keydown="onComposerKeydown"
          />
          <div class="composer-actions">
            <span class="composer-hint">Enter 发送 · Shift+Enter 换行</span>
            <div class="mode-selector">
              <button
                type="button"
                class="mode-btn"
                :class="{ active: mode === 'chat' }"
                :aria-pressed="mode === 'chat'"
                @click="mode = 'chat'"
              >
                普通
              </button>
              <button
                type="button"
                class="mode-btn"
                :class="{ active: mode === 'rag' }"
                :aria-pressed="mode === 'rag'"
                @click="mode = 'rag'"
              >
                知识库
              </button>
              <button
                type="button"
                class="mode-btn"
                :class="{ active: mode === 'agent' }"
                :aria-pressed="mode === 'agent'"
                @click="mode = 'agent'"
              >
                Agent
              </button>
            </div>
            <button
              v-if="showRegenerate"
              type="button"
              class="regenerate-btn"
              :disabled="!canRegenerate"
              @click="regenerate"
            >
              重新生成
            </button>
            <button
              v-if="isStreaming"
              type="button"
              class="send-btn stop"
              aria-label="停止生成"
              @click="stopGeneration"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <rect
                  x="6"
                  y="6"
                  width="12"
                  height="12"
                  rx="2"
                />
              </svg>
            </button>
            <button
              v-else
              type="submit"
              class="send-btn"
              aria-label="发送"
              :disabled="!inputContent.trim()"
              @click="sendMessage"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

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
      >
        <h2 id="delete-dialog-title">
          删除对话
        </h2>
        <p id="delete-dialog-description">
          删除后，该对话及其消息将无法恢复。
          <span class="legacy-delete-copy">删除后无法恢复</span>
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
  </div>
</template>

<style scoped>
.chat-page {
  --bg: #f7f7f8;
  --surface: #ffffff;
  --surface-hover: #f4f4f5;
  --border: #e8e8ea;
  --text-primary: #1f1f23;
  --text-secondary: #71717a;
  --accent: #4f46e5;
  --accent-soft: rgba(79, 70, 229, 0.08);
  --danger: #dc2626;

  display: flex;
  height: 100vh;
  width: 100vw;
  background: var(--bg);
  color: var(--text-primary);
  overflow: hidden;
  font-family: system-ui, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--border);
  box-sizing: border-box;
  overflow-x: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 16px;
}

.brand-mark {
  color: var(--accent);
}

.new-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.new-btn:hover {
  background: var(--surface-hover);
}

.new-btn:focus-visible,
.sidebar-search input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.new-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.new-btn svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 8px;
}

.sidebar-search {
  display: grid;
  gap: 5px;
  padding: 0 16px 8px;
}

.sidebar-search label {
  color: var(--text-secondary);
  font-size: 12px;
}

.sidebar-search input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--surface);
  color: var(--text-primary);
  font: inherit;
  font-size: 14px;
}

.sidebar-hint {
  color: var(--text-secondary);
  font-size: 13px;
  padding: 8px 10px;
}

.sidebar-hint.error {
  color: var(--danger);
}

.sidebar-load-error,
.sidebar-refresh-error {
  display: grid;
  gap: 8px;
  margin: 4px 2px;
  padding: 10px;
  border: 1px solid rgba(220, 38, 38, 0.25);
  border-radius: 8px;
  background: #fef2f2;
  color: var(--danger);
  font-size: 13px;
}

.sidebar-refresh-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-load-error button,
.sidebar-refresh-error button {
  width: fit-content;
  border: 1px solid currentColor;
  border-radius: 6px;
  padding: 4px 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.sidebar-load-error button:hover,
.sidebar-load-error button:focus-visible,
.sidebar-refresh-error button:hover,
.sidebar-refresh-error button:focus-visible {
  background: rgba(220, 38, 38, 0.08);
}

.skeleton-list {
  padding: 4px;
}

.skeleton-item {
  height: 36px;
  border-radius: 8px;
  margin-bottom: 8px;
  background: var(--surface-hover);
  animation: pulse 1.4s ease-in-out infinite;
}

.conversation-row {
  display: flex;
  align-items: center;
  position: relative;
  gap: 2px;
}

.conversation-item {
  display: block;
  flex: 1;
  min-width: 0;
  text-align: left;
  padding: 10px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.conversation-item:hover {
  background: var(--surface-hover);
}

.conversation-item.active {
  background: var(--accent-soft);
  color: var(--accent);
}

.conversation-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-rename-input {
  flex: 1;
  width: 100%;
  min-width: 0;
  border: 1px solid var(--accent);
  border-radius: 5px;
  padding: 3px 5px;
  color: var(--text-primary);
  font: inherit;
  background: var(--surface);
  outline: none;
}

.conversation-more {
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  padding: 7px 8px;
  cursor: pointer;
  line-height: 1;
  font-weight: 700;
}

.conversation-more:hover,
.conversation-more:focus-visible {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.conversation-menu {
  position: absolute;
  top: calc(100% - 3px);
  right: 0;
  z-index: 10;
  min-width: 104px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.12);
}

.conversation-menu button {
  display: block;
  width: 100%;
  border: none;
  border-radius: 5px;
  padding: 7px 8px;
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.conversation-menu button:hover:not(:disabled),
.conversation-menu button:focus-visible:not(:disabled) {
  background: var(--surface-hover);
}

.conversation-menu button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.danger {
  color: #b45309;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 13px;
}

.knowledge-nav-btn {
  flex-shrink: 0;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.knowledge-nav-btn:hover,
.knowledge-nav-btn:focus-visible {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.footer-user {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.footer-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
}

.footer-username {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-btn {
  flex-shrink: 0;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.logout-btn:hover,
.logout-btn:focus-visible {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.menu-btn {
  display: none;
  border: none;
  background: transparent;
  padding: 4px;
  cursor: pointer;
  color: var(--text-primary);
}

.menu-btn svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}

.header-title {
  font-weight: 600;
  font-size: 15px;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-badge {
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 32px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.skeleton-message {
  width: 160px;
  height: 40px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-message.right {
  align-self: flex-end;
  background: var(--accent-soft);
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}

.empty-state.error {
  color: var(--danger);
}

.empty-mark {
  font-size: 32px;
  color: var(--accent);
  margin-bottom: 12px;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
}

.empty-subtitle {
  margin: 0 0 24px;
  color: var(--text-secondary);
  font-size: 15px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  width: 100%;
  max-width: 560px;
}

.suggestion-card {
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.suggestion-card:hover {
  border-color: var(--accent);
  background: var(--surface-hover);
}

.message {
  display: flex;
  gap: 12px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

.message.user {
  justify-content: flex-end;
}

.message-body {
  max-width: 78%;
  min-width: 0;
}

.message.user .message-body {
  display: flex;
  justify-content: flex-end;
}

.bubble {
  display: inline-block;
  padding: 12px 16px;
  border-radius: 18px;
  border-bottom-right-radius: 6px;
  background: var(--accent);
  color: #fff;
  font-size: 15px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.scroll-bottom-btn {
  position: absolute;
  bottom: 130px;
  left: 50%;
  transform: translateX(-50%);
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--text-primary);
  font-size: 18px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 20px 10px;
  padding: 8px 12px;
  border: 1px solid rgba(220, 38, 38, 0.2);
  border-radius: 8px;
  background: #fef2f2;
  color: var(--danger);
  font-size: 13px;
}

.error-close {
  border: none;
  background: transparent;
  color: var(--danger);
  font-size: 16px;
  cursor: pointer;
  line-height: 1;
}

.retry-btn,
.regenerate-btn {
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.retry-btn {
  margin-left: auto;
  padding: 3px 8px;
}

.regenerate-btn {
  margin-left: auto;
  margin-right: 8px;
  padding: 5px 8px;
  color: var(--accent);
}

.retry-btn:hover,
.retry-btn:focus-visible,
.regenerate-btn:hover,
.regenerate-btn:focus-visible {
  background: var(--accent-soft);
}

.regenerate-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.composer-wrap {
  padding: 0 20px 20px;
  background: var(--bg);
}

.composer {
  max-width: 800px;
  margin: 0 auto;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface);
  padding: 8px 8px 8px 16px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.composer-input {
  display: block;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 8px 0;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.6;
  color: var(--text-primary);
  background: transparent;
  max-height: 200px;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 6px;
}

.composer-hint {
  font-size: 11px;
  color: var(--text-secondary);
}

.mode-selector {
  margin-left: auto;
  margin-right: 8px;
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
}

.mode-btn {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.mode-btn:hover,
.mode-btn:focus-visible,
.mode-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft, rgba(79, 70, 229, 0.08));
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn.stop {
  background: #fef2f2;
  color: var(--danger);
}

.send-btn svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.backdrop {
  display: none;
}

.confirm-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.32);
}

.confirm-modal {
  width: min(100%, 360px);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  background: var(--surface);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}

.confirm-modal h2,
.confirm-modal p {
  margin: 0;
}

.confirm-modal p {
  margin-top: 8px;
  color: var(--text-secondary);
}

.legacy-delete-copy {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

.confirm-actions button {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 7px 13px;
  background: var(--surface);
  color: var(--text-primary);
  cursor: pointer;
}

.confirm-actions button:hover:not(:disabled),
.confirm-actions button:focus-visible:not(:disabled) {
  background: var(--surface-hover);
}

.confirm-actions .danger {
  border-color: #d97706;
  background: #fffbeb;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@media (max-width: 768px) {
  .sidebar {
    width: min(280px, 92vw);
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 30;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 20;
    background: rgba(0, 0, 0, 0.32);
  }

  .menu-btn {
    display: block;
  }

  .message-body {
    max-width: 92%;
  }

  .suggestions {
    grid-template-columns: 1fr;
  }
}
</style>
