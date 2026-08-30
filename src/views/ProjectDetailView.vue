<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { createConversation } from '../api/modules/conversation'
import { uploadDocument } from '../api/modules/document'
import { deleteProject, getProject, listProjectConversations, listProjectDocuments, updateProject } from '../api/modules/project'

const route = useRoute()
const router = useRouter()
const project = ref(null)
const conversations = ref([])
const documents = ref([])
const loading = ref(true)
const errorMessage = ref('')
const activeTab = ref('overview')
const editingName = ref(false)
const nameDraft = ref('')
const savingName = ref(false)
const instructionsDraft = ref('')
const savingInstructions = ref(false)
const creatingConversation = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const nameInput = ref(null)
const fileInput = ref(null)

const projectId = computed(() => route.params.id)
const recentConversations = computed(() => conversations.value.slice(0, 4))
const recentDocuments = computed(() => documents.value.slice(0, 4))
const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'conversations', label: 'Conversations' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'instructions', label: 'Instructions' },
]

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function statusText(status) {
  if (status === 'queued' || status === 'processing') return '处理中'
  if (status === 'ready') return '可用'
  if (status === 'failed') return '处理失败'
  return '状态未知'
}

async function loadProject() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [loadedProject, loadedConversations, loadedDocuments] = await Promise.all([
      getProject(projectId.value), listProjectConversations(projectId.value), listProjectDocuments(projectId.value),
    ])
    project.value = loadedProject
    nameDraft.value = loadedProject.name || ''
    instructionsDraft.value = loadedProject.instructions || ''
    conversations.value = Array.isArray(loadedConversations) ? loadedConversations : []
    documents.value = Array.isArray(loadedDocuments) ? loadedDocuments : []
  } catch (error) {
    if (error?.status === 404) { router.replace('/projects'); return }
    errorMessage.value = '加载项目详情失败，请稍后重试'
  } finally { loading.value = false }
}

function startRename() { if (project.value) { nameDraft.value = project.value.name; editingName.value = true; nextTick(() => nameInput.value?.focus()) } }
function cancelRename() { if (!savingName.value) { nameDraft.value = project.value?.name || ''; editingName.value = false } }
async function saveName() {
  const name = nameDraft.value.trim()
  if (!name) { errorMessage.value = '请输入项目名称'; return }
  if (!project.value || savingName.value) return
  savingName.value = true; errorMessage.value = ''
  try { project.value = await updateProject(project.value.id, { name }); nameDraft.value = project.value.name; editingName.value = false }
  catch { errorMessage.value = '重命名项目失败，请稍后重试' }
  finally { savingName.value = false }
}
async function saveInstructions() {
  if (!project.value || savingInstructions.value) return
  savingInstructions.value = true; errorMessage.value = ''
  try { project.value = await updateProject(project.value.id, { instructions: instructionsDraft.value.trim() }); instructionsDraft.value = project.value.instructions || '' }
  catch { errorMessage.value = '保存 Instructions 失败，请稍后重试' }
  finally { savingInstructions.value = false }
}
async function startConversation() {
  if (creatingConversation.value) return
  creatingConversation.value = true; errorMessage.value = ''
  try { const conversation = await createConversation({ project_id: projectId.value }); router.push({ path: '/chat', query: { conversation_id: conversation.id, project_id: projectId.value } }) }
  catch { errorMessage.value = '新建项目对话失败，请稍后重试' }
  finally { creatingConversation.value = false }
}
function openConversation(conversation) { router.push({ path: '/chat', query: { conversation_id: conversation.id, project_id: projectId.value } }) }
function openKnowledge() { activeTab.value = 'knowledge'; nextTick(() => fileInput.value?.focus()) }
function selectUpload(event) { const file = event.target.files?.[0]; if (file) uploadFile(file); event.target.value = '' }
async function uploadFile(file) {
  if (uploading.value) return
  uploading.value = true; errorMessage.value = ''
  try { await uploadDocument(file, projectId.value); const loaded = await listProjectDocuments(projectId.value); documents.value = Array.isArray(loaded) ? loaded : documents.value }
  catch { errorMessage.value = '上传资料失败，请稍后重试' }
  finally { uploading.value = false }
}
async function removeProject() {
  if (!project.value || deleting.value) return
  if (!window.confirm(`确定要删除“${project.value.name}”吗？删除会解除会话和资料的项目关联，不删除它们本身。`)) return
  deleting.value = true; errorMessage.value = ''
  try { await deleteProject(project.value.id); router.push('/projects') }
  catch { errorMessage.value = '删除项目失败，请稍后重试' }
  finally { deleting.value = false }
}

watch(projectId, loadProject)
onMounted(loadProject)
</script>

<template>
  <main class="project-detail-page">
    <header class="detail-header">
      <div class="header-title">
        <BrandIdentity variant="compact" /><div v-if="project">
          <div
            v-if="editingName"
            class="name-editor"
          >
            <input
              ref="nameInput"
              v-model="nameDraft"
              maxlength="120"
              aria-label="项目名称"
              @keydown.enter.prevent="saveName"
              @keydown.escape.prevent="cancelRename"
            ><button
              type="button"
              class="quiet-button"
              :disabled="savingName"
              @click="cancelRename"
            >
              取消
            </button><button
              type="button"
              class="primary-button"
              :disabled="savingName"
              @click="saveName"
            >
              {{ savingName ? '正在保存…' : '保存' }}
            </button>
          </div><div
            v-else
            class="title-row"
          >
            <h1>{{ project.name }}</h1><button
              type="button"
              class="text-button"
              @click="startRename"
            >
              重命名
            </button>
          </div><p class="description">
            {{ project.description || '尚未添加项目说明' }}
          </p>
        </div>
      </div>
      <div class="header-actions">
        <ThemeToggle /><button
          type="button"
          class="quiet-button header-nav-button back-chat-button"
          @click="router.push('/chat')"
        >
          返回 Chat
        </button><button
          type="button"
          class="quiet-button header-nav-button projects-button"
          @click="router.push('/projects')"
        >
          返回项目
        </button><button
          type="button"
          class="quiet-button header-nav-button knowledge-button"
          @click="router.push('/knowledge')"
        >
          知识库
        </button>
      </div>
    </header>
    <p
      v-if="errorMessage"
      class="error-banner"
      role="alert"
    >
      {{ errorMessage }}
    </p>
    <p
      v-if="loading"
      class="state-message"
    >
      正在加载项目…
    </p>
    <template v-else-if="project">
      <nav
        class="project-tabs"
        aria-label="项目分区"
      >
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeTab === tab.id }"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>

      <section
        v-if="activeTab === 'overview'"
        class="tab-panel overview-panel"
        aria-label="项目概览"
      >
        <div class="overview-intro">
          <div><h2>项目概览</h2><p>{{ project.description || '添加说明，帮助团队快速了解这个项目。' }}</p></div><div class="overview-actions">
            <button
              type="button"
              class="primary-button"
              :disabled="creatingConversation"
              @click="startConversation"
            >
              {{ creatingConversation ? '正在创建…' : '开始新对话' }}
            </button><button
              type="button"
              class="quiet-button"
              @click="openKnowledge"
            >
              添加资料
            </button>
          </div>
        </div>
        <div class="overview-grid">
          <section class="overview-card">
            <div class="card-heading">
              <h3>最近对话</h3><button
                type="button"
                class="text-button"
                @click="activeTab = 'conversations'"
              >
                查看全部
              </button>
            </div><p
              v-if="!recentConversations.length"
              class="section-empty"
            >
              这个项目还没有对话。
            </p><ul
              v-else
              class="linked-list"
            >
              <li
                v-for="conversation in recentConversations"
                :key="conversation.id"
              >
                <button
                  type="button"
                  @click="openConversation(conversation)"
                >
                  <span>{{ conversation.title || '未命名对话' }}</span><small>更新于 {{ formatDate(conversation.updated_at) }}</small>
                </button>
              </li>
            </ul>
          </section><section class="overview-card">
            <div class="card-heading">
              <h3>最近资料</h3><button
                type="button"
                class="text-button"
                @click="activeTab = 'knowledge'"
              >
                查看全部
              </button>
            </div><p
              v-if="!recentDocuments.length"
              class="section-empty"
            >
              还没有关联资料。
            </p><ul
              v-else
              class="linked-list"
            >
              <li
                v-for="document in recentDocuments"
                :key="document.id"
              >
                <span>{{ document.original_filename || document.filename || '未命名文档' }}</span><span
                  class="status-badge"
                  :class="`status-${document.status || 'unknown'}`"
                >{{ statusText(document.status) }}</span>
              </li>
            </ul>
          </section>
        </div>
        <section class="instructions-summary">
          <div class="card-heading">
            <h3>Instructions</h3><button
              type="button"
              class="text-button"
              @click="activeTab = 'instructions'"
            >
              编辑
            </button>
          </div><p>{{ project.instructions || '尚未设置 Instructions。' }}</p>
        </section>
      </section>

      <section
        v-else-if="activeTab === 'conversations'"
        class="tab-panel"
        aria-labelledby="project-conversations-title"
      >
        <div class="section-header">
          <div>
            <h2 id="project-conversations-title">
              项目对话
            </h2><p>此处仅显示关联到当前项目的会话。</p>
          </div><button
            type="button"
            class="primary-button"
            :disabled="creatingConversation"
            @click="startConversation"
          >
            开始新对话
          </button>
        </div><p
          v-if="!conversations.length"
          class="section-empty"
        >
          这个项目还没有对话。
        </p><ul
          v-else
          class="linked-list full-list"
        >
          <li
            v-for="conversation in conversations"
            :key="conversation.id"
          >
            <button
              type="button"
              @click="openConversation(conversation)"
            >
              <span>{{ conversation.title || '未命名对话' }}</span><small>更新于 {{ formatDate(conversation.updated_at) }}</small>
            </button>
          </li>
        </ul>
      </section>

      <section
        v-else-if="activeTab === 'knowledge'"
        class="tab-panel"
        aria-labelledby="project-documents-title"
      >
        <div class="section-header">
          <div>
            <h2 id="project-documents-title">
              项目资料
            </h2><p>上传资料会自动关联到当前项目。</p>
          </div><div>
            <input
              ref="fileInput"
              class="file-input"
              type="file"
              accept=".txt,.md,.pdf"
              :disabled="uploading"
              @change="selectUpload"
            ><button
              type="button"
              class="primary-button"
              :disabled="uploading"
              @click="fileInput?.click()"
            >
              {{ uploading ? '正在上传…' : '上传资料到项目' }}
            </button>
          </div>
        </div><p
          v-if="!documents.length"
          class="section-empty"
        >
          还没有关联资料。上传后，资料会自动归属此项目。
        </p><ul
          v-else
          class="linked-list full-list document-list"
        >
          <li
            v-for="document in documents"
            :key="document.id"
          >
            <div><span>{{ document.original_filename || document.filename || '未命名文档' }}</span><small>上传于 {{ formatDate(document.created_at) }}</small></div><span
              class="status-badge"
              :class="`status-${document.status || 'unknown'}`"
            >{{ statusText(document.status) }}</span>
          </li>
        </ul>
      </section>

      <section
        v-else
        class="tab-panel"
        aria-labelledby="instructions-title"
      >
        <div class="section-header">
          <div>
            <h2 id="instructions-title">
              Instructions
            </h2><p>这些说明会在本项目的会话中作为工作上下文。</p>
          </div><button
            type="button"
            class="primary-button"
            :disabled="savingInstructions"
            @click="saveInstructions"
          >
            {{ savingInstructions ? '正在保存…' : '保存说明' }}
          </button>
        </div><textarea
          v-model="instructionsDraft"
          rows="10"
          maxlength="5000"
          aria-label="项目 Instructions"
          placeholder="例如：目标、语气、约束条件与交付标准"
        />
      </section>
      <button
        type="button"
        class="delete-project"
        :disabled="deleting"
        @click="removeProject"
      >
        {{ deleting ? '正在删除…' : '删除项目' }}
      </button>
    </template>
  </main>
</template>

<style scoped>
.project-detail-page { min-height: 100vh; padding: var(--space-8) max(var(--space-5), calc((100vw - 1040px) / 2)); background: var(--color-bg); color: var(--color-text-primary); }.detail-header, .header-actions, .title-row, .name-editor, .section-header, .overview-intro, .overview-actions, .card-heading { display: flex; align-items: center; }.detail-header, .section-header, .overview-intro, .card-heading { justify-content: space-between; gap: var(--space-5); }.detail-header { margin-bottom: var(--space-6); }.header-title { display: grid; gap: var(--space-2); }.title-row, .name-editor, .header-actions, .overview-actions { gap: var(--space-2); } h1, h2, h3, p { margin: 0; } h1 { font-size: var(--text-page-title); } h2 { font-size: var(--text-section-title); } .description, .section-header p, .overview-intro p, small, .section-empty { color: var(--color-text-secondary); } small { font-size: var(--text-xs); }.primary-button, .quiet-button, .text-button, .delete-project { min-height: var(--space-11); border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-2) var(--space-4); background: var(--color-surface); color: inherit; font: inherit; cursor: pointer; }.primary-button { border-color: transparent; background: var(--color-action); color: var(--color-action-text); font-weight: 650; }.primary-button:hover:not(:disabled) { background: var(--color-action-hover); }.quiet-button:hover:not(:disabled), .text-button:hover:not(:disabled) { background: var(--color-surface-hover); }.header-nav-button:hover:not(:disabled) { color: var(--color-accent); }.text-button { min-height: auto; border: 0; padding: var(--space-1) var(--space-2); color: var(--color-accent); }.project-detail-page :is(button, input, textarea):focus-visible { outline: 3px solid var(--color-focus-ring); outline-offset: 2px; }.name-editor input, textarea { width: 100%; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-3); background: var(--color-surface-sunken); color: inherit; font: inherit; resize: vertical; }.name-editor input { width: min(100%, 360px); }.project-tabs { display: flex; gap: var(--space-1); overflow-x: auto; margin-bottom: var(--space-5); border-bottom: 1px solid var(--color-border); }.project-tabs button { flex: 0 0 auto; border: 0; border-bottom: 2px solid transparent; padding: var(--space-3) var(--space-4); background: transparent; color: var(--color-text-secondary); font: inherit; cursor: pointer; }.project-tabs button:hover, .project-tabs button.active { border-bottom-color: var(--color-accent); color: var(--color-text-primary); }.tab-panel, .overview-card, .instructions-summary { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); background: var(--color-surface); box-shadow: var(--shadow-float); }.tab-panel { padding: var(--space-6); }.overview-panel { display: grid; gap: var(--space-5); }.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); }.overview-card, .instructions-summary { padding: var(--space-5); }.linked-list { display: grid; gap: var(--space-2); margin: var(--space-4) 0 0; padding: 0; list-style: none; }.linked-list li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-xl); background: var(--color-surface-sunken); }.linked-list button { display: grid; width: 100%; gap: var(--space-1); border: 0; padding: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }.linked-list button:hover span { color: var(--color-accent); }.section-empty { padding: var(--space-5) 0 0; }.full-list { margin-top: var(--space-5); }.status-badge { flex-shrink: 0; border-radius: var(--radius-pill); padding: 2px var(--space-2); font-size: var(--text-xs); font-weight: 700; }.status-ready { background: var(--color-surface-hover); }.status-queued, .status-processing { background: var(--color-accent-soft); color: var(--color-accent); }.status-failed, .status-unknown { background: var(--color-danger-soft); color: var(--color-danger); }.document-list li > div { display: grid; min-width: 0; gap: var(--space-1); overflow-wrap: anywhere; }.file-input { position: absolute; width: 1px; height: 1px; opacity: 0; }.tab-panel textarea { display: block; margin-top: var(--space-5); }.error-banner { margin-bottom: var(--space-4); border-radius: var(--radius-lg); padding: var(--space-3); background: var(--color-danger-soft); color: var(--color-danger); }.state-message { padding: var(--space-5) 0; color: var(--color-text-secondary); }.delete-project { margin-top: var(--space-6); border-color: var(--color-danger); color: var(--color-danger); }.delete-project:hover:not(:disabled) { background: var(--color-danger-soft); } button:disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 680px) { .project-detail-page { padding: var(--space-5); }.detail-header, .section-header, .overview-intro { align-items: flex-start; flex-direction: column; }.header-actions, .overview-actions { width: 100%; justify-content: space-between; }.header-actions { flex-wrap: wrap; }.overview-grid { grid-template-columns: 1fr; }.section-header .primary-button, .overview-actions .primary-button, .overview-actions .quiet-button { width: 100%; }.name-editor { flex-wrap: wrap; } }
</style>
