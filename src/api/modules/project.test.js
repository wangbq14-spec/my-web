import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  createProject,
  deleteProject,
  getProject,
  listProjectConversations,
  listProjectDocuments,
  listProjects,
  updateProject,
} from './project'

vi.mock('../http', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

describe('project API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the project collection endpoints', () => {
    listProjects()
    createProject({ name: '产品发布' })
    expect(http.get).toHaveBeenCalledWith('/projects')
    expect(http.post).toHaveBeenCalledWith('/projects', { name: '产品发布' })
  })

  it('uses an individual project endpoint for get, update, and delete', () => {
    getProject(4)
    updateProject(4, { instructions: '简洁回答' })
    deleteProject(4)
    expect(http.get).toHaveBeenCalledWith('/projects/4')
    expect(http.patch).toHaveBeenCalledWith('/projects/4', { instructions: '简洁回答' })
    expect(http.delete).toHaveBeenCalledWith('/projects/4')
  })

  it('uses the linked conversation and document endpoints', () => {
    listProjectConversations(4)
    listProjectDocuments(4)
    expect(http.get).toHaveBeenCalledWith('/projects/4/conversations')
    expect(http.get).toHaveBeenCalledWith('/projects/4/documents')
  })
})
