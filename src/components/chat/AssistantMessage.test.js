import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AssistantMessage from './AssistantMessage.vue'

describe('AssistantMessage', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('渲染 Markdown', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '**加粗** 文本', isStreaming: false, stopped: false } },
    })

    expect(wrapper.find('strong').text()).toBe('加粗')
  })

  it('streaming 时显示 caret', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '文本', isStreaming: true, stopped: false } },
    })

    expect(wrapper.find('.caret').exists()).toBe(true)
  })

  it('stopped 时仍显示已有 Markdown 与提示', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '**已有内容**', isStreaming: false, stopped: true } },
    })

    expect(wrapper.find('strong').text()).toBe('已有内容')
    expect(wrapper.find('.stopped-hint').text()).toContain('已停止生成')
  })

  it('copies the original Markdown content', async () => {
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '**raw markdown**', isStreaming: false, stopped: false } },
    })

    await wrapper.find('.copy-btn').trigger('click')

    expect(writeText).toHaveBeenCalledWith('**raw markdown**')
  })

  it('shows Copied briefly after a successful copy', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: 'content', isStreaming: false, stopped: false } },
    })

    await wrapper.find('.copy-btn').trigger('click')
    expect(wrapper.find('.copy-btn').text()).toBe('Copied')

    await vi.advanceTimersByTimeAsync(1800)
    expect(wrapper.find('.copy-btn').text()).toBe('Copy')
  })
})
