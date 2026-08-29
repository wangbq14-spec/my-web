import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatView from './ChatView.vue'

const authStore = vi.hoisted(() => ({
  user: { username: 'alice' },
  logout: vi.fn(),
}))
const routerMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
}))

vi.mock('../api/modules/conversation', () => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  updateConversation: vi.fn(),
}))
vi.mock('../api/modules/message', () => ({
  listMessages: vi.fn(),
}))
vi.mock('../api/stream', () => ({
  streamAgent: vi.fn(),
  streamChat: vi.fn(),
  streamRegenerate: vi.fn(),
}))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => authStore,
}))
vi.mock('vue-router', () => ({
  useRouter: () => routerMock,
}))

import {
  deleteConversation,
  listConversations,
  updateConversation,
} from '../api/modules/conversation'
import { listMessages } from '../api/modules/message'
import { streamAgent, streamChat, streamRegenerate } from '../api/stream'

async function mountChat() {
  const wrapper = mount(ChatView)
  await flushPromises()
  return wrapper
}

async function openFirstConversation(wrapper) {
  await wrapper.find('.conversation-item').trigger('click')
  await flushPromises()
}

async function send(wrapper, text) {
  await wrapper.find('.composer-input').setValue(text)
  await wrapper.find('.send-btn').trigger('click')
  await flushPromises()
}

function modeButton(wrapper, label) {
  return wrapper.findAll('.mode-btn').find((button) => button.text() === label)
}

describe('ChatView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    authStore.user = { username: 'alice' }
  })

  it('侧边栏显示退出登录按钮', async () => {
    listConversations.mockResolvedValue([])
    const wrapper = await mountChat()

    expect(wrapper.find('.logout-btn').text()).toBe('退出登录')
  })

  it('点击退出登录会清理认证状态并跳转登录页', async () => {
    listConversations.mockResolvedValue([])
    const wrapper = await mountChat()

    await wrapper.find('.logout-btn').trigger('click')

    expect(authStore.logout).toHaveBeenCalledTimes(1)
    expect(routerMock.replace).toHaveBeenCalledWith('/login')
  })

  it('退出登录按钮位于侧边栏内', async () => {
    listConversations.mockResolvedValue([])
    const wrapper = await mountChat()

    expect(wrapper.find('.sidebar').find('.logout-btn').exists()).toBe(true)
  })

  it('sidebar 显示知识库入口且点击跳转知识库', async () => {
    listConversations.mockResolvedValue([])
    const wrapper = await mountChat()

    const knowledgeButton = wrapper.find('.sidebar .knowledge-nav-btn')
    expect(knowledgeButton.text()).toBe('知识库')
    await knowledgeButton.trigger('click')

    expect(routerMock.push).toHaveBeenCalledWith('/knowledge')
  })

  it('移动端抽屉 sidebar 内同样显示知识库入口', async () => {
    listConversations.mockResolvedValue([])
    const wrapper = await mountChat()
    await wrapper.find('.menu-btn').trigger('click')

    expect(wrapper.find('.sidebar').classes()).toContain('open')
    expect(wrapper.find('.sidebar .knowledge-nav-btn').exists()).toBe(true)
  })

  it('加载 conversation list', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])

    const wrapper = await mountChat()

    expect(listConversations).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('会话一')
  })

  it('切换 conversation 加载 messages', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([{ id: 1, role: 'user', content: '历史消息' }])

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    expect(listMessages).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('历史消息')
  })

  it('send 后立即出现临时 user message 并调用 streamChat', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, '你好')

    expect(wrapper.text()).toContain('你好')
    expect(streamChat).toHaveBeenCalledTimes(1)
    expect(streamChat.mock.calls[0][0].content).toBe('你好')
  })

  it('streaming delta 增量更新同一个 assistant message', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDelta, onDone }) => {
      onDelta({ content: '你' })
      onDelta({ content: '好' })
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    const assistantMessages = wrapper.findAll('.message.assistant')
    expect(assistantMessages.length).toBe(1)
    expect(assistantMessages[0].text()).toContain('你好')
  })

  it('done 后不重复 push user/assistant', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    expect(wrapper.findAll('.message.user').length).toBe(1)
    expect(wrapper.findAll('.message.assistant').length).toBe(1)
  })

  it('streaming 时禁止重复发送', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    await wrapper.find('.composer-input').setValue('again')
    await wrapper
      .find('.composer-input')
      .trigger('keydown', { key: 'Enter', isComposing: false })
    await flushPromises()

    expect(streamChat).toHaveBeenCalledTimes(1)
  })

  it('stop 调用 AbortController.abort()', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    const abortSpy = vi.fn()
    vi.stubGlobal(
      'AbortController',
      class {
        constructor() {
          this.signal = {}
          this.abort = abortSpy
        }
      },
    )
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    await wrapper.find('.send-btn.stop').trigger('click')

    expect(abortSpy).toHaveBeenCalledTimes(1)
  })

  it('Enter 发送', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await wrapper.find('.composer-input').setValue('你好')
    await wrapper
      .find('.composer-input')
      .trigger('keydown', { key: 'Enter', isComposing: false })
    await flushPromises()

    expect(streamChat).toHaveBeenCalledTimes(1)
  })

  it('Shift+Enter 换行不发送', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await wrapper.find('.composer-input').setValue('hi')
    await wrapper
      .find('.composer-input')
      .trigger('keydown', { key: 'Enter', shiftKey: true, isComposing: false })
    await flushPromises()

    expect(streamChat).not.toHaveBeenCalled()
  })

  it('IME composing 时 Enter 不发送', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await wrapper.find('.composer-input').setValue('你好')
    await wrapper
      .find('.composer-input')
      .trigger('keydown', { key: 'Enter', isComposing: true })
    await flushPromises()

    expect(streamChat).not.toHaveBeenCalled()
  })

  it('textarea 自动增长', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    const textarea = wrapper.find('.composer-input')
    Object.defineProperty(textarea.element, 'scrollHeight', {
      value: 120,
      configurable: true,
    })

    await textarea.setValue('第一行\n第二行\n第三行')

    expect(textarea.element.style.height).toBe('120px')
  })

  it('非 streaming 时显示 Send 按钮', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    expect(wrapper.find('.send-btn').exists()).toBe(true)
    expect(wrapper.find('.send-btn.stop').exists()).toBe(false)
  })

  it('streaming 时显示 Stop 按钮', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    expect(wrapper.find('.send-btn.stop').exists()).toBe(true)
  })

  it('empty state 正常显示', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    expect(wrapper.text()).toContain('有什么可以帮你？')
    expect(wrapper.findAll('.suggestion-card').length).toBe(4)
  })

  it('suggestion 点击可填充输入框', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await wrapper.findAll('.suggestion-card')[0].trigger('click')

    expect(wrapper.find('.composer-input').element.value).toBe('帮我解释一段代码')
  })

  it('stopped 状态显示在消息附近', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'abort', message: '已停止生成' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    expect(wrapper.find('.stopped-hint').text()).toContain('已停止生成')
  })

  it('error banner 显示', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'stream', code: 'upstream_error', message: 'LLM 上游服务错误' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await send(wrapper, 'hi')

    expect(wrapper.find('.error-banner').text()).toContain('生成失败，请重试')
  })

  it('active conversation 有 aria-current', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: '会话一' },
      { id: 2, title: '会话二' },
    ])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()
    await wrapper.findAll('.conversation-item')[1].trigger('click')
    await flushPromises()

    const active = wrapper.findAll('.conversation-item')[1]
    expect(active.attributes('aria-current')).toBe('true')
  })

  it('mobile sidebar toggle 基础行为', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '会话一' }])
    listMessages.mockResolvedValue([])

    const wrapper = await mountChat()

    expect(wrapper.find('.sidebar').classes()).not.toContain('open')

    await wrapper.find('.menu-btn').trigger('click')

    expect(wrapper.find('.sidebar').classes()).toContain('open')
  })

  it('defaults to chat mode with 普通 active', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    expect(modeButton(wrapper, '普通').classes()).toContain('active')
    expect(modeButton(wrapper, '普通').attributes('aria-pressed')).toBe('true')
  })

  it('switches to RAG mode and sends streamChat with useRag', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, '知识库').trigger('click')
    await send(wrapper, 'retrieve this')

    expect(modeButton(wrapper, '知识库').classes()).toContain('active')
    expect(streamChat.mock.calls[0][0].useRag).toBe(true)
  })

  it('switches to Agent mode', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    await modeButton(wrapper, 'Agent').trigger('click')

    expect(modeButton(wrapper, 'Agent').classes()).toContain('active')
    expect(modeButton(wrapper, 'Agent').attributes('aria-pressed')).toBe('true')
  })

  it('keeps exactly one mode active', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    for (const label of ['知识库', 'Agent', '普通']) {
      await modeButton(wrapper, label).trigger('click')
      expect(wrapper.findAll('.mode-btn.active')).toHaveLength(1)
      expect(modeButton(wrapper, label).classes()).toContain('active')
    }
  })

  it('sends in Agent mode through streamAgent without streamChat', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamAgent.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'act on this')

    expect(streamAgent).toHaveBeenCalledWith(expect.objectContaining({ content: 'act on this' }))
    expect(streamChat).not.toHaveBeenCalled()
  })

  it('uses the latest tool_start state without adding assistant messages', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamAgent.mockImplementation(async ({ onAgentStep, onToolStart }) => {
      onAgentStep({ step: 'plan' })
      onToolStart({ name: 'calculator' })
      onToolStart({ name: 'knowledge_search' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'use tools')

    const assistantMessages = wrapper.findAllComponents({ name: 'AssistantMessage' })
    expect(assistantMessages).toHaveLength(1)
    expect(assistantMessages[0].props('message')).toMatchObject({
      agentStatus: 'using_tool',
      activeTool: 'knowledge_search',
    })
  })

  it('appends Agent deltas to the assistant content', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamAgent.mockImplementation(async ({ onDelta, onDone }) => {
      onDelta({ content: 'Agent ' })
      onDelta({ content: 'answer' })
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'answer this')

    expect(wrapper.findComponent({ name: 'AssistantMessage' }).props('message').content).toBe('Agent answer')
  })

  it('clears Agent status and active tool after done', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamAgent.mockImplementation(async ({ onAgentStep, onToolStart, onDone }) => {
      onAgentStep({ step: 'plan' })
      onToolStart({ name: 'calculator' })
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'finish this')

    expect(wrapper.findComponent({ name: 'AssistantMessage' }).props('message')).toMatchObject({
      agentStatus: null,
      activeTool: null,
    })
  })

  it('stores streaming sources and delta on the assistant message', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onSources, onDelta, onDone }) => {
      onSources({
        sources: [{ document_id: 1, filename: 'handbook.pdf', chunk_index: 3, score: 0.82, excerpt: 'Relevant excerpt' }],
      })
      onDelta({ content: 'Grounded answer' })
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'retrieve this')

    const assistant = wrapper.findComponent({ name: 'AssistantMessage' })
    expect(assistant.props('message').content).toBe('Grounded answer')
    expect(assistant.props('message').sources).toEqual([
      expect.objectContaining({ filename: 'handbook.pdf', chunk_index: 3 }),
    ])
    expect(wrapper.find('.sources').text()).toContain('handbook.pdf')
  })

  it('shows the existing error banner for a retrieval_error without breaking the UI', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'stream', code: 'retrieval_error' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'retrieve this')

    expect(wrapper.find('.error-banner').text()).toContain('生成失败，请重试')
    expect(wrapper.find('.composer-input').exists()).toBe(true)
  })

  it('stops an Agent stream and ignores later deltas', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    let abortStream
    let callbacks
    vi.stubGlobal(
      'AbortController',
      class {
        constructor() {
          this.signal = {}
        }

        abort() {
          abortStream()
        }
      },
    )
    streamAgent.mockImplementation((handlers) => new Promise((resolve) => {
      callbacks = handlers
      abortStream = () => {
        handlers.onError({ type: 'abort' })
        resolve()
      }
    }))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'stop this')
    await wrapper.find('.send-btn.stop').trigger('click')
    await flushPromises()
    callbacks.onDelta({ content: 'late delta' })
    await flushPromises()

    expect(wrapper.find('.stopped-hint').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('late delta')
  })

  it('retries a failed Agent request through streamAgent', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamAgent
      .mockImplementationOnce(async ({ onError }) => {
        onError({ type: 'stream', code: 'upstream_error' })
      })
      .mockImplementationOnce(async ({ onDone }) => {
        onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
      })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await modeButton(wrapper, 'Agent').trigger('click')
    await send(wrapper, 'retry agent')
    await wrapper.find('.retry-btn').trigger('click')
    await flushPromises()

    expect(streamAgent).toHaveBeenCalledTimes(2)
    expect(streamChat).not.toHaveBeenCalled()
  })

  it('renders the mode selector in the mobile composer', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    const wrapper = await mountChat()
    await openFirstConversation(wrapper)

    expect(wrapper.find('.composer .mode-selector').exists()).toBe(true)
  })

  it('opens the conversation operation menu', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')

    expect(wrapper.find('.conversation-menu').exists()).toBe(true)
    expect(wrapper.findAll('.conversation-menu button')).toHaveLength(2)
  })

  it('closes the operation menu when clicking outside', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    document.body.dispatchEvent(new Event('click', { bubbles: true }))
    await flushPromises()

    expect(wrapper.find('.conversation-menu').exists()).toBe(false)
  })

  it('closes the operation menu with Escape', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.find('.conversation-menu').exists()).toBe(false)
  })

  it('starts renaming with the original title in the input', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Original title' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')

    expect(wrapper.find('.conversation-rename-input').element.value).toBe('Original title')
  })

  it('saves a rename with Enter', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Original title' }])
    updateConversation.mockResolvedValue({ id: 1, title: 'Renamed title' })

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')
    const input = wrapper.find('.conversation-rename-input')
    await input.setValue('Renamed title')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(updateConversation).toHaveBeenCalledWith(1, { title: 'Renamed title' })
    expect(wrapper.find('.conversation-title').text()).toBe('Renamed title')
  })

  it('cancels a rename with Escape without calling the API', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Original title' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')
    const input = wrapper.find('.conversation-rename-input')
    await input.setValue('Do not save')
    await input.trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(updateConversation).not.toHaveBeenCalled()
    expect(wrapper.find('.conversation-title').text()).toBe('Original title')
  })

  it('synchronizes the header after renaming the active conversation', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Original title' }])
    listMessages.mockResolvedValue([])
    updateConversation.mockResolvedValue({ id: 1, title: 'Renamed title' })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')
    const input = wrapper.find('.conversation-rename-input')
    await input.setValue('Renamed title')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.find('.header-title').text()).toBe('Renamed title')
  })

  it('opens the delete confirmation modal', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')

    expect(wrapper.find('.confirm-modal').exists()).toBe(true)
    expect(wrapper.find('.confirm-modal').text()).toContain('删除对话')
    expect(wrapper.find('.confirm-modal').text()).toContain('删除后无法恢复')
  })

  it('cancels deletion without making a request', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.find('.confirm-actions button').trigger('click')

    expect(deleteConversation).not.toHaveBeenCalled()
    expect(wrapper.find('.confirm-modal').exists()).toBe(false)
  })

  it('confirms deletion through deleteConversation', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    deleteConversation.mockResolvedValue()

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(deleteConversation).toHaveBeenCalledWith(1)
  })

  it('switches to the remaining conversation after deleting the active one', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: 'Conversation one' },
      { id: 2, title: 'Conversation two' },
    ])
    listMessages.mockImplementation(async (id) => (
      id === 1 ? [{ id: 1, role: 'user', content: 'Old message' }] : []
    ))
    deleteConversation.mockResolvedValue()

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    expect(wrapper.text()).toContain('Old message')
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.header-title').text()).toBe('Conversation two')
    expect(wrapper.text()).not.toContain('Old message')
    expect(listMessages).toHaveBeenCalledWith(2)
  })

  it('disables rename and delete operations while streaming', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hi')
    await wrapper.find('.conversation-more').trigger('click')

    const actions = wrapper.findAll('.conversation-menu button')
    expect(actions[0].element.disabled).toBe(true)
    expect(actions[1].element.disabled).toBe(true)
  })

  it('opens the conversation menu in the mobile sidebar', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])

    const wrapper = await mountChat()
    await wrapper.find('.menu-btn').trigger('click')
    await wrapper.find('.conversation-more').trigger('click')

    expect(wrapper.find('.sidebar').classes()).toContain('open')
    expect(wrapper.find('.conversation-menu').exists()).toBe(true)
  })

  it('retries with the original content without adding optimistic messages', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat
      .mockImplementationOnce(async ({ onError }) => {
        onError({ type: 'stream', code: 'upstream_error' })
      })
      .mockImplementationOnce(async ({ onDone }) => {
        onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
      })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'retry this')
    await wrapper.find('.retry-btn').trigger('click')
    await flushPromises()

    expect(streamChat).toHaveBeenCalledTimes(2)
    expect(streamChat.mock.calls[1][0].content).toBe('retry this')
    expect(wrapper.findAll('.message.user')).toHaveLength(1)
    expect(wrapper.findAll('.message.assistant')).toHaveLength(1)
  })

  it('shows Retry for a stream error and dismisses the banner', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'stream', code: 'upstream_error' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hi')

    expect(wrapper.find('.error-banner').text()).toContain('生成失败，请重试')
    expect(wrapper.find('.retry-btn').exists()).toBe(true)
    await wrapper.find('.error-close').trigger('click')
    expect(wrapper.find('.error-banner').exists()).toBe(false)
  })

  it('disables Regenerate after a failed send and does not regenerate', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'stream', code: 'upstream_error' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hi')

    const regenerateButton = wrapper.find('.regenerate-btn')
    expect(regenerateButton.exists()).toBe(true)
    expect(regenerateButton.element.disabled).toBe(true)
    await regenerateButton.trigger('click')

    expect(streamRegenerate).not.toHaveBeenCalled()
  })

  it('disables Regenerate while streaming', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([{ id: 1, role: 'assistant', content: 'completed' }])
    streamChat.mockImplementation(() => new Promise(() => {}))

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hi')

    expect(wrapper.find('.regenerate-btn').element.disabled).toBe(true)
  })

  it('regenerates into a new assistant message', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([{ id: 1, role: 'assistant', content: 'completed' }])
    streamRegenerate.mockImplementation(async ({ onDelta, onDone }) => {
      onDelta({ content: 'new answer' })
      onDone({ assistant_message_id: 2, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await wrapper.find('.regenerate-btn').trigger('click')
    await flushPromises()

    expect(streamRegenerate).toHaveBeenCalledWith(expect.objectContaining({ conversationId: 1 }))
    expect(wrapper.findAll('.message.assistant')).toHaveLength(2)
    expect(wrapper.text()).toContain('new answer')
  })
})
