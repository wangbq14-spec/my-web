import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeView from './KnowledgeView.vue'

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('../api/modules/document', () => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  getDocument: vi.fn(),
  retryDocument: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRouter: () => routerMock,
}))

import { deleteDocument, getDocument, listDocuments, retryDocument, uploadDocument } from '../api/modules/document'

const readyDocument = {
  id: 1,
  original_filename: 'handbook.pdf',
  file_size: 2048,
  status: 'ready',
  error_message: null,
  created_at: '2026-08-29T08:30:00Z',
}

const queuedDocument = { ...readyDocument, status: 'queued' }

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
    vi.useRealTimers()
    listDocuments.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a loading state while documents are loading', () => {
    listDocuments.mockImplementation(() => new Promise(() => {}))
    const wrapper = mount(KnowledgeView)

    expect(wrapper.text()).toContain('正在加载资料…')
  })

  it('shows the empty state when there are no documents', async () => {
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('还没有添加资料')
    expect(wrapper.text()).toContain('Chat 回答和 Agent 能力')
  })

  it('renders a document-led upload area with drag and file-choice guidance', async () => {
    const wrapper = await mountKnowledge()
    const uploadArea = wrapper.get('.upload-area')

    expect(uploadArea.find('.upload-icon svg').exists()).toBe(true)
    expect(uploadArea.get('h2').text()).toBe('添加资料')
    expect(uploadArea.text()).toContain('拖拽文档到这里，或选择文件')
    expect(uploadArea.get('.file-picker').text()).toBe('选择文件')
    expect(uploadArea.text()).toContain('支持 TXT、Markdown、PDF，不超过 10 MB')
  })

  it('renders a ready document as available', async () => {
    listDocuments.mockResolvedValue([readyDocument])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('handbook.pdf')
    expect(wrapper.text()).toContain('可用')
    expect(wrapper.text()).toContain('AI 已可在回答中参考')
  })

  it('links users to Chat to use their materials', async () => {
    const wrapper = await mountKnowledge()

    await wrapper.find('.chat-link').trigger('click')

    expect(routerMock.push).toHaveBeenCalledWith({ path: '/chat', query: { mode: 'rag' } })
  })

  it('provides direct Chat and project entries', async () => {
    const wrapper = await mountKnowledge()

    await wrapper.get('.back-chat-button').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/chat')

    await wrapper.get('.projects-button').trigger('click')
    expect(routerMock.push).toHaveBeenLastCalledWith('/projects')
  })

  it('renders a processing document with text status', async () => {
    listDocuments.mockResolvedValue([{ ...readyDocument, status: 'processing' }])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('处理中')
    expect(wrapper.text()).toContain('正在准备，完成后即可使用')
  })

  it('renders a queued document with text status', async () => {
    listDocuments.mockResolvedValue([queuedDocument])
    const wrapper = await mountKnowledge()

    expect(wrapper.text()).toContain('处理中')
  })

  it('starts polling queued and processing documents restored from the list', async () => {
    vi.useFakeTimers()
    const processingDocument = { ...readyDocument, id: 2, status: 'processing' }
    listDocuments.mockResolvedValue([queuedDocument, processingDocument])
    getDocument.mockResolvedValue(readyDocument)

    const wrapper = await mountKnowledge()

    expect(getDocument).toHaveBeenCalledWith(1, expect.any(Object))
    expect(getDocument).toHaveBeenCalledWith(2, expect.any(Object))
    wrapper.unmount()
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
    expect(wrapper.find('.refresh-error-banner').text()).toContain('资料刷新失败')
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

  it('polls an uploaded queued document until it is ready', async () => {
    vi.useFakeTimers()
    uploadDocument.mockResolvedValue(queuedDocument)
    getDocument.mockResolvedValueOnce({ ...queuedDocument, status: 'processing' }).mockResolvedValueOnce(readyDocument)
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()
    expect(getDocument).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('处理中')

    await vi.advanceTimersByTimeAsync(2000)
    expect(getDocument).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('可用')

    await vi.advanceTimersByTimeAsync(4000)
    expect(getDocument).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows a refresh hint after the finite polling window ends while a document is non-terminal', async () => {
    vi.useFakeTimers()
    listDocuments.mockResolvedValue([queuedDocument])
    getDocument.mockResolvedValue(queuedDocument)
    const wrapper = await mountKnowledge()

    await vi.advanceTimersByTimeAsync(30000)

    expect(getDocument).toHaveBeenCalledTimes(15)
    expect(wrapper.text()).toContain('仍在准备中，完成后会自动更新；你也可以刷新查看最新状态')
    wrapper.unmount()
  })

  it('restarts polling and clears the refresh hint when the document list is refreshed', async () => {
    vi.useFakeTimers()
    listDocuments.mockResolvedValue([queuedDocument])
    getDocument.mockResolvedValue(queuedDocument)
    const wrapper = await mountKnowledge()

    await vi.advanceTimersByTimeAsync(30000)
    expect(wrapper.text()).toContain('仍在准备中，完成后会自动更新；你也可以刷新查看最新状态')

    await wrapper.vm.$.setupState.loadDocuments()

    expect(getDocument).toHaveBeenCalledTimes(16)
    expect(wrapper.text()).not.toContain('仍在准备中，完成后会自动更新；你也可以刷新查看最新状态')
    wrapper.unmount()
  })

  it('stops polling on failure and shows reprocess action', async () => {
    vi.useFakeTimers()
    uploadDocument.mockResolvedValue(queuedDocument)
    getDocument.mockResolvedValue({ ...queuedDocument, status: 'failed', error_message: null })
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('.retry-btn').text()).toBe('重新处理')
    await vi.advanceTimersByTimeAsync(4000)
    expect(getDocument).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('requeues a failed document and resumes polling after reprocessing', async () => {
    vi.useFakeTimers()
    listDocuments.mockResolvedValue([{ ...queuedDocument, status: 'failed' }])
    const pendingPoll = deferred()
    retryDocument.mockResolvedValue(queuedDocument)
    getDocument.mockImplementationOnce(() => pendingPoll.promise).mockResolvedValueOnce(readyDocument)
    const wrapper = await mountKnowledge()

    await wrapper.find('.retry-btn').trigger('click')
    await flushPromises()
    expect(retryDocument).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('处理中')
    expect(getDocument).toHaveBeenCalledTimes(1)

    pendingPoll.resolve({ ...queuedDocument, status: 'processing' })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    expect(getDocument).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('does not update a queued document after unmounting during polling', async () => {
    vi.useFakeTimers()
    const pendingPoll = deferred()
    uploadDocument.mockResolvedValue(queuedDocument)
    getDocument.mockImplementation(() => pendingPoll.promise)
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()
    wrapper.unmount()
    pendingPoll.resolve(readyDocument)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(4000)

    expect(getDocument).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.$.setupState.documents).toEqual([queuedDocument])
  })

  it('does not let a stale polling response restore a deleted document', async () => {
    vi.useFakeTimers()
    const pendingPoll = deferred()
    listDocuments.mockResolvedValueOnce([]).mockResolvedValueOnce([queuedDocument]).mockResolvedValueOnce([])
    uploadDocument.mockResolvedValue(queuedDocument)
    getDocument.mockImplementation(() => pendingPoll.promise)
    deleteDocument.mockResolvedValue()
    const wrapper = await mountKnowledge()

    await selectFile(wrapper, new File(['hello'], 'notes.txt', { type: 'text/plain' }))
    await wrapper.find('.upload-btn').trigger('click')
    await flushPromises()
    await wrapper.find('.delete-btn').trigger('click')
    await wrapper.find('.confirm-actions .danger').trigger('click')
    await flushPromises()
    pendingPoll.resolve(readyDocument)
    await flushPromises()

    expect(wrapper.find('.document-list').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('handbook.pdf')
    wrapper.unmount()
  })

  it('does not let an older polling response overwrite a refreshed document list', async () => {
    vi.useFakeTimers()
    const pendingPoll = deferred()
    listDocuments.mockResolvedValueOnce([queuedDocument]).mockResolvedValueOnce([readyDocument])
    getDocument.mockImplementationOnce(() => pendingPoll.promise)
    const wrapper = await mountKnowledge()

    await wrapper.vm.$.setupState.loadDocuments()
    pendingPoll.resolve({ ...queuedDocument, status: 'processing' })
    await flushPromises()

    expect(wrapper.text()).toContain('可用')
    expect(wrapper.text()).not.toContain('处理中')
    wrapper.unmount()
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

  it('traps focus in the delete dialog and restores it after Escape', async () => {
    listDocuments.mockResolvedValue([readyDocument])
    const wrapper = mount(KnowledgeView, { attachTo: document.body })
    await flushPromises()
    const deleteButton = wrapper.find('.delete-btn')

    await deleteButton.trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.find('.confirm-actions button').element)
    expect(wrapper.get('[role="dialog"]').attributes('aria-describedby')).toBe('delete-document-dialog-description')
    expect(wrapper.find('.knowledge-header').element.parentElement.inert).toBe(true)

    const cancelButton = wrapper.find('.confirm-actions button')
    const confirmButton = wrapper.find('.confirm-actions .danger')
    confirmButton.element.focus()
    await confirmButton.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(cancelButton.element)
    await cancelButton.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirmButton.element)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('.confirm-modal').exists()).toBe(false)
    expect(wrapper.find('.knowledge-header').element.parentElement.inert).toBe(false)
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
    expect(wrapper.text()).toContain('还没有添加资料')
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
    expect(document.activeElement).toBe(wrapper.find('.back-chat-button').element)
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
