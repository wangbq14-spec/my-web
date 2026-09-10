import { describe, expect, it } from 'vitest'
import { createSSEParser } from './sse'

function parseAll(chunks) {
  const parse = createSSEParser()
  const events = []
  for (const chunk of chunks) {
    for (const event of parse(chunk)) {
      events.push(event)
    }
  }
  return events
}

describe('SSE parser', () => {
  it('解析单个事件', () => {
    const events = parseAll(['event: delta\ndata: {"content":"你"}\n\n'])

    expect(events).toEqual([{ event: 'delta', data: { content: '你' } }])
  })

  it('解析一个 chunk 内多个事件', () => {
    const chunk =
      'event: delta\ndata: {"content":"你"}\n\n' +
      'event: delta\ndata: {"content":"好"}\n\n' +
      'event: done\ndata: {"id":1}\n\n'

    const events = parseAll([chunk])

    expect(events.map((e) => e.event)).toEqual(['delta', 'delta', 'done'])
  })

  it('处理跨 chunk 拆分的 event', () => {
    const events = parseAll(['event: delta\ndata: {"content":"你', '好"}\n\n'])

    expect(events).toEqual([{ event: 'delta', data: { content: '你好' } }])
  })

  it('正确处理中文 delta', () => {
    const events = parseAll(['event: delta\ndata: {"content":"你好世界"}\n\n'])

    expect(events[0].data.content).toBe('你好世界')
  })

  it('正确处理 emoji delta', () => {
    const events = parseAll(['event: delta\ndata: {"content":"👍🎉"}\n\n'])

    expect(events[0].data.content).toBe('👍🎉')
  })
})
