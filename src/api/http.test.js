import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  requestFulfilled: null,
  createConfig: null,
}))

vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: {
        use: (onFulfilled) => {
          mocks.requestFulfilled = onFulfilled
        },
      },
      response: {
        use: () => {},
      },
    },
  }
  return {
    default: {
      create: (config) => {
        mocks.createConfig = config
        return instance
      },
    },
  }
})

import http from './http'

describe('http client', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('自动附加 Authorization', () => {
    localStorage.setItem('access_token', 'token-abc')

    const config = { headers: {} }
    mocks.requestFulfilled(config)

    expect(config.headers.Authorization).toBe('Bearer token-abc')
  })

  it('无 token 时不附加 Authorization', () => {
    const config = { headers: {} }
    mocks.requestFulfilled(config)

    expect(config.headers.Authorization).toBeUndefined()
  })

  it('导出默认 http 实例', () => {
    expect(http).toBeTruthy()
  })

  it('does not set a default JSON Content-Type', () => {
    expect(mocks.createConfig.headers?.['Content-Type']).toBeUndefined()
  })
})
