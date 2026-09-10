import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AttachmentGallery from './AttachmentGallery.vue'
import http from '../../api/http'

vi.mock('../../api/http', () => ({
  default: { get: vi.fn() },
}))

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('AttachmentGallery', () => {
  beforeEach(() => {
    http.get.mockReset()
  })
  it('loads server images through the authorized http client and renders a thumbnail', async () => {
    // The http interceptor unwraps axios `response.data`, so the call resolves
    // to the Blob directly (NOT `{ data: Blob }`) — mirror production.
    http.get.mockResolvedValue(new Blob(['x'], { type: 'image/png' }))
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [
          { id: 1, original_name: 'a.png', url: '/api/chat/attachments/1' },
        ],
      },
    })
    await flush()
    // The server URL is resolved to an absolute URL (attachmentUrl) so axios
    // does not double-prefix `/api`; assert on the path tail, not the origin.
    expect(http.get).toHaveBeenCalledTimes(1)
    const [calledUrl, calledOpts] = http.get.mock.calls[0]
    expect(calledUrl).toContain('/chat/attachments/1')
    expect(calledOpts).toEqual({ responseType: 'blob' })
    expect(wrapper.findAll('.attachment-thumbnail')).toHaveLength(1)
    expect(wrapper.find('img').attributes('src')).toMatch(/^blob:/)
  })

  it('prefers the local blob preview over the server url after upload resolves', async () => {
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [
          { id: 4, original_name: 'p.png', url: '/api/chat/attachments/4', preview: 'blob:http://x/preview' },
        ],
      },
    })
    await flush()
    expect(http.get).not.toHaveBeenCalled()
    expect(wrapper.find('img').attributes('src')).toBe('blob:http://x/preview')
  })

  it('uses local blob previews directly without a fetch', async () => {
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [{ id: 5, original_name: 'p.png', url: 'blob:http://x/preview' }],
      },
    })
    await flush()
    expect(http.get).not.toHaveBeenCalled()
    expect(wrapper.find('img').attributes('src')).toBe('blob:http://x/preview')
  })

  it('does not hand a raw server URL to the img before it resolves', async () => {
    let resolveBlob
    http.get.mockReturnValue(new Promise((resolve) => { resolveBlob = resolve }))
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [
          { id: 6, original_name: 's.png', url: '/api/chat/attachments/6' },
        ],
      },
    })
    await flush()
    // While the fetch is in flight the img must not point at the unauthenticated URL.
    expect(wrapper.find('img').exists()).toBe(false)
    resolveBlob(new Blob(['x'], { type: 'image/png' }))
    await flush()
    await flush()
    expect(wrapper.find('img').exists()).toBe(true)
    expect(wrapper.find('img').attributes('src')).toMatch(/^blob:/)
  })

  it('shows a lost-image fallback instead of crashing when the fetch or image fails', async () => {
    http.get.mockRejectedValue(new Error('401'))
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [{ id: 7, original_name: 'gone.png', url: '/api/chat/attachments/7' }],
      },
    })
    await flush()
    expect(wrapper.text()).toContain('图片已失效')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('.attachment-lost').exists()).toBe(true)
  })

  it('never fetches a cross-origin attachment URL (no bearer-token exfiltration)', async () => {
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [{ id: 8, original_name: 'evil.png', url: 'https://evil.example.com/steal' }],
      },
    })
    await flush()
    expect(http.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('图片已失效')
  })

  it('does not re-fetch while a server image is already loading', async () => {
    let resolveBlob
    http.get.mockReturnValue(new Promise((resolve) => { resolveBlob = resolve }))
    const wrapper = mount(AttachmentGallery, {
      props: {
        attachments: [{ id: 9, original_name: 'x.png', url: '/api/chat/attachments/9' }],
      },
    })
    await flush()
    expect(http.get).toHaveBeenCalledTimes(1)
    // Re-trigger the deep watcher with an equal item; the in-flight guard
    // must skip the duplicate fetch.
    await wrapper.setProps({ attachments: [{ id: 9, original_name: 'x.png', url: '/api/chat/attachments/9' }] })
    await flush()
    expect(http.get).toHaveBeenCalledTimes(1)
    resolveBlob(new Blob(['x'], { type: 'image/png' }))
    await flush()
    await flush()
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('opens the lightbox on click and closes on cancel', async () => {
    const wrapper = mount(AttachmentGallery, {
      props: { attachments: [{ id: 3, original_name: 'c.png', url: 'blob:http://x/c' }] },
    })
    const showModal = vi.fn()
    const close = vi.fn()
    wrapper.find('dialog').element.showModal = showModal
    wrapper.find('dialog').element.close = close
    await wrapper.find('.attachment-thumbnail').trigger('click')
    expect(showModal).toHaveBeenCalled()
    await wrapper.find('dialog').trigger('cancel')
    expect(close).toHaveBeenCalled()
  })
})
