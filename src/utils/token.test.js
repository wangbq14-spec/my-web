import { beforeEach, describe, expect, it } from 'vitest'
import {
  TOKEN_KEY,
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from './token'

describe('token utils', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('写入后可以读取 token', () => {
    setAccessToken('abc123')

    expect(getAccessToken()).toBe('abc123')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('abc123')
  })

  it('未设置时返回 null', () => {
    expect(getAccessToken()).toBeNull()
  })

  it('可以清除 token', () => {
    setAccessToken('abc123')
    clearAccessToken()

    expect(getAccessToken()).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })
})
