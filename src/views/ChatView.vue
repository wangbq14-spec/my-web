<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createConversation,
  deleteConversation,
  listConversations,
  updateConversation,
} from '../api/modules/conversation'
import { listMessages } from '../api/modules/message'
import { listDocuments } from '../api/modules/document'
import { listProjects, updateProject } from '../api/modules/project'
import { streamAgent, streamChat, streamRegenerate } from '../api/stream'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import AssistantMessage from '../components/chat/AssistantMessage.vue'
import { useAuthStore } from '../stores/auth'

const MAX_TEXTAREA_HEIGHT = 200

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const conversations = ref([])
const projects = ref([])
const SIDEBAR_COLLAPSED_KEY = 'omnixa.sidebar.collapsed'
const defaultCollapsedSections = {
  pinned: false,
  projects: false,
  conversations: false,
}

function readCollapsedSections() {
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

const collapsedSections = reactive(readCollapsedSections())
const activeProjectId = ref(null)
const conversationListLoading = ref(false)
const conversationListError = ref(null)
const conversationSearch = ref('')
const recentConversations = computed(() => conversations.value.filter((conversation) => !conversation.pinned))
const filteredConversations = computed(() => {
  const query = conversationSearch.value.trim().toLocaleLowerCase()
  if (!query) return recentConversations.value

  return recentConversations.value.filter((conversation) =>
    String(conversation.title || '').toLocaleLowerCase().includes(query),
  )
})

const activeConversationId = ref(null)
const activeConversationTitle = computed(() => {
  const current = conversations.value.find((c) => c.id === activeConversationId.value)
  return current?.title || '新对话'
})
const routeProjectId = computed(() => {
  const value = Array.isArray(route.query.project_id) ? route.query.project_id[0] : route.query.project_id
  return value === undefined || value === null || value === '' ? null : value
})
const activeProject = computed(() => projects.value.find((project) => String(project.id) === String(activeProjectId.value)))
const activeProjectName = computed(() => activeProject.value?.name || (activeProjectId.value ? `项目 ${activeProjectId.value}` : ''))
const recentProjects = computed(() => projects.value.slice(0, 3))
const pinnedConversations = computed(() => conversations.value.filter((conversation) => conversation.pinned).slice(0, 3))
const pinnedProjects = computed(() => projects.value.filter((project) => project.pinned).slice(0, 3))
const hasPinnedItems = computed(() => pinnedConversations.value.length > 0 || pinnedProjects.value.length > 0)
const knowledgeRouteActive = computed(() => (route.path || '').replace(/\/$/, '') === '/knowledge')

const messages = ref([])
const messagesLoading = ref(false)
const messagesError = ref(null)
const hasAddedMaterials = ref(null)

const inputContent = ref('')
const mode = ref('chat')
const isCapabilityPopoverOpen = ref(false)
const capabilityTriggerRef = ref(null)
const chatTitleRef = ref(null)
const isSidebarDrawer = ref(false)
const sidebarTriggerRef = ref(null)
const sidebarFirstControlRef = ref(null)
const isStreaming = ref(false)
const prefersReducedMotion = ref(false)
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
const conversationMenuOpensUp = ref(false)
const pinningConversationId = ref(null)
const pinningProjectId = ref(null)
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
let localMessageSequence = 0

const suggestionsByMode = {
  chat: [
    '这段代码是什么意思？',
    '我应该怎么规划这个项目？',
    '这段内容可以怎么总结？',
    '这个报错应该怎么解决？',
  ],
  rag: [
    '这份资料主要讲了什么？',
    '资料中有哪些关键结论？',
    '资料里的不同方案有什么区别？',
    '根据这些资料，我下一步应该怎么做？',
  ],
  agent: [
    '帮我比较这两个方案，并给出下一步建议',
    '把这个目标拆成可执行的步骤',
    '分析手头资料后，列出需要确认的风险点',
    '制定一个从现状到目标的行动计划',
  ],
}

const capabilityOptions = [
  {
    id: 'chat',
    name: '智能对话',
    description: '适合写作、分析、问答',
    placeholder: '问任何问题，或粘贴内容让我处理',
    helper: '提问、写作、分析，直接对话协作',
  },
  {
    id: 'rag',
    name: '使用资料',
    description: '基于上传资料进行检索与回答',
    placeholder: '就你的资料提问，例如：总结项目说明',
    helper: '从已添加资料中查找依据，并标出来源',
  },
  {
    id: 'agent',
    name: 'Agent',
    description: '自主规划并使用工具完成任务',
    placeholder: '描述目标，例如：比较方案并给出下一步',
    helper: '把目标拆成步骤，汇总可执行建议',
  },
]

const currentCapability = computed(
  () => capabilityOptions.find((option) => option.id === mode.value) || capabilityOptions[0],
)
const suggestions = computed(() => suggestionsByMode[mode.value] || suggestionsByMode.chat)
const isConversationActive = computed(() => messages.value.length > 0 || isStreaming.value)
const isComposerBreathing = computed(
  () => !inputContent.value.trim() && !isStreaming.value && !prefersReducedMotion.value,
)

function getFocusableElements(container) {
  if (!container) return []
  return [...container.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hasAttribute('hidden'))
}

function focusCurrentCapability() {
  nextTick(() => document.querySelector(`.capability-option[data-mode="${mode.value}"]`)?.focus())
}

function openCapabilityPopover() {
  isCapabilityPopoverOpen.value = true
  focusCurrentCapability()
}

function closeCapabilityPopover({ restoreFocus = true } = {}) {
  if (!isCapabilityPopoverOpen.value) return
  isCapabilityPopoverOpen.value = false
  if (restoreFocus) nextTick(() => capabilityTriggerRef.value?.focus())
}

function toggleCapabilityPopover() {
  if (isCapabilityPopoverOpen.value) {
    closeCapabilityPopover()
  } else {
    openCapabilityPopover()
  }
}

function selectCapability(nextMode) {
  mode.value = nextMode
  closeCapabilityPopover()
}

async function loadMaterialAvailability() {
  try {
    const documents = await listDocuments()
    if (isMounted) hasAddedMaterials.value = Array.isArray(documents) && documents.length > 0
  } catch {
    // Keep the prompt hidden when material availability cannot be determined.
  }
}

async function loadProjects() {
  try {
    const result = await listProjects()
    if (isMounted) projects.value = Array.isArray(result) ? result : []
  } catch {
    // Project navigation remains available when this lightweight sidebar section cannot load.
  }
}

function applyCapabilityFromRoute() {
  const requestedMode = Array.isArray(route.query.mode) ? route.query.mode[0] : route.query.mode
  if (!capabilityOptions.some((option) => option.id === requestedMode)) return

  mode.value = requestedMode
  const query = { ...route.query }
  delete query.mode
  router.replace({ query })
}

function onCapabilityKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeCapabilityPopover()
    return
  }
  if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!isCapabilityPopoverOpen.value) {
    openCapabilityPopover()
    return
  }
  const options = [...document.querySelectorAll('.capability-option')]
  const currentIndex = options.indexOf(document.activeElement)
  const nextIndex = event.key === 'ArrowDown'
    ? (currentIndex + 1 + options.length) % options.length
    : (currentIndex - 1 + options.length) % options.length
  options[nextIndex]?.focus()
}

function getMessageKey(message) {
  return message.id != null ? `message-${message.id}` : message.localId
}

function normalizeMessage(message) {
  return {
    ...message,
    content: message?.content ?? '',
    localId: message?.localId ?? `local-message-${++localMessageSequence}`,
  }
}

function updateSidebarDrawerState() {
  isSidebarDrawer.value = window.matchMedia?.('(max-width: 768px)').matches ?? false
  if (!isSidebarDrawer.value) isSidebarOpen.value = false
}

function updateMotionPreference() {
  prefersReducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
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
      return right.id - left.id
    }
    if (hasLeftTime) return -1
    if (hasRightTime) return 1
    return 0
  })
}

function toggleSidebarSection(section) {
  collapsedSections[section] = !collapsedSections[section]
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, JSON.stringify(collapsedSections))
  } catch {
    // The sidebar still works when storage is unavailable.
  }
}

function conversationProjectName(conversation) {
  if (conversation?.project_id === undefined || conversation?.project_id === null) return ''
  return projects.value.find((project) => String(project.id) === String(conversation.project_id))?.name || ''
}

function isProjectActive(projectId) {
  const routeProjectParam = Array.isArray(route.params?.id) ? route.params.id[0] : route.params?.id
  if (routeProjectParam !== undefined && routeProjectParam !== null) {
    return String(routeProjectParam) === String(projectId)
  }
  return (route.path || '').replace(/\/$/, '') === `/projects/${projectId}`
}

function openProject(projectId) {
  isSidebarOpen.value = false
  router.push({ name: 'project-detail', params: { id: projectId } })
}

function navigateFromSidebar(location) {
  isSidebarOpen.value = false
  router.push(location)
}

function openProjectQuickCreate() {
  navigateFromSidebar({ path: '/projects', query: { create: '1' } })
}

async function toggleConversationPinned(conversation) {
  if (pinningConversationId.value !== null || isStreaming.value) return
  closeConversationMenu()
  const pinned = !conversation.pinned
  pinningConversationId.value = conversation.id
  try {
    const updated = await updateConversation(conversation.id, { pinned })
    const index = conversations.value.findIndex((item) => String(item.id) === String(conversation.id))
    if (index !== -1) conversations.value[index] = { ...conversations.value[index], ...updated, pinned }
  } catch {
    error.value = pinned ? '置顶会话失败，请稍后重试' : '取消置顶会话失败，请稍后重试'
  } finally {
    pinningConversationId.value = null
  }
}

async function toggleProjectPinned(project) {
  if (pinningProjectId.value !== null) return
  const pinned = !project.pinned
  pinningProjectId.value = project.id
  try {
    const updated = await updateProject(project.id, { pinned })
    const index = projects.value.findIndex((item) => String(item.id) === String(project.id))
    if (index !== -1) projects.value[index] = { ...projects.value[index], ...updated, pinned }
  } catch {
    error.value = pinned ? '置顶项目失败，请稍后重试' : '取消置顶项目失败，请稍后重试'
  } finally {
    pinningProjectId.value = null
  }
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
  const conversation = conversations.value.find((item) => String(item.id) === String(id))
  activeProjectId.value = conversation ? (conversation.project_id ?? null) : routeProjectId.value
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
    messages.value = Array.isArray(loadedMessages) ? loadedMessages.map(normalizeMessage) : []
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
  if (isSidebarDrawer.value) {
    nextTick(() => (textareaRef.value || chatTitleRef.value || messagesContainer.value)?.focus())
  }
}

async function openConversationFromRoute() {
  const requestedId = Array.isArray(route.query.conversation_id)
    ? route.query.conversation_id[0]
    : route.query.conversation_id
  if (requestedId === undefined || requestedId === null || requestedId === '') return

  const matchingConversation = conversations.value.find(
    (conversation) => String(conversation.id) === String(requestedId),
  )
  await selectConversation(matchingConversation?.id ?? requestedId)
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
      conversationMenuOpensUp.value = listRect.bottom - rowRect.bottom < 120
    }

    document.querySelector('.conversation-menu [role="menuitem"]')?.focus()
  })
}

function closeConversationMenu({ restoreFocus = true } = {}) {
  const trigger = menuTriggerRef.value
  openConversationMenuId.value = null
  conversationMenuOpensUp.value = false
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
  const moreButton = menuTriggerRef.value
  closeConversationMenu({ restoreFocus: false })
  deleteTriggerRef.value = moreButton ?? event?.currentTarget ?? null
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
    const conversation = await createConversation({
      title: '新对话',
      ...(activeProjectId.value ? { project_id: activeProjectId.value } : {}),
    })
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

function toggleSidebar(event) {
  const willOpen = !isSidebarOpen.value
  if (willOpen) {
    sidebarTriggerRef.value = event?.currentTarget ?? null
    isSidebarOpen.value = true
    nextTick(() => sidebarFirstControlRef.value?.focus())
    return
  }

  isSidebarOpen.value = false
  const trigger = sidebarTriggerRef.value
  sidebarTriggerRef.value = null
  if (trigger?.isConnected) nextTick(() => trigger.focus())
}

function closeSidebar({ restoreFocus = true } = {}) {
  if (!isSidebarOpen.value) return
  isSidebarOpen.value = false
  const trigger = sidebarTriggerRef.value
  sidebarTriggerRef.value = null
  if (restoreFocus && trigger?.isConnected) nextTick(() => trigger.focus())
}

function handleLogout() {
  authStore.logout()
  router.replace('/')
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
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduceMotion ? 'smooth' : 'auto' })
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

let ambientFrame = null
let pendingAmbientTarget = null
let pendingAmbientPoint = null

function canRenderAmbient() {
  return window.matchMedia?.('(hover: hover) and (pointer: fine)').matches &&
    !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function updateAmbientField(event) {
  if (!canRenderAmbient() || event.pointerType !== 'mouse') return

  pendingAmbientTarget = event.currentTarget
  pendingAmbientPoint = { clientX: event.clientX, clientY: event.clientY }
  if (ambientFrame !== null) return

  const schedule = window.requestAnimationFrame || ((callback) => window.setTimeout(callback, 32))
  ambientFrame = schedule(() => {
    const target = pendingAmbientTarget
    const point = pendingAmbientPoint
    ambientFrame = null
    if (!target || !point) return

    const rect = target.getBoundingClientRect()
    target.style.setProperty('--pointer-x', `${point.clientX - rect.left}px`)
    target.style.setProperty('--pointer-y', `${point.clientY - rect.top}px`)
  })
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
      if (activeConversationId.value !== streamConversationId) return
      if (streamTerminal) return
      assistantMessage.agentStatus = null
      assistantMessage.activeTool = null
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
  if (!content || isStreaming.value || isCreating.value) return

  if (!activeConversationId.value) {
    isCreating.value = true
    error.value = null
    try {
      const conversation = await createConversation({
        title: '新对话',
        ...(activeProjectId.value ? { project_id: activeProjectId.value } : {}),
      })
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
    } catch {
      if (isMounted) error.value = '新建会话失败，请稍后重试'
      return
    } finally {
      if (isMounted) isCreating.value = false
    }
  }

  inputContent.value = ''
  resetTextarea()
  error.value = null
  retryContext.value = null

  const userMessage = reactive({ id: null, localId: `local-message-${++localMessageSequence}`, role: 'user', content })
  const assistantMessage = reactive({
    id: null,
    localId: `local-message-${++localMessageSequence}`,
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
    localId: `local-message-${++localMessageSequence}`,
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
  if (!event.target.closest('.capability-selector')) {
    closeCapabilityPopover()
  }
}

function onDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  if (confirmDeleteId.value !== null) {
    closeDeleteConfirmation()
  } else if (isCapabilityPopoverOpen.value) {
    closeCapabilityPopover()
  } else if (isSidebarDrawer.value && isSidebarOpen.value) {
    closeSidebar()
  } else if (editingConversationId.value !== null) {
    cancelRename()
  } else {
    closeConversationMenu()
  }
}

function onDeleteDialogKeydown(event) {
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

function onSidebarKeydown(event) {
  if (event.key !== 'Tab' || !isSidebarDrawer.value || !isSidebarOpen.value) return
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

onMounted(() => {
  applyCapabilityFromRoute()
  activeProjectId.value = routeProjectId.value
  loadConversations().then(openConversationFromRoute)
  loadProjects()
  loadMaterialAvailability()
  updateSidebarDrawerState()
  updateMotionPreference()
  window.addEventListener('resize', updateSidebarDrawerState)
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})

watch(
  () => route.query.conversation_id,
  (conversationId, previousConversationId) => {
    if (conversationId !== previousConversationId) openConversationFromRoute()
  },
)

watch(routeProjectId, (projectId) => {
  activeProjectId.value = projectId
})

onBeforeUnmount(() => {
  isMounted = false
  listRequestSeq += 1
  activeController?.abort()
  activeController = null
  if (ambientFrame !== null && window.cancelAnimationFrame) {
    window.cancelAnimationFrame(ambientFrame)
  }
  ambientFrame = null
  pendingAmbientTarget = null
  pendingAmbientPoint = null
  window.removeEventListener('resize', updateSidebarDrawerState)
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div class="chat-page">
    <div
      class="chat-shell"
      :inert="confirmDeleteId !== null ? '' : undefined"
    >
      <button
        v-if="isSidebarOpen"
        type="button"
        class="backdrop"
        aria-label="关闭侧边栏"
        @click="closeSidebar"
      />

      <aside
        id="chat-sidebar"
        class="sidebar"
        :class="{ open: isSidebarOpen }"
        :role="isSidebarDrawer ? 'dialog' : undefined"
        :aria-modal="isSidebarDrawer && isSidebarOpen ? 'true' : undefined"
        :aria-label="isSidebarDrawer ? '导航侧边栏' : undefined"
        :inert="isSidebarDrawer && !isSidebarOpen ? '' : undefined"
        :aria-hidden="isSidebarDrawer && !isSidebarOpen ? 'true' : undefined"
        @keydown="onSidebarKeydown"
      >
        <div class="sidebar-header">
          <div class="brand">
            <BrandIdentity variant="compact" />
          </div>
          <button
            ref="sidebarFirstControlRef"
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

        <div class="sidebar-primary">
          <section class="sidebar-group pinned-section">
            <button
              type="button"
              class="sidebar-section-toggle"
              data-sidebar-section-toggle="pinned"
              aria-controls="sidebar-pinned-items"
              :aria-expanded="collapsedSections.pinned ? 'false' : 'true'"
              @click="toggleSidebarSection('pinned')"
            >
              <span>置顶</span>
              <svg
                class="section-chevron"
                :class="{ collapsed: collapsedSections.pinned }"
                viewBox="0 0 20 20"
                aria-hidden="true"
              >
                <path d="m6 8 4 4 4-4" />
              </svg>
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
                    :class="{ active: conv.id === activeConversationId }"
                    :aria-current="conv.id === activeConversationId ? 'true' : undefined"
                    @click="selectConversation(conv.id)"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path d="M5 5h14v10H9l-4 4Z" />
                    </svg>
                    <span class="pinned-entry-copy">
                      <span class="pinned-entry-title">{{ conv.title }}</span>
                      <small>会话</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="sidebar-pin-toggle"
                    :aria-label="`取消置顶会话：${conv.title}`"
                    :disabled="pinningConversationId !== null || isStreaming"
                    @click="toggleConversationPinned(conv)"
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
                    >
                      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5Z" />
                      <path d="M4 9h16" />
                    </svg>
                    <span class="pinned-entry-copy">
                      <span class="pinned-entry-title">{{ project.name }}</span>
                      <small>项目</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="sidebar-pin-toggle"
                    :aria-label="`取消置顶项目：${project.name}`"
                    :disabled="pinningProjectId !== null"
                    @click="toggleProjectPinned(project)"
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
                data-sidebar-section-toggle="projects"
                aria-controls="sidebar-recent-projects"
                :aria-expanded="collapsedSections.projects ? 'false' : 'true'"
                @click="toggleSidebarSection('projects')"
              >
                <svg
                  class="section-chevron"
                  :class="{ collapsed: collapsedSections.projects }"
                  viewBox="0 0 20 20"
                  aria-hidden="true"
                >
                  <path d="m6 8 4 4 4-4" />
                </svg>
                <span>项目</span>
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
                    >
                      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5Z" />
                      <path d="M4 9h16" />
                    </svg>
                    <span class="recent-project-copy">
                      <span class="recent-project-name">{{ project.name }}</span>
                      <small>{{ project.conversation_count || 0 }} 会话 · {{ project.document_count || 0 }} 资料</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="sidebar-pin-toggle project-pin-toggle"
                    :aria-label="`${project.pinned ? '取消置顶' : '置顶'}项目：${project.name}`"
                    :disabled="pinningProjectId !== null"
                    @click="toggleProjectPinned(project)"
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
              :aria-current="knowledgeRouteActive ? 'page' : undefined"
              @click="navigateFromSidebar('/knowledge')"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v17.5H7.5A2.5 2.5 0 0 0 5 22Z" />
                <path d="M5 4.5v15" />
                <path d="M9 6h6M9 10h6" />
              </svg>
              <span>知识库</span>
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
            @click="toggleSidebarSection('conversations')"
          >
            <span>最近</span>
            <svg
              class="section-chevron"
              :class="{ collapsed: collapsedSections.conversations }"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path d="m6 8 4 4 4-4" />
            </svg>
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
                <strong>会话加载失败</strong>
                <span>{{ conversationListError }}</span>
                <button
                  type="button"
                  class="conversation-list-retry"
                  @click="loadConversations"
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
                <span>刷新会话失败</span>
                <button
                  type="button"
                  class="conversation-list-retry"
                  @click="loadConversations"
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
                  :class="{ active: conv.id === activeConversationId }"
                  :aria-current="conv.id === activeConversationId ? 'true' : undefined"
                  @click="selectConversation(conv.id)"
                >
                  <svg
                    class="conversation-icon"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M5 5h14v10H9l-4 4Z" />
                  </svg>
                  <span class="conversation-copy">
                    <span
                      class="conversation-title"
                      @dblclick.stop="startRename(conv)"
                    >{{ conv.title }}</span>
                    <span
                      v-if="conversationProjectName(conv)"
                      class="conversation-project-tag"
                    >{{ conversationProjectName(conv) }}</span>
                  </span>
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
                    >
                      <path d="M5 12h.01M12 12h.01M19 12h.01" />
                    </svg>
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
                    <button
                      type="button"
                      role="menuitem"
                      :disabled="isStreaming || pinningConversationId !== null"
                      @click="toggleConversationPinned(conv)"
                    >
                      {{ conv.pinned ? '取消置顶' : '置顶' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </Transition>
        </section>

        <div class="sidebar-footer">
          <div class="footer-account-row">
            <span>当前用户</span>
            <strong class="footer-username">{{ authStore.user?.username || '已登录' }}</strong>
          </div>
          <div class="footer-settings-row">
            <span>设置 / 主题</span>
            <ThemeToggle />
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

      <section
        class="main"
        :class="{ 'is-conversation-active': isConversationActive }"
        :inert="isSidebarDrawer && isSidebarOpen ? '' : undefined"
      >
        <header class="chat-header">
          <button
            type="button"
            class="menu-btn"
            aria-controls="chat-sidebar"
            :aria-expanded="isSidebarOpen ? 'true' : 'false'"
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
          <span
            ref="chatTitleRef"
            class="header-title"
            tabindex="-1"
          >{{ activeConversationTitle }}</span>
          <span class="header-context">{{ currentCapability.name }}</span>
        </header>
        <div
          v-if="activeProjectId"
          class="project-context-bar"
        >
          <span>当前项目：{{ activeProjectName }}</span>
          <button
            type="button"
            @click="router.push({ name: 'project-detail', params: { id: activeProjectId } })"
          >
            返回项目
          </button>
        </div>

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
          v-else-if="isConversationActive"
          ref="messagesContainer"
          class="messages conversation-messages"
          @scroll="onScroll"
        >
          <div
            v-for="msg in messages"
            :key="getMessageKey(msg)"
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
        <section
          v-else
          class="idle-workbench"
          aria-label="Omnixa 工作台"
        >
          <div class="idle-intro">
            <div class="empty-mark">
              <span class="idle-wordmark">Omnixa</span>
            </div>
            <h2 class="empty-title">
              今天想做些什么？
            </h2>
          </div>
          <div class="suggestions idle-prompt-rows">
            <button
              v-for="s in suggestions"
              :key="s"
              type="button"
              class="suggestion-card prompt-row"
              @click="fillSuggestion(s)"
            >
              {{ s }}
            </button>
            <button
              v-if="currentCapability.id === 'rag' && hasAddedMaterials === false"
              type="button"
              class="empty-knowledge-link"
              @click="router.push('/knowledge')"
            >
              前往添加资料
            </button>
          </div>
        </section>

        <button
          v-if="showScrollToBottom"
          type="button"
          class="scroll-bottom-btn"
          aria-label="回到底部"
          @click="handleScrollToBottom"
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="M12 5v14M6 13l6 6 6-6" />
          </svg>
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
            重试
          </button>
          <button
            type="button"
            class="error-close"
            aria-label="关闭"
            @click="dismissError"
          >
            <svg
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="m6 6 12 12M18 6 6 18" />
            </svg>
          </button>
        </div>

        <div
          class="composer-wrap"
          :class="{ 'is-idle': !isConversationActive, 'is-conversation': isConversationActive }"
        >
          <div
            class="composer"
            :class="{ 'inward-breathing': isComposerBreathing }"
          >
            <textarea
              ref="textareaRef"
              v-model="inputContent"
              class="composer-input"
              rows="1"
              :placeholder="currentCapability.placeholder"
              :aria-label="currentCapability.placeholder"
              @input="autoResize"
              @keydown="onComposerKeydown"
            />
            <div class="composer-actions composer-control-rail">
              <div class="composer-meta">
                <div
                  class="capability-selector"
                  @keydown="onCapabilityKeydown"
                >
                  <button
                    ref="capabilityTriggerRef"
                    type="button"
                    class="capability-trigger"
                    aria-haspopup="menu"
                    :aria-controls="isCapabilityPopoverOpen ? 'capability-popover' : undefined"
                    :aria-expanded="isCapabilityPopoverOpen ? 'true' : 'false'"
                    @click="toggleCapabilityPopover"
                  >
                    <svg
                      v-if="currentCapability.id === 'chat'"
                      class="capability-icon"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path d="m12 3 1.4 5.1L18.5 9.5l-5.1 1.4L12 16l-1.4-5.1-5.1-1.4 5.1-1.4L12 3Z" />
                      <path d="m18 15 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7L18 15Z" />
                    </svg>
                    <svg
                      v-else-if="currentCapability.id === 'rag'"
                      class="capability-icon"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path d="M6 3.5h8l4 4v13H6Z" />
                      <path d="M14 3.5v4h4M9 12h4" />
                      <circle
                        cx="15.5"
                        cy="16"
                        r="2.5"
                      />
                      <path d="m17.3 17.8 2.2 2.2" />
                    </svg>
                    <svg
                      v-else
                      class="capability-icon"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <circle
                        cx="12"
                        cy="12"
                        r="3"
                      />
                      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
                    </svg>
                    <span>{{ currentCapability.name }}</span>
                    <span
                      class="capability-caret"
                      aria-hidden="true"
                    >
                      <svg viewBox="0 0 24 24">
                        <path d="m7 10 5 5 5-5" />
                      </svg>
                    </span>
                  </button>
                  <div
                    v-if="isCapabilityPopoverOpen"
                    class="capability-popover-shell"
                    @pointermove="updateAmbientField"
                  >
                    <span
                      class="ambient-field capability-ambient"
                      aria-hidden="true"
                      style="pointer-events: none"
                    />
                    <p
                      id="capability-popover-title"
                      class="capability-popover-title"
                    >
                      告诉 Omnixa 可用什么能力
                    </p>
                    <div
                      id="capability-popover"
                      class="capability-popover"
                      role="menu"
                      aria-labelledby="capability-popover-title"
                    >
                      <button
                        v-for="option in capabilityOptions"
                        :key="option.id"
                        type="button"
                        class="capability-option"
                        :class="{ selected: mode === option.id }"
                        :data-mode="option.id"
                        role="menuitemradio"
                        :aria-checked="mode === option.id ? 'true' : 'false'"
                        @click="selectCapability(option.id)"
                      >
                        <span
                          class="capability-icon"
                          aria-hidden="true"
                        >
                          <svg
                            v-if="option.id === 'chat'"
                            viewBox="0 0 24 24"
                          >
                            <path d="m12 3 1.4 5.1L18.5 9.5l-5.1 1.4L12 16l-1.4-5.1-5.1-1.4 5.1-1.4L12 3Z" />
                            <path d="m18 15 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7L18 15Z" />
                          </svg>
                          <svg
                            v-else-if="option.id === 'rag'"
                            viewBox="0 0 24 24"
                          >
                            <path d="M6 3.5h8l4 4v13H6Z" />
                            <path d="M14 3.5v4h4M9 12h4" />
                            <circle
                              cx="15.5"
                              cy="16"
                              r="2.5"
                            />
                            <path d="m17.3 17.8 2.2 2.2" />
                          </svg>
                          <svg
                            v-else
                            viewBox="0 0 24 24"
                          >
                            <circle
                              cx="12"
                              cy="12"
                              r="3"
                            />
                            <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
                          </svg>
                        </span>
                        <span class="capability-copy">
                          <strong>{{ option.name }}</strong>
                          <small>{{ option.description }}</small>
                        </span>
                        <span
                          v-if="mode === option.id"
                          class="capability-check"
                          aria-hidden="true"
                        >
                          <svg viewBox="0 0 24 24">
                            <path d="m5 12 4.5 4.5L19 7" />
                          </svg>
                        </span>
                      </button>
                    </div>
                  </div>
                </div>
                <span class="composer-helper">{{ currentCapability.helper }}</span>
              </div>
              <span class="composer-hint">Enter 发送 · Shift+Enter 换行</span>
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
                <span>停止</span>
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
    </div>

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
        @keydown="onDeleteDialogKeydown"
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
  --chat-focus-width: 2px;
  --chat-focus-offset: 2px;
  --chat-space-tight: 3px;
  --chat-space-1-25: 5px;
  --chat-space-1-5: 6px;
  --chat-space-2-5: 10px;
  --chat-space-3-5: 14px;
  --chat-icon-sm: 14px;
  --chat-menu-min-width: 104px;
  --chat-bubble-radius: var(--radius-2xl);
  --chat-scroll-to-bottom-offset: 130px;
  display: flex;
  height: 100vh;
  height: 100dvh;
  width: 100vw;
  background: var(--color-bg);
  color: var(--color-text-primary);
  overflow: hidden;
  font-family: var(--font-sans);
}

.chat-shell {
  display: flex;
  flex: 1;
  min-width: 0;
}

.sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface-sunken);
  border-right: 1px solid var(--color-border-subtle);
  box-sizing: border-box;
  overflow-x: hidden;
}

.sidebar-header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-secondary-identity);
  font-weight: 700;
  font-size: var(--text-md);
}


.new-btn {
  display: flex;
  align-items: center;
  min-height: var(--space-11);
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border: 0;
  border-radius: var(--radius-xl);
  background: transparent;
  color: var(--color-secondary-identity);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.new-btn:hover,
.new-btn:focus-visible {
  background: var(--color-accent-soft);
}

.chat-page :is(button, input, textarea):focus-visible {
  outline: var(--chat-focus-width) solid var(--color-focus-ring);
  outline-offset: var(--chat-focus-offset);
  box-shadow: 0 0 0 var(--chat-focus-width) color-mix(in srgb, var(--color-focus-ring) 28%, transparent);
}

.new-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.new-btn svg {
  width: var(--chat-icon-sm);
  height: var(--chat-icon-sm);
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}

.conversation-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--space-1) var(--space-2);
  scrollbar-gutter: stable;
}

.sidebar-search {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-1);
  padding: 0 var(--space-4) var(--space-2);
}

.sidebar-search label {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.sidebar-search input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--chat-space-2-5);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
}

.sidebar-primary {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-1);
  padding: 0 var(--space-2) var(--space-1);
}

.sidebar-group {
  min-width: 0;
}

.sidebar-section-toggle {
  display: flex;
  width: 100%;
  min-height: var(--space-8);
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  border: 0;
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-align: left;
  cursor: pointer;
}

.sidebar-section-toggle:hover,
.sidebar-section-toggle:focus-visible {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.section-chevron {
  width: var(--space-4);
  height: var(--space-4);
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.7;
  transition: transform var(--duration-normal) var(--ease-standard);
}

.section-chevron.collapsed {
  transform: rotate(-90deg);
}

.sidebar-collapse-enter-active,
.sidebar-collapse-leave-active {
  transform-origin: top;
  transition: opacity var(--duration-normal) var(--ease-standard), transform var(--duration-normal) var(--ease-standard);
}

.sidebar-collapse-enter-from,
.sidebar-collapse-leave-to {
  opacity: 0;
  transform: scaleY(0.96) translateY(-4px);
}

.sidebar-collapsible {
  transform-origin: top;
}

.project-section-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: var(--space-1);
}

.project-section-toggle {
  flex: 1;
  min-width: 0;
  justify-content: flex-start;
}

.project-section-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 1px;
}

.project-section-action {
  width: var(--space-8);
  height: var(--space-8);
  border: 0;
  border-radius: var(--radius-md);
  padding: 0;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-md);
  line-height: 1;
  cursor: pointer;
}

.project-section-action:hover,
.project-section-action:focus-visible {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.workspace-nav-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: var(--space-11);
  gap: var(--space-3);
  border: 0;
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.workspace-nav-item svg {
  width: var(--space-4);
  height: var(--space-4);
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.workspace-nav-item:hover,
.workspace-nav-item:focus-visible {
  background: var(--color-surface-sunken);
  color: var(--color-accent);
}

.workspace-nav-item[aria-current="page"] {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-weight: 650;
}

.knowledge-nav-item {
  border-radius: var(--radius-md);
  padding: var(--space-2);
}

.sidebar-empty-hint {
  padding: var(--space-1) var(--space-2) var(--space-2);
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.pinned-list {
  display: grid;
  gap: 1px;
}

.pinned-entry-row,
.recent-project-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 1px;
}

.pinned-entry {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: var(--space-9);
  align-items: center;
  gap: var(--space-2);
  border: 0;
  border-radius: var(--radius-lg);
  padding: var(--space-1) var(--space-2);
  overflow: hidden;
  background: transparent;
  color: var(--color-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.pinned-entry > svg,
.recent-project-link > svg {
  width: var(--space-4);
  height: var(--space-4);
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.pinned-conversation-entry > svg {
  color: var(--color-accent);
}

.pinned-project-entry > svg {
  color: var(--color-secondary-identity);
}

.pinned-entry-copy,
.recent-project-copy {
  display: grid;
  min-width: 0;
  gap: 1px;
}

.pinned-entry-title,
.recent-project-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pinned-entry small,
.recent-project-link small {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  font-weight: 400;
}

.pinned-entry:hover,
.pinned-entry:focus-visible {
  background: var(--color-surface-hover);
}

.pinned-entry.active {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent);
  background: var(--color-surface-hover);
  font-weight: 650;
}

.sidebar-pin-toggle {
  width: var(--space-9);
  min-width: var(--space-9);
  height: var(--space-9);
  border: 0;
  border-radius: var(--radius-lg);
  padding: 0;
  background: transparent;
  color: var(--color-accent);
  font: inherit;
  cursor: pointer;
}

.sidebar-pin-toggle:hover:not(:disabled),
.sidebar-pin-toggle:focus-visible:not(:disabled) {
  background: var(--color-surface-hover);
}

.sidebar-pin-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.recent-projects {
  display: grid;
  gap: 1px;
  min-width: 0;
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.recent-project-link,
.more-projects-link {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  border: 0;
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-2);
  overflow: hidden;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.recent-project-link {
  min-height: var(--space-11);
  justify-content: flex-start;
  padding: var(--space-1) var(--space-2);
}

.recent-project-link.active {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-weight: 650;
}

.recent-project-link:hover,
.recent-project-link:focus-visible,
.more-projects-link:hover,
.more-projects-link:focus-visible {
  background: var(--color-surface-sunken);
  color: var(--color-accent);
}

.more-projects-link {
  margin-left: calc(var(--space-4) + var(--space-2));
  color: var(--color-accent);
}

.recent-conversations {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}

.recent-conversations-title {
  flex: 0 0 auto;
  margin: 0 var(--space-2);
  padding: var(--space-2);
}

.sidebar-hint {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  padding: var(--space-2) var(--chat-space-2-5);
}

.sidebar-hint.error {
  color: var(--color-danger);
}

.sidebar-load-error,
.sidebar-refresh-error {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-1) var(--chat-focus-width);
  padding: var(--chat-space-2-5);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-size: var(--text-sm);
}

.sidebar-refresh-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-load-error button,
.sidebar-refresh-error button {
  min-height: var(--space-11);
  width: fit-content;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
}

.sidebar-load-error button:hover,
.sidebar-load-error button:focus-visible,
.sidebar-refresh-error button:hover,
.sidebar-refresh-error button:focus-visible {
  background: var(--color-danger-soft);
}

.skeleton-list {
  padding: var(--space-1);
}

.skeleton-item {
  height: var(--space-9);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  background: var(--color-surface-hover);
}

.conversation-row {
  display: flex;
  align-items: center;
  position: relative;
  gap: var(--chat-space-tight);
}

.conversation-item {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: flex-start;
  gap: var(--space-2);
  text-align: left;
  min-height: var(--space-11);
  padding: var(--space-2) var(--space-3);
  border: none;
  border-radius: var(--radius-xl);
  background: transparent;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.conversation-item:hover,
.conversation-item:focus-visible,
.conversation-row:hover .conversation-item {
  background: var(--color-surface-sunken);
  color: var(--color-text-primary);
}

.conversation-item.active {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-accent) 68%, transparent);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-weight: 600;
}

.conversation-icon {
  width: var(--space-4);
  height: var(--space-4);
  flex: 0 0 auto;
  margin-top: 2px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.conversation-copy {
  display: block;
  min-width: 0;
}

.conversation-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-project-tag {
  display: block;
  width: fit-content;
  max-width: 100%;
  margin-top: 2px;
  border-radius: var(--radius-pill);
  padding: 1px var(--space-2);
  overflow: hidden;
  background: color-mix(in srgb, var(--color-secondary-identity) 10%, transparent);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-rename-input {
  flex: 1;
  width: 100%;
  min-width: 0;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-xl);
  padding: var(--chat-space-tight) var(--chat-space-1-25);
  color: var(--color-text-primary);
  font: inherit;
  background: var(--color-surface);
}

.conversation-more {
  min-width: var(--space-11);
  min-height: var(--space-11);
  border: none;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--color-text-secondary);
  padding: var(--space-2);
  cursor: pointer;
  line-height: 1;
  font-weight: 700;
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);
}

.conversation-row:hover .conversation-more,
.conversation-row:focus-within .conversation-more {
  opacity: 1;
}

@media (hover: none) {
  .conversation-more {
    opacity: 1;
  }
}

.conversation-more:hover,
.conversation-more:focus-visible {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.conversation-more svg,
.scroll-bottom-btn svg,
.error-close svg,
.capability-caret svg,
.capability-check svg,
.manage-knowledge-btn > svg {
  width: var(--space-4);
  height: var(--space-4);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.conversation-menu {
  position: absolute;
  top: calc(100% - var(--chat-space-tight));
  right: 0;
  z-index: 10;
  min-width: var(--chat-menu-min-width);
  padding: var(--space-1);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-float);
}

.conversation-menu.menu-up {
  top: auto;
  bottom: calc(100% - 3px);
}

.conversation-menu button {
  min-height: var(--space-11);
  display: block;
  width: 100%;
  border: none;
  border-radius: var(--radius-lg);
  padding: var(--space-2);
  background: transparent;
  color: var(--color-text-primary);
  text-align: left;
  cursor: pointer;
}

.conversation-menu button:hover:not(:disabled),
.conversation-menu button:focus-visible:not(:disabled) {
  background: var(--color-surface-hover);
}

.conversation-menu button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.danger {
  color: var(--color-warning);
}

.sidebar-footer {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border-subtle);
  padding: var(--space-3) var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.footer-account-row {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.footer-settings-row {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.footer-username {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-btn {
  width: 100%;
  min-height: var(--space-11);
  border: 0;
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  color: var(--color-danger);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.logout-btn:hover,
.logout-btn:focus-visible {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--space-12);
  box-sizing: border-box;
  padding: var(--space-3) clamp(var(--space-5), 4vw, var(--space-8));
  background: color-mix(in srgb, var(--color-surface) 62%, transparent);
}

.menu-btn {
  display: none;
  border: none;
  background: transparent;
  min-width: var(--space-11);
  min-height: var(--space-11);
  padding: var(--space-1);
  cursor: pointer;
  color: var(--color-text-primary);
}

.menu-btn svg {
  width: var(--space-5);
  height: var(--space-5);
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}

.header-title {
  font-weight: 600;
  font-size: var(--text-base);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-context {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  padding: var(--space-1) 0;
}

.project-context-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) clamp(var(--space-5), 4vw, var(--space-8));
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-surface-sunken);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.project-context-bar button {
  flex: 0 0 auto;
  border: 0;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--color-accent);
  font: inherit;
  cursor: pointer;
}

.project-context-bar button:hover,
.project-context-bar button:focus-visible {
  background: var(--color-accent-soft);
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-8) clamp(var(--space-5), 5vw, var(--space-10));
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.skeleton-message {
  width: 160px;
  height: 40px;
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.skeleton-message.right {
  align-self: flex-end;
  background: var(--color-accent-soft);
}

.empty-state {
  position: relative;
  isolation: isolate;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-6);
}

.idle-workbench {
  display: contents;
}

.idle-intro {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: clamp(var(--space-8), 13vh, 9rem) var(--space-6) var(--space-6);
  text-align: center;
}

.empty-state.error {
  color: var(--color-danger);
}

.empty-mark {
  display: block;
  text-align: center;
  margin: 0 auto var(--space-5);
}

.idle-wordmark {
  font-family: Iowan Old Style, Baskerville, Georgia, 'Times New Roman', serif;
  font-size: clamp(26px, 3vw, 34px);
  letter-spacing: -0.04em;
  color: var(--color-text-primary);
  line-height: 1;
}

.empty-title {
  margin: 0;
  font-size: clamp(var(--text-xl), 2vw, var(--text-2xl));
  font-weight: 650;
}

.empty-subtitle {
  margin: 0 0 var(--space-6);
  color: var(--color-text-secondary);
  font-size: var(--text-base);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  max-width: 860px;
}

.idle-prompt-rows {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: var(--space-2);
  width: min(100% - var(--space-10), 860px);
  margin: var(--space-6) auto clamp(var(--space-8), 8vh, var(--space-10));
}

.suggestion-card {
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: var(--space-11);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-surface) 84%, transparent);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-standard);
}

.suggestion-card:hover {
  border-color: color-mix(in srgb, var(--color-accent) 36%, var(--color-border-subtle));
  background: color-mix(in srgb, var(--color-accent-soft) 64%, var(--color-surface));
  transform: translateY(-1px);
}

.empty-knowledge-link {
  min-height: var(--space-11);
  margin-top: var(--space-3);
  border: 0;
  border-radius: var(--radius-xl);
  background: transparent;
  color: var(--color-accent);
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}

.empty-knowledge-link:hover,
.empty-knowledge-link:focus-visible {
  background: var(--color-accent-soft);
  outline: none;
}

.message {
  display: flex;
  gap: var(--space-3);
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
  animation: user-message-in 160ms var(--ease-standard) both;
}

@keyframes user-message-in {
  from {
    opacity: 0;
    transform: translateY(var(--space-1));
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.bubble {
  display: inline-block;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--chat-bubble-radius);
  background: var(--color-user-message);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.scroll-bottom-btn {
  position: absolute;
  bottom: var(--chat-scroll-to-bottom-offset);
  left: 50%;
  transform: translateX(-50%);
  width: var(--space-11);
  height: var(--space-11);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  cursor: pointer;
  box-shadow: var(--shadow-float);
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin: 0 var(--space-5) var(--chat-space-2-5);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-lg);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-size: var(--text-sm);
}

.error-close {
  min-width: var(--space-11);
  min-height: var(--space-11);
  border: none;
  background: transparent;
  color: var(--color-danger);
  font-size: var(--text-md);
  cursor: pointer;
  line-height: 1;
}

.retry-btn,
.regenerate-btn {
  min-height: var(--space-11);
  border: 1px solid currentColor;
  border-radius: var(--radius-lg);
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
}

.retry-btn {
  margin-left: auto;
  padding: var(--space-1) var(--space-2);
}

.regenerate-btn {
  margin-left: auto;
  margin-right: var(--space-2);
  padding: var(--space-1) var(--space-2);
  color: var(--color-accent);
}

.retry-btn:hover,
.retry-btn:focus-visible,
.regenerate-btn:hover,
.regenerate-btn:focus-visible {
  background: var(--color-accent-soft);
}

.regenerate-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.composer-wrap {
  position: sticky;
  bottom: 0;
  z-index: 5;
  padding: var(--space-5) clamp(var(--space-5), 5vw, var(--space-10)) var(--space-6);
  background: var(--color-bg);
}

.composer-wrap.is-idle {
  padding-top: 0;
  padding-bottom: 0;
  background: transparent;
}

.composer {
  position: relative;
  isolation: isolate;
  max-width: 800px;
  margin: 0 auto;
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  padding: var(--space-3) var(--space-5) var(--space-3);
  box-shadow: var(--shadow-composer);
  transition: border-color var(--duration-normal) var(--ease-standard), box-shadow var(--duration-normal) var(--ease-standard), background-color var(--duration-normal) var(--ease-standard);
}

.composer-wrap.is-idle .composer {
  max-width: min(860px, 100%);
  min-height: 138px;
  padding: var(--space-4) var(--space-5) var(--space-3);
}

.composer:focus-within {
  border-color: var(--color-glass-border);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-border) 22%, transparent), var(--shadow-composer);
}

.composer::before {
  position: absolute;
  z-index: 0;
  inset: 0;
  border-radius: inherit;
  content: '';
  pointer-events: none;
}

.composer.inward-breathing::before {
  display: none;
}

@keyframes inward-breathing {
  0%,
  100% {
    opacity: 0.028;
    box-shadow: inset 0 0 0 6px color-mix(in srgb, var(--color-accent) 40%, transparent);
  }

  50% {
    opacity: 0.06;
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 40%, transparent);
  }
}

.ambient-field {
  display: none;
  pointer-events: none;
}

.composer-input {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  border: 0;
  resize: none;
  padding: var(--space-3) 0 var(--space-5);
  font-size: var(--text-base);
  font-family: inherit;
  line-height: 1.6;
  color: var(--color-text-primary);
  background: transparent !important;
  max-height: 200px;
}

.chat-page .composer .composer-input:focus,
.chat-page .composer .composer-input:focus-visible {
  outline: none;
  box-shadow: none;
}

.composer-actions {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--space-11);
  padding-top: var(--space-3);
}

.composer-hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.composer-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.capability-selector {
  position: relative;
}

.capability-trigger {
  display: inline-flex;
  min-height: var(--space-11);
  align-items: center;
  gap: var(--space-1);
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  padding: var(--space-1) var(--space-2);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.capability-trigger:hover,
.capability-trigger:focus-visible {
  border-color: var(--color-border);
  background: var(--color-surface);
}

.capability-caret {
  display: inline-flex;
  color: var(--color-text-secondary);
}

.capability-popover-shell {
  position: absolute;
  z-index: 20;
  bottom: calc(100% + var(--space-2));
  left: 0;
  width: min-content;
  min-width: min(100vw - var(--space-6), 22rem);
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-overlay);
  isolation: isolate;
  animation: capability-popover-in var(--duration-normal) var(--ease-standard);
}

.capability-popover {
  position: relative;
  z-index: 1;
  width: 100%;
}

.capability-popover-title {
  position: relative;
  z-index: 1;
  margin: var(--space-1) var(--space-2) var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.capability-option,
.manage-knowledge-btn {
  display: flex;
  width: 100%;
  min-height: var(--space-11);
  align-items: center;
  gap: var(--space-2);
  border: 0;
  border-radius: var(--radius-xl);
  padding: var(--space-2);
  background: transparent;
  color: var(--color-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.capability-option:hover,
.capability-option:focus-visible,
.manage-knowledge-btn:hover,
.manage-knowledge-btn:focus-visible {
  background: var(--color-surface-hover);
}

.capability-option.selected {
  border: 1px solid color-mix(in srgb, var(--color-accent) 22%, var(--color-border));
  background: var(--color-accent-soft);
  font-weight: 600;
}

.capability-icon,
.capability-check {
  flex: 0 0 auto;
  color: var(--color-accent);
}

.capability-check {
  display: inline-flex;
}

.capability-icon {
  width: var(--text-md);
  height: var(--text-md);
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.capability-icon > svg {
  display: block;
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.capability-copy {
  display: grid;
  flex: 1;
  gap: var(--space-1);
}

.capability-copy small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: 1.4;
}

.manage-knowledge-btn {
  margin-top: var(--space-2);
  color: var(--color-accent);
  justify-content: space-between;
}

.composer-helper {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes capability-popover-in {
  from { opacity: 0; transform: translateY(var(--space-1)); }
  to { opacity: 1; transform: translateY(0); }
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--space-11);
  height: var(--space-11);
  border: none;
  border-radius: var(--radius-lg);
  background: var(--color-action);
  color: var(--color-action-text);
  cursor: pointer;
  box-shadow: 0 4px 10px color-mix(in srgb, var(--color-action) 16%, transparent);
  transition: background var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), opacity var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-standard);
}

.send-btn:hover:not(:disabled),
.send-btn:focus-visible {
  background: var(--color-action-hover);
  box-shadow: 0 6px 14px color-mix(in srgb, var(--color-action) 20%, transparent);
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn.stop {
  width: var(--space-11);
  padding: 0;
  background: var(--color-secondary-identity);
  color: var(--color-surface);
}

.send-btn.stop span {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.send-btn svg {
  width: var(--text-lg);
  height: var(--text-lg);
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
  padding: var(--space-5);
  background: color-mix(in srgb, var(--color-text-primary) 32%, transparent);
}

.confirm-modal {
  width: min(100%, 360px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  padding: var(--space-6);
  background: var(--color-surface);
  box-shadow: var(--shadow-overlay);
}

.confirm-modal h2,
.confirm-modal p {
  margin: 0;
}

.confirm-modal p {
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
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
  gap: var(--space-2);
  margin-top: var(--space-5);
}

.confirm-actions button {
  min-height: var(--space-11);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface);
  color: var(--color-text-primary);
  cursor: pointer;
}

.confirm-actions button:hover:not(:disabled),
.confirm-actions button:focus-visible:not(:disabled) {
  background: var(--color-surface-hover);
}

.confirm-actions .danger {
  border-color: var(--color-danger);
  background: var(--color-danger);
  color: var(--color-surface);
}

@keyframes blink {
  50% {
    opacity: 0;
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
    transition: transform var(--duration-normal) var(--ease-standard);
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 20;
    border: 0;
    padding: 0;
    background: color-mix(in srgb, var(--color-text-primary) 32%, transparent);
    cursor: pointer;
  }

  .menu-btn {
    display: block;
  }

  .capability-popover-shell {
    position: fixed;
    z-index: 20;
    right: 0;
    bottom: 0;
    left: 0;
    width: auto;
    min-width: 0;
    max-height: min(70dvh, 32rem);
    overflow-y: auto;
    padding: var(--space-3) var(--space-3) calc(var(--space-3) + env(safe-area-inset-bottom));
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-2xl) var(--radius-2xl) 0 0;
  }

  .capability-option,
  .manage-knowledge-btn {
    min-height: var(--space-11);
  }

  .message-body {
    max-width: 92%;
  }

  .idle-prompt-rows {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .chat-header,
  .messages,
  .composer-wrap {
    padding-left: var(--space-3);
    padding-right: var(--space-3);
  }

  .composer-wrap {
    padding-bottom: var(--space-3);
  }

  .composer {
    padding-left: var(--space-3);
  }

  .composer-hint {
    display: none;
  }

  .composer-actions {
    gap: var(--space-2);
  }

  .composer-meta {
    flex: 1;
  }

  .capability-trigger,
  .send-btn {
    min-width: var(--space-11);
    min-height: var(--space-11);
  }

  .composer-helper {
    overflow: visible;
    white-space: normal;
    line-height: 1.3;
  }
}

@media (hover: hover) and (pointer: fine) {
  .ambient-field {
    position: absolute;
    z-index: 0;
    inset: 0;
    display: block;
    border-radius: inherit;
    opacity: 0.055;
    background: radial-gradient(280px at var(--pointer-x, 50%) var(--pointer-y, 50%), color-mix(in srgb, var(--color-accent) 70%, transparent), transparent 72%);
    transition: opacity 360ms var(--ease-standard);
  }

  .empty-ambient {
    border-radius: 50%;
    background: radial-gradient(360px at var(--pointer-x, 50%) var(--pointer-y, 50%), color-mix(in srgb, var(--color-accent) 55%, transparent), transparent 74%);
  }

  .capability-ambient {
    border-radius: inherit;
    background: radial-gradient(220px at var(--pointer-x, 50%) var(--pointer-y, 50%), color-mix(in srgb, var(--color-accent) 64%, transparent), transparent 72%);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto;
    animation: none !important;
    transition: none !important;
  }

  .message.user .message-body {
    animation: none;
  }

  .ambient-field {
    display: none;
  }
}
</style>
