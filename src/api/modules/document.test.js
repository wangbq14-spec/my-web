import { beforeEach, describe, expect, it, vi } from 'vitest'
import http from '../http'
import {
  deleteDocument,
  getDocument,
  listDocuments,
  retryDocument,
  uploadDocument,
} from './document'

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('document API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listDocuments calls the documents endpoint', () => {
    listDocuments()

    expect(http.get).toHaveBeenCalledWith('/documents')
  })

  it('uploadDocument sends the file as multipart FormData', () => {
    const file = new File(['content'], 'document.txt', { type: 'text/plain' })

    uploadDocument(file)

    expect(http.post).toHaveBeenCalledTimes(1)

    const [url, formData, options] = http.post.mock.calls[0]
    expect(url).toBe('/documents')
    expect(formData).toBeInstanceOf(FormData)
    expect(formData.get('file')).toBe(file)
    expect(options.headers['Content-Type']).toBe('multipart/form-data')
  })

  it('associates an upload with a project when a project id is supplied', () => {
    const file = new File(['content'], 'project-notes.txt', { type: 'text/plain' })

    uploadDocument(file, 9)

    const [, formData] = http.post.mock.calls[0]
    expect(formData.get('project_id')).toBe('9')
  })

  it('getDocument calls the document endpoint', () => {
    getDocument(7)

    expect(http.get).toHaveBeenCalledWith('/documents/7')
  })

  it('retryDocument calls the document retry endpoint', () => {
    retryDocument(7)

    expect(http.post).toHaveBeenCalledWith('/documents/7/retry')
  })

  it('deleteDocument calls the document endpoint', () => {
    deleteDocument(7)

    expect(http.delete).toHaveBeenCalledWith('/documents/7')
  })
})
