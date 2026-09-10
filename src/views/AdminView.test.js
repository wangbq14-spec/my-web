import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminView from './AdminView.vue'

const api = vi.hoisted(() => ({
  getAdminOverview: vi.fn(),
  listUsers: vi.fn(),
  getUserDetail: vi.fn(),
  getUserUsage: vi.fn(),
  getUserLedger: vi.fn(),
  getUserFeedback: vi.fn(),
  getUserRecharges: vi.fn(),
  grantCredits: vi.fn(),
  listRechargeRequests: vi.fn(),
  approveRecharge: vi.fn(),
  rejectRecharge: vi.fn(),
  listFeedback: vi.fn(),
  updateFeedbackStatus: vi.fn(),
  getAnalytics: vi.fn(),
  listInviteCodes: vi.fn(),
  createInviteCode: vi.fn(),
  disableInviteCode: vi.fn(),
}))
vi.mock('../api/modules/admin', () => api)

const overview = {
  generated_at: '2026-09-06T08:00:00Z',
  today: {
    new_users: 3,
    active_users: 2,
    chat_requests: 4,
    rag_requests: 1,
    agent_requests: 1,
    vision_requests: 1,
    documents_uploaded: 2,
    credits_consumed: 12,
    pending_recharge_requests: 1,
    new_feedback: 2,
    unreviewed_feedback: 1,
  },
  last_7d: {
    active_users: 5,
    total_ai_requests: 20,
    credits_consumed: 60,
    most_used_model_tier: 'standard',
    vision_usage: { requests: 3, credits: 6 },
    rag_usage: 4,
  },
  health: {
    active_users: 5,
    returning_users: 2,
    ai_success_rate: null,
    ai_error_rate: null,
    document_success_rate: 0.8,
    vision_success_rate: null,
    credits_consumed: 60,
  },
}

const users = [
  { id: 1, username: 'alice', email: 'alice@example.com', role: 'user', is_active: true, created_at: '2026-09-01T00:00:00Z', balance: 500, usage_count: 3, credits_charged: 12, last_active_at: '2026-09-06T07:00:00Z' },
  { id: 2, username: 'bob', email: 'bob@example.com', role: 'user', is_active: true, created_at: '2026-09-05T00:00:00Z', balance: 20, usage_count: 0, credits_charged: 0, last_active_at: null },
]

const pending = [{ id: 9, user_id: 1, username: 'alice', package_code: 'custom', amount_cny: '10.00', amount_display: '10 CNY', credits_requested: 3000, pricing_snapshot: '{}', status: 'pending', note: null, created_at: '2026-09-06T06:00:00Z', reviewed_at: null, reviewed_by: null }]

const feedbackList = [{ id: 5, user_id: 1, username: 'alice', type: 'bug', path: '/chat', message: '图片发不出去', status: 'new', created_at: '2026-09-06T06:00:00Z' }]

const invites = [{ id: 3, code: 'OMNIXA-AI-ABC', channel: 'classroom', max_uses: 20, used_count: 3, is_active: true, expires_at: null, created_at: '2026-09-01T00:00:00Z' }]

const analytics = {
  range: '7d',
  registered: 8,
  active_users: 5,
  new_users: 2,
  chat_messages: 20,
  rag_chunks: 120,
  agent_steps: 6,
  workflows: 2,
  documents: 4,
  projects: 3,
  credits: { granted: 16000, consumed: -60 },
  model_tier: { standard: 15, deep: 5 },
  feedback: 2,
}

async function mountOverview() {
  api.getAdminOverview.mockResolvedValue(overview)
  const wrapper = mount(AdminView)
  await flushPromises()
  return wrapper
}

describe('AdminView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getAdminOverview.mockResolvedValue(overview)
    api.listUsers.mockResolvedValue(users)
    api.getUserDetail.mockResolvedValue(users[0])
    api.getUserUsage.mockResolvedValue([])
    api.getUserLedger.mockResolvedValue([])
    api.getUserFeedback.mockResolvedValue([])
    api.getUserRecharges.mockResolvedValue([])
    api.grantCredits.mockResolvedValue({ balance: 600, updated_at: '2026-09-06T08:00:00Z' })
    api.listRechargeRequests.mockResolvedValue(pending)
    api.approveRecharge.mockResolvedValue({ ...pending[0], status: 'approved' })
    api.listFeedback.mockResolvedValue(feedbackList)
    api.updateFeedbackStatus.mockResolvedValue({ ...feedbackList[0], status: 'reviewed' })
    api.getAnalytics.mockResolvedValue(analytics)
    api.listInviteCodes.mockResolvedValue(invites)
    api.createInviteCode.mockResolvedValue({ ...invites[0], id: 4, code: 'OMNIXA-AI-NEW' })
    api.disableInviteCode.mockResolvedValue({ ...invites[0], is_active: false })
  })

  it('shows overview today and 7-day metrics without exposing content', async () => {
    const wrapper = await mountOverview()
    expect(wrapper.text()).toContain('Beta Operations Center')
    expect(wrapper.text()).toContain('今日')
    expect(wrapper.text()).toContain('近 7 天')
    expect(wrapper.text()).toContain('文档处理成功率')
    expect(wrapper.text()).toContain('80%')
    expect(wrapper.text()).toContain('暂不可统计')
    expect(wrapper.text()).not.toContain('hashed_password')
  })

  it('loads users and opens the detail panel with grant form', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[1].trigger('click')
    await flushPromises()

    expect(api.listUsers).toHaveBeenCalled()
    expect(wrapper.text()).toContain('alice')
    await wrapper.findAll('button').find((b) => b.text() === '详情').trigger('click')
    await flushPromises()

    expect(api.getUserDetail).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('用户详情：alice')
    expect(wrapper.text()).toContain('补发 Credits')
  })

  it('grants credits through the form and reflects the new balance', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[1].trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '详情').trigger('click')
    await flushPromises()

    await wrapper.find('.grant-form input[type="number"]').setValue(100)
    await wrapper.find('.grant-form input[type="text"]').setValue('课堂奖励')
    await wrapper.find('.grant-form button[type="submit"]').trigger('submit')
    await flushPromises()

    expect(api.grantCredits).toHaveBeenCalledWith(1, { amount: 100, reason: '课堂奖励', request_id: undefined })
    expect(wrapper.text()).toContain('已补发，当前余额')
  })

  it('requires a second click to approve a recharge request', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[2].trigger('click')
    await flushPromises()

    expect(api.listRechargeRequests).toHaveBeenCalledWith({ status: 'pending' })
    expect(wrapper.text()).toContain('alice')
    // First click only arms the confirm button.
    const approveButton = wrapper.findAll('button').find((b) => b.text() === '批准')
    await approveButton.trigger('click')
    expect(api.approveRecharge).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('再次点击确认')
    // Second click on the explicit confirm executes the approve.
    await wrapper.findAll('button').find((b) => b.text() === '确认批准').trigger('click')
    await flushPromises()
    expect(api.approveRecharge).toHaveBeenCalledWith(9, null)
  })

  it('marks feedback as reviewed', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[3].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('图片发不出去')
    await wrapper.findAll('button').find((b) => b.text() === '标记已读').trigger('click')
    await flushPromises()
    expect(api.updateFeedbackStatus).toHaveBeenCalledWith(5, 'reviewed')
  })

  it('loads analytics for the selected range', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[4].trigger('click')
    await flushPromises()

    expect(api.getAnalytics).toHaveBeenCalledWith('7d')
    expect(wrapper.text()).toContain('注册用户（全部）')
    expect(wrapper.text()).toContain('按模型档位')
  })

  it('creates and disables invite codes', async () => {
    const wrapper = await mountOverview()
    await wrapper.findAll('.admin-tab')[5].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('OMNIXA-AI-ABC')
    await wrapper.find('.invite-form input[type="text"]').setValue('classroom')
    await wrapper.find('.invite-form input[type="number"]').setValue('20')
    await wrapper.find('.invite-form button[type="submit"]').trigger('submit')
    await flushPromises()

    expect(api.createInviteCode).toHaveBeenCalledWith({ channel: 'classroom', max_uses: 20, expires_at: null })
    expect(wrapper.text()).toContain('已创建：OMNIXA-AI-NEW')

    await wrapper.findAll('button').find((b) => b.text() === '关闭').trigger('click')
    await flushPromises()
    expect(api.disableInviteCode).toHaveBeenCalledWith(3)
  })
})
