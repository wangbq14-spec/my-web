import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PricingView from './PricingView.vue'

const api = vi.hoisted(() => ({
  getPaymentInfo: vi.fn(),
  getRechargeQuote: vi.fn(),
  submitRecharge: vi.fn(),
  submitCustomRecharge: vi.fn(),
  listRechargeRequests: vi.fn(),
  cancelRechargeRequest: vi.fn(),
}))
vi.mock('../api/modules/recharge', () => api)

const packages = [{ code: 'p1', credits: 1000, amount_display: '¥10' }]
const pendingRequest = {
  id: 1,
  package_code: 'p1',
  credits_requested: 1000,
  amount_display: '¥10',
  status: 'pending',
  note: null,
  created_at: '2026-09-05T08:00:00Z',
}
const customRecharge = {
  enabled: true,
  min_cny: '1',
  max_cny: '500',
  step_cny: '1',
  credit_per_cny: '300',
  pricing_version: 'v1',
}

describe('PricingView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages })
    api.listRechargeRequests.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders packages with amount and credits', async () => {
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.text()).toContain('人工充值')
    expect(wrapper.text()).toContain('¥10')
    expect(wrapper.text()).toContain('1,000 积分')
  })

  it('shows a placeholder instead of an image when no QR is configured', async () => {
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.text()).toContain('当前暂未开放扫码充值')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('renders the QR image when configured', async () => {
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: 'https://example.com/qr.png', packages })
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.get('img').attributes('src')).toBe('https://example.com/qr.png')
  })

  it('shows a success message after submitting a recharge request', async () => {
    api.submitRecharge.mockResolvedValue({ id: 2, status: 'pending' })
    const wrapper = mount(PricingView)
    await flushPromises()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.submitRecharge).toHaveBeenCalledWith({ package_code: 'p1', credits_requested: 1000 })
    expect(wrapper.text()).toContain('充值申请已提交，等待人工审核到账')
  })

  it('shows a cancel action for pending requests', async () => {
    api.listRechargeRequests.mockResolvedValue([pendingRequest])
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.text()).toContain('取消')
  })

  it('renders the custom amount section when enabled', async () => {
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: customRecharge })
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.find('#custom-amount').exists()).toBe(true)
    expect(wrapper.text()).toContain('自定义金额')
    expect(wrapper.text()).toContain('1–500 元')
  })

  it('hides the custom amount section when disabled', async () => {
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: { ...customRecharge, enabled: false } })
    const wrapper = mount(PricingView)
    await flushPromises()

    expect(wrapper.find('#custom-amount').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('自定义金额')
  })

  it('shows estimated credits for a valid custom amount', async () => {
    vi.useFakeTimers()
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: customRecharge })
    api.getRechargeQuote.mockResolvedValue({ amount_cny: '10', credits: 3000, pricing_version: 'v1', expires_at: '2026-09-06T00:00:00' })
    const wrapper = mount(PricingView)
    await flushPromises()

    await wrapper.get('#custom-amount').setValue('10')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(api.getRechargeQuote).toHaveBeenCalledWith('10')
    expect(wrapper.text()).toContain('预计获得：3,000 Credits')
  })

  it('rejects invalid custom amounts without calling the quote API', async () => {
    vi.useFakeTimers()
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: customRecharge })
    const wrapper = mount(PricingView)
    await flushPromises()

    await wrapper.get('#custom-amount').setValue('0')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(wrapper.text()).toContain('金额必须大于 0')
    expect(api.getRechargeQuote).not.toHaveBeenCalled()
    expect(wrapper.get('button.custom-submit').attributes('disabled')).toBeDefined()
  })

  it('rejects over-max and non-numeric amounts with clear errors', async () => {
    vi.useFakeTimers()
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: customRecharge })
    const wrapper = mount(PricingView)
    await flushPromises()

    await wrapper.get('#custom-amount').setValue('9999')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(wrapper.text()).toContain('金额不能超过 500 元')

    await wrapper.get('#custom-amount').setValue('-5')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(wrapper.text()).toContain('请输入有效的金额')

    await wrapper.get('#custom-amount').setValue('abc')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(wrapper.text()).toContain('请输入有效的金额')
    expect(api.getRechargeQuote).not.toHaveBeenCalled()
  })

  it('submits a custom recharge and shows the success message', async () => {
    vi.useFakeTimers()
    api.getPaymentInfo.mockResolvedValue({ qr_image_url: null, packages, custom_recharge: customRecharge })
    api.getRechargeQuote.mockResolvedValue({ amount_cny: '10', credits: 3000, pricing_version: 'v1', expires_at: '' })
    api.submitCustomRecharge.mockResolvedValue({ id: 9, status: 'pending' })
    const wrapper = mount(PricingView)
    await flushPromises()

    await wrapper.get('#custom-amount').setValue('10')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    await wrapper.get('button.custom-submit').trigger('click')
    await flushPromises()

    expect(api.submitCustomRecharge).toHaveBeenCalledWith('10')
    expect(wrapper.text()).toContain('充值申请已提交，等待人工审核到账')
  })
})
