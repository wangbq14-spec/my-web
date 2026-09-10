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

  it('streaming 时显示 companion glyph，而不是 blinking caret', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '文本', isStreaming: true, stopped: false } },
    })

    expect(wrapper.find('.streaming-glyph').exists()).toBe(true)
    expect(wrapper.find('.streaming-glyph').attributes('data-state')).toBe('streaming')
    expect(wrapper.find('.caret').exists()).toBe(false)
    expect(wrapper.find('[data-streaming-anchor]').exists()).toBe(true)
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

  it('uses a dedicated editorial width and a 44px copy touch target', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '正文内容', isStreaming: false, stopped: false } },
    })

    expect(wrapper.find('.assistant-editorial-width').exists()).toBe(true)
    expect(wrapper.find('.reading-prose').exists()).toBe(true)
    expect(wrapper.find('.copy-touch-target').exists()).toBe(true)
  })

  it('shows 已复制 briefly after a successful copy', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: 'content', isStreaming: false, stopped: false } },
    })

    await wrapper.find('.copy-btn').trigger('click')
    expect(wrapper.find('.copy-btn').text()).toBe('已复制')

    await vi.advanceTimersByTimeAsync(1800)
    expect(wrapper.find('.copy-btn').text()).toBe('')
  })

  it('renders collapsed 参考资料 without internal metadata', () => {
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
    expect(wrapper.find('.sources-radius-lg').exists()).toBe(true)
    expect(wrapper.find('.sources-toggle').text()).toContain('参考资料 · 1')
    expect(wrapper.text()).not.toContain('Chunk')
    expect(wrapper.text()).not.toContain('Score')
  })

  it('expands 参考资料 to show document name and excerpt', async () => {
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

    await wrapper.find('.sources-toggle').trigger('click')

    expect(wrapper.find('.sources-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.source-name').text()).toBe('handbook.pdf')
    expect(wrapper.find('.source-item-radius-lg').exists()).toBe(true)
    expect(wrapper.find('.source-excerpt').text()).toContain('Relevant excerpt')
    expect(wrapper.text()).not.toContain('82%')
  })

  it('shows a fallback when a source has no excerpt', async () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: false,
          stopped: false,
          sources: [{ filename: 'handbook.pdf' }],
        },
      },
    })

    await wrapper.find('.sources-toggle').trigger('click')

    expect(wrapper.find('.source-excerpt').text()).toBe('暂无可展示摘录。')
  })

  it('does not show 参考资料 for legacy messages without sources', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: 'Answer', isStreaming: false, stopped: false } },
    })

    expect(wrapper.find('.sources').exists()).toBe(false)
  })

  it('shows the glyph before the first streaming delta without thinking copy', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '', isStreaming: true, stopped: false } },
    })

    expect(wrapper.find('.streaming-glyph').exists()).toBe(true)
    expect(wrapper.find('.thinking-status').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('正在思考')
  })

  it('keeps the glyph while a whitespace-only streaming delta arrives', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '  \n ', isStreaming: true, stopped: false } },
    })

    expect(wrapper.find('.streaming-glyph').exists()).toBe(true)
    expect(wrapper.find('.thinking-status').exists()).toBe(false)
    expect(wrapper.find('[data-streaming-anchor]').classes()).toContain('is-streaming')
    expect(wrapper.find('[data-streaming-anchor]').attributes('data-streaming-anchor-state')).toBe('streaming')
  })

  it('links the brand avatar to the active streaming presence', () => {
    const wrapper = mount(AssistantMessage, {
      props: { message: { content: '文本', isStreaming: true, stopped: false } },
    })

    expect(wrapper.find('.assistant-avatar').exists()).toBe(true)
    expect(wrapper.find('.assistant-avatar').classes()).toContain('is-streaming')
    expect(wrapper.find('.assistant-avatar .brand-mark-svg').exists()).toBe(true)
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

    expect(wrapper.find('.agent-status').text()).toBe('正在计算…')
    expect(wrapper.find('.agent-status').attributes('role')).toBe('status')
    expect(wrapper.find('.streaming-glyph').exists()).toBe(false)
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

    expect(wrapper.find('.agent-status').text()).toBe('正在搜索资料…')
  })

  it.each(['tool_result', 'done'])('hides Agent status for %s', (agentStatus) => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: {
          content: 'Answer',
          isStreaming: true,
          stopped: false,
          agentStatus,
          activeTool: 'calculator',
        },
      },
    })

    expect(wrapper.find('.agent-status').exists()).toBe(false)
    expect(wrapper.find('.streaming-glyph').exists()).toBe(true)
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-inward-breathing')
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

    expect(wrapper.find('.agent-status').text()).toBe('正在分析…')
    expect(wrapper.findComponent({ name: 'MarkdownRenderer' }).text()).toBe('Final answer')
    expect(wrapper.findComponent({ name: 'MarkdownRenderer' }).text()).not.toMatch(/reasoning|chain/i)
    expect(wrapper.text()).not.toMatch(/reasoning|chain/i)
  })
})
