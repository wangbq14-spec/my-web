import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeView from './KnowledgeView.vue'

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('../api/modules/document', () => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRouter: () => routerMock,
}))

import { deleteDocument, listDocuments, uploadDocument } from '../api/modules/document'

const readyDocument = {
  id: 1,
  original_filename: 'handbook.pdf',
  file_size: 2048,
  status: 'ready',
  error_message: null,
  created_at: '2026-08-29T08:30:00Z',
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

async function mountKnowledge() {
  const wrapper = mount(KnowledgeView)
  await flushPromises()
  return wrapper
}

async function selectFile(wrapper, file) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [file],
  })
  await input.trigger('change')
}

describe('KnowledgeView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDocuments.mockResolvedValue([])
  })

  it('shows a loading state while documents are loading', () => {
    listDocuments.mockImplementation(() => new Promise(() => {}))
    const wrapper = mount(KnowledgeView)

    expect(wrapper.text()).toContain('加载中…')
  })

  it('shows the empty state when there are no documents', async () => {
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('知识库还是空的')
    expect(wrapper.text()).toContain('知识库模式或 Agent')
  })

  it('renders a ready document as available', async () => {
    listDocuments.mockResolvedValue([readyDocument])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('handbook.pdf')
    expect(wrapper.text()).toContain('可用')
  })

  it('renders a processing document with text status', async () => {
    listDocuments.mockResolvedValue([{ ...readyDocument, status: 'processing' }])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('处理中…')
  })

  it('shows safe failed-document recovery guidance', async () => {
    listDocuments.mockResolvedValue([{ ...readyDocument, status: 'failed', error_message: null }])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('处理失败，可删除后重新上传')
  })

  it('does not expose sensitive failed-document error details', async () => {
    const sensitiveMessage = 'Authorization: Bearer sensitive-token'
    listDocuments.mockResolvedValue([{ ...readyDocument, status: 'failed', error_message: sensitiveMessage }])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).not.toContain(sensitiveMessage)
  })

  it.each([
    'API Key: xyz',
    'Authorization: Bearer abc',
    'access_token=abc',
    'DATABASE_URL=mysql://localhost/knowledge',
    'C:\\secret\\path',
    '/etc/passwd',
    'https://example.com/x',
  ])('redacts sensitive failed-document error message: %s', async (sensitiveMessage) => {
    listDocuments.mockResolvedValue([{ ...readyDocument, status: 'failed', error_message: sensitiveMessage }])
    const wrapper = await mountKnowledge()

    expect(wrapper.find('.document-error').text()).toBe('处理失败，可删除后重新上传')
    expect(wrapper.text()).not.toContain(sensitiveMessage)
    wrapper.unmount()
  })

  it('shows an initial load failure instead of the empty state', async () => {
    listDocuments.mockRejectedValue({ message: '文档服务暂不可用' })
    const wrapper = await mountKnowledge()

    expect(wrapper.find('.load-error-state').text()).toContain('文档服务暂不可用')
    expect(wrapper.find('.empty-state').exists()).toBe(false)
  })

  it('retries document loading from the initial error state', async () => {
    listDocuments.mockRejectedValueOnce({ message: '网络错误' }).mockResolvedValueOnce([])
    const wrapper = await mountKnowledge()

    await wrapper.get('.load-error-state button').trigger('click')
    await flushPromises()

    expect(listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('keeps existing documents and shows a retry banner when refresh fails', async () => {
    listDocuments.mockResolvedValueOnce([readyDocument]).mockRejectedValueOnce({ message: '刷新服务暂不可用' })
    uploadDocument.mockResolvedValue(readyDocument)
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('handbook.pdf')
    expect(wrapper.find('.refresh-error-banner').text()).toContain('刷新失败，可重试')
  })

  it('does not let an older list response overwrite a newer refresh', async () => {
    const oldRequest = deferred()
    listDocuments.mockImplementationOnce(() => oldRequest.promise).mockResolvedValueOnce([readyDocument])
    uploadDocument.mockResolvedValue(readyDocument)
    const wrapper = mount(KnowledgeView)

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()
    oldRequest.resolve([])
    await flushPromises()

    expect(wrapper.text()).toContain('handbook.pdf')
    expect(wrapper.find('.empty-state').exists()).toBe(false)
  })

  it('does not update exposed list state after unmounting', async () => {
    const pending = deferred()
    listDocuments.mockImplementationOnce(() => pending.promise)
    const wrapper = mount(KnowledgeView)

    wrapper.unmount()
    pending.resolve([readyDocument])
    await flushPromises()

    expect(wrapper.vm.$.setupState.documents).toEqual([])
  })

  it('uploads a selected file and refreshes the document list', async () => {
    listDocuments.mockResolvedValueOnce([]).mockResolvedValueOnce([readyDocument])
    uploadDocument.mockResolvedValue(readyDocument)
    const wrapper = await mountKnowledge()
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })

    await selectFile(wrapper, file)
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(uploadDocument).toHaveBeenCalledWith(file)
    expect(listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('handbook.pdf')
    expect(wrapper.find('input[type="file"]').element.value).toBe('')
  })

  it('resets the native input after an upload failure so the same file can be selected again', async () => {
    uploadDocument.mockRejectedValueOnce({ message: '上传服务暂不可用' }).mockResolvedValueOnce(readyDocument)
    const wrapper = await mountKnowledge()
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })

    await selectFile(wrapper, file)
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('input[type="file"]').element.value).toBe('')

    await selectFile(wrapper, file)
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(uploadDocument).toHaveBeenCalledTimes(2)
  })

  it('shows a safe error when upload fails', async () => {
    uploadDocument.mockRejectedValue({ message: '上传服务暂不可用' })
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-banner').text()).toContain('上传服务暂不可用')
  })

  it('rejects unsupported extensions without calling the upload API', async () => {
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.exe', { type: 'application/octet-stream' }))

    expect(wrapper.find('.error-banner').text()).toContain('仅支持 TXT、Markdown、PDF，且不超过 10 MB')
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  it('rejects empty and oversized files without calling the upload API', async () => {
    const wrapper = await mountKnowledge()
    const oversizedFile = new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' })

    await selectFile(wrapper, new File([], 'empty.txt', { type: 'text/plain' }))
    expect(wrapper.find('.error-banner').text()).toContain('仅支持 TXT、Markdown、PDF，且不超过 10 MB')

    await selectFile(wrapper, oversizedFile)
    expect(wrapper.find('.error-banner').text()).toContain('仅支持 TXT、Markdown、PDF，且不超过 10 MB')
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  it('applies real drag-over feedback and accepts a dropped file', async () => {
    const wrapper = await mountKnowledge()
    const area = wrapper.find('.upload-area')

    await area.trigger('dragenter')
    expect(area.classes()).toContain('dragging')
    await area.trigger('dragleave')
    expect(area.classes()).not.toContain('dragging')
    await area.trigger('drop', { dataTransfer: { files: [new File(['hello'], 'drop.md', { type: 'text/markdown' })] } })

    expect(wrapper.text()).toContain('drop.md')
  })

  it('focuses the cancel button and restores focus after Escape', async () => {
    listDocuments.mockResolvedValue([readyDocument])
    const wrapper = mount(KnowledgeView, { attachTo: document.body })
    await flushPromises()
    const deleteButton = wrapper.find('.delete-btn')

    await deleteButton.trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.find('.confirm-actions button').element)
    expect(wrapper.get('[role="dialog"]').attributes('aria-describedby')).toBe('delete-document-dialog-description')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('.confirm-modal').exists()).toBe(false)
    expect(document.activeElement).toBe(deleteButton.element)
    wrapper.unmount()
  })

  it('deletes a confirmed document and refreshes the list', async () => {
    listDocuments.mockResolvedValueOnce([readyDocument]).mockResolvedValueOnce([])
    deleteDocument.mockResolvedValue()
    const wrapper = await mountKnowledge()

    await wrapper.find('.delete-btn').trigger('click')
    await wrapper.find('.confirm-actions .danger').trigger('click')
    await flushPromises()

    expect(deleteDocument).toHaveBeenCalledWith(1)
    expect(listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('知识库还是空的')
  })

  it('moves focus to the back button when the deleted trigger no longer exists', async () => {
    listDocuments.mockResolvedValueOnce([readyDocument]).mockResolvedValueOnce([])
    deleteDocument.mockResolvedValue()
    const wrapper = mount(KnowledgeView, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('.delete-btn').trigger('click')
    await wrapper.find('.confirm-actions .danger').trigger('click')
    await flushPromises()

    expect(wrapper.find('.delete-btn').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('.back-btn').element)
    wrapper.unmount()
  })

  it('shows a safe error when deletion fails', async () => {
    listDocuments.mockResolvedValue([readyDocument])
    deleteDocument.mockRejectedValue({ message: '删除服务暂不可用' })
    const wrapper = await mountKnowledge()

    await wrapper.find('.delete-btn').trigger('click')
    await wrapper.find('.confirm-actions .danger').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-banner').text()).toContain('删除服务暂不可用')
    expect(wrapper.find('.confirm-modal').exists()).toBe(true)
  })

  it('disables file controls while an upload is in progress', async () => {
    uploadDocument.mockImplementation(() => new Promise(() => {}))
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.md', { type: 'text/markdown' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('input[type="file"]').element.disabled).toBe(true)
    expect(wrapper.find('.upload-btn').element.disabled).toBe(true)
  })
})
