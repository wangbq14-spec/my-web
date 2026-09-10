import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UsageView from './UsageView.vue'

const api = vi.hoisted(() => ({ getBalance: vi.fn(), listUsage: vi.fn() }))
vi.mock('../api/modules/usage', () => api)

const records = [{ provider: 'OpenAI', model: 'gpt-5', model_tier: 'deep', prompt_tokens: 120, completion_tokens: 30, total_tokens: 150, credits_charged: 12, created_at: '2026-09-05T08:00:00Z' }]

describe('UsageView', () => {
  beforeEach(() => { vi.clearAllMocks(); api.getBalance.mockResolvedValue({ balance: 988 }); api.listUsage.mockResolvedValue(records) })

  it('renders balance, total spending, tier, tokens, and credits', async () => {
    const wrapper = mount(UsageView)
    await flushPromises()
    expect(wrapper.text()).toContain('988')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('深度思考')
    expect(wrapper.text()).toContain('120 / 30 / 150')
    expect(wrapper.text()).toContain('OpenAI')
  })

  it('renders empty and retryable error states', async () => {
    api.listUsage.mockResolvedValueOnce([])
    const empty = mount(UsageView)
    await flushPromises()
    expect(empty.text()).toContain('暂无使用记录')

    api.getBalance.mockRejectedValueOnce(new Error('network'))
    const failed = mount(UsageView)
    await flushPromises()
    expect(failed.text()).toContain('用量加载失败')
    api.getBalance.mockResolvedValueOnce({ balance: 1 })
    api.listUsage.mockResolvedValueOnce([])
    await failed.get('button').trigger('click')
    await flushPromises()
    expect(api.getBalance).toHaveBeenCalledTimes(3)
  })
})
