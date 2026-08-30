import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectDetailView from './ProjectDetailView.vue'

const routeMock = vi.hoisted(() => ({ params: { id: '7' } }))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('../api/modules/project', () => ({ getProject: vi.fn(), listProjectConversations: vi.fn(), listProjectDocuments: vi.fn(), updateProject: vi.fn(), deleteProject: vi.fn() }))
vi.mock('../api/modules/conversation', () => ({ createConversation: vi.fn() }))
vi.mock('../api/modules/document', () => ({ uploadDocument: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => routeMock, useRouter: () => routerMock }))

import { createConversation } from '../api/modules/conversation'
import { getProject, listProjectConversations, listProjectDocuments, updateProject } from '../api/modules/project'
import { uploadDocument } from '../api/modules/document'

const project = { id: 7, name: '产品发布', description: '整理发布素材', instructions: '语气清晰', created_at: '2026-08-30T08:00:00Z' }

async function mountDetail() {
  const wrapper = mount(ProjectDetailView)
  await flushPromises()
  return wrapper
}

describe('ProjectDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.params.id = '7'
    getProject.mockResolvedValue(project)
    listProjectConversations.mockResolvedValue([{ id: 3, title: '发布文案', updated_at: '2026-08-30T09:00:00Z' }])
    listProjectDocuments.mockResolvedValue([{ id: 2, original_filename: 'brief.pdf', status: 'ready', created_at: '2026-08-30T08:00:00Z' }])
  })

  it('renders the Overview tab with project-linked conversations and documents', async () => {
    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('产品发布')
    expect(wrapper.text()).toContain('发布文案')
    expect(wrapper.text()).toContain('brief.pdf')
    expect(wrapper.text()).toContain('可用')
    expect(wrapper.get('.project-tabs').text()).toContain('Knowledge')
  })

  it('provides direct Chat, project-list, and Knowledge entries', async () => {
    const wrapper = await mountDetail()

    await wrapper.get('.back-chat-button').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/chat')

    await wrapper.get('.projects-button').trigger('click')
    expect(routerMock.push).toHaveBeenLastCalledWith('/projects')

    await wrapper.get('.knowledge-button').trigger('click')
    expect(routerMock.push).toHaveBeenLastCalledWith('/knowledge')
  })

  it('saves a renamed project', async () => {
    updateProject.mockResolvedValue({ ...project, name: '新版产品发布' })
    const wrapper = await mountDetail()
    await wrapper.get('.text-button').trigger('click')
    await wrapper.get('.name-editor input').setValue('新版产品发布')
    await wrapper.get('.name-editor .primary-button').trigger('click')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(7, { name: '新版产品发布' })
  })

  it('starts a conversation with the current project id', async () => {
    createConversation.mockResolvedValue({ id: 12 })
    const wrapper = await mountDetail()
    await wrapper.find('.overview-actions .primary-button').trigger('click')
    expect(createConversation).toHaveBeenCalledWith({ project_id: '7' })
    expect(routerMock.push).toHaveBeenCalledWith({ path: '/chat', query: { conversation_id: 12, project_id: '7' } })
  })

  it('uploads Knowledge files with the current project id', async () => {
    uploadDocument.mockResolvedValue({ id: 4 })
    const wrapper = await mountDetail()
    await wrapper.get('.project-tabs button:nth-child(3)').trigger('click')
    const file = new File(['brief'], 'brief.txt', { type: 'text/plain' })
    const input = wrapper.get('.file-input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(uploadDocument).toHaveBeenCalledWith(file, '7')
  })
})
