<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { listMessages } from '../api/modules/message'
import { listDocuments } from '../api/modules/document'
import { listModels } from '../api/modules/models'
import { streamAgent, streamChat, streamRegenerate } from '../api/stream'
import AssistantMessage from '../components/chat/AssistantMessage.vue'
import { useWorkspaceStore } from '../stores/workspace'

import AttachmentGallery from '../components/chat/AttachmentGallery.vue'
import { useAttachments } from '../components/chat/useAttachments'

const { attachments, uploadError, blocked: attachmentsBlocked, add: addAttachments, remove: removeAttachment, clear: clearAttachments } = useAttachments()
const imageInput = ref(null)
function selectImages(event) {
  if (!isStreaming.value && !isCreating.value) addAttachments(event.target.files)
  event.target.value = ''
}
function pasteImages(event) {
  const files = Array.from(event.clipboardData?.items || []).filter((item) => item.kind === 'file').map((item) => item.getAsFile()).filter(Boolean)
  if (!files.length) return
  event.preventDefault()
  if (!isStreaming.value && !isCreating.value) addAttachments(files)
}
function dropImages(event) {
  if (!isStreaming.value && !isCreating.value) addAttachments(event.dataTransfer?.files || [])
}

const MAX_TEXTAREA_HEIGHT = 200

const router = useRouter()
const route = useRoute()
const workspaceStore = useWorkspaceStore()
const { activeConversationId, conversations, projects } = storeToRefs(workspaceStore)
const activeProjectId = ref(null)
const activeConversationTitle = computed(() => {
  const current = conversations.value.find((c) => String(c.id) === String(activeConversationId.value))
  return current?.title || '新对话'
})
const routeProjectId = computed(() => {
  const value = Array.isArray(route.query.project_id) ? route.query.project_id[0] : route.query.project_id
  return value === undefined || value === null || value === '' ? null : value
})
const activeProject = computed(() => projects.value.find((project) => String(project.id) === String(activeProjectId.value)))
const activeProjectName = computed(() => activeProject.value?.name || (activeProjectId.value ? `项目 ${activeProjectId.value}` : ''))

const messages = ref([])
const messagesLoading = ref(false)
const messagesError = ref(null)
const hasAddedMaterials = ref(null)

const inputContent = ref('')
const mode = ref('chat')
const isCapabilityPopoverOpen = ref(false)
const capabilityTriggerRef = ref(null)
const isModelPopoverOpen = ref(false)
const modelTriggerRef = ref(null)
const modelTier = ref('auto')
const chatTitleRef = ref(null)
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

const isCreating = ref(false)
const showOnboarding = ref(false)

const messagesContainer = ref(null)
const textareaRef = ref(null)
const shouldAutoScroll = ref(true)
const showScrollToBottom = ref(false)

let activeController = null
let messageRequestSeq = 0
let isMounted = true
let localMessageSequence = 0
let skipConversationLoadId = null

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

// Classroom Beta starter examples — suggested prompts only, never fabricated history.
const classroomStarters = [
  { mode: 'chat', text: '解释 FastAPI Depends 与 yield' },
  { mode: 'chat', text: '帮我看这张报错截图' },
  { mode: 'rag', text: '根据我的 Python 面试题资料回答' },
  { mode: 'chat', text: 'ORM 和 SQL 分别要学到什么程度' },
]

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

const fallbackModelOptions = [
  { tier: 'auto', name: '自动', description: '自动选择适合当前任务的模型' },
  { tier: 'fast', name: '快速', description: '更快获得回答' },
  { tier: 'standard', name: '均衡', description: '速度与质量兼顾' },
  { tier: 'reasoning', name: '深度思考', description: '适合更复杂的分析与推理' },
]
const modelOptions = ref(fallbackModelOptions)

const currentCapability = computed(
  () => capabilityOptions.find((option) => option.id === mode.value) || capabilityOptions[0],
)
const currentModel = computed(
  () => modelOptions.value.find((option) => option.tier === modelTier.value) || fallbackModelOptions[0],
)
const suggestions = computed(() => suggestionsByMode[mode.value] || suggestionsByMode.chat)
const isConversationActive = computed(() => messages.value.length > 0 || isStreaming.value)
const isComposerBreathing = computed(
  () => !inputContent.value.trim() && !isStreaming.value && !prefersReducedMotion.value,
)

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

function focusCurrentModel() {
  nextTick(() => document.querySelector(`.model-option[data-tier="${modelTier.value}"]`)?.focus())
}

function openModelPopover() {
  isModelPopoverOpen.value = true
  focusCurrentModel()
}

function closeModelPopover({ restoreFocus = true } = {}) {
  if (!isModelPopoverOpen.value) return
  isModelPopoverOpen.value = false
  if (restoreFocus) nextTick(() => modelTriggerRef.value?.focus())
}

function toggleModelPopover() {
  if (isModelPopoverOpen.value) closeModelPopover()
  else openModelPopover()
}

function selectModel(nextTier) {
  modelTier.value = nextTier
  closeModelPopover()
}

function onModelKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeModelPopover()
    return
  }
  if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!isModelPopoverOpen.value) {
    openModelPopover()
    return
  }
  const options = [...document.querySelectorAll('.model-option')]
  const currentIndex = options.indexOf(document.activeElement)
  const nextIndex = event.key === 'ArrowDown'
    ? (currentIndex + 1 + options.length) % options.length
    : (currentIndex - 1 + options.length) % options.length
  options[nextIndex]?.focus()
}

async function loadModelOptions() {
  try {
    const models = await listModels()
    if (Array.isArray(models) && models.length) {
      modelOptions.value = models
      if (!models.some((option) => option.tier === modelTier.value)) modelTier.value = 'auto'
    }
  } catch {
    // The built-in tiers keep model selection available when the endpoint is unavailable.
  }
}

async function loadMaterialAvailability() {
  try {
    const documents = await listDocuments()
    if (isMounted) hasAddedMaterials.value = Array.isArray(documents) && documents.length > 0
  } catch {
    // Keep the prompt hidden when material availability cannot be determined.
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

function updateMotionPreference() {
  prefersReducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}
async function loadConversationMessages(id, previousId = null) {
  if (id === undefined || id === null || id === '') {
    messageRequestSeq += 1
    activeController?.abort()
    activeController = null
    isStreaming.value = false
    messages.value = []
    messagesLoading.value = false
    messagesError.value = null
    return
  }

  const isSwitchingConversation = previousId != null && String(previousId) !== String(id)
  const conversation = conversations.value.find((item) => String(item.id) === String(id))
  activeProjectId.value = conversation ? (conversation.project_id ?? null) : routeProjectId.value
  if (isSwitchingConversation && activeController) {
    activeController.abort()
    isStreaming.value = false
    activeController = null
  }
  const requestId = ++messageRequestSeq
  messages.value = []
  error.value = null
  messagesLoading.value = true
  messagesError.value = null
  try {
    const loadedMessages = await listMessages(id)
    if (!isMounted || requestId !== messageRequestSeq || String(activeConversationId.value) !== String(id)) return
    messages.value = Array.isArray(loadedMessages) ? loadedMessages.map(normalizeMessage) : []
  } catch (err) {
    if (!isMounted || requestId !== messageRequestSeq || String(activeConversationId.value) !== String(id)) return
    messagesError.value = err?.message || '加载消息失败'
  } finally {
    if (isMounted && requestId === messageRequestSeq && String(activeConversationId.value) === String(id)) {
      messagesLoading.value = false
    }
  }
  if (!isMounted || requestId !== messageRequestSeq || String(activeConversationId.value) !== String(id)) return
  await nextTick()
  if (!isMounted || requestId !== messageRequestSeq || String(activeConversationId.value) !== String(id)) return
  scrollToBottom()
}

function openConversationFromRoute() {
  const requestedId = Array.isArray(route.query.conversation_id)
    ? route.query.conversation_id[0]
    : route.query.conversation_id
  if (requestedId === undefined || requestedId === null || requestedId === '') return

  const matchingConversation = conversations.value.find(
    (conversation) => String(conversation.id) === String(requestedId),
  )
  workspaceStore.selectConversation(matchingConversation?.id ?? requestedId)
}

function fillSuggestion(text) {
  inputContent.value = text
  nextTick(() => {
    textareaRef.value?.focus()
    autoResize()
  })
}

function useStarter(starter) {
  if (starter.mode !== mode.value) {
    selectCapability(starter.mode)
  }
  fillSuggestion(starter.text)
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

function streamErrorMessage(err) {
  if (!err) return '生成失败，请重试'
  if (err.type === 'http') {
    if (err.status === 402) return '积分不足，无法继续生成'
    if (err.status === 413) return '图片太大（>10MB），请压缩后重试'
    if (err.status === 415) return '图片格式不支持，仅支持 JPEG、PNG、WebP'
    if (err.status === 404) return '图片文件不存在，请重新上传'
    if (err.status === 409) return '图片已被其他消息使用，请重新上传'
    if (err.status >= 500) return '服务器错误，请稍后重试'
    return err.message || '请求失败，请重试'
  }
  if (err.type === 'stream') {
    switch (err.code) {
      case 'vision_not_supported':
        return '当前模型不支持图片理解，请切换支持图片的模型。'
      case 'configuration_error':
        return 'Vision 服务未配置，请联系管理员'
      case 'timeout':
        return '图片理解请求超时，请重试'
      case 'upstream_error':
        return 'Vision 服务暂时不可用，请稍后重试'
      case 'insufficient_credits':
        return '积分不足，无法继续生成'
      case 'attachment_error':
        return err.message || '图片处理失败，请重试'
      case 'image_read_failed':
        return '图片读取失败，请重新上传'
      case 'image_too_large':
        return '图片太大（>10MB），请压缩后重试'
      case 'image_format':
        return '图片格式不支持，仅支持 JPEG、PNG、WebP'
      case 'retrieval_error':
        return err.message || '知识库检索失败，请稍后重试'
      default:
        return err.message || '生成失败，请重试'
    }
  }
  if (err.type === 'network') return '网络连接失败，请检查网络后重试'
  return err.message || '生成失败，请重试'
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
    ...(content === undefined ? {} : { modelTier: modelTier.value }),
    ...(selectedStream === streamChat ? { useRag: streamMode === 'rag' } : {}),
    ...(userMessage?.attachments?.length ? { attachmentIds: userMessage.attachments.map((item) => item.id) } : {}),
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
      void workspaceStore.loadConversations().catch(() => {})
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
      error.value = streamErrorMessage(err)
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
  if ((!content && !attachments.value.length) || attachmentsBlocked.value || isStreaming.value || isCreating.value) return

  if (!activeConversationId.value) {
    isCreating.value = true
    error.value = null
    try {
      const conversation = await workspaceStore.createNewConversation({
        title: '新对话',
        ...(activeProjectId.value ? { project_id: activeProjectId.value } : {}),
      }, { activate: false })
      if (!isMounted) return
      messageRequestSeq += 1
      skipConversationLoadId = String(conversation.id)
      workspaceStore.selectConversation(conversation.id)
      messages.value = []
      messagesLoading.value = false
      messagesError.value = null
      router.replace({
        name: 'chat',
        query: {
          conversation_id: conversation.id,
          ...(activeProjectId.value ? { project_id: activeProjectId.value } : {}),
        },
      })
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

  const userMessage = reactive({ id: null, localId: `local-message-${++localMessageSequence}`, role: 'user', content, attachments: attachments.value.map(({ id, type, url, original_name, mime_type }) => ({ id, type, url, original_name, mime_type })) })
  clearAttachments()
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

function dismissOnboarding() {
  try {
    localStorage.setItem('omnixa:onboarding:seen', '1')
  } catch {
    // Storage is unavailable; the hint will simply show again on the next visit.
  }
  showOnboarding.value = false
}

function startChatEntry() {
  dismissOnboarding()
  nextTick(() => textareaRef.value?.focus())
}

function openKnowledgeEntry() {
  dismissOnboarding()
  router.push('/knowledge')
}

function openProjectEntry() {
  dismissOnboarding()
  router.push({ name: 'projects', query: { create: '1' } })
}

function startScreenshotEntry() {
  dismissOnboarding()
  nextTick(() => imageInput.value?.click())
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
  if (!event.target.closest('.capability-selector')) {
    closeCapabilityPopover()
  }
  if (!event.target.closest('.model-selector')) {
    closeModelPopover()
  }
}

function onDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  if (isCapabilityPopoverOpen.value) closeCapabilityPopover()
  if (isModelPopoverOpen.value) closeModelPopover()
}

onMounted(() => {
  applyCapabilityFromRoute()
  activeProjectId.value = routeProjectId.value
  openConversationFromRoute()
  loadMaterialAvailability()
  void loadModelOptions()
  updateMotionPreference()
  try {
    showOnboarding.value = localStorage.getItem('omnixa:onboarding:seen') !== '1'
  } catch {
    showOnboarding.value = true
  }
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

watch(
  activeConversationId,
  (conversationId, previousConversationId) => {
    if (conversationId != null && String(conversationId) === skipConversationLoadId) {
      skipConversationLoadId = null
      return
    }
    clearAttachments()
    void loadConversationMessages(conversationId, previousConversationId)
  },
  { immediate: true },
)

watch(isStreaming, (streaming) => {
  workspaceStore.conversationLocked = streaming
})

onBeforeUnmount(() => {
  isMounted = false
  workspaceStore.conversationLocked = false
  activeController?.abort()
  activeController = null
  if (ambientFrame !== null && window.cancelAnimationFrame) {
    window.cancelAnimationFrame(ambientFrame)
  }
  ambientFrame = null
  pendingAmbientTarget = null
  pendingAmbientPoint = null
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div class="chat-page">
    <section
      class="main"
      :class="{ 'is-conversation-active': isConversationActive }"
    >
      <header class="chat-header">
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
              <span v-if="msg.content">{{ msg.content }}</span>
              <AttachmentGallery :attachments="msg.attachments || []" />
            </div>
          </div>
        </div>
      </div>
      <section
        v-else
        class="idle-workbench"
        aria-label="Omnixa 工作台"
      >
        <div
          v-if="showOnboarding && !isConversationActive"
          class="onboarding-hint"
        >
          <strong>欢迎来到 Omnixa 教室 Beta</strong>
          <p>新用户赠送 2000 积分，可在「用量 / Usage」与「定价 / 充值」中查看余额并充值。</p>
          <div class="onboarding-entries" aria-label="快速开始">
            <span class="onboarding-entries-label">从这里开始</span>
            <button type="button" @click="startChatEntry">智能对话</button>
            <button type="button" @click="openKnowledgeEntry">上传课程资料</button>
            <button type="button" @click="openProjectEntry">创建学习项目</button>
            <button type="button" @click="startScreenshotEntry">上传代码报错截图</button>
          </div>
          <button type="button" @click="dismissOnboarding">知道了</button>
        </div>
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
        <div v-if="!isConversationActive" class="classroom-starters">
          <p class="classroom-starters-title">课堂示例 <span class="classroom-starters-hint">点选填入，不会自动发送</span></p>
          <div class="suggestions idle-prompt-rows">
            <button
              v-for="s in classroomStarters"
              :key="s.text"
              type="button"
              class="classroom-starter-card prompt-row"
              @click="useStarter(s)"
            >
              {{ s.text }}
            </button>
          </div>
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
          v-if="error === '积分不足，无法继续生成'"
          type="button"
          class="retry-btn"
          @click="router.push('/usage')"
        >
          查看用量
        </button>
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
          @paste="pasteImages"
          @dragover.prevent
          @drop.prevent="dropImages"
          :class="{ 'inward-breathing': isComposerBreathing }"
        >
          <div v-if="attachments.length" class="composer-attachments" aria-label="待发送图片">
            <div v-for="item in attachments" :key="item.preview" class="composer-attachment">
              <AttachmentGallery :attachments="[item]" />
              <span v-if="item.status === 'uploading'" role="status">上传中</span>
              <span v-if="item.error" role="alert">{{ item.error }}</span>
              <button type="button" :disabled="isCreating" :aria-label="`删除附件：${item.original_name}`" @click="removeAttachment(item)">删除</button>
            </div>
          </div>
          <p v-if="uploadError" class="attachment-error" role="alert">{{ uploadError }}</p>
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
              <input ref="imageInput" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" multiple tabindex="-1" aria-label="上传图片" :disabled="isStreaming || isCreating" @change="selectImages">
              <button type="button" class="attachment-trigger" :disabled="isStreaming || isCreating || attachments.length >= 4" @click="imageInput?.click()">
                <svg class="capability-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 5-5 4 4 4-6 5 7" /></svg>
                图片
              </button>
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
              <div
                class="model-selector"
                @keydown="onModelKeydown"
              >
                <button
                  ref="modelTriggerRef"
                  type="button"
                  class="model-trigger"
                  aria-haspopup="menu"
                  :aria-controls="isModelPopoverOpen ? 'model-popover' : undefined"
                  :aria-expanded="isModelPopoverOpen ? 'true' : 'false'"
                  @click="toggleModelPopover"
                >
                  <span>{{ currentModel.name }}</span>
                  <span
                    class="capability-caret"
                    aria-hidden="true"
                  >
                    <svg viewBox="0 0 24 24"><path d="m7 10 5 5 5-5" /></svg>
                  </span>
                </button>
                <div
                  v-if="isModelPopoverOpen"
                  class="model-popover-shell"
                  @pointermove="updateAmbientField"
                >
                  <span
                    class="ambient-field capability-ambient"
                    aria-hidden="true"
                    style="pointer-events: none"
                  />
                  <p
                    id="model-popover-title"
                    class="capability-popover-title"
                  >
                    选择模型档位
                  </p>
                  <div
                    id="model-popover"
                    class="capability-popover"
                    role="menu"
                    aria-labelledby="model-popover-title"
                  >
                    <button
                      v-for="option in modelOptions"
                      :key="option.tier"
                      type="button"
                      class="model-option"
                      :class="{ selected: modelTier === option.tier }"
                      :data-tier="option.tier"
                      role="menuitemradio"
                      :aria-checked="modelTier === option.tier ? 'true' : 'false'"
                      @click="selectModel(option.tier)"
                    >
                      <span class="capability-copy">
                        <strong>{{ option.name }}</strong>
                        <small>{{ option.description }}</small>
                      </span>
                      <span
                        v-if="modelTier === option.tier"
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
              :disabled="(!inputContent.trim() && !attachments.length) || attachmentsBlocked || isCreating"
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
</template>

<style scoped>
.composer-attachments { display: flex; flex-wrap: wrap; gap: var(--space-3); padding: var(--space-3); }
.composer-attachment { display: flex; flex-direction: column; gap: var(--space-1); max-width: 140px; font-size: var(--text-xs); color: var(--color-text-secondary); }
.composer-attachment button { border: 0; border-radius: var(--radius-sm); background: var(--color-surface-sunken); color: inherit; cursor: pointer; }
.composer-attachment button:hover { background: var(--color-surface-hover); }
.composer-attachment [role='alert'], .attachment-error { color: var(--color-danger); }
.attachment-error { padding: 0 var(--space-4); font-size: var(--text-sm); }
.attachment-trigger:disabled { opacity: .5; cursor: not-allowed; }

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
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--color-bg);
  color: var(--color-text-primary);
  overflow: hidden;
  font-family: var(--font-sans);
}

.chat-page :is(button, input, textarea):focus-visible {
  outline: var(--chat-focus-width) solid var(--color-focus-ring);
  outline-offset: var(--chat-focus-offset);
  box-shadow: 0 0 0 var(--chat-focus-width) color-mix(in srgb, var(--color-focus-ring) 28%, transparent);
}

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

.onboarding-hint {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: min(100% - var(--space-10), 560px);
  margin: clamp(var(--space-6), 6vh, var(--space-8)) auto var(--space-2);
  padding: var(--space-4) var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  text-align: left;
}

.onboarding-hint strong {
  font-weight: 650;
}

.onboarding-hint p {
  margin: 0;
  color: var(--color-text-secondary);
}

.onboarding-hint button {
  align-self: flex-start;
  min-height: var(--space-11);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
}

.onboarding-hint button:hover,
.onboarding-hint button:focus-visible {
  background: var(--color-surface-hover);
}

.onboarding-entries {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.onboarding-entries-label {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.onboarding-entries button {
  align-self: auto;
  min-height: var(--space-9);
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
}

.onboarding-entries button:hover,
.onboarding-entries button:focus-visible {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
  color: var(--color-accent);
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

.classroom-starters {
  width: 100%;
  max-width: 860px;
  margin: calc(-1 * var(--space-4)) auto var(--space-8);
}
.classroom-starters .idle-prompt-rows {
  margin: var(--space-3) auto 0;
}
.classroom-starters-title {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  text-align: center;
}
.classroom-starters-hint {
  opacity: .75;
}
.classroom-starters .classroom-starter-card {
  border-style: dashed;
}

.suggestion-card,
.classroom-starter-card {
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

.suggestion-card:hover,
.classroom-starter-card:hover {
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

.model-selector {
  position: relative;
}

.attachment-trigger,
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

.model-trigger {
  display: inline-flex;
  min-height: var(--space-11);
  align-items: center;
  gap: var(--space-1);
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.attachment-trigger:hover,
.attachment-trigger:focus-visible,
.capability-trigger:hover,
.capability-trigger:focus-visible {
  border-color: var(--color-border);
  background: var(--color-surface);
}

.model-trigger:hover,
.model-trigger:focus-visible {
  border-color: var(--color-border);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
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

.model-popover-shell {
  position: absolute;
  z-index: 20;
  bottom: calc(100% + var(--space-2));
  left: 0;
  width: min-content;
  min-width: min(100vw - var(--space-6), 20rem);
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
.model-option,
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
.model-option:hover,
.model-option:focus-visible,
.manage-knowledge-btn:hover,
.manage-knowledge-btn:focus-visible {
  background: var(--color-surface-hover);
}

.capability-option.selected {
  border: 1px solid color-mix(in srgb, var(--color-accent) 22%, var(--color-border));
  background: var(--color-accent-soft);
  font-weight: 600;
}

.model-option.selected {
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

@media (max-width: 768px) {
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

  .model-popover-shell {
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
  .model-option,
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

  .attachment-trigger,
  .capability-trigger,
  .model-trigger,
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
