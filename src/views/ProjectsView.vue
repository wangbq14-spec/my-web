<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { createProject, deleteProject, listProjects, updateProject } from '../api/modules/project'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const loading = ref(true)
const errorMessage = ref('')
const search = ref('')
const quickName = ref('')
const editorOpen = ref(false)
const editingProject = ref(null)
const form = ref({ name: '', description: '', instructions: '' })
const saving = ref(false)
const pinningProjectId = ref(null)
const projectToDelete = ref(null)
const deleting = ref(false)
const formNameInput = ref(null)
const quickCreateInput = ref(null)

const templates = [
  { name: '学习研究', description: '整理研究问题、资料与结论。', instructions: '帮助我明确研究问题，优先给出可信依据，输出清晰的学习笔记和下一步。' },
  { name: '产品开发', description: '推进产品设计、开发与发布。', instructions: '以产品目标和用户价值为先。用简洁的结构说明方案、风险、验收标准和下一步。' },
  { name: '公司知识库', description: '沉淀团队资料与工作规范。', instructions: '基于项目资料回答。区分事实和推测，保持专业、准确，并标明需要确认的内容。' },
  { name: '个人项目', description: '聚焦个人目标与持续推进。', instructions: '帮助我拆解目标、记录决策并维持可执行的下一步，语气直接且鼓励。' },
  { name: '空白项目', description: '', instructions: '' },
]

let mounted = true

const filteredProjects = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  if (!query) return projects.value
  return projects.value.filter((project) => [project.name, project.description]
    .some((value) => String(value || '').toLocaleLowerCase().includes(query)))
})
const recentProjects = computed(() => filteredProjects.value.slice(0, 4))
const allProjects = computed(() => filteredProjects.value)

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function relativeActivity(value) {
  const time = Date.parse(value)
  if (!Number.isFinite(time)) return '最近活动未知'
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000))
  if (seconds < 60) return '刚刚活动'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前活动`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前活动`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} 天前活动`
  return '最近活动'
}

function sortByActivity(items) {
  return [...items].sort((left, right) => {
    if (Boolean(left.pinned) !== Boolean(right.pinned)) return left.pinned ? -1 : 1
    const leftTime = Date.parse(left.last_activity_at || left.updated_at || left.created_at)
    const rightTime = Date.parse(right.last_activity_at || right.updated_at || right.created_at)
    return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0)
  })
}

async function loadProjects() {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await listProjects()
    if (mounted) projects.value = sortByActivity(Array.isArray(result) ? result : [])
  } catch {
    if (mounted) errorMessage.value = '加载项目失败，请稍后重试'
  } finally {
    if (mounted) loading.value = false
  }
}

async function quickCreate() {
  const name = quickName.value.trim()
  if (!name) {
    nextTick(() => quickCreateInput.value?.focus())
    return
  }

  errorMessage.value = ''
  try {
    await createProject({ name })
    quickName.value = ''
    await loadProjects()
  } catch {
    if (mounted) errorMessage.value = '新建项目失败，请稍后重试'
  }
}

function focusQuickCreate() {
  nextTick(() => quickCreateInput.value?.focus())
}

function openCreateForm() {
  editingProject.value = null
  form.value = { name: '', description: '', instructions: '' }
  editorOpen.value = true
  nextTick(() => formNameInput.value?.focus())
}

function openRenameForm(project) {
  editingProject.value = project
  form.value = { name: project.name, description: project.description || '', instructions: project.instructions || '' }
  editorOpen.value = true
  nextTick(() => formNameInput.value?.focus())
}

function applyTemplate(template) {
  form.value = {
    name: form.value.name,
    description: template.description,
    instructions: template.instructions,
  }
}

function closeEditor() {
  if (!saving.value) editorOpen.value = false
}

async function saveProject() {
  const name = form.value.name.trim()
  if (!name) {
    errorMessage.value = '请输入项目名称'
    nextTick(() => formNameInput.value?.focus())
    return
  }
  saving.value = true
  errorMessage.value = ''
  const data = {
    name,
    description: form.value.description.trim(),
    instructions: form.value.instructions.trim(),
  }
  try {
    if (editingProject.value) await updateProject(editingProject.value.id, data)
    else await createProject(data)
    editorOpen.value = false
    await loadProjects()
  } catch {
    if (mounted) errorMessage.value = editingProject.value ? '更新项目失败，请稍后重试' : '新建项目失败，请稍后重试'
  } finally {
    if (mounted) saving.value = false
  }
}

async function togglePin(project) {
  if (pinningProjectId.value !== null) return
  pinningProjectId.value = project.id
  errorMessage.value = ''
  try {
    await updateProject(project.id, { pinned: !project.pinned })
    await loadProjects()
  } catch {
    if (mounted) errorMessage.value = '更新项目置顶状态失败，请稍后重试'
  } finally {
    if (mounted) pinningProjectId.value = null
  }
}

function openProject(project) {
  router.push({ name: 'project-detail', params: { id: project.id } })
}

function requestDelete(project) {
  if (!deleting.value) projectToDelete.value = project
}

async function confirmDelete() {
  const project = projectToDelete.value
  if (!project || deleting.value) return
  deleting.value = true
  errorMessage.value = ''
  try {
    await deleteProject(project.id)
    projectToDelete.value = null
    await loadProjects()
  } catch {
    if (mounted) errorMessage.value = '删除项目失败，请稍后重试'
  } finally {
    if (mounted) deleting.value = false
  }
}

watch(editorOpen, async (open) => {
  if (open) await nextTick()
})

onMounted(async () => {
  await loadProjects()
  if (route.query.create === '1') focusQuickCreate()
})
onBeforeUnmount(() => { mounted = false })
</script>

<template>
  <main class="projects-page">
    <header class="projects-header">
      <div>
        <BrandIdentity variant="compact" />
        <h1>项目</h1>
        <p>把对话、资料和工作说明组织到同一个上下文中。</p>
      </div>
      <div class="header-actions">
        <button
          type="button"
          class="quiet-button header-nav-button back-chat-button"
          @click="router.push('/chat')"
        >
          返回 Chat
        </button>
        <button
          type="button"
          class="quiet-button header-nav-button knowledge-button"
          @click="router.push('/knowledge')"
        >
          知识库
        </button>
        <ThemeToggle />
      </div>
    </header>

    <form
      class="quick-create"
      @submit.prevent="quickCreate"
    >
      <input
        ref="quickCreateInput"
        v-model="quickName"
        type="text"
        placeholder="新建项目，输入名称…"
        aria-label="新建项目名称"
        maxlength="120"
        autocomplete="off"
      >
      <button
        type="submit"
        class="primary-button"
      >
        创建
      </button>
      <button
        type="button"
        class="quiet-button quick-create-options"
        @click="openCreateForm"
      >
        模板 / 更多选项
      </button>
    </form>

    <label class="project-search">
      <span class="sr-only">搜索项目</span>
      <input
        v-model="search"
        type="search"
        placeholder="搜索项目名称或说明"
        autocomplete="off"
      >
    </label>

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

    <template v-else-if="projects.length === 0">
      <section
        class="empty-state"
        aria-label="创建第一个项目"
      >
        <BrandIdentity variant="compact" />
        <h2>为工作建立一个项目</h2>
        <p>在 Omnixa 中把相关对话、资料和 Instructions 放在一起，后续协作更连贯。</p>
        <button
          type="button"
          class="primary-button"
          @click="focusQuickCreate"
        >
          创建第一个项目
        </button>
      </section>
    </template>

    <template v-else>
      <section
        v-if="recentProjects.length"
        class="project-section"
        aria-labelledby="recent-projects-title"
      >
        <div class="section-heading">
          <div>
            <h2 id="recent-projects-title">
              最近项目
            </h2><p>按最近活动排序</p>
          </div>
        </div>
        <div class="recent-grid">
          <article
            v-for="project in recentProjects"
            :key="project.id"
            class="project-card"
          >
            <button
              type="button"
              class="project-summary"
              @click="openProject(project)"
            >
              <span class="activity-label">{{ relativeActivity(project.last_activity_at || project.updated_at) }}</span>
              <strong>{{ project.name }}</strong>
              <span class="project-description">{{ project.description || '尚未添加项目说明' }}</span>
              <span class="project-metrics"><span>{{ project.conversation_count || 0 }} 个会话</span><span>{{ project.document_count || 0 }} 份资料</span></span>
              <small>更新于 {{ formatDate(project.last_activity_at || project.updated_at || project.created_at) }}</small>
            </button>
            <div
              class="project-actions"
              aria-label="项目操作"
            >
              <button
                type="button"
                class="quiet-button pin-button"
                :aria-label="project.pinned ? `取消置顶 ${project.name}` : `置顶 ${project.name}`"
                :aria-pressed="Boolean(project.pinned)"
                :disabled="pinningProjectId === project.id"
                @click="togglePin(project)"
              >
                {{ project.pinned ? '取消置顶' : '置顶' }}
              </button>
              <button
                type="button"
                class="quiet-button"
                @click="openRenameForm(project)"
              >
                编辑
              </button>
              <button
                type="button"
                class="delete-button"
                @click="requestDelete(project)"
              >
                删除
              </button>
            </div>
          </article>
        </div>
      </section>

      <section
        class="project-section all-projects"
        aria-labelledby="all-projects-title"
      >
        <div class="section-heading">
          <div>
            <h2 id="all-projects-title">
              全部项目
            </h2><p v-if="search">
              显示 {{ allProjects.length }} 个匹配项目
            </p>
          </div>
        </div>
        <p
          v-if="allProjects.length === 0"
          class="state-message"
        >
          没有找到匹配的项目。
        </p>
        <div
          v-else
          class="project-rows"
        >
          <article
            v-for="project in allProjects"
            :key="project.id"
            class="project-row"
          >
            <button
              type="button"
              class="project-summary"
              @click="openProject(project)"
            >
              <strong>{{ project.name }}</strong>
              <span class="project-description">{{ project.description || '尚未添加项目说明' }}</span>
            </button>
            <div class="row-meta">
              <span>{{ project.conversation_count || 0 }} 会话</span><span>{{ project.document_count || 0 }} 资料</span><small>{{ relativeActivity(project.last_activity_at || project.updated_at) }}</small>
            </div>
            <div class="project-actions">
              <button
                type="button"
                class="quiet-button pin-button"
                :aria-label="project.pinned ? `取消置顶 ${project.name}` : `置顶 ${project.name}`"
                :aria-pressed="Boolean(project.pinned)"
                :disabled="pinningProjectId === project.id"
                @click="togglePin(project)"
              >
                {{ project.pinned ? '取消置顶' : '置顶' }}
              </button>
              <button
                type="button"
                class="quiet-button"
                @click="openRenameForm(project)"
              >
                编辑
              </button><button
                type="button"
                class="delete-button"
                @click="requestDelete(project)"
              >
                删除
              </button>
            </div>
          </article>
        </div>
      </section>
    </template>

    <div
      v-if="editorOpen"
      class="modal-backdrop"
      @click.self="closeEditor"
    >
      <section
        class="project-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-editor-title"
      >
        <div class="editor-heading">
          <div>
            <h2 id="project-editor-title">
              {{ editingProject ? '编辑项目' : '新建项目' }}
            </h2><p>{{ editingProject ? '更新项目名称和说明。' : '从一个轻量模板开始，随时可以修改。' }}</p>
          </div><button
            type="button"
            class="close-button"
            aria-label="关闭"
            @click="closeEditor"
          >
            ×
          </button>
        </div>
        <form @submit.prevent="saveProject">
          <div
            v-if="!editingProject"
            class="template-list"
            aria-label="项目模板"
          >
            <button
              v-for="template in templates"
              :key="template.name"
              type="button"
              :class="{ selected: form.instructions === template.instructions && form.description === template.description }"
              @click="applyTemplate(template)"
            >
              {{ template.name }}
            </button>
          </div>
          <label>项目名称<input
            ref="formNameInput"
            v-model="form.name"
            maxlength="120"
            required
          ></label>
          <label>简短描述<textarea
            v-model="form.description"
            rows="2"
            maxlength="500"
          /></label>
          <label>项目 Instructions<textarea
            v-model="form.instructions"
            rows="5"
            maxlength="5000"
            placeholder="目标、语气、约束条件与交付标准"
          /></label>
          <div class="form-actions">
            <button
              type="button"
              class="quiet-button"
              :disabled="saving"
              @click="closeEditor"
            >
              取消
            </button><button
              type="submit"
              class="primary-button"
              :disabled="saving"
            >
              {{ saving ? '正在保存…' : '保存项目' }}
            </button>
          </div>
        </form>
      </section>
    </div>

    <div
      v-if="projectToDelete"
      class="modal-backdrop"
      @click.self="projectToDelete = null"
    >
      <section
        class="confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
      >
        <h2 id="delete-project-title">
          删除项目
        </h2>
        <p>确定要删除“{{ projectToDelete.name }}”吗？删除项目会解除其下会话与资料的项目关联，不删除会话或资料本身。</p>
        <div class="form-actions">
          <button
            type="button"
            class="quiet-button"
            :disabled="deleting"
            @click="projectToDelete = null"
          >
            取消
          </button><button
            type="button"
            class="delete-button"
            :disabled="deleting"
            @click="confirmDelete"
          >
            {{ deleting ? '正在删除…' : '删除项目' }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.projects-page { min-height: 100vh; padding: var(--space-8) max(var(--space-5), calc((100vw - 1040px) / 2)); color: var(--color-text-primary); background: var(--color-bg); }
.projects-header, .header-actions, .section-heading, .project-actions, .form-actions, .editor-heading, .row-meta { display: flex; align-items: center; }
.projects-header, .section-heading { justify-content: space-between; gap: var(--space-6); }.projects-header { margin-bottom: var(--space-6); }.projects-header h1, h2, p { margin: 0; }.projects-header h1 { margin-top: var(--space-2); font-size: var(--text-page-title); }.projects-header p, .section-heading p, .project-description, small, .row-meta { color: var(--color-text-secondary); }.header-actions, .project-actions, .form-actions { gap: var(--space-2); }
.primary-button, .quiet-button, .delete-button, .close-button { min-height: var(--space-11); border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-2) var(--space-4); background: var(--color-surface); color: inherit; font: inherit; cursor: pointer; }.primary-button { border-color: transparent; background: var(--color-action); color: var(--color-action-text); font-weight: 650; }.primary-button:hover:not(:disabled) { background: var(--color-action-hover); }.quiet-button:hover:not(:disabled), .close-button:hover { background: var(--color-surface-hover); }.header-nav-button:hover:not(:disabled) { color: var(--color-accent); }.delete-button { color: var(--color-danger); }.delete-button:hover:not(:disabled) { background: var(--color-danger-soft); }
.quick-create { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-5); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-2xl); padding: var(--space-2); background: var(--color-surface); box-shadow: var(--shadow-float); }.quick-create input { min-width: 0; flex: 1; min-height: var(--space-11); border: 0; padding: 0 var(--space-3); background: transparent; color: inherit; font: inherit; font-size: var(--text-md); }.quick-create input:focus { outline: 0; }.quick-create-options { flex: 0 0 auto; }
.project-search { display: block; margin-bottom: var(--space-8); }.project-search input { width: min(100%, 520px); min-height: var(--space-11); border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-2) var(--space-4); background: var(--color-surface-sunken); color: inherit; font: inherit; }.projects-page :is(button, input, textarea):focus-visible { outline: 3px solid var(--color-focus-ring); outline-offset: 2px; }
.project-section { margin-top: var(--space-8); }.section-heading { margin-bottom: var(--space-4); }.section-heading h2 { font-size: var(--text-section-title); }.recent-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); }.project-card, .project-row { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); background: var(--color-surface); box-shadow: var(--shadow-float); }.project-card { display: flex; min-height: 220px; flex-direction: column; padding: var(--space-5); }.project-summary { display: grid; min-width: 0; gap: var(--space-2); border: 0; padding: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }.project-summary strong { font-size: var(--text-md); overflow-wrap: anywhere; }.project-description { font-size: var(--text-sm); overflow-wrap: anywhere; }.activity-label { width: fit-content; border-radius: var(--radius-pill); padding: 2px var(--space-2); background: var(--color-accent-soft); color: var(--color-accent); font-size: var(--text-xs); font-weight: 650; }.project-metrics, .row-meta { display: flex; flex-wrap: wrap; gap: var(--space-3); font-size: var(--text-xs); }.project-card .project-actions { justify-content: flex-end; margin-top: auto; padding-top: var(--space-4); }.all-projects { padding-top: var(--space-4); border-top: 1px solid var(--color-border-subtle); }.project-rows { display: grid; gap: var(--space-2); }.project-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: var(--space-5); padding: var(--space-4) var(--space-5); box-shadow: none; }.row-meta { justify-content: flex-end; }
.empty-state, .state-message { padding: var(--space-12) var(--space-5); text-align: center; color: var(--color-text-secondary); }.empty-state { display: grid; justify-items: center; gap: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-3xl); background: var(--color-surface); }.empty-state h2 { color: var(--color-text-primary); }.empty-state p { max-width: 460px; }.error-banner { margin: 0 0 var(--space-4); padding: var(--space-3); border-radius: var(--radius-lg); background: var(--color-danger-soft); color: var(--color-danger); }
.modal-backdrop { position: fixed; z-index: 30; inset: 0; display: grid; place-items: center; padding: var(--space-5); background: color-mix(in srgb, var(--color-secondary-identity) 32%, transparent); }.project-editor, .confirm-modal { width: min(100%, 600px); border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-6); background: var(--color-surface); box-shadow: var(--shadow-overlay); }.confirm-modal { width: min(100%, 440px); }.confirm-modal p, .editor-heading p { margin-top: var(--space-2); color: var(--color-text-secondary); }.editor-heading { justify-content: space-between; }.close-button { min-height: var(--space-9); width: var(--space-9); padding: 0; font-size: var(--text-lg); }.project-editor form { display: grid; gap: var(--space-4); margin-top: var(--space-5); }.project-editor label { display: grid; gap: var(--space-2); font-size: var(--text-sm); font-weight: 600; }.project-editor input, .project-editor textarea { width: 100%; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-3); background: var(--color-surface-sunken); color: inherit; font: inherit; resize: vertical; }.template-list { display: flex; flex-wrap: wrap; gap: var(--space-2); }.template-list button { border: 1px solid var(--color-border); border-radius: var(--radius-pill); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: inherit; font: inherit; font-size: var(--text-sm); cursor: pointer; }.template-list button:hover, .template-list button.selected { border-color: var(--color-accent); background: var(--color-accent-soft); }.form-actions { justify-content: flex-end; margin-top: var(--space-2); } button:disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 680px) { .projects-page { padding: var(--space-5); }.projects-header, .project-row { align-items: flex-start; flex-direction: column; }.header-actions { width: 100%; flex-wrap: wrap; justify-content: space-between; }.quick-create { flex-wrap: wrap; }.quick-create input { flex-basis: 100%; }.quick-create-options { margin-left: auto; }.project-row { display: flex; }.row-meta, .project-actions { width: 100%; justify-content: flex-start; }.project-row .project-actions { margin-top: var(--space-1); }.modal-backdrop { align-items: end; }.project-editor, .confirm-modal { border-radius: var(--radius-2xl) var(--radius-2xl) 0 0; } }
</style>
