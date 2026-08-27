import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import HelloWorld from './HelloWorld.vue'

describe('HelloWorld', () => {
  it('组件可以正常挂载', () => {
    const wrapper = mount(HelloWorld, {
      props: {
        msg: '测试标题',
      },
    })

    expect(wrapper.exists()).toBe(true)
  })
})