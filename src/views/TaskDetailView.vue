<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProject } from '../api/modules/project'
import {
  approveTask,
  cancelTask,
  getTask,
  listArtifacts,
  rejectTask,
  retryTask,
  startTask,
} from '../api/modules/workflow'
import MarkdownRenderer from '../components/chat/MarkdownRenderer.vue'

const route = useRoute()
const router = useRouter()
const task = ref(null)
const project = ref(null)
const artifacts = ref([])
const loading = ref(true)
const refreshing = ref(false)
const loadError = ref('')
const actionError = ref('')
const actionBusy = ref('')
const approvalComment = ref('')
const projectUnavailable = ref(false)
let mounted = true
let refreshPromise = null
let pollingTimer = null

const POLLING_INTERVAL = 3000
const POLLING_STATUSES = new Set(['queued', 'running'])

const expectedSteps = [
  { id: 'research', label: '调研' },
  { id: 'summary', label: '总结' },
  { id: 'review', label: '审核' },
  { id: 'finalize', label: '定稿' },
]
const statusLabels = {
  queued: '排队中',
  running: '运行中',
  waiting_approval: '等待审批',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
}
const stepStatusLabels = {
  pending: '待处理',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  skipped: '已跳过',
}
const taskId = computed(() => route.params.id)
const timelineSteps = computed(() => expectedSteps.map((expected) => {
  const step = task.value?.steps?.find((item) => item.step_name === expected.id)
  return { ...expected, ...(step || { status: 'pending', attempt: 0 }) }
}))

function taskStatus(status) {
  return statusLabels[status] || '未知状态'
}

function stepStatus(status) {
  return stepStatusLabels[status] || '状态未知'
}

function currentStep(taskValue) {
  const terminalLabels = {
    succeeded: '已完成',
    cancelled: '已取消',
    waiting_approval: '等待审批',
  }
  if (terminalLabels[taskValue.status]) return terminalLabels[taskValue.status]
  if (!taskValue.current_step) {
    return {
      queued: '排队中',
      running: '执行中',
      failed: '失败',
    }[taskValue.status] || '尚未开始'
  }
  return expectedSteps.find((step) => step.id === taskValue.current_step)?.label || taskValue.current_step
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function artifactContent(artifact) {
  if (typeof artifact.content === 'string') return artifact.content
  return artifact.content == null ? '' : `\`\`\`json\n${JSON.stringify(artifact.content, null, 2)}\n\`\`\``
}

function stopPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

function syncPolling() {
  if (!mounted || !POLLING_STATUSES.has(task.value?.status)) {
    stopPolling()
    return
  }
  if (pollingTimer === null) {
    pollingTimer = setInterval(() => {
      if (!refreshPromise && !actionBusy.value) void loadTask({ showLoading: false })
    }, POLLING_INTERVAL)
  }
}

async function performLoadTask(showLoading) {
  if (showLoading) loading.value = true
  refreshing.value = true
  loadError.value = ''
  try {
    const loadedTask = await getTask(taskId.value)
    const projectRequest = loadedTask.project_id == null
      ? Promise.resolve(null)
      : getProject(loadedTask.project_id)
    const [projectResult, artifactsResult] = await Promise.allSettled([
      projectRequest,
      listArtifacts(taskId.value),
    ])
    if (!mounted) return
    task.value = loadedTask
    project.value = projectResult.status === 'fulfilled' ? projectResult.value : null
    projectUnavailable.value = loadedTask.project_id == null || !project.value
    const loadedArtifacts = artifactsResult.status === 'fulfilled' ? artifactsResult.value : null
    artifacts.value = Array.isArray(loadedArtifacts)
      ? loadedArtifacts
      : (Array.isArray(loadedTask.artifacts) ? loadedTask.artifacts : [])
    syncPolling()
  } catch (error) {
    if (!mounted) return
    stopPolling()
    task.value = null
    project.value = null
    projectUnavailable.value = false
    artifacts.value = []
    loadError.value = error?.status === 404 ? '任务不存在或已被删除' : '加载任务详情失败，请稍后重试'
  } finally {
    if (mounted) {
      loading.value = false
      refreshing.value = false
    }
  }
}

function loadTask({ showLoading = !task.value } = {}) {
  if (refreshPromise) return refreshPromise
  refreshPromise = performLoadTask(showLoading).finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

async function runAction(name, action, failureMessage) {
  if (!task.value || actionBusy.value) return
  actionBusy.value = name
  actionError.value = ''
  try {
    await action()
    if (refreshPromise) await refreshPromise
    await loadTask()
  } catch (err) {
    if (mounted) {
      actionError.value = err?.status === 402 ? '积分不足，无法执行任务' : failureMessage
    }
  } finally {
    if (mounted) actionBusy.value = ''
  }
}

function start() {
  return runAction('start', () => startTask(task.value.id), '启动任务失败，请稍后重试')
}

function cancel() {
  return runAction('cancel', () => cancelTask(task.value.id), '取消任务失败，请稍后重试')
}

function retry() {
  return runAction('retry', () => retryTask(task.value.id), '重试任务失败，请稍后重试')
}

async function decide(decision) {
  const data = approvalComment.value.trim() ? { comment: approvalComment.value.trim() } : {}
  const action = decision === 'approve' ? approveTask : rejectTask
  const failureMessage = decision === 'approve' ? '批准任务失败，请稍后重试' : '驳回任务失败，请稍后重试'
  await runAction(decision, () => action(task.value.id, data), failureMessage)
  if (!actionError.value) approvalComment.value = ''
}

watch(taskId, () => {
  stopPolling()
  task.value = null
  project.value = null
  artifacts.value = []
  projectUnavailable.value = false
  loadTask()
})
onMounted(loadTask)
onBeforeUnmount(() => {
  mounted = false
  stopPolling()
})
</script>

<template>
  <main class="task-detail-page">
    <header class="detail-header">
      <div>
        <p class="eyebrow">
          工作流任务
        </p>
        <h1>{{ task?.title || (task ? `任务 #${task.id}` : '任务详情') }}</h1>
        <p v-if="task">
          <span
            v-if="projectUnavailable"
            class="project-unavailable"
            role="status"
          >项目已删除</span>
          <span v-else>{{ project?.name || task.project_name || `项目 #${task.project_id}` }}</span>
        </p>
      </div>
      <div class="header-actions">
        <button
          type="button"
          class="quiet-button refresh-button"
          :disabled="loading || refreshing"
          @click="loadTask({ showLoading: false })"
        >
          {{ refreshing ? '正在刷新…' : '刷新' }}
        </button>
      </div>
    </header>

    <section
      v-if="loadError"
      class="load-error"
      role="alert"
    >
      <p>{{ loadError }}</p>
      <button
        type="button"
        class="quiet-button"
        @click="loadTask"
      >
        重新加载
      </button>
    </section>
    <p
      v-else-if="loading"
      class="state-message"
      role="status"
    >
      正在加载任务详情…
    </p>
    <section
      v-else-if="!task"
      class="empty-state"
    >
      <h2>没有可显示的任务</h2>
      <p>请从左侧任务入口选择其他任务。</p>
    </section>

    <template v-else>
      <div
        v-if="actionError"
        class="error-banner"
        role="alert"
      >
        <span>{{ actionError }}</span>
        <button
          v-if="actionError === '积分不足，无法执行任务'"
          type="button"
          class="quiet-button"
          @click="router.push('/usage')"
        >
          查看用量
        </button>
      </div>

      <section class="task-summary">
        <div class="summary-copy">
          <span
            class="status-badge"
            :class="`status-${task.status}`"
          >{{ taskStatus(task.status) }}</span>
          <dl>
            <div>
              <dt>当前步骤</dt>
              <dd>{{ currentStep(task) }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatDate(task.created_at) || '时间未知' }}</dd>
            </div>
          </dl>
        </div>
        <div
          class="task-actions"
          aria-label="任务操作"
        >
          <button
            v-if="task.status === 'queued'"
            type="button"
            class="primary-button start-button"
            :disabled="Boolean(actionBusy)"
            @click="start"
          >
            {{ actionBusy === 'start' ? '正在启动…' : '启动' }}
          </button>
          <button
            v-if="task.status === 'queued' || task.status === 'running'"
            type="button"
            class="quiet-button cancel-button"
            :disabled="Boolean(actionBusy)"
            @click="cancel"
          >
            {{ actionBusy === 'cancel' ? '正在取消…' : '取消' }}
          </button>
          <button
            v-if="task.status === 'failed'"
            type="button"
            class="primary-button retry-button"
            :disabled="Boolean(actionBusy)"
            @click="retry"
          >
            {{ actionBusy === 'retry' ? '正在重试…' : '重试' }}
          </button>
        </div>
      </section>

      <section
        v-if="task.error"
        class="task-error"
        role="alert"
        aria-labelledby="task-error-title"
      >
        <h2 id="task-error-title">
          错误原因
        </h2>
        <p>{{ task.error }}</p>
      </section>

      <section
        class="detail-section"
        aria-labelledby="timeline-title"
      >
        <div class="section-heading">
          <div>
            <p class="eyebrow">
              执行进度
            </p>
            <h2 id="timeline-title">
              步骤时间线
            </h2>
          </div>
        </div>
        <ol class="timeline">
          <li
            v-for="step in timelineSteps"
            :key="step.id"
            :class="`step-${step.status}`"
          >
            <span
              class="step-marker"
              aria-hidden="true"
            />
            <div class="step-card">
              <div class="step-heading">
                <h3>{{ step.label }}</h3>
                <span>{{ stepStatus(step.status) }}</span>
              </div>
              <p>尝试次数：{{ step.attempt || 0 }}</p>
              <p
                v-if="step.started_at || step.completed_at"
                class="step-time"
              >
                <span v-if="step.started_at">开始于 {{ formatDate(step.started_at) }}</span>
                <span v-if="step.completed_at">完成于 {{ formatDate(step.completed_at) }}</span>
              </p>
              <p
                v-if="step.error"
                class="step-error"
                role="alert"
              >
                {{ step.error }}
              </p>
            </div>
          </li>
        </ol>
      </section>

      <section
        v-if="task.status === 'waiting_approval'"
        class="approval-card"
        aria-labelledby="approval-title"
      >
        <div>
          <p class="eyebrow">
            需要你的决定
          </p>
          <h2 id="approval-title">
            等待审批
          </h2>
          <p>检查当前结果后批准继续，或附上原因驳回。</p>
        </div>
        <label for="approval-comment">审批评论（可选）</label>
        <textarea
          id="approval-comment"
          v-model="approvalComment"
          rows="4"
          maxlength="2000"
          placeholder="补充审批意见"
        />
        <div class="approval-actions">
          <button
            type="button"
            class="primary-button approve-button"
            :disabled="Boolean(actionBusy)"
            @click="decide('approve')"
          >
            {{ actionBusy === 'approve' ? '正在批准…' : '批准' }}
          </button>
          <button
            type="button"
            class="reject-button"
            :disabled="Boolean(actionBusy)"
            @click="decide('reject')"
          >
            {{ actionBusy === 'reject' ? '正在驳回…' : '驳回' }}
          </button>
        </div>
      </section>

      <section
        class="detail-section artifacts-section"
        aria-labelledby="artifacts-title"
      >
        <div class="section-heading">
          <div>
            <p class="eyebrow">
              交付内容
            </p>
            <h2 id="artifacts-title">
              最终产物
            </h2>
          </div>
        </div>
        <p
          v-if="artifacts.length === 0"
          class="section-empty"
        >
          任务完成后，最终产物会显示在这里。
        </p>
        <template v-else>
          <article
            v-for="(artifact, index) in artifacts"
            :key="`${artifact.artifact_type || 'artifact'}-${artifact.created_at || index}`"
            class="artifact-card"
          >
            <header>
              <div>
                <p>{{ artifact.artifact_type || 'artifact' }}</p>
                <h3>{{ artifact.title || `产物 ${index + 1}` }}</h3>
              </div>
              <time
                v-if="artifact.created_at"
                :datetime="artifact.created_at"
              >{{ formatDate(artifact.created_at) }}</time>
            </header>
            <MarkdownRenderer :content="artifactContent(artifact)" />
          </article>
        </template>
      </section>
    </template>
  </main>
</template>

<style scoped>
.task-detail-page {
  min-height: 100vh;
  padding: var(--space-8) max(var(--space-5), calc((100vw - 960px) / 2));
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.detail-header,
.header-actions,
.task-summary,
.task-actions,
.step-heading,
.approval-actions,
.artifact-card > header {
  display: flex;
  align-items: center;
}

.detail-header,
.task-summary,
.step-heading,
.artifact-card > header {
  justify-content: space-between;
}

.detail-header {
  gap: var(--space-5);
  margin-bottom: var(--space-6);
}

.detail-header h1,
.detail-header p,
.task-error h2,
.task-error p,
.section-heading h2,
.section-heading p,
.approval-card h2,
.approval-card p,
.empty-state h2,
.empty-state p,
.load-error p,
.step-card h3,
.step-card p,
.artifact-card h3,
.artifact-card p {
  margin: 0;
}

.detail-header h1 {
  font-size: var(--text-page-title);
}

.detail-header > div:first-child > p:last-child,
.step-card > p,
.step-time,
.section-empty,
.artifact-card time,
.approval-card > div > p:last-child,
.empty-state p {
  color: var(--color-text-secondary);
}

.eyebrow {
  margin-top: var(--space-2) !important;
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.header-actions,
.task-actions,
.approval-actions {
  gap: var(--space-2);
}

.quiet-button,
.primary-button,
.reject-button {
  min-height: var(--space-11);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.quiet-button:hover:not(:disabled),
.quiet-button:active:not(:disabled) {
  background: var(--color-surface-hover);
  color: var(--color-accent);
}

.primary-button {
  border-color: transparent;
  background: var(--color-action);
  color: var(--color-action-text);
  font-weight: 650;
}

.primary-button:hover:not(:disabled),
.primary-button:active:not(:disabled) {
  background: var(--color-action-hover);
}

.reject-button {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.reject-button:hover:not(:disabled),
.reject-button:active:not(:disabled) {
  background: var(--color-danger-soft);
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.task-summary,
.detail-section,
.approval-card,
.task-error,
.load-error,
.empty-state {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-float);
}

.task-summary {
  gap: var(--space-5);
  padding: var(--space-5);
}

.summary-copy {
  display: grid;
  gap: var(--space-4);
}

.summary-copy dl {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.summary-copy dl div {
  display: grid;
  gap: var(--space-1);
}

.summary-copy dt {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.summary-copy dd {
  margin: 0;
  font-size: var(--text-sm);
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  min-height: 26px;
  align-items: center;
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  background: var(--color-surface-hover);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 700;
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

.error-banner,
.task-error,
.load-error {
  color: var(--color-danger);
}

.error-banner {
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-danger-soft);
}

.task-error,
.load-error,
.empty-state {
  margin-top: var(--space-4);
  padding: var(--space-5);
}

.task-error p,
.empty-state p {
  margin-top: var(--space-2);
}

.load-error,
.empty-state {
  text-align: center;
}

.load-error .quiet-button {
  margin-top: var(--space-4);
}

.detail-section,
.approval-card {
  margin-top: var(--space-5);
  padding: var(--space-6);
}

.section-heading {
  margin-bottom: var(--space-5);
}

.timeline {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline li {
  position: relative;
  display: grid;
  grid-template-columns: var(--space-5) minmax(0, 1fr);
  gap: var(--space-3);
  padding-bottom: var(--space-4);
}

.timeline li:not(:last-child)::before {
  position: absolute;
  top: var(--space-4);
  bottom: 0;
  left: 9px;
  width: 2px;
  background: var(--color-border);
  content: '';
}

.step-marker {
  position: relative;
  z-index: 1;
  width: var(--space-5);
  height: var(--space-5);
  border: 4px solid var(--color-surface);
  border-radius: 50%;
  background: var(--color-border-strong);
  box-shadow: 0 0 0 1px var(--color-border);
}

.step-running .step-marker {
  background: var(--color-accent);
}

.step-succeeded .step-marker {
  background: var(--color-success);
}

.step-failed .step-marker {
  background: var(--color-danger);
}

.step-card {
  display: grid;
  gap: var(--space-2);
  padding: 0 0 var(--space-2);
}

.step-heading {
  gap: var(--space-3);
}

.step-heading h3 {
  font-size: var(--text-base);
}

.step-heading span,
.step-card > p {
  font-size: var(--text-xs);
}

.step-time {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.step-error {
  color: var(--color-danger) !important;
}

.approval-card {
  display: grid;
  gap: var(--space-4);
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent-soft) 45%, var(--color-surface));
}

.approval-card label {
  font-size: var(--text-sm);
  font-weight: 650;
}

.approval-card textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  background: var(--color-surface);
  color: inherit;
  font: inherit;
  resize: vertical;
}

.artifacts-section {
  display: grid;
  gap: var(--space-4);
}

.artifacts-section .section-heading {
  margin-bottom: 0;
}

.artifact-card {
  display: grid;
  gap: var(--space-5);
  padding: var(--space-5);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: var(--color-surface-sunken);
}

.artifact-card > header {
  gap: var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border-subtle);
}

.artifact-card header p {
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: 700;
}

.artifact-card header h3 {
  margin-top: var(--space-1);
  font-size: var(--text-lg);
}

.artifact-card time {
  flex: 0 0 auto;
  font-size: var(--text-xs);
}

.state-message {
  padding: var(--space-8) 0;
  color: var(--color-text-secondary);
  text-align: center;
}

@media (max-width: 720px) {
  .task-detail-page {
    padding: var(--space-5);
  }

  .detail-header,
  .task-summary,
  .artifact-card > header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions,
  .task-actions,
  .approval-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .task-actions button,
  .approval-actions button {
    flex: 1 1 140px;
  }
}
</style>
