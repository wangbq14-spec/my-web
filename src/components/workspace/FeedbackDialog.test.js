import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FeedbackDialog from './FeedbackDialog.vue'
import { submitFeedback } from '../../api/modules/feedback'

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/chat' }),
}))
vi.mock('../../api/modules/feedback', () => ({
  submitFeedback: vi.fn(),
}))

describe('FeedbackDialog', () => {
  beforeEach(() => {
    submitFeedback.mockReset()
    submitFeedback.mockResolvedValue({})
  })

  it('requires a message before submitting', async () => {
    const wrapper = mount(FeedbackDialog, { props: { modelValue: true } })
    await wrapper.find('.submit').trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toBe('请填写反馈内容')
    expect(submitFeedback).not.toHaveBeenCalled()
  })

  it('submits the feedback and shows the thank-you state', async () => {
    const wrapper = mount(FeedbackDialog, { props: { modelValue: true } })
    await wrapper.find('#feedback-message').setValue('聊天记录无法加载')
    await wrapper.find('.submit').trigger('click')
    await flushPromises()
    expect(submitFeedback).toHaveBeenCalledWith({
      type: 'suggestion',
      path: '/chat',
      message: '聊天记录无法加载',
    })
    expect(wrapper.text()).toContain('感谢反馈')
  })

  it('surfaces a submit error', async () => {
    submitFeedback.mockRejectedValue({ message: '反馈提交失败' })
    const wrapper = mount(FeedbackDialog, { props: { modelValue: true } })
    await wrapper.find('#feedback-message').setValue('测试')
    await wrapper.find('.submit').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('反馈提交失败')
  })
})
