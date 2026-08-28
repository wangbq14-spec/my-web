import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarkdownRenderer from './MarkdownRenderer.vue'

function render(content) {
  return mount(MarkdownRenderer, { props: { content } })
}

describe('MarkdownRenderer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('paragraph', () => {
    const wrapper = render('一段文本')
    expect(wrapper.find('p').text()).toBe('一段文本')
  })

  it('bold', () => {
    const wrapper = render('**加粗**')
    expect(wrapper.find('strong').text()).toBe('加粗')
  })

  it('italic', () => {
    const wrapper = render('*斜体*')
    expect(wrapper.find('em').text()).toBe('斜体')
  })

  it('unordered list', () => {
    const wrapper = render('- a\n- b')
    expect(wrapper.findAll('ul li').length).toBe(2)
  })

  it('ordered list', () => {
    const wrapper = render('1. a\n2. b')
    expect(wrapper.findAll('ol li').length).toBe(2)
  })

  it('nested list', () => {
    const wrapper = render('- a\n  - b')
    expect(wrapper.findAll('li').length).toBe(2)
  })

  it('blockquote', () => {
    const wrapper = render('> 引用')
    expect(wrapper.find('blockquote').text()).toBe('引用')
  })

  it('heading', () => {
    const wrapper = render('# 标题')
    expect(wrapper.find('h1').text()).toBe('标题')
  })

  it('inline code', () => {
    const wrapper = render('`code`')
    expect(wrapper.find('code').text()).toBe('code')
  })

  it('fenced code block', () => {
    const wrapper = render('```python\nprint(1)\n```')
    expect(wrapper.find('.code-block pre code').text()).toContain('print(1)')
  })

  it('language label', () => {
    const wrapper = render('```python\nprint(1)\n```')
    expect(wrapper.find('.code-lang').text()).toBe('python')
  })

  it('copy button', () => {
    const wrapper = render('```python\nprint(1)\n```')
    expect(wrapper.find('.code-copy').exists()).toBe(true)
  })

  it('clipboard copy', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const wrapper = render('```python\nprint("hello")\n```')
    await wrapper.find('.code-copy').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('print("hello")')
  })

  it('Copied 状态', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const wrapper = render('```\ncode\n```')
    await wrapper.find('.code-copy').trigger('click')
    await flushPromises()

    expect(wrapper.find('.code-copy').text()).toBe('Copied')
  })

  it('table', () => {
    const wrapper = render('| a | b |\n| - | - |\n| 1 | 2 |')
    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.findAll('th').length).toBe(2)
  })

  it('link target=_blank', () => {
    const wrapper = render('[链接](https://example.com)')
    expect(wrapper.find('a').attributes('target')).toBe('_blank')
  })

  it('link noopener noreferrer', () => {
    const wrapper = render('[链接](https://example.com)')
    expect(wrapper.find('a').attributes('rel')).toBe('noopener noreferrer')
  })

  it('script 被过滤', () => {
    const wrapper = render('<script>alert(1)</script>')
    expect(wrapper.html()).not.toContain('<script')
  })

  it('onerror 被过滤', () => {
    const wrapper = render('<img src=x onerror=alert(1)>')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('javascript href 被过滤', () => {
    const wrapper = render('[x](javascript:alert(1))')
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('半截 Markdown streaming 不崩', () => {
    const wrapper = render('```pyth\nprint(')
    expect(wrapper.find('.markdown').exists()).toBe(true)
  })

  it('后续 chunk 更新正常', async () => {
    const wrapper = render('```pyth\nprint(')
    await wrapper.setProps({ content: '```python\nprint("hi")\n```' })
    expect(wrapper.find('.code-block').exists()).toBe(true)
  })

  it('中文正常', () => {
    const wrapper = render('你好世界 **加粗**')
    expect(wrapper.text()).toContain('你好世界')
    expect(wrapper.find('strong').text()).toBe('加粗')
  })

  it('emoji 正常', () => {
    const wrapper = render('👍🎉')
    expect(wrapper.text()).toContain('👍🎉')
  })

  it('unknown language fallback', () => {
    const wrapper = render('```unknownlang\ncode\n```')
    const code = wrapper.find('.code-block code')
    expect(code.text()).toContain('code')
    expect(wrapper.find('.hljs-keyword').exists()).toBe(false)
  })

  it('长代码不崩', () => {
    const long = 'x'.repeat(1000)
    const wrapper = render(`\`\`\`\n${long}\n\`\`\``)
    expect(wrapper.find('.code-block pre').text()).toContain('x')
  })
})
