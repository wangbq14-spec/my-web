import { describe, expect, it, vi } from 'vitest'
import http from '../http'
import { uploadAttachment, attachmentError } from './attachments'
vi.mock('../http', () => ({ default: { post: vi.fn() } }))
describe('attachments', () => {
  it('uploads a multipart file', async () => {
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    http.post.mockResolvedValue({ id: 1 })
    expect(await uploadAttachment(file)).toEqual({ id: 1 })
    expect(http.post.mock.calls[0][0]).toBe('/chat/attachments')
    expect(http.post.mock.calls[0][1].get('file')).toBe(file)
  })
  it.each([
    [{ status: 413 }, '图片太大（>10MB）'],
    [{ status: 415 }, '图片格式不支持'],
    [{ status: 402 }, '积分不足，无法继续生成'],
    [{ code: 'vision_not_supported' }, '当前模型不支持图片'],
    [{ code: 'vision_provider_unavailable' }, 'Vision provider 不可用'],
    [{}, '图片上传失败，请重试'],
  ])('explains %j', (error, message) => expect(attachmentError(error)).toBe(message))
})
