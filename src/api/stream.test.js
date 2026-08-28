import { beforeEach, describe, expect, it, vi } from 'vitest'
import { streamChat, streamRegenerate } from './stream'

function encode(text) {
  return new TextEncoder().encode(text)
}

function createFakeStream(chunks) {
  const encoded = chunks.map(encode)
  let i = 0
  return {
    ok: true,
    status: 200,
    async json() {
      return {}
    },
    body: {
      getReader() {
        return {
          async read() {
            if (i < encoded.length) {
              return { done: false, value: encoded[i++] }
            }
            return { done: true, value: undefined }
          },
        }
      },
    },
  }
}

describe('streamChat', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('access_token', 'test-token')
    vi.unstubAllGlobals()
  })

  it('使用 POST 且 body 正确', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(createFakeStream(['event: done\ndata: {}\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    await streamChat({ conversationId: 1, content: '你好' })

    const [url, options] = fetchMock.mock.calls[0]
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(url).toContain('/conversations/1/chat/stream')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ content: '你好' })
  })

  it('带 Authorization header', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(createFakeStream(['event: done\ndata: {}\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    await streamChat({ conversationId: 1, content: 'hi' })

    const [, options] = fetchMock.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer test-token')
  })

  it('start/delta/done callbacks 正确触发', async () => {
    const sse =
      'event: start\ndata: {"conversation_id":1}\n\n' +
      'event: delta\ndata: {"content":"你"}\n\n' +
      'event: delta\ndata: {"content":"好"}\n\n' +
      'event: done\ndata: {"user_message_id":1,"assistant_message_id":2}\n\n'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createFakeStream([sse])))

    const onStart = vi.fn()
    const onDelta = vi.fn()
    const onDone = vi.fn()

    await streamChat({ conversationId: 1, content: 'hi', onStart, onDelta, onDone })

    expect(onStart).toHaveBeenCalledWith({ conversation_id: 1 })
    expect(onDelta.mock.calls.map((c) => c[0].content)).toEqual(['你', '好'])
    expect(onDone).toHaveBeenCalledWith({
      user_message_id: 1,
      assistant_message_id: 2,
    })
  })

  it('error event 正确转换', async () => {
    const sse = 'event: error\ndata: {"code":"upstream_error","message":"boom"}\n\n'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(createFakeStream([sse])))

    const onError = vi.fn()
    await streamChat({ conversationId: 1, content: 'hi', onError })

    expect(onError).toHaveBeenCalledWith({
      type: 'stream',
      code: 'upstream_error',
      message: 'boom',
    })
  })

  it('HTTP 非 2xx 走 http error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        async json() {
          return { detail: '会话不存在' }
        },
      }),
    )

    const onError = vi.fn()
    await streamChat({ conversationId: 1, content: 'hi', onError })

    expect(onError).toHaveBeenCalledWith({
      type: 'http',
      status: 404,
      message: '会话不存在',
    })
  })

  it('AbortError 不转换为 upstream error', async () => {
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    const onError = vi.fn()
    await streamChat({ conversationId: 1, content: 'hi', onError })

    expect(onError).toHaveBeenCalledWith({ type: 'abort', message: '已停止生成' })
  })
})

describe('streamRegenerate', () => {
  it('posts without a body and dispatches done data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      createFakeStream(['event: done\ndata: {"assistant_message_id":2,"model":"m"}\n\n']),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onDone = vi.fn()

    await streamRegenerate({ conversationId: 1, onDone })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toContain('/conversations/1/regenerate/stream')
    expect(options.body).toBeUndefined()
    expect(onDone).toHaveBeenCalledWith({ assistant_message_id: 2, model: 'm' })
  })
})
