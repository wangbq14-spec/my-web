import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  approveTask,
  cancelTask,
  createTask,
  getTask,
  listArtifacts,
  listTasks,
  rejectTask,
  retryTask,
  startTask,
} from './workflow'

vi.mock('../http', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

describe('workflow API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists all tasks or filters them by status', () => {
    listTasks()
    listTasks('running')

    expect(http.get).toHaveBeenNthCalledWith(1, '/tasks')
    expect(http.get).toHaveBeenNthCalledWith(2, '/tasks', { params: { status: 'running' } })
  })

  it('creates and gets a task', () => {
    createTask({ project_id: 7, title: '发布研究' })
    getTask(12)

    expect(http.post).toHaveBeenCalledWith('/tasks', { project_id: 7, title: '发布研究' })
    expect(http.get).toHaveBeenCalledWith('/tasks/12')
  })

  it('starts a task with the extended synchronous execution timeout', () => {
    startTask(12)

    expect(http.post).toHaveBeenCalledWith('/tasks/12/start', undefined, { timeout: 120000 })
  })

  it('uses task action endpoints', () => {
    cancelTask(12)
    retryTask(12)
    approveTask(12, { comment: '可以发布' })
    rejectTask(12, { comment: '需要补充来源' })

    expect(http.post).toHaveBeenNthCalledWith(1, '/tasks/12/cancel')
    expect(http.post).toHaveBeenNthCalledWith(2, '/tasks/12/retry')
    expect(http.post).toHaveBeenNthCalledWith(3, '/tasks/12/approve', { comment: '可以发布' })
    expect(http.post).toHaveBeenNthCalledWith(4, '/tasks/12/reject', { comment: '需要补充来源' })
  })

  it('lists task artifacts', () => {
    listArtifacts(12)
    expect(http.get).toHaveBeenCalledWith('/tasks/12/artifacts')
  })
})
