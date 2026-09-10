import { describe, expect, it, vi } from 'vitest'
import { submitFeedback } from './feedback'
import http from '../http'

vi.mock('../http', () => ({
  default: { post: vi.fn() },
}))

describe('feedback api', () => {
  it('posts feedback to /feedback', () => {
    http.post.mockResolvedValue({})
    submitFeedback({ type: 'bug', path: '/chat', message: '出错了' })
    expect(http.post).toHaveBeenCalledWith('/feedback', {
      type: 'bug', path: '/chat', message: '出错了',
    })
  })
})
