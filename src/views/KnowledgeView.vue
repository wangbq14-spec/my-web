<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { deleteDocument, getDocument, listDocuments, retryDocument, uploadDocument } from '../api/modules/document'

const ALLOWED_EXTENSIONS = ['.txt', '.md', '.pdf']
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
const GENERIC_ERROR = '操作失败，请稍后重试'
const FILE_VALIDATION_MESSAGE = '仅支持 TXT、Markdown、PDF，且不超过 10 MB。请选择有效文件后重试。'

const router = useRouter()
const documents = ref([])
const loading = ref(true)
const loadError = ref('')
const uploading = ref(false)
const deleting = ref(false)
const selectedFile = ref(null)
const errorMessage = ref('')
const documentToDelete = ref(null)
const fileInput = ref(null)
const cancelDeleteButton = ref(null)
const deleteTriggerRef = ref(null)
const backButton = ref(null)
const pageContent = ref(null)
const confirmationDialog = ref(null)
const dragging = ref(false)
const retrying = ref(new Set())
const pollingTimedOut = ref(new Set())

let listRequestSeq = 0
let isMounted = true
const documentVersions = new Map()
const pollStates = new Map()
const MAX_POLL_ATTEMPTS = 15
const POLL_INTERVAL_MS = 2000

function isSupportedFile(file) {
  const filename = file?.name?.toLowerCase() || ''
  return ALLOWED_EXTENSIONS.some((extension) => filename.endsWith(extension))
}

function isValidUploadFile(file) {
  return isSupportedFile(file) && Number.isFinite(file?.size) && file.size > 0 && file.size <= MAX_UPLOAD_BYTES
}

function safeErrorMessage(error, fallback = GENERIC_ERROR) {
  const message = typeof error?.message === 'string' ? error.message.trim() : ''
  const unsafePattern = /(traceback|stack\s*trace|\bsql\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|api\s*key|authorization|bearer\s|access[_\s-]*token|token\s*[:=]|secret\s*[:=]|password\s*[:=]|database_url|\/(?:etc|home|tmp|var)\/|[a-z]:\\|https?:\/\/|begin\s+[a-z ]*private\s+key)/i
  const safeProductMessagePattern = /^(?=.{1,160}$)(?=.*[\u4e00-\u9fff])(?=.*(?:失败|超时|不存在|过大|为空|不支持|不可用|请重试|错误|异常|稍后|重试|文件|文档|上传|删除|加载|处理|服务|网络|格式|大小|限制|繁忙))[\u4e00-\u9fff\w\s，。！？、：；（）()“”‘’《》【】·—…%+.,!?-]+$/

  return message && !unsafePattern.test(message) && safeProductMessagePattern.test(message) ? message : fallback
}

function formatFileSize(size) {
  if (!Number.isFinite(size) || size < 0) return '未知大小'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

function statusText(status) {
  if (status === 'queued' || status === 'processing') return '处理中'
  if (status === 'ready') return '可用'
  if (status === 'failed') return '处理失败'
  return '状态未知'
}

function statusDescription(status) {
  if (status === 'queued' || status === 'processing') return '正在准备，完成后即可使用'
  if (status === 'ready') return 'AI 已可在回答中参考'
  if (status === 'failed') return '资料暂时无法使用，请重新处理'
  return '暂时无法确认资料是否可用'
}

function documentVersion(id) {
  return documentVersions.get(id) ?? 0
}

function updateDocument(updatedDocument) {
  const index = documents.value.findIndex((document) => document.id === updatedDocument.id)
  if (index === -1) {
    documents.value = [updatedDocument, ...documents.value]
  } else {
    documents.value = documents.value.map((document, itemIndex) => (itemIndex === index ? updatedDocument : document))
  }
  documentVersions.set(updatedDocument.id, documentVersion(updatedDocument.id) + 1)
  if (isTerminalStatus(updatedDocument.status)) setPollingTimedOut(updatedDocument.id, false)
}

function removeDocument(id) {
  documents.value = documents.value.filter((document) => document.id !== id)
  documentVersions.set(id, documentVersion(id) + 1)
}

function isTerminalStatus(status) {
  return ['ready', 'failed', 'deleted'].includes(status)
}

function setPollingTimedOut(id, timedOut) {
  const next = new Set(pollingTimedOut.value)
  if (timedOut) next.add(id)
  else next.delete(id)
  pollingTimedOut.value = next
}

function isPollingTimedOut(id) {
  return pollingTimedOut.value.has(id)
}

function applyDocumentList(nextDocuments) {
  const affectedIds = new Set([
    ...documents.value.map((document) => document.id),
    ...nextDocuments.map((document) => document.id),
  ])
  affectedIds.forEach((id) => {
    documentVersions.set(id, documentVersion(id) + 1)
  })
  documents.value = nextDocuments

  const nextById = new Map(nextDocuments.map((document) => [document.id, document]))
  pollStates.forEach((_, id) => {
    const document = nextById.get(id)
    if (!document || isTerminalStatus(document.status)) stopDocumentPolling(id)
  })
  nextDocuments.forEach((document) => {
    if (!isTerminalStatus(document.status)) startDocumentPolling(document.id)
  })
}

function stopDocumentPolling(id) {
  const state = pollStates.get(id)
  if (!state) return

  if (state.timer) clearTimeout(state.timer)
  state.controller?.abort()
  state.requestSeq += 1
  pollStates.delete(id)
}

function scheduleDocumentPoll(id, state) {
  if (!isMounted || pollStates.get(id) !== state) return
  if (state.attempts >= MAX_POLL_ATTEMPTS) {
    const document = documents.value.find((item) => item.id === id)
    if (document && !isTerminalStatus(document.status)) setPollingTimedOut(id, true)
    stopDocumentPolling(id)
    return
  }

  state.timer = setTimeout(() => {
    state.timer = null
    pollDocument(id, state)
  }, POLL_INTERVAL_MS)
}

async function pollDocument(id, state) {
  if (!isMounted || pollStates.get(id) !== state) return

  const version = documentVersion(id)
  const requestSeq = ++state.requestSeq
  state.attempts += 1
  state.controller = new AbortController()

  try {
    const updatedDocument = await getDocument(id, { signal: state.controller.signal })
    if (
      !isMounted ||
      pollStates.get(id) !== state ||
      state.requestSeq !== requestSeq ||
      documentVersion(id) !== version
    ) return

    state.controller = null
    updateDocument(updatedDocument)
    if (isTerminalStatus(updatedDocument.status)) {
      stopDocumentPolling(id)
    } else {
      scheduleDocumentPoll(id, state)
    }
  } catch {
    if (!isMounted || pollStates.get(id) !== state || state.requestSeq !== requestSeq) return
    state.controller = null
    scheduleDocumentPoll(id, state)
  }
}

function startDocumentPolling(id) {
  if (!id || pollStates.has(id) || !isMounted) return

  setPollingTimedOut(id, false)
  const state = { attempts: 0, controller: null, requestSeq: 0, timer: null }
  pollStates.set(id, state)
  pollDocument(id, state)
}

function isRetrying(id) {
  return retrying.value.has(id)
}

function failedDocumentMessage(document) {
  return safeErrorMessage({ message: document.error_message }, '处理失败，可删除后重新上传')
}

async function loadDocuments() {
  const seq = ++listRequestSeq
  if (isMounted) {
    loading.value = true
    loadError.value = ''
  }

  try {
    const result = await listDocuments()
    if (isMounted && seq === listRequestSeq) {
      applyDocumentList(result)
      loadError.value = ''
    }
  } catch (error) {
    if (isMounted && seq === listRequestSeq) {
      loadError.value = safeErrorMessage(error, '加载文档失败，请稍后重试')
    }
  } finally {
    if (isMounted && seq === listRequestSeq) {
      loading.value = false
    }
  }
}

function selectFile(file) {
  errorMessage.value = ''
  if (!file) return
  if (!isValidUploadFile(file)) {
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    errorMessage.value = FILE_VALIDATION_MESSAGE
    return
  }
  selectedFile.value = file
}

function handleFileChange(event) {
  selectFile(event.target.files?.[0])
}

function handleDragEnter() {
  if (!uploading.value) dragging.value = true
}

function handleDragOver() {
  if (!uploading.value) dragging.value = true
}

function handleDragLeave() {
  dragging.value = false
}

function handleDrop(event) {
  dragging.value = false
  if (uploading.value) return
  selectFile(event.dataTransfer?.files?.[0])
}

function openFilePicker() {
  if (!uploading.value) fileInput.value?.click()
}

async function handleUpload() {
  const file = selectedFile.value
  if (!file || uploading.value) return

  uploading.value = true
  errorMessage.value = ''
  try {
    const uploadedDocument = await uploadDocument(file)
    if (!isMounted) return
    selectedFile.value = null
    if (!uploadedDocument?.id) {
      await loadDocuments()
      return
    }

    updateDocument(uploadedDocument)
    try {
      await loadDocuments()
    } finally {
      if (isMounted) {
        const latestDocument = documents.value.find((document) => document.id === uploadedDocument.id)
        const documentToPoll = latestDocument ?? uploadedDocument
        if (!latestDocument) updateDocument(uploadedDocument)
        if (!isTerminalStatus(documentToPoll.status)) startDocumentPolling(uploadedDocument.id)
      }
    }
  } catch (error) {
    if (isMounted) errorMessage.value = safeErrorMessage(error, '上传失败，请稍后重试')
  } finally {
    if (fileInput.value) fileInput.value.value = ''
    if (isMounted) uploading.value = false
  }
}

async function handleRetry(document) {
  if (!document || isRetrying(document.id)) return

  retrying.value = new Set(retrying.value).add(document.id)
  errorMessage.value = ''
  try {
    const retriedDocument = await retryDocument(document.id)
    if (!isMounted) return

    const queuedDocument = retriedDocument?.id
      ? retriedDocument
      : { ...document, status: 'queued', error_message: null }
    updateDocument(queuedDocument)
    stopDocumentPolling(document.id)
    if (queuedDocument.status === 'queued') startDocumentPolling(document.id)
  } catch (error) {
    if (isMounted) errorMessage.value = safeErrorMessage(error, '重试处理失败，请稍后再试')
  } finally {
    if (isMounted) {
      const retryingDocuments = new Set(retrying.value)
      retryingDocuments.delete(document.id)
      retrying.value = retryingDocuments
    }
  }
}

function restoreDeleteTriggerFocus() {
  const trigger = deleteTriggerRef.value
  deleteTriggerRef.value = null
  nextTick(() => {
    if (trigger?.isConnected) {
      trigger.focus()
      return
    }
    backButton.value?.focus()
  })
}

function requestDelete(document, event) {
  if (deleting.value) return
  deleteTriggerRef.value = event?.currentTarget ?? null
  documentToDelete.value = document
}

function closeDeleteConfirmation() {
  if (deleting.value) return
  documentToDelete.value = null
  restoreDeleteTriggerFocus()
}

async function confirmDelete() {
  const document = documentToDelete.value
  if (!document || deleting.value) return

  deleting.value = true
  errorMessage.value = ''
  try {
    await deleteDocument(document.id)
    if (!isMounted) return
    stopDocumentPolling(document.id)
    removeDocument(document.id)
    documentToDelete.value = null
    restoreDeleteTriggerFocus()
    await loadDocuments()
  } catch (error) {
    if (isMounted) errorMessage.value = safeErrorMessage(error, '删除失败，请稍后重试')
  } finally {
    if (isMounted) deleting.value = false
  }
}

function onDocumentKeydown(event) {
  if (!documentToDelete.value) return

  if (event.key === 'Escape') {
    closeDeleteConfirmation()
    return
  }

  if (event.key !== 'Tab' || !confirmationDialog.value) return

  const focusableElements = confirmationDialog.value.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )
  const focusable = [...focusableElements]
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const activeElement = document.activeElement
  if (event.shiftKey && (event.target === first || activeElement === first)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (event.target === last || activeElement === last)) {
    event.preventDefault()
    first.focus()
  }
}

watch(documentToDelete, async (document) => {
  if (document) {
    if (pageContent.value) pageContent.value.inert = true
    await nextTick()
    cancelDeleteButton.value?.focus()
  } else if (pageContent.value) {
    pageContent.value.inert = false
  }
})

onMounted(() => {
  loadDocuments()
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  isMounted = false
  listRequestSeq += 1
  pollStates.forEach((_, id) => stopDocumentPolling(id))
  if (pageContent.value) pageContent.value.inert = false
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <main class="knowledge-page">
    <div ref="pageContent">
      <header class="knowledge-header">
        <div>
          <div class="brand">
            <BrandIdentity variant="compact" />
          </div>
          <h1>知识库</h1>
          <p class="header-subtitle">
            让 AI 了解你的资料
          </p>
          <p class="header-description">
            在 Chat 中选择「使用资料」后，AI 可引用其中的信息回答。
          </p>
        </div>
        <div class="knowledge-header-actions">
          <ThemeToggle />
          <button
            ref="backButton"
            type="button"
            class="header-nav-button back-chat-button"
            @click="router.push('/chat')"
          >
            返回 Chat
          </button>
          <button
            type="button"
            class="header-nav-button projects-button"
            @click="router.push('/projects')"
          >
            项目
          </button>
          <a
            class="chat-link"
            href="/chat"
            @click.prevent="router.push({ path: '/chat', query: { mode: 'rag' } })"
          >
            <span>在 Chat 中使用资料</span>
            <svg
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M5 12h14m-5-5 5 5-5 5" />
            </svg>
          </a>
        </div>
      </header>

      <section
        class="upload-area"
        :class="{ dragging }"
        aria-labelledby="upload-title"
        @dragenter.prevent="handleDragEnter"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div
          class="upload-icon"
          aria-hidden="true"
        >
          <svg viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8" />
          </svg>
        </div>
        <h2 id="upload-title">
          添加资料
        </h2>
        <p>拖拽文档到这里，或选择文件</p>
        <input
          id="document-upload"
          ref="fileInput"
          class="file-input"
          type="file"
          accept=".txt,.md,.pdf"
          :disabled="uploading"
          @change="handleFileChange"
        >
        <label
          class="file-picker"
          for="document-upload"
        >选择文件</label>
        <p class="upload-hint">
          支持 TXT、Markdown、PDF，不超过 10 MB
        </p>
        <p
          v-if="selectedFile"
          class="selected-file"
        >
          已选择：{{ selectedFile.name }}（{{ formatFileSize(selectedFile.size) }}）
        </p>
        <button
          v-if="selectedFile"
          type="button"
          class="upload-btn"
          :disabled="uploading"
          @click="handleUpload"
        >
          {{ uploading ? '正在添加…' : '添加资料' }}
        </button>
      </section>

      <p
        v-if="errorMessage"
        class="error-banner"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <section
        class="documents-section"
        aria-labelledby="documents-title"
      >
        <div class="section-heading">
          <div>
            <h2 id="documents-title">
              已添加的资料
            </h2>
            <p>可用的资料会在 Chat 回答和 Agent 能力中提供参考。</p>
          </div>
        </div>

        <p
          v-if="loading && documents.length === 0"
          class="loading-state"
        >
          正在加载资料…
        </p>
        <div
          v-else-if="loadError && documents.length === 0"
          class="load-error-state"
          role="alert"
        >
          <h3>资料加载失败</h3>
          <p>{{ loadError }}</p>
          <button
            type="button"
            @click="loadDocuments"
          >
            重新加载
          </button>
        </div>
        <template v-else>
          <div
            v-if="loadError"
            class="refresh-error-banner"
            role="alert"
          >
            <span>资料刷新失败：{{ loadError }}</span>
            <button
              type="button"
              @click="loadDocuments"
            >
              重新加载
            </button>
          </div>
          <div
            v-if="documents.length === 0"
            class="empty-state"
          >
            <h3>还没有添加资料</h3>
            <p>添加文档后，AI 可在 Chat 回答和 Agent 能力中参考其中的信息。</p>
            <button
              type="button"
              class="empty-upload-btn"
              :disabled="uploading"
              @click="openFilePicker"
            >
              添加资料
            </button>
          </div>
          <ul
            v-else
            class="document-list"
          >
            <li
              v-for="document in documents"
              :key="document.id"
              class="document-item"
            >
              <div class="document-details">
                <strong>{{ document.original_filename }}</strong>
                <span class="document-meta">{{ formatFileSize(document.file_size) }} · 更新于 {{ formatDate(document.created_at) }}</span>
              </div>
              <div class="document-status-area">
                <span
                  class="document-status"
                  :class="`status-${document.status}`"
                >
                  <svg
                    v-if="document.status === 'ready'"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="m5 12 4 4L19 6" />
                  </svg>
                  <svg
                    v-else-if="['queued', 'processing'].includes(document.status)"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M12 6v6l4 2M12 3a9 9 0 1 1-9 9" />
                  </svg>
                  <svg
                    v-else
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M12 8v5m0 4h.01M10 3.9 2.8 16.4A2 2 0 0 0 4.53 19h14.94a2 2 0 0 0 1.73-2.6L14 3.9a2.3 2.3 0 0 0-4 0Z" />
                  </svg>
                  {{ statusText(document.status) }}
                </span>
                <p class="status-description">
                  {{ statusDescription(document.status) }}
                </p>
                <p
                  v-if="['queued', 'processing'].includes(document.status) && isPollingTimedOut(document.id)"
                  class="document-processing-hint"
                >
                  仍在准备中，完成后会自动更新；你也可以刷新查看最新状态
                </p>
                <p
                  v-if="document.status === 'failed'"
                  class="document-error"
                >
                  {{ failedDocumentMessage(document) }}
                </p>
              </div>
              <div class="document-actions">
                <button
                  v-if="document.status === 'failed'"
                  type="button"
                  class="retry-btn"
                  :disabled="isRetrying(document.id)"
                  @click="handleRetry(document)"
                >
                  {{ isRetrying(document.id) ? '正在重新处理…' : '重新处理' }}
                </button>
                <button
                  type="button"
                  class="delete-btn"
                  aria-label="删除文档"
                  :disabled="deleting"
                  @click="requestDelete(document, $event)"
                >
                  删除
                </button>
              </div>
            </li>
          </ul>
        </template>
      </section>
    </div>

    <div
      v-if="documentToDelete"
      class="confirm-modal-backdrop"
      @click.self="closeDeleteConfirmation"
    >
      <section
        ref="confirmationDialog"
        class="confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-document-dialog-title"
        aria-describedby="delete-document-dialog-description"
      >
        <h2 id="delete-document-dialog-title">
          删除文档
        </h2>
        <p id="delete-document-dialog-description">
          删除后，AI 将不再在 Chat 回答或 Agent 能力中参考这份资料。
        </p>
        <div class="confirm-actions">
          <button
            ref="cancelDeleteButton"
            type="button"
            :disabled="deleting"
            @click="closeDeleteConfirmation"
          >
            取消
          </button>
          <button
            type="button"
            class="danger"
            :disabled="deleting"
            @click="confirmDelete"
          >
            {{ deleting ? '正在删除…' : '删除' }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.knowledge-page {
  min-height: 100vh;
  padding: var(--space-8) max(var(--space-5), calc((100vw - 960px) / 2));
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.knowledge-header,
.section-heading,
.confirm-actions,
.refresh-error-banner {
  display: flex;
  align-items: center;
}

.knowledge-header {
  justify-content: space-between;
  gap: var(--space-6);
  margin-bottom: var(--space-6);
}

.knowledge-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.knowledge-page h1,
.knowledge-page h2,
.knowledge-page h3,
.knowledge-page p {
  margin: 0;
}

.knowledge-page h1 {
  font-size: var(--text-page-title);
  line-height: 1.25;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  font-size: var(--text-md);
  font-weight: 600;
}


.header-subtitle {
  margin-top: var(--space-1) !important;
  font-size: var(--text-lg);
  font-weight: 600;
}

.header-description,
.section-heading p,
.upload-area p,
.document-meta {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.header-description {
  margin-top: var(--space-1) !important;
}

.chat-link,
.header-nav-button,
.file-picker,
.upload-btn,
.empty-upload-btn,
.retry-btn,
.delete-btn,
.confirm-actions button,
.load-error-state button,
.refresh-error-banner button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: var(--space-11);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  cursor: pointer;
  text-decoration: none;
  transition: background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.chat-link,
.header-nav-button,
.retry-btn,
.delete-btn,
.confirm-actions button,
.load-error-state button,
.refresh-error-banner button {
  padding: var(--space-2) var(--space-3);
}

.chat-link:hover,
.header-nav-button:hover,
.empty-upload-btn:hover:not(:disabled),
.retry-btn:hover:not(:disabled),
.delete-btn:hover:not(:disabled),
.confirm-actions button:hover:not(:disabled),
.load-error-state button:hover,
.refresh-error-banner button:hover {
  background: var(--color-surface-hover);
}

.header-nav-button:hover {
  color: var(--color-accent);
}

.knowledge-page :is(a, button, input):focus-visible {
  outline: 3px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.upload-area,
.documents-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
}

.upload-area {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
  padding: var(--space-8);
  background: var(--color-surface-sunken);
  box-shadow: inset 0 1px 0 var(--color-surface), inset 0 -1px 0 var(--color-border);
  text-align: center;
  transition: background-color var(--duration-normal) var(--ease-standard), border-color var(--duration-normal) var(--ease-standard), box-shadow var(--duration-normal) var(--ease-standard), transform var(--duration-normal) var(--ease-standard);
}

@media (hover: hover) {
  .upload-area:hover {
    border-color: var(--color-border-strong);
    background: var(--color-surface-elevated);
    box-shadow: var(--shadow-float);
    transform: translateY(-1px);
  }
}

.upload-area.dragging {
  border-color: var(--color-accent);
  background: var(--color-surface-elevated);
  box-shadow: var(--shadow-float);
  transform: translateY(-1px);
}

.upload-icon {
  display: grid;
  width: var(--space-11);
  height: var(--space-11);
  place-items: center;
  border-radius: var(--radius-pill);
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.upload-icon svg,
.chat-link svg {
  width: var(--space-4);
  height: var(--space-4);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.chat-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.header-nav-button {
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-3);
}

.upload-area h2 {
  margin-top: var(--space-1);
  font-size: var(--text-section-title);
}

.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.file-picker,
.empty-upload-btn {
  padding: var(--space-2) var(--space-4);
  color: var(--color-accent);
  font-weight: 600;
}

.file-picker {
  cursor: pointer;
}

.file-input:focus-visible + .file-picker {
  outline: 3px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.upload-hint {
  font-size: var(--text-xs) !important;
}

.selected-file {
  color: var(--color-text-primary) !important;
  overflow-wrap: anywhere;
}

.upload-btn {
  min-width: 132px;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-xl);
  border-color: transparent;
  background: var(--color-action);
  color: var(--color-action-text);
  font-weight: 600;
}

.upload-btn:hover:not(:disabled) {
  border-color: transparent;
  background: var(--color-action-hover);
  color: var(--color-action-text);
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.error-banner,
.refresh-error-banner {
  margin-top: var(--space-4);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.documents-section {
  margin-top: var(--space-6);
  overflow: hidden;
}

.section-heading {
  justify-content: space-between;
  padding: var(--space-5);
  border-bottom: 1px solid var(--color-border);
}

.section-heading h2 {
  font-size: var(--text-section-title);
}

.section-heading p {
  margin-top: var(--space-1);
}

.loading-state,
.empty-state,
.load-error-state {
  padding: var(--space-8) var(--space-5);
  text-align: center;
  color: var(--color-text-secondary);
}

.empty-state h3,
.load-error-state h3 {
  color: var(--color-text-primary);
  font-size: var(--text-section-title);
}

.empty-state p,
.load-error-state p {
  max-width: 480px;
  margin: var(--space-2) auto var(--space-4);
  font-size: var(--text-sm);
}

.load-error-state button,
.refresh-error-banner button {
  color: var(--color-secondary-identity);
}

.refresh-error-banner {
  justify-content: space-between;
  gap: var(--space-3);
  margin: var(--space-4) var(--space-5) 0;
}

.document-list {
  margin: 0;
  padding: var(--space-3);
  list-style: none;
  display: grid;
  gap: var(--space-2);
  background: var(--color-surface-sunken);
}

.document-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(150px, 0.75fr) auto;
  gap: var(--space-5);
  align-items: center;
  padding: var(--space-4) var(--space-5);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: var(--color-surface-elevated);
}

.document-item:last-child {
  border-color: var(--color-border-subtle);
}

.document-details {
  display: grid;
  min-width: 0;
  gap: var(--space-1);
}

.document-details strong,
.document-error {
  overflow-wrap: anywhere;
}

.document-status {
  display: inline-flex;
  width: fit-content;
  min-height: 24px;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--text-xs);
  font-weight: 700;
  line-height: 1.4;
  white-space: nowrap;
}

.document-status svg {
  width: var(--space-3);
  height: var(--space-3);
  margin-right: var(--space-1);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.status-ready {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.status-queued,
.status-processing {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.status-failed,
.status-unknown {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.document-status-area {
  min-width: 0;
}

.status-description,
.document-processing-hint,
.document-error {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
}

.document-error {
  color: var(--color-danger);
}

.document-processing-hint {
  color: var(--color-text-secondary);
}

.document-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.retry-btn {
  color: var(--color-accent);
}

.delete-btn {
  color: var(--color-secondary-identity);
}

.confirm-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  background: color-mix(in srgb, var(--color-secondary-identity) 32%, transparent);
}

.confirm-modal {
  width: min(100%, 360px);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  background: var(--color-surface-elevated);
  box-shadow: var(--shadow-overlay);
}

.confirm-modal p {
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
}

.confirm-actions {
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-5);
}

.confirm-actions .danger {
  border-color: var(--color-secondary-identity);
  background: var(--color-secondary-identity);
  color: var(--color-surface);
}

.confirm-actions .danger:hover:not(:disabled),
.confirm-actions .danger:active:not(:disabled) {
  border-color: var(--color-danger);
  background: var(--color-danger);
}

@media (prefers-reduced-motion: reduce) {
  .upload-area {
    transition: none;
  }

  .upload-area:hover,
  .upload-area.dragging {
    transform: none;
  }
}

@media (max-width: 600px) {
  .knowledge-page {
    padding: var(--space-5);
  }

  .knowledge-header,
  .refresh-error-banner {
    align-items: flex-start;
  }

  .knowledge-header {
    flex-direction: column;
  }

  .knowledge-header-actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: space-between;
  }

  .document-item {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-3);
  }

  .refresh-error-banner {
    flex-direction: column;
  }

  .document-actions {
    justify-content: flex-start;
  }

  .document-actions button,
  .empty-upload-btn,
  .file-picker,
  .upload-btn,
  .chat-link,
  .header-nav-button {
    min-height: var(--space-11);
  }
}
</style>
