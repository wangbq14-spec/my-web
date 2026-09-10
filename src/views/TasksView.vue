<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '../api/modules/project'
import { listTasks } from '../api/modules/workflow'

const router = useRouter()
const tasks = ref([])
const projects = ref([])
const statusFilter = ref('')
const loading = ref(true)
const errorMessage = ref('')
let mounted = true

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '运行中' },
  { value: 'waiting_approval', label: '等待审批' },
  { value: 'succeeded', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

const statusLabels = Object.fromEntries(statusOptions.filter((item) => item.value).map((item) => [item.value, item.label]))
const stepLabels = {
  research: '调研',
  summary: '总结',
  review: '审核',
  finalize: '定稿',
}
const projectNames = computed(() => new Map(projects.value.map((project) => [String(project.id), project.name])))

function taskStatus(status) {
  return statusLabels[status] || '未知状态'
}

function currentStep(task) {
  const terminalLabels = {
    succeeded: '已完成',
    cancelled: '已取消',
    waiting_approval: '等待审批',
  }
  if (terminalLabels[task.status]) return terminalLabels[task.status]
  if (!task.current_step) {
    return {
      queued: '排队中',
      running: '执行中',
      failed: '失败',
    }[task.status] || '尚未开始'
  }
  return stepLabels[task.current_step] || task.current_step
}

function projectName(task) {
  return task.project_name || projectNames.value.get(String(task.project_id)) || `项目 #${task.project_id}`
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

async function loadTasks() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [loadedTasks, loadedProjects] = await Promise.all([
      listTasks(statusFilter.value || undefined),
      listProjects(),
    ])
    if (!mounted) return
    tasks.value = Array.isArray(loadedTasks) ? loadedTasks : []
    projects.value = Array.isArray(loadedProjects) ? loadedProjects : []
  } catch {
    if (mounted) errorMessage.value = '加载任务失败，请稍后重试'
  } finally {
    if (mounted) loading.value = false
  }
}

function openTask(task) {
  router.push({ name: 'task-detail', params: { id: task.id } })
}

watch(statusFilter, loadTasks)
onMounted(loadTasks)
onBeforeUnmount(() => { mounted = false })
</script>

<template>
  <main class="tasks-page">
    <header class="tasks-header">
      <div>
        <h1>任务中心</h1>
        <p>查看工作流进度、处理审批并获取最终产物。</p>
      </div>
    </header>

    <section
      class="task-toolbar"
      aria-label="任务筛选"
    >
      <label for="task-status-filter">状态</label>
      <select
        id="task-status-filter"
        v-model="statusFilter"
      >
        <option
          v-for="option in statusOptions"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </option>
      </select>
    </section>

    <section
      v-if="errorMessage"
      class="error-state"
      role="alert"
    >
      <p>{{ errorMessage }}</p>
      <button
        type="button"
        class="quiet-button"
        @click="loadTasks"
      >
        重新加载
      </button>
    </section>
    <p
      v-else-if="loading"
      class="state-message"
      role="status"
    >
      正在加载任务…
    </p>
    <section
      v-else-if="tasks.length === 0"
      class="empty-state"
      aria-labelledby="empty-task-title"
    >
      <h2 id="empty-task-title">
        {{ statusFilter ? '当前状态下没有任务' : '还没有任务' }}
      </h2>
      <p>{{ statusFilter ? '选择其他状态查看任务。' : '进入项目详情，创建第一个工作流任务。' }}</p>
      <button
        type="button"
        class="primary-button"
        @click="router.push('/projects')"
      >
        前往项目
      </button>
    </section>
    <section
      v-else
      class="task-list"
      aria-label="任务列表"
    >
      <article
        v-for="task in tasks"
        :key="task.id"
        class="task-card"
      >
        <button
          type="button"
          class="task-link"
          :aria-label="`查看任务：${task.title || `任务 #${task.id}`}`"
          @click="openTask(task)"
        >
          <span class="task-main">
            <span class="task-heading">
              <strong>{{ task.title || `任务 #${task.id}` }}</strong>
              <span
                class="status-badge"
                :class="`status-${task.status}`"
              >{{ taskStatus(task.status) }}</span>
            </span>
            <span class="project-name">{{ projectName(task) }}</span>
          </span>
          <span class="task-meta">
            <span><small>当前步骤</small>{{ currentStep(task) }}</span>
            <span><small>创建时间</small>{{ formatDate(task.created_at) }}</span>
          </span>
        </button>
      </article>
    </section>
  </main>
</template>

<style scoped>
.tasks-page {
  min-height: 100vh;
  padding: var(--space-8) max(var(--space-5), calc((100vw - 1040px) / 2));
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.tasks-header,
.header-actions,
.task-toolbar,
.task-heading {
  display: flex;
  align-items: center;
}

.tasks-header {
  justify-content: space-between;
  gap: var(--space-5);
  margin-bottom: var(--space-6);
}

.tasks-header h1,
.tasks-header p,
.error-state p,
.empty-state h2,
.empty-state p {
  margin: 0;
}

.tasks-header h1 {
  margin-top: var(--space-2);
  font-size: var(--text-page-title);
}

.tasks-header p,
.project-name,
.task-meta,
.state-message,
.empty-state p {
  color: var(--color-text-secondary);
}

.header-actions {
  gap: var(--space-2);
}

.quiet-button,
.primary-button,
select {
  min-height: var(--space-11);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  color: inherit;
  font: inherit;
}

.quiet-button,
.primary-button {
  cursor: pointer;
}

.quiet-button:hover,
.quiet-button:active {
  background: var(--color-surface-hover);
  color: var(--color-accent);
}

.primary-button {
  border-color: transparent;
  background: var(--color-action);
  color: var(--color-action-text);
  font-weight: 650;
}

.primary-button:hover,
.primary-button:active {
  background: var(--color-action-hover);
}

.task-toolbar {
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-2xl);
  background: var(--color-surface-sunken);
}

.task-toolbar label {
  font-size: var(--text-sm);
  font-weight: 650;
}

.task-list {
  display: grid;
  gap: var(--space-3);
}

.task-card {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-float);
}

.task-link {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(0, 1fr) minmax(280px, .8fr);
  gap: var(--space-5);
  align-items: center;
  padding: var(--space-5);
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.task-link:hover,
.task-link:active {
  background: var(--color-surface-hover);
}

.task-link:focus-visible {
  outline: 3px solid var(--color-focus-ring);
  outline-offset: -3px;
}

.task-main {
  display: grid;
  min-width: 0;
  gap: var(--space-2);
}

.task-heading {
  flex-wrap: wrap;
  gap: var(--space-2);
}

.task-heading strong {
  overflow-wrap: anywhere;
  font-size: var(--text-lg);
}

.project-name {
  font-size: var(--text-sm);
}

.task-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  font-size: var(--text-sm);
}

.task-meta span {
  display: grid;
  gap: var(--space-1);
}

.task-meta small {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  min-height: 24px;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--color-surface-hover);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 700;
  white-space: nowrap;
}

.status-running,
.status-waiting_approval {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.status-succeeded {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.status-failed {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.error-state,
.empty-state {
  padding: var(--space-8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  text-align: center;
}

.error-state {
  color: var(--color-danger);
}

.error-state .quiet-button,
.empty-state .primary-button {
  margin-top: var(--space-4);
}

.empty-state p {
  margin-top: var(--space-2);
}

.state-message {
  padding: var(--space-8) 0;
  text-align: center;
}

@media (max-width: 720px) {
  .tasks-page {
    padding: var(--space-5);
  }

  .tasks-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .task-link,
  .task-meta {
    grid-template-columns: 1fr;
  }
}
</style>
