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
  createConversation,
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

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
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

    const wrapper = mount(ChatView, { attachTo: document.body })
    await flushPromises()
    const menuTrigger = wrapper.find('.conversation-more')
    await menuTrigger.trigger('click')
    expect(document.activeElement).toBe(wrapper.find('.conversation-menu button').element)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.find('.conversation-menu').exists()).toBe(false)
    expect(document.activeElement).toBe(menuTrigger.element)
    wrapper.unmount()
  })

  it('does not let a stale message request overwrite the newly selected conversation', async () => {
    const firstRequest = deferred()
    const secondRequest = deferred()
    listConversations.mockResolvedValue([
      { id: 1, title: 'Conversation one' },
      { id: 2, title: 'Conversation two' },
    ])
    listMessages
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise)

    const wrapper = await mountChat()
    const conversations = wrapper.findAll('.conversation-item')
    await conversations[0].trigger('click')
    await conversations[1].trigger('click')
    secondRequest.resolve([{ id: 2, role: 'assistant', content: 'Current conversation' }])
    await flushPromises()
    firstRequest.resolve([{ id: 1, role: 'assistant', content: 'Stale conversation' }])
    await flushPromises()

    expect(wrapper.text()).toContain('Current conversation')
    expect(wrapper.text()).not.toContain('Stale conversation')
  })

  it('does not leave message loading active when creating a conversation invalidates an older request', async () => {
    const oldRequest = deferred()
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockReturnValue(oldRequest.promise)
    createConversation.mockResolvedValue({ id: 2, title: 'New conversation' })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    expect(wrapper.find('.skeleton-message').exists()).toBe(true)

    await wrapper.find('.new-btn').trigger('click')
    await flushPromises()
    oldRequest.resolve([{ id: 1, role: 'assistant', content: 'Stale message' }])
    await flushPromises()

    expect(wrapper.find('.skeleton-message').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Stale message')
  })

  it('aborts an in-flight stream before creating a conversation and allows the new conversation to send', async () => {
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
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation A' }])
    listMessages.mockResolvedValue([])
    createConversation.mockResolvedValue({ id: 2, title: 'New conversation' })
    let oldCallbacks
    streamChat.mockImplementation((handlers) => {
      if (!oldCallbacks) oldCallbacks = handlers
      return new Promise(() => {})
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'first request')
    await wrapper.find('.new-btn').trigger('click')
    await flushPromises()

    expect(abortSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.send-btn.stop').exists()).toBe(false)

    await send(wrapper, 'new request')
    expect(streamChat).toHaveBeenCalledTimes(2)

    oldCallbacks.onDelta({ content: 'late output' })
    oldCallbacks.onSources({ sources: [{ filename: 'stale.pdf' }] })
    oldCallbacks.onDone({ user_message_id: 1, assistant_message_id: 2, model: 'm' })
    oldCallbacks.onError({ type: 'stream' })
    await flushPromises()

    expect(wrapper.text()).not.toContain('late output')
    expect(wrapper.text()).not.toContain('stale.pdf')
    expect(wrapper.find('.error-banner').exists()).toBe(false)
  })

  it('ignores streaming callbacks after switching conversations', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: 'Conversation one' },
      { id: 2, title: 'Conversation two' },
    ])
    listMessages.mockResolvedValue([])
    let callbacks
    streamChat.mockImplementation((handlers) => {
      callbacks = handlers
      return new Promise(() => {})
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hello')
    await wrapper.findAll('.conversation-item')[1].trigger('click')
    await flushPromises()

    callbacks.onDelta({ content: 'late delta' })
    callbacks.onDone({ user_message_id: 1, assistant_message_id: 2, model: 'm' })
    callbacks.onError({ type: 'stream' })
    await flushPromises()

    expect(wrapper.text()).not.toContain('late delta')
    expect(wrapper.find('.error-banner').exists()).toBe(false)
    expect(listConversations).toHaveBeenCalledTimes(1)
  })

  it('aborts and ignores an old stream after switching from A to B and back to A', async () => {
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
    listConversations.mockResolvedValue([
      { id: 1, title: 'Conversation A' },
      { id: 2, title: 'Conversation B' },
    ])
    listMessages.mockResolvedValue([])
    let callbacks
    streamChat.mockImplementation((handlers) => {
      callbacks = handlers
      return new Promise(() => {})
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hello')
    await wrapper.findAll('.conversation-item')[1].trigger('click')
    await flushPromises()
    await wrapper.findAll('.conversation-item')[0].trigger('click')
    await flushPromises()

    callbacks.onDelta({ content: 'stale A delta' })
    callbacks.onDone({ user_message_id: 1, assistant_message_id: 2, model: 'm' })
    callbacks.onError({ type: 'stream' })
    await flushPromises()

    expect(abortSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('stale A delta')
    expect(wrapper.find('.error-banner').exists()).toBe(false)
  })

  it('aborts and ignores streaming callbacks after unmount', async () => {
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
    listConversations.mockResolvedValue([{ id: 1, title: 'Conversation one' }])
    listMessages.mockResolvedValue([])
    let callbacks
    streamChat.mockImplementation((handlers) => {
      callbacks = handlers
      return new Promise(() => {})
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'hello')
    wrapper.unmount()

    callbacks.onDelta({ content: 'late delta' })
    callbacks.onDone({ user_message_id: 1, assistant_message_id: 2, model: 'm' })
    callbacks.onError({ type: 'stream' })
    await flushPromises()

    expect(abortSpy).toHaveBeenCalledTimes(1)
    expect(listConversations).toHaveBeenCalledTimes(1)
  })

  it('ignores regeneration when the retry context belongs to a different conversation', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: 'Conversation one' },
      { id: 2, title: 'Conversation two' },
    ])
    listMessages.mockImplementation(async (id) => (
      id === 2 ? [{ id: 2, role: 'assistant', content: 'Completed response' }] : []
    ))
    streamChat.mockImplementation(async ({ onError }) => {
      onError({ type: 'stream' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, 'failed request')
    await wrapper.findAll('.conversation-item')[1].trigger('click')
    await flushPromises()
    await wrapper.find('.regenerate-btn').trigger('click')

    expect(streamRegenerate).not.toHaveBeenCalled()
  })

  it('refreshes the conversation list and selects the next conversation after a 404 delete', async () => {
    listConversations
      .mockResolvedValueOnce([
        { id: 1, title: 'Conversation one' },
        { id: 2, title: 'Conversation two' },
      ])
      .mockResolvedValueOnce([{ id: 2, title: 'Conversation two' }])
    listMessages.mockResolvedValue([])
    deleteConversation.mockRejectedValue({ status: 404 })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.conversation-title')).toHaveLength(1)
    expect(wrapper.find('.conversation-title').text()).toBe('Conversation two')
    expect(wrapper.find('.conversation-item').attributes('aria-current')).toBe('true')
    expect(listMessages).toHaveBeenCalledWith(2)
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
    expect(wrapper.find('.confirm-modal').text()).toContain('删除后，该对话及其消息将无法恢复。')
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

describe('ChatView conversation management contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    authStore.user = { username: 'alice' }
  })

  it('shows a conversation-list loading state while the first request is pending', async () => {
    const request = deferred()
    listConversations.mockReturnValue(request.promise)

    const wrapper = mount(ChatView)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.skeleton-list').exists()).toBe(true)
  })

  it('shows “还没有对话” when the loaded conversation list is empty', async () => {
    listConversations.mockResolvedValue([])

    const wrapper = await mountChat()

    expect(wrapper.find('.sidebar-hint').text()).toBe('还没有对话')
  })

  it('shows “会话加载失败” when the initial conversation request fails', async () => {
    listConversations.mockRejectedValue(new Error('会话加载失败'))

    const wrapper = await mountChat()

    expect(wrapper.find('.sidebar-load-error').text()).toContain('会话加载失败')
  })

  it('retries loading conversations after a list failure', async () => {
    listConversations
      .mockRejectedValueOnce(new Error('会话加载失败'))
      .mockResolvedValueOnce([{ id: 1, title: '重试后的会话' }])

    const wrapper = await mountChat()
    await wrapper.find('.sidebar-load-error button').trigger('click')
    await flushPromises()

    expect(listConversations).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('重试后的会话')
  })

  it('filters conversations locally by title when searching', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: '项目计划' },
      { id: 2, title: '读书笔记' },
    ])

    const wrapper = await mountChat()
    await wrapper.find('#conversation-search').setValue('项目')

    expect(wrapper.text()).toContain('项目计划')
    expect(wrapper.text()).not.toContain('读书笔记')
    expect(listConversations).toHaveBeenCalledTimes(1)
  })

  it('shows “没有找到相关对话” when a title search has no match', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '项目计划' }])

    const wrapper = await mountChat()
    await wrapper.find('#conversation-search').setValue('不存在')

    expect(wrapper.find('.sidebar-hint').text()).toBe('没有找到相关对话')
  })

  it('creates a conversation and makes it active', async () => {
    listConversations.mockResolvedValue([])
    createConversation.mockResolvedValue({ id: 7, title: '新对话' })

    const wrapper = await mountChat()
    await wrapper.find('.new-btn').trigger('click')
    await flushPromises()

    expect(createConversation).toHaveBeenCalledWith({ title: '新对话' })
    expect(wrapper.find('.conversation-item').attributes('aria-current')).toBe('true')
    expect(wrapper.find('.header-title').text()).toBe('新对话')
  })

  it('only creates one conversation for a rapid double click', async () => {
    const request = deferred()
    listConversations.mockResolvedValue([])
    createConversation.mockReturnValue(request.promise)

    const wrapper = await mountChat()
    const createButton = wrapper.find('.new-btn')
    await createButton.trigger('click')
    await createButton.trigger('click')

    expect(createConversation).toHaveBeenCalledTimes(1)

    request.resolve({ id: 7, title: '新对话' })
    await flushPromises()
  })

  it('restores the original title and reports a safe error when rename fails', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '原标题' }])
    updateConversation.mockRejectedValue(new Error('重命名会话失败'))

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')
    const input = wrapper.find('.conversation-rename-input')
    await input.setValue('失败的新标题')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.find('.conversation-title').text()).toBe('原标题')
    expect(wrapper.find('.error-banner').text()).toContain('重命名会话失败')
  })

  it('saves a rename on blur', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '原标题' }])
    updateConversation.mockResolvedValue({ id: 1, title: '失焦后的标题' })

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.find('.conversation-menu button').trigger('click')
    const input = wrapper.find('.conversation-rename-input')
    await input.setValue('失焦后的标题')
    await input.trigger('blur')
    await flushPromises()

    expect(updateConversation).toHaveBeenCalledWith(1, { title: '失焦后的标题' })
    expect(wrapper.find('.conversation-title').text()).toBe('失焦后的标题')
  })

  it('opens a delete modal with the irreversible-message warning', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '对话一' }])

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')

    expect(wrapper.find('.confirm-modal').text()).toContain('删除后，该对话及其消息将无法恢复。')
  })

  it('removes the conversation from the list after a successful delete', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '对话一' }])
    deleteConversation.mockResolvedValue()

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.conversation-row').exists()).toBe(false)
  })

  it('keeps the item and shows a safe error when deletion fails', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '对话一' }])
    deleteConversation.mockRejectedValue(new Error('删除会话失败'))

    const wrapper = await mountChat()
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.conversation-title').text()).toBe('对话一')
    expect(wrapper.find('.error-banner').text()).toContain('删除会话失败')
  })

  it('clears the active conversation when deleting the final conversation', async () => {
    listConversations.mockResolvedValue([{ id: 1, title: '对话一' }])
    listMessages.mockResolvedValue([])
    deleteConversation.mockResolvedValue()

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await wrapper.find('.conversation-more').trigger('click')
    await wrapper.findAll('.conversation-menu button')[1].trigger('click')
    await wrapper.findAll('.confirm-actions button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.header-title').text()).toBe('新对话')
    expect(wrapper.find('.composer-wrap').exists()).toBe(false)
  })

  it('renders conversations in descending updated_at order', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: '较早', updated_at: '2026-08-01T08:00:00Z' },
      { id: 2, title: '最新', updated_at: '2026-08-29T08:00:00Z' },
    ])

    const wrapper = await mountChat()

    expect(wrapper.findAll('.conversation-title').map((item) => item.text())).toEqual(['最新', '较早'])
  })

  it('breaks equal updated_at ties by descending id', async () => {
    listConversations.mockResolvedValue([
      { id: 1, title: 'Older id', updated_at: '2026-08-29T08:00:00Z' },
      { id: 2, title: 'Newer id', updated_at: '2026-08-29T08:00:00Z' },
    ])

    const wrapper = await mountChat()

    expect(wrapper.findAll('.conversation-title').map((item) => item.text())).toEqual([
      'Newer id',
      'Older id',
    ])
  })

  it('refreshes and moves the active conversation to the top after a successful send', async () => {
    listConversations
      .mockResolvedValueOnce([
        { id: 1, title: '当前对话', updated_at: '2026-08-01T08:00:00Z' },
        { id: 2, title: '另一对话', updated_at: '2026-08-29T08:00:00Z' },
      ])
      .mockResolvedValueOnce([
        { id: 1, title: '当前对话', updated_at: '2026-08-30T08:00:00Z' },
        { id: 2, title: '另一对话', updated_at: '2026-08-29T08:00:00Z' },
      ])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, '发送后置顶')

    expect(listConversations).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.conversation-title')[0].text()).toBe('当前对话')
  })

  it('refreshes the automatic title after the first successful response', async () => {
    listConversations
      .mockResolvedValueOnce([{ id: 1, title: '新建对话' }])
      .mockResolvedValueOnce([{ id: 1, title: '帮我规划周末行程' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, '帮我规划周末行程')

    expect(wrapper.find('.conversation-title').text()).toBe('帮我规划周末行程')
    expect(wrapper.find('.header-title').text()).toBe('帮我规划周末行程')
  })

  it('does not let an older list response overwrite a newer refresh', async () => {
    const oldRefresh = deferred()
    listConversations
      .mockResolvedValueOnce([{ id: 1, title: '初始列表' }])
      .mockReturnValueOnce(oldRefresh.promise)
      .mockResolvedValueOnce([{ id: 2, title: '最新列表' }])
    listMessages.mockResolvedValue([])
    streamChat.mockImplementation(async ({ onDone }) => {
      onDone({ user_message_id: 10, assistant_message_id: 11, model: 'm' })
    })

    const wrapper = await mountChat()
    await openFirstConversation(wrapper)
    await send(wrapper, '第一次发送')
    await send(wrapper, '第二次发送')
    oldRefresh.resolve([{ id: 1, title: '过期列表' }])
    await flushPromises()

    expect(wrapper.text()).toContain('最新列表')
    expect(wrapper.text()).not.toContain('过期列表')
  })

  it('allows creating a conversation from the mobile drawer', async () => {
    listConversations.mockResolvedValue([])
    createConversation.mockResolvedValue({ id: 7, title: '移动端对话' })

    const wrapper = await mountChat()
    await wrapper.find('.menu-btn').trigger('click')
    await wrapper.find('.sidebar.open .new-btn').trigger('click')
    await flushPromises()

    expect(createConversation).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.sidebar').classes()).not.toContain('open')
    expect(wrapper.find('.header-title').text()).toBe('移动端对话')
  })
})
