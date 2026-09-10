import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import { listModels } from './models'

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('models API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('lists available model tiers from the models endpoint', () => {
    listModels()

    expect(http.get).toHaveBeenCalledWith('/models')
  })
})
