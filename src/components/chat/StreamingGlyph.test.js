import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import StreamingGlyph from './StreamingGlyph.vue'

describe('StreamingGlyph', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('appears as a compact orbit presence while streaming', () => {
    const wrapper = mount(StreamingGlyph, { props: { state: 'streaming' } })

    expect(wrapper.find('.streaming-glyph').exists()).toBe(true)
    expect(wrapper.find('.streaming-glyph').attributes('data-state')).toBe('streaming')
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-inward-breathing')
    expect(wrapper.find('.glyph-orbit').exists()).toBe(true)
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('fades out subtly when streaming completes', async () => {
    vi.useFakeTimers()
    const wrapper = mount(StreamingGlyph, { props: { state: 'streaming' } })

    await wrapper.setProps({ state: 'done' })
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-leaving')

    await vi.advanceTimersByTimeAsync(200)
    expect(wrapper.find('.streaming-glyph').exists()).toBe(false)
  })

  it.each(['stopped', 'error'])('fades out quickly when %s', async (state) => {
    vi.useFakeTimers()
    const wrapper = mount(StreamingGlyph, { props: { state: 'streaming' } })

    await wrapper.setProps({ state })
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-leaving-fast')

    await vi.advanceTimersByTimeAsync(100)
    expect(wrapper.find('.streaming-glyph').exists()).toBe(false)
  })

  it('keeps a static glyph when reduced motion is preferred', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))

    const wrapper = mount(StreamingGlyph, { props: { state: 'streaming' } })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.streaming-glyph').attributes('data-reduced-motion')).toBe('true')
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-streaming')
    expect(wrapper.find('.streaming-glyph').classes()).toContain('is-static')
    expect(wrapper.find('.streaming-glyph').classes()).not.toContain('is-inward-breathing')
  })
})
