<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { deleteDocument, listDocuments, uploadDocument } from '../api/modules/document'

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
const dragging = ref(false)

let listRequestSeq = 0
let isMounted = true

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
  if (status === 'processing') return '处理中…'
  if (status === 'ready') return '可用'
  if (status === 'failed') return '处理失败'
  return '状态未知'
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
      documents.value = result
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
    await uploadDocument(file)
    if (!isMounted) return
    selectedFile.value = null
    await loadDocuments()
  } catch (error) {
    if (isMounted) errorMessage.value = safeErrorMessage(error, '上传失败，请稍后重试')
  } finally {
    if (fileInput.value) fileInput.value.value = ''
    if (isMounted) uploading.value = false
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
    documents.value = documents.value.filter((item) => item.id !== document.id)
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
  if (event.key === 'Escape' && documentToDelete.value) closeDeleteConfirmation()
}

watch(documentToDelete, async (document) => {
  if (document) {
    await nextTick()
    cancelDeleteButton.value?.focus()
  }
})

onMounted(() => {
  loadDocuments()
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  isMounted = false
  listRequestSeq += 1
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <main class="knowledge-page">
    <header class="knowledge-header">
      <div>
        <h1>知识库</h1>
        <p>上传文档后，可在「知识库」模式或 Agent 中检索这些资料。</p>
      </div>
      <button
        ref="backButton"
        type="button"
        class="back-btn"
        aria-label="返回 Chat"
        @click="router.push('/chat')"
      >
        返回 Chat
      </button>
    </header>

    <section
      class="upload-area"
      :class="{ dragging }"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <input
        id="document-upload"
        ref="fileInput"
        class="file-input"
        type="file"
        accept=".txt,.md,.pdf"
        :disabled="uploading"
        @change="handleFileChange"
      >
      <label for="document-upload">选择文档</label>
      <p>支持 TXT、Markdown、PDF 文件，也可拖放到这里。单个文件不超过 10 MB。</p>
      <p
        v-if="selectedFile"
        class="selected-file"
      >
        已选择：{{ selectedFile.name }}（{{ formatFileSize(selectedFile.size) }}）
      </p>
      <button
        type="button"
        class="upload-btn"
        :disabled="!selectedFile || uploading"
        @click="handleUpload"
      >
        {{ uploading ? '正在上传…' : '上传文档' }}
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
            我的文档
          </h2>
          <p>处理完成的文档可供知识库模式和 Agent 使用。</p>
        </div>
      </div>

      <p
        v-if="loading && documents.length === 0"
        class="loading-state"
      >
        加载中…
      </p>
      <div
        v-else-if="loadError && documents.length === 0"
        class="load-error-state"
        role="alert"
      >
        <h3>加载文档失败</h3>
        <p>{{ loadError }}</p>
        <button
          type="button"
          @click="loadDocuments"
        >
          重试加载
        </button>
      </div>
      <template v-else>
        <div
          v-if="loadError"
          class="refresh-error-banner"
          role="alert"
        >
          <span>刷新失败，可重试：{{ loadError }}</span>
          <button
            type="button"
            @click="loadDocuments"
          >
            重试加载
          </button>
        </div>
        <div
          v-if="documents.length === 0"
          class="empty-state"
        >
          <h3>知识库还是空的</h3>
          <p>上传 TXT、Markdown 或 PDF 后，可在知识库模式或 Agent 中检索这些内容。</p>
          <button
            type="button"
            class="empty-upload-btn"
            :disabled="uploading"
            @click="openFilePicker"
          >
            上传文档
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
              <span>{{ formatFileSize(document.file_size) }} · {{ formatDate(document.created_at) }}</span>
              <span class="document-status">{{ statusText(document.status) }}</span>
              <p
                v-if="document.status === 'failed'"
                class="document-error"
              >
                {{ failedDocumentMessage(document) }}
              </p>
            </div>
            <button
              type="button"
              class="delete-btn"
              aria-label="删除文档"
              :disabled="deleting"
              @click="requestDelete(document, $event)"
            >
              删除
            </button>
          </li>
        </ul>
      </template>
    </section>

    <div
      v-if="documentToDelete"
      class="confirm-modal-backdrop"
      @click.self="closeDeleteConfirmation"
    >
      <section
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
          删除后，该文档将无法再被知识库和 Agent 检索。
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
  --bg: #f7f7f8;
  --surface: #ffffff;
  --surface-hover: #f4f4f5;
  --border: #e8e8ea;
  --text-primary: #1f1f23;
  --text-secondary: #71717a;
  --accent: #4f46e5;
  --accent-soft: rgba(79, 70, 229, 0.08);
  --danger: #dc2626;

  min-height: 100vh;
  box-sizing: border-box;
  padding: 32px max(20px, calc((100vw - 920px) / 2));
  background: var(--bg);
  color: var(--text-primary);
  font-family: system-ui, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.knowledge-header,
.section-heading,
.document-item,
.confirm-actions,
.refresh-error-banner {
  display: flex;
  align-items: center;
}

.knowledge-header {
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 28px;
}

.knowledge-header p,
.section-heading p,
.upload-area p,
.document-details span {
  color: var(--text-secondary);
  font-size: 14px;
}

.knowledge-header p {
  margin-top: 6px;
}

.back-btn,
.upload-area label,
.upload-btn,
.empty-upload-btn,
.delete-btn,
.confirm-actions button,
.load-error-state button,
.refresh-error-banner button {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-primary);
  font: inherit;
  cursor: pointer;
}

.back-btn,
.delete-btn,
.confirm-actions button,
.load-error-state button,
.refresh-error-banner button {
  padding: 8px 12px;
}

.back-btn:hover,
.back-btn:focus-visible,
.empty-upload-btn:hover:not(:disabled),
.empty-upload-btn:focus-visible:not(:disabled),
.delete-btn:hover:not(:disabled),
.delete-btn:focus-visible:not(:disabled),
.confirm-actions button:hover:not(:disabled),
.confirm-actions button:focus-visible:not(:disabled),
.load-error-state button:hover,
.load-error-state button:focus-visible,
.refresh-error-banner button:hover,
.refresh-error-banner button:focus-visible {
  background: var(--surface-hover);
}

.upload-area,
.documents-section {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}

.upload-area {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 28px;
  border-style: dashed;
  text-align: center;
}

.upload-area.dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.upload-area label,
.empty-upload-btn {
  padding: 9px 14px;
  color: var(--accent);
  font-weight: 600;
}

.upload-area label {
  cursor: pointer;
}

.upload-area label:focus-within {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.selected-file {
  color: var(--text-primary) !important;
}

.upload-btn {
  min-width: 112px;
  padding: 9px 14px;
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}

.upload-btn:hover:not(:disabled),
.upload-btn:focus-visible:not(:disabled) {
  filter: brightness(0.95);
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.error-banner,
.refresh-error-banner {
  margin-top: 16px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fef2f2;
  color: var(--danger);
}

.documents-section {
  margin-top: 24px;
  overflow: hidden;
}

.section-heading {
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--border);
}

h2 {
  font-size: 18px;
}

.section-heading p {
  margin-top: 4px;
}

.loading-state,
.empty-state,
.load-error-state {
  padding: 32px 20px;
  text-align: center;
  color: var(--text-secondary);
}

.empty-state h3,
.load-error-state h3 {
  color: var(--text-primary);
  font-size: 17px;
}

.empty-state p,
.load-error-state p {
  max-width: 480px;
  margin: 8px auto 16px;
  font-size: 14px;
}

.load-error-state button,
.refresh-error-banner button {
  color: var(--danger);
}

.refresh-error-banner {
  justify-content: space-between;
  gap: 12px;
  margin: 16px 20px 0;
}

.document-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.document-item {
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.document-item:last-child {
  border-bottom: none;
}

.document-details {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.document-details strong,
.document-error {
  overflow-wrap: anywhere;
}

.document-status {
  color: var(--text-primary) !important;
}

.document-error {
  color: var(--danger);
  font-size: 13px;
}

.delete-btn {
  flex-shrink: 0;
  color: var(--danger);
}

.confirm-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.32);
}

.confirm-modal {
  width: min(100%, 360px);
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}

.confirm-modal p {
  margin-top: 8px;
  color: var(--text-secondary);
}

.confirm-actions {
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

.confirm-actions .danger {
  border-color: var(--danger);
  background: var(--danger);
  color: #fff;
}

@media (max-width: 600px) {
  .knowledge-page {
    padding: 20px;
  }

  .knowledge-header,
  .document-item,
  .refresh-error-banner {
    align-items: flex-start;
  }

  .knowledge-header {
    flex-direction: column;
  }

  .document-item,
  .refresh-error-banner {
    flex-direction: column;
  }
}
</style>
