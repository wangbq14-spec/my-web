<script setup>
import { onMounted, ref } from 'vue'
import * as adminApi from '../api/modules/admin'

const tabs = [
  { key: 'overview', label: 'Overview' },
  { key: 'users', label: 'Users' },
  { key: 'recharge', label: 'Recharge Requests' },
  { key: 'feedback', label: 'Feedback' },
  { key: 'analytics', label: 'Analytics' },
  { key: 'invites', label: 'Invite Codes' },
]
const activeTab = ref('overview')
const loading = ref(false)
const errorMessage = ref('')

const number = (value) => Number(value || 0).toLocaleString('zh-CN')
const date = (value) => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('zh-CN')
}

const METRIC_LABELS = {
  new_users: '新用户',
  active_users: '活跃用户',
  chat_requests: 'Chat 请求',
  rag_requests: 'RAG 请求',
  agent_requests: 'Agent 请求',
  vision_requests: 'Vision 请求',
  documents_uploaded: '上传文档',
  credits_consumed: 'Credits 消耗',
  pending_recharge_requests: '待审核充值',
  new_feedback: '新 Feedback',
  unreviewed_feedback: '未读 Feedback',
}
const metricLabel = (key) => METRIC_LABELS[key] || key
const metricValue = (key, value) =>
  typeof value === 'number' ? Number(value).toLocaleString('zh-CN') : String(value ?? '—')

/* ---------- Overview ---------- */
const overview = ref(null)
async function loadOverview() {
  loading.value = true
  errorMessage.value = ''
  try {
    overview.value = await adminApi.getAdminOverview()
  } catch (error) {
    errorMessage.value = error?.message || 'Overview 加载失败'
  } finally {
    loading.value = false
  }
}

/* ---------- Users ---------- */
const users = ref([])
const search = ref('')
const userFilter = ref('')
const selectedUser = ref(null)
const detail = ref(null)
const grantForm = ref({ amount: 100, reason: '', request_id: '' })
const grantMessage = ref('')
const grantError = ref('')

async function loadUsers() {
  loading.value = true
  errorMessage.value = ''
  try {
    users.value = await adminApi.listUsers({ search: search.value, filter: userFilter.value })
  } catch (error) {
    errorMessage.value = error?.message || '用户列表加载失败'
  } finally {
    loading.value = false
  }
}

function openUser(user) {
  selectedUser.value = user
  detail.value = null
  grantMessage.value = ''
  grantError.value = ''
  loadUserDetail(user.id)
}

async function loadUserDetail(userId) {
  detail.value = { summary: null, usage: [], ledger: [], feedback: [], recharges: [] }
  try {
    const [summary, usage, ledger, feedbackList, recharges] = await Promise.all([
      adminApi.getUserDetail(userId),
      adminApi.getUserUsage(userId),
      adminApi.getUserLedger(userId),
      adminApi.getUserFeedback(userId),
      adminApi.getUserRecharges(userId),
    ])
    detail.value = { summary, usage, ledger, feedback: feedbackList, recharges }
  } catch (error) {
    detail.value = { summary: null, usage: [], ledger: [], feedback: [], recharges: [], error: error?.message || '详情加载失败' }
  }
}

async function submitGrant() {
  if (!selectedUser.value) return
  grantMessage.value = ''
  grantError.value = ''
  try {
    const result = await adminApi.grantCredits(selectedUser.value.id, {
      amount: grantForm.value.amount,
      reason: grantForm.value.reason,
      request_id: grantForm.value.request_id || undefined,
    })
    grantMessage.value = `已补发，当前余额 ${number(result.balance)}`
    await loadUsers()
    await loadUserDetail(selectedUser.value.id)
  } catch (error) {
    grantError.value = error?.message || '补发失败'
  }
}

/* ---------- Recharge ---------- */
const recharges = ref([])
const rechargeStatus = ref('pending')
const confirmRechargeId = ref(null)

async function loadRecharges() {
  loading.value = true
  errorMessage.value = ''
  try {
    recharges.value = await adminApi.listRechargeRequests({ status: rechargeStatus.value })
  } catch (error) {
    errorMessage.value = error?.message || '充值申请加载失败'
  } finally {
    loading.value = false
  }
}

async function reviewRecharge(requestId, action, note = '') {
  confirmRechargeId.value = null
  errorMessage.value = ''
  try {
    if (action === 'approve') {
      await adminApi.approveRecharge(requestId, note || null)
    } else {
      await adminApi.rejectRecharge(requestId, note || null)
    }
    await loadRecharges()
    if (overview.value) await loadOverview()
  } catch (error) {
    errorMessage.value = error?.message || '审核操作失败'
  }
}

/* ---------- Feedback ---------- */
const feedbackList = ref([])
const feedbackStatus = ref('new')

async function loadFeedback() {
  loading.value = true
  errorMessage.value = ''
  try {
    feedbackList.value = await adminApi.listFeedback({ status: feedbackStatus.value })
  } catch (error) {
    errorMessage.value = error?.message || 'Feedback 加载失败'
  } finally {
    loading.value = false
  }
}

async function setFeedbackStatus(id, status) {
  errorMessage.value = ''
  try {
    await adminApi.updateFeedbackStatus(id, status)
    await loadFeedback()
  } catch (error) {
    errorMessage.value = error?.message || '状态更新失败'
  }
}

/* ---------- Analytics ---------- */
const analytics = ref(null)
const analyticsRange = ref('7d')

async function loadAnalytics() {
  loading.value = true
  errorMessage.value = ''
  try {
    analytics.value = await adminApi.getAnalytics(analyticsRange.value)
  } catch (error) {
    errorMessage.value = error?.message || 'Analytics 加载失败'
  } finally {
    loading.value = false
  }
}

/* ---------- Invites ---------- */
const invites = ref([])
const inviteForm = ref({ channel: 'classroom', max_uses: 20, expires_at: '' })
const inviteMessage = ref('')
const inviteError = ref('')

async function loadInvites() {
  loading.value = true
  errorMessage.value = ''
  try {
    invites.value = await adminApi.listInviteCodes()
  } catch (error) {
    errorMessage.value = error?.message || '邀请码加载失败'
  } finally {
    loading.value = false
  }
}

async function createInvite() {
  inviteMessage.value = ''
  inviteError.value = ''
  try {
    const payload = {
      channel: inviteForm.value.channel.trim(),
      max_uses: Number(inviteForm.value.max_uses),
      expires_at: inviteForm.value.expires_at || null,
    }
    if (!payload.channel || !Number.isInteger(payload.max_uses) || payload.max_uses <= 0) {
      inviteError.value = '请填写有效的渠道与使用次数'
      return
    }
    const created = await adminApi.createInviteCode(payload)
    inviteMessage.value = `已创建：${created.code}`
    await loadInvites()
  } catch (error) {
    inviteError.value = error?.message || '创建失败'
  }
}

async function disableInvite(id) {
  errorMessage.value = ''
  try {
    await adminApi.disableInviteCode(id)
    await loadInvites()
  } catch (error) {
    errorMessage.value = error?.message || '关闭失败'
  }
}

async function switchTab(key) {
  activeTab.value = key
  loading.value = false
  errorMessage.value = ''
  if (key === 'overview' && !overview.value) await loadOverview()
  if (key === 'users') await loadUsers()
  if (key === 'recharge') await loadRecharges()
  if (key === 'feedback') await loadFeedback()
  if (key === 'analytics') await loadAnalytics()
  if (key === 'invites') await loadInvites()
}

onMounted(() => switchTab('overview'))
</script>

<template>
  <main class="admin-page">
    <header class="admin-header">
      <h1>Beta Operations Center</h1>
      <p>管理第一批 Classroom Beta 用户与运营数据。</p>
    </header>

    <nav class="admin-tabs" aria-label="运营中心模块">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="admin-tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <p v-if="errorMessage" class="error-banner" role="alert">{{ errorMessage }}</p>
    <p v-if="loading" class="state-message">正在加载…</p>

    <!-- ============ Overview ============ -->
    <section v-if="activeTab === 'overview'" aria-label="Overview">
      <template v-if="overview">
        <h2 class="section-title">今日</h2>
        <div class="metric-grid">
          <article class="metric-card" v-for="(item, key) in overview.today" :key="key">
            <span>{{ metricLabel(key) }}</span>
            <strong>{{ metricValue(key, item) }}</strong>
          </article>
        </div>

        <h2 class="section-title">近 7 天</h2>
        <div class="metric-grid">
          <article class="metric-card">
            <span>活跃用户</span><strong>{{ number(overview.last_7d.active_users) }}</strong>
          </article>
          <article class="metric-card">
            <span>AI 请求总数</span><strong>{{ number(overview.last_7d.total_ai_requests) }}</strong>
          </article>
          <article class="metric-card">
            <span>Credits 消耗</span><strong>{{ number(overview.last_7d.credits_consumed) }}</strong>
          </article>
          <article class="metric-card">
            <span>最常用模型档位</span><strong>{{ overview.last_7d.most_used_model_tier || '—' }}</strong>
          </article>
          <article class="metric-card">
            <span>Vision 用量</span>
            <strong>{{ number(overview.last_7d.vision_usage.requests) }}</strong>
            <p v-if="overview.last_7d.vision_usage.credits">消耗 {{ number(overview.last_7d.vision_usage.credits) }} Credits</p>
          </article>
          <article class="metric-card">
            <span>RAG 检索用量</span><strong>{{ number(overview.last_7d.rag_usage) }}</strong>
          </article>
        </div>

        <h2 class="section-title">Beta Health</h2>
        <div class="metric-grid">
          <article class="metric-card">
            <span>活跃用户（7 天）</span><strong>{{ number(overview.health.active_users) }}</strong>
          </article>
          <article class="metric-card">
            <span>回归用户</span><strong>{{ number(overview.health.returning_users) }}</strong>
          </article>
          <article class="metric-card">
            <span>文档处理成功率</span>
            <strong>{{ overview.health.document_success_rate === null ? '—' : `${Math.round(overview.health.document_success_rate * 100)}%` }}</strong>
          </article>
          <article class="metric-card">
            <span>Credits 消耗（7 天）</span><strong>{{ number(overview.health.credits_consumed) }}</strong>
          </article>
          <article class="metric-card muted">
            <span>AI 成功率 / 错误率</span>
            <strong>暂不可统计</strong>
            <p>当前数据模型未记录失败请求，已按规范延期。</p>
          </article>
          <article class="metric-card muted">
            <span>Vision 成功率</span>
            <strong>暂不可统计</strong>
            <p>当前数据模型未记录失败请求，已按规范延期。</p>
          </article>
        </div>
        <p class="generated-at">数据生成于 {{ date(overview.generated_at) }}</p>
      </template>
    </section>

    <!-- ============ Users ============ -->
    <section v-if="activeTab === 'users'" aria-label="用户管理">
      <div class="toolbar">
        <label class="sr-only" for="user-search">搜索用户</label>
        <input id="user-search" v-model="search" type="search" placeholder="搜索用户名 / 邮箱" @keyup.enter="loadUsers" />
        <label class="sr-only" for="user-filter">用户过滤</label>
        <select id="user-filter" v-model="userFilter" @change="loadUsers">
          <option value="">全部用户</option>
          <option value="active">活跃</option>
          <option value="new">新用户</option>
          <option value="low_balance">低余额</option>
        </select>
        <button type="button" class="btn" @click="loadUsers">查询</button>
      </div>

      <div v-if="selectedUser" class="detail-panel">
        <div class="detail-head">
          <h3>用户详情：{{ selectedUser.username }}</h3>
          <button type="button" class="btn subtle" @click="selectedUser = null; detail = null">关闭</button>
        </div>
        <template v-if="detail && detail.summary">
          <div class="detail-basic">
            <span>ID {{ detail.summary.id }} · {{ detail.summary.email }} · 角色 {{ detail.summary.role }}</span>
            <span>注册于 {{ date(detail.summary.created_at) }} · 最近活跃 {{ date(detail.summary.last_active_at) }}</span>
            <span><strong>{{ number(detail.summary.balance) }}</strong> Credits · 累计消耗 {{ number(detail.summary.credits_charged) }}</span>
          </div>

          <form class="grant-form" @submit.prevent="submitGrant">
            <h4>补发 Credits（走 Billing Service，带审计与幂等）</h4>
            <label>金额<input v-model.number="grantForm.amount" type="number" min="1" required /></label>
            <label>原因（必填）<input v-model="grantForm.reason" type="text" required maxlength="10000" placeholder="如：课堂奖励" /></label>
            <label>request_id（可选，幂等键）<input v-model="grantForm.request_id" type="text" maxlength="64" placeholder="留空自动生成" /></label>
            <button type="submit" class="btn">补发</button>
            <p v-if="grantMessage" class="ok-message">{{ grantMessage }}</p>
            <p v-if="grantError" class="error-banner">{{ grantError }}</p>
          </form>

          <h4>最近 Usage</h4>
          <div class="table-wrap"><table>
            <thead><tr><th>时间</th><th>模型</th><th>档位</th><th>Credits</th></tr></thead>
            <tbody>
              <tr v-for="(item, i) in detail.usage" :key="`u${i}`">
                <td>{{ date(item.created_at) }}</td><td>{{ item.model }}</td><td>{{ item.model_tier || '—' }}</td><td>{{ number(item.credits_charged) }}</td>
              </tr>
              <tr v-if="detail.usage.length === 0"><td colspan="4" class="empty-cell">无使用记录</td></tr>
            </tbody>
          </table></div>

          <h4>最近 Ledger</h4>
          <div class="table-wrap"><table>
            <thead><tr><th>时间</th><th>操作</th><th>金额</th><th>request_id</th><th>描述</th></tr></thead>
            <tbody>
              <tr v-for="item in detail.ledger" :key="`l${item.id}`">
                <td>{{ date(item.created_at) }}</td><td>{{ item.operation }}</td><td>{{ item.amount }}</td><td class="mono">{{ item.request_id || '—' }}</td><td>{{ item.description || '—' }}</td>
              </tr>
              <tr v-if="detail.ledger.length === 0"><td colspan="5" class="empty-cell">无流水</td></tr>
            </tbody>
          </table></div>

          <h4>Feedback</h4>
          <ul class="mini-list">
            <li v-for="item in detail.feedback" :key="`f${item.id}`">{{ date(item.created_at) }} · [{{ item.type }}] {{ item.message }}</li>
            <li v-if="detail.feedback.length === 0" class="empty-cell">无反馈</li>
          </ul>

          <h4>充值申请</h4>
          <ul class="mini-list">
            <li v-for="item in detail.recharges" :key="`r${item.id}`">
              {{ date(item.created_at) }} · {{ item.package_code }} · {{ number(item.credits_requested) }} Credits · {{ item.status }}
            </li>
            <li v-if="detail.recharges.length === 0" class="empty-cell">无充值申请</li>
          </ul>
        </template>
        <p v-else class="state-message">{{ detail?.error || '加载中…' }}</p>
      </div>

      <div class="table-wrap"><table>
        <thead><tr><th>用户</th><th>角色</th><th>注册时间</th><th>余额</th><th>总用量</th><th>累计 Credits</th><th>最近活跃</th><th></th></tr></thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td><strong>{{ user.username }}</strong><small>{{ user.email }}</small></td>
            <td>{{ user.role }}</td>
            <td>{{ date(user.created_at) }}</td>
            <td>{{ number(user.balance) }}</td>
            <td>{{ number(user.usage_count) }}</td>
            <td>{{ number(user.credits_charged) }}</td>
            <td>{{ date(user.last_active_at) }}</td>
            <td><button type="button" class="btn subtle" @click="openUser(user)">详情</button></td>
          </tr>
          <tr v-if="users.length === 0"><td colspan="8" class="empty-cell">无匹配用户</td></tr>
        </tbody>
      </table></div>
    </section>

    <!-- ============ Recharge ============ -->
    <section v-if="activeTab === 'recharge'" aria-label="充值审核">
      <div class="toolbar">
        <label class="sr-only" for="recharge-status">充值状态</label>
        <select id="recharge-status" v-model="rechargeStatus" @change="loadRecharges">
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <button type="button" class="btn" @click="loadRecharges">刷新</button>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>用户</th><th>套餐</th><th>金额</th><th>Credits</th><th>申请时间</th><th>状态</th><th>备注</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in recharges" :key="item.id">
            <td class="mono">{{ item.id }}</td>
            <td>{{ item.username || `#${item.user_id}` }}</td>
            <td>{{ item.package_code }}</td>
            <td>{{ item.amount_cny !== null && item.amount_cny !== undefined ? `¥${item.amount_cny}` : item.amount_display }}</td>
            <td>{{ number(item.credits_requested) }}</td>
            <td>{{ date(item.created_at) }}</td>
            <td><span class="status-pill" :class="item.status">{{ item.status }}</span></td>
            <td class="note-cell">{{ item.note || '—' }}</td>
            <td>
              <template v-if="item.status === 'pending'">
                <button
                  type="button"
                  class="btn primary"
                  @click="confirmRechargeId = confirmRechargeId === item.id ? null : item.id"
                >
                  {{ confirmRechargeId === item.id ? '再次点击确认' : '批准' }}
                </button>
                <button v-if="confirmRechargeId === item.id" type="button" class="btn danger" @click="reviewRecharge(item.id, 'approve')">确认批准</button>
                <button type="button" class="btn subtle" @click="reviewRecharge(item.id, 'reject', '由管理员拒绝')">拒绝</button>
              </template>
              <span v-else class="muted-text">{{ item.reviewed_by ? `管理员 #${item.reviewed_by}` : '—' }}</span>
            </td>
          </tr>
          <tr v-if="recharges.length === 0"><td colspan="9" class="empty-cell">暂无申请</td></tr>
        </tbody>
      </table></div>
      <p class="hint">批准走服务端事务：RechargeRequest → CreditLedger grant → Wallet 入账；重复/并发批准会被拒绝（409）。</p>
    </section>

    <!-- ============ Feedback ============ -->
    <section v-if="activeTab === 'feedback'" aria-label="Feedback">
      <div class="toolbar">
        <label class="sr-only" for="feedback-status">反馈状态</label>
        <select id="feedback-status" v-model="feedbackStatus" @change="loadFeedback">
          <option value="new">New</option>
          <option value="reviewed">Reviewed</option>
          <option value="closed">Closed</option>
        </select>
        <button type="button" class="btn" @click="loadFeedback">刷新</button>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>用户</th><th>类型</th><th>路径</th><th>内容</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in feedbackList" :key="item.id">
            <td class="mono">{{ item.id }}</td>
            <td>{{ item.username || `#${item.user_id}` }}</td>
            <td>{{ item.type }}</td>
            <td class="mono">{{ item.path }}</td>
            <td class="note-cell">{{ item.message }}</td>
            <td>{{ date(item.created_at) }}</td>
            <td>
              <button v-if="item.status === 'new'" type="button" class="btn subtle" @click="setFeedbackStatus(item.id, 'reviewed')">标记已读</button>
              <button v-else type="button" class="btn subtle" @click="setFeedbackStatus(item.id, 'closed')">关闭</button>
            </td>
          </tr>
          <tr v-if="feedbackList.length === 0"><td colspan="7" class="empty-cell">暂无反馈</td></tr>
        </tbody>
      </table></div>
    </section>

    <!-- ============ Analytics ============ -->
    <section v-if="activeTab === 'analytics'" aria-label="Analytics">
      <div class="toolbar">
        <label class="sr-only" for="analytics-range">时间范围</label>
        <select id="analytics-range" v-model="analyticsRange" @change="loadAnalytics">
          <option value="7d">近 7 天</option>
          <option value="30d">近 30 天</option>
          <option value="all">全部</option>
        </select>
        <button type="button" class="btn" @click="loadAnalytics">刷新</button>
      </div>
      <template v-if="analytics">
        <div class="metric-grid">
          <article class="metric-card"><span>注册用户（全部）</span><strong>{{ number(analytics.registered) }}</strong></article>
          <article class="metric-card"><span>活跃用户</span><strong>{{ number(analytics.active_users) }}</strong></article>
          <article class="metric-card"><span>新用户</span><strong>{{ number(analytics.new_users) }}</strong></article>
          <article class="metric-card"><span>Chat 消息</span><strong>{{ number(analytics.chat_messages) }}</strong></article>
          <article class="metric-card"><span>RAG Chunks</span><strong>{{ number(analytics.rag_chunks) }}</strong></article>
          <article class="metric-card"><span>Agent Steps</span><strong>{{ number(analytics.agent_steps) }}</strong></article>
          <article class="metric-card"><span>Workflows</span><strong>{{ number(analytics.workflows) }}</strong></article>
          <article class="metric-card"><span>文档</span><strong>{{ number(analytics.documents) }}</strong></article>
          <article class="metric-card"><span>项目</span><strong>{{ number(analytics.projects) }}</strong></article>
          <article class="metric-card"><span>Feedback</span><strong>{{ number(analytics.feedback) }}</strong></article>
        </div>
        <div class="metric-grid">
          <article class="metric-card"><span>发放 Credits</span><strong>{{ number(analytics.credits.granted) }}</strong></article>
          <article class="metric-card"><span>消耗 Credits</span><strong>{{ number(-analytics.credits.consumed) }}</strong></article>
        </div>
        <h2 class="section-title">按模型档位</h2>
        <div class="metric-grid">
          <article class="metric-card" v-for="(count, tier) in analytics.model_tier" :key="tier">
            <span>{{ tier }}</span><strong>{{ number(count) }}</strong>
          </article>
        </div>
      </template>
    </section>

    <!-- ============ Invites ============ -->
    <section v-if="activeTab === 'invites'" aria-label="邀请码管理">
      <form class="invite-form" @submit.prevent="createInvite">
        <h3>创建邀请码</h3>
        <label>渠道<input v-model="inviteForm.channel" type="text" required maxlength="40" placeholder="classroom" /></label>
        <label>最大使用次数<input v-model.number="inviteForm.max_uses" type="number" min="1" required /></label>
        <label>过期时间（可选）<input v-model="inviteForm.expires_at" type="datetime-local" /></label>
        <button type="submit" class="btn primary">创建</button>
        <p v-if="inviteMessage" class="ok-message mono">{{ inviteMessage }}</p>
        <p v-if="inviteError" class="error-banner">{{ inviteError }}</p>
      </form>
      <div class="table-wrap"><table>
        <thead><tr><th>邀请码</th><th>渠道</th><th>已用 / 上限</th><th>状态</th><th>过期时间</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in invites" :key="item.id">
            <td class="mono"><strong>{{ item.code }}</strong></td>
            <td>{{ item.channel }}</td>
            <td>{{ item.used_count }} / {{ item.max_uses }}</td>
            <td><span class="status-pill" :class="item.is_active ? 'active' : 'disabled'">{{ item.is_active ? 'active' : 'disabled' }}</span></td>
            <td>{{ item.expires_at ? date(item.expires_at) : '永不过期' }}</td>
            <td>{{ date(item.created_at) }}</td>
            <td>
              <button v-if="item.is_active" type="button" class="btn subtle" @click="disableInvite(item.id)">关闭</button>
              <span v-else class="muted-text">已关闭</span>
            </td>
          </tr>
          <tr v-if="invites.length === 0"><td colspan="7" class="empty-cell">暂无邀请码</td></tr>
        </tbody>
      </table></div>
    </section>
  </main>
</template>

<style scoped>
.admin-page { min-height: 100%; padding: var(--space-8) max(var(--space-5), calc((100vw - 1080px) / 2)); color: var(--color-text-primary); }
.admin-header h1, .admin-header p, .section-title, .detail-panel h3, .detail-panel h4 { margin: 0; }
.admin-header p { margin-top: var(--space-2); color: var(--color-text-secondary); }
.admin-tabs { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: var(--space-6) 0; }
.admin-tab { border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-2) var(--space-3); background: transparent; color: var(--color-text-secondary); font: inherit; font-size: var(--text-sm); cursor: pointer; }
.admin-tab.active { background: var(--color-primary, var(--color-secondary-identity)); color: var(--color-surface); border-color: transparent; }
.section-title { margin: var(--space-6) 0 var(--space-3); }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: var(--space-3); }
.metric-card { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-4); background: var(--color-surface); }
.metric-card span { color: var(--color-text-secondary); font-size: var(--text-xs); }
.metric-card strong { display: block; margin-top: var(--space-2); font-size: 1.5rem; word-break: break-word; }
.metric-card p { margin: var(--space-2) 0 0; color: var(--color-text-secondary); font-size: var(--text-xs); }
.metric-card.muted { opacity: .75; }
.generated-at { margin-top: var(--space-4); color: var(--color-text-secondary); font-size: var(--text-xs); }
.toolbar { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-4); align-items: center; }
.toolbar input[type='search'], .toolbar select { min-width: 200px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); }
.table-wrap { overflow-x: auto; border: 1px solid var(--color-border); border-radius: var(--radius-2xl); background: var(--color-surface); }
table { width: 100%; border-collapse: collapse; white-space: nowrap; }
th, td { padding: var(--space-3); border-bottom: 1px solid var(--color-border-subtle); text-align: left; }
th { color: var(--color-text-secondary); font-size: var(--text-xs); }
td small { display: block; margin-top: 2px; color: var(--color-text-secondary); }
td strong { color: var(--color-text-primary); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: var(--text-xs); }
.note-cell { max-width: 280px; white-space: normal; word-break: break-word; }
.empty-cell { color: var(--color-text-secondary); text-align: center; padding: var(--space-6); }
.error-banner { color: var(--color-danger); margin: var(--space-3) 0; }
.ok-message { color: var(--color-success, #2e9e5b); margin: var(--space-2) 0; }
.state-message { padding: var(--space-8); color: var(--color-text-secondary); text-align: center; }
.hint { color: var(--color-text-secondary); font-size: var(--text-xs); margin-top: var(--space-3); }
.muted-text { color: var(--color-text-secondary); font-size: var(--text-xs); }
.status-pill { border-radius: var(--radius-full, 999px); padding: 2px var(--space-2); font-size: var(--text-xs); }
.status-pill.pending, .status-pill.new, .status-pill.active { background: color-mix(in srgb, var(--color-secondary-identity) 16%, transparent); color: var(--color-secondary-identity); }
.status-pill.approved, .status-pill.reviewed { background: color-mix(in srgb, var(--color-success, #2e9e5b) 16%, transparent); color: var(--color-success, #2e9e5b); }
.status-pill.rejected, .status-pill.disabled { background: color-mix(in srgb, var(--color-danger) 16%, transparent); color: var(--color-danger); }
.status-pill.cancelled { background: var(--color-surface-alt, var(--color-border-subtle)); color: var(--color-text-secondary); }
.btn { border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); cursor: pointer; }
.btn.primary { background: var(--color-secondary-identity); color: var(--color-surface); border-color: transparent; }
.btn.danger { background: var(--color-danger); color: var(--color-surface); border-color: transparent; }
.btn.subtle { background: transparent; }
.detail-panel { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-5); margin-bottom: var(--space-5); background: var(--color-surface); }
.detail-head { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); }
.detail-basic { display: flex; flex-wrap: wrap; gap: var(--space-3); margin: var(--space-4) 0; color: var(--color-text-secondary); font-size: var(--text-sm); }
.detail-basic strong { color: var(--color-text-primary); }
.grant-form { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: end; border: 1px dashed var(--color-border); border-radius: var(--radius-xl); padding: var(--space-4); margin: var(--space-4) 0; }
.grant-form h4 { width: 100%; }
.grant-form label { display: flex; flex-direction: column; gap: var(--space-1); color: var(--color-text-secondary); font-size: var(--text-xs); }
.grant-form input { min-width: 160px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; }
.mini-list { margin: var(--space-2) 0 var(--space-4); padding-left: var(--space-5); color: var(--color-text-secondary); font-size: var(--text-sm); }
.mini-list li { margin: var(--space-1) 0; word-break: break-word; }
.invite-form { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: end; border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-5); margin-bottom: var(--space-5); background: var(--color-surface); }
.invite-form h3 { width: 100%; margin: 0; }
.invite-form label { display: flex; flex-direction: column; gap: var(--space-1); color: var(--color-text-secondary); font-size: var(--text-xs); }
.invite-form input { min-width: 160px; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
@media (max-width: 640px) { .admin-page { padding: var(--space-6) var(--space-4); }.metric-grid { grid-template-columns: 1fr 1fr; } }
</style>
