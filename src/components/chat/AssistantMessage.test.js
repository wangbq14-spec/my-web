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

  it('shows Sources with filename and Chunk number', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: false,
          stopped: false,
          sources: [{ document_id: 1, filename: 'handbook.pdf', chunk_index: 3, score: 0.82 }],
        },
      },
    })

    expect(wrapper.find('.sources').exists()).toBe(true)
    expect(wrapper.find('.source-toggle').text()).toContain('1. handbook.pdf · Chunk 3')
  })

  it('expands a source to show its excerpt', async () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: false,
          stopped: false,
          sources: [{ filename: 'handbook.pdf', chunk_index: 3, score: 0.82, excerpt: 'Relevant excerpt' }],
        },
      },
    })

    await wrapper.find('.source-toggle').trigger('click')

    expect(wrapper.find('.source-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.source-detail').text()).toContain('Relevant excerpt')
    expect(wrapper.find('.source-detail').text()).toContain('82%')
  })

  it('does not show Sources for legacy messages without sources', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: 'Answer', isStreaming: false, stopped: false } },
    })

    expect(wrapper.find('.sources').exists()).toBe(false)
  })

  it('shows the calculator Agent status', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: true,
          stopped: false,
          agentStatus: 'using_tool',
          activeTool: 'calculator',
        },
      },
    })

    expect(wrapper.find('.agent-status').text()).toBe('⌕ 正在计算…')
  })

  it('shows the knowledge search Agent status', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: true,
          stopped: false,
          agentStatus: 'using_tool',
          activeTool: 'knowledge_search',
        },
      },
    })

    expect(wrapper.find('.agent-status').text()).toBe('⌕ 正在搜索知识库…')
  })

  it('keeps Agent status outside Markdown without rendering reasoning text', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: '**Final answer**',
          isStreaming: true,
          stopped: false,
          agentStatus: 'thinking',
          activeTool: null,
          reasoning: 'private reasoning chain',
        },
      },
    })

    expect(wrapper.find('.agent-status').text()).toBe('✦ 正在分析…')
    expect(wrapper.findComponent({ name: 'MarkdownRenderer' }).text()).toBe('Final answer')
    expect(wrapper.findComponent({ name: 'MarkdownRenderer' }).text()).not.toMatch(/reasoning|chain/i)
    expect(wrapper.text()).not.toMatch(/reasoning|chain/i)
  })
})
