import { createSSEParser } from '../utils/sse'
import { getAccessToken } from '../utils/token'

function buildUrl(conversationId, path) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  return `${baseURL}/conversations/${conversationId}/${path}`
}

async function streamRequest({
  conversationId,
  path,
  body,
  signal,
  onStart,
  onAgentStep,
  onToolStart,
  onToolResult,
  onDelta,
  onSources,
  onDone,
  onError,
}) {
  const token = getAccessToken()
  const headers = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(buildUrl(conversationId, path), {
      method: 'POST',
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      onError?.({ type: 'abort', message: '已停止生成' })
    } else {
      onError?.({ type: 'network', message: '网络连接失败' })
    }
    return
  }

  if (!response.ok) {
    let message = '请求失败'
    try {
      const body = await response.json()
      message = body?.detail || body?.message || message
    } catch {
      // 忽略响应体解析失败
    }
    onError?.({ type: 'http', status: response.status, message })
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parse = createSSEParser()

  const dispatch = (event) => {
    switch (event.event) {
      case 'start':
        onStart?.(event.data)
        break
      case 'agent_step':
        onAgentStep?.(event.data)
        break
      case 'tool_start':
        onToolStart?.(event.data)
        break
      case 'tool_result':
        onToolResult?.(event.data)
        break
      case 'delta':
        onDelta?.(event.data)
        break
      case 'sources':
        onSources?.(event.data)
        break
      case 'done':
        onDone?.(event.data)
        break
      case 'error':
        onError?.({
          type: 'stream',
          code: event.data?.code,
          message: event.data?.message || '生成失败',
        })
        break
      default:
        break
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      const text = decoder.decode(value, { stream: true })
      for (const event of parse(text)) {
        dispatch(event)
      }
    }
    const tail = decoder.decode()
    if (tail) {
      for (const event of parse(tail)) {
        dispatch(event)
      }
    }
  } catch (error) {
    if (error?.name === 'AbortError') {
      onError?.({ type: 'abort', message: '已停止生成' })
    } else {
      onError?.({ type: 'network', message: '流传输中断' })
    }
  }
}

export function streamAgent({
  conversationId,
  content,
  signal,
  onStart,
  onAgentStep,
  onToolStart,
  onToolResult,
  onDelta,
  onDone,
  onError,
}) {
  return streamRequest({
    conversationId,
    path: 'agent/stream',
    body: { content },
    signal,
    onStart,
    onAgentStep,
    onToolStart,
    onToolResult,
    onDelta,
    onDone,
    onError,
  })
}

export function streamChat({
  conversationId,
  content,
  useRag = false,
  topK = 5,
  signal,
  onStart,
  onDelta,
  onSources,
  onDone,
  onError,
}) {
  const body = useRag ? { content, use_rag: true, top_k: topK } : { content }
  return streamRequest({
    conversationId,
    path: 'chat/stream',
    body,
    signal,
    onStart,
    onDelta,
    onSources,
    onDone,
    onError,
  })
}

export function streamRegenerate({
  conversationId,
  signal,
  onStart,
  onDelta,
  onSources,
  onDone,
  onError,
}) {
  return streamRequest({
    conversationId,
    path: 'regenerate/stream',
    signal,
    onStart,
    onDelta,
    onSources,
    onDone,
    onError,
  })
}
