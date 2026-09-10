import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle.vue'

describe('ThemeToggle', () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = 'light'
    window.localStorage.clear()
  })

  it('switches the document and persisted preference to dark mode', async () => {
    const wrapper = mount(ThemeToggle)

    await wrapper.get('button').trigger('click')

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem('omnixa-theme')).toBe('dark')
    expect(wrapper.get('button').attributes('aria-label')).toBe('切换到白天模式')
  })
})
