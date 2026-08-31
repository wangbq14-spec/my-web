import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectsView from './ProjectsView.vue'

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
const routeMock = vi.hoisted(() => ({ query: {} }))
vi.mock('../api/modules/project', () => ({ listProjects: vi.fn(), createProject: vi.fn(), updateProject: vi.fn(), deleteProject: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => routeMock, useRouter: () => routerMock }))

import { createProject, deleteProject, listProjects, updateProject } from '../api/modules/project'

const project = { id: 7, name: '产品发布', description: '整理发布素材', instructions: '保持简洁', pinned: false, conversation_count: 3, document_count: 2, last_activity_at: '2026-08-30T09:00:00Z', created_at: '2026-08-30T08:00:00Z' }

async function mountProjects() {
  const wrapper = mount(ProjectsView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('ProjectsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.query = {}
    listProjects.mockResolvedValue([project])
  })

  it('renders the project list and opens a project', async () => {
    const wrapper = await mountProjects()
    expect(wrapper.text()).toContain('产品发布')
    await wrapper.find('.project-summary').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith({ name: 'project-detail', params: { id: 7 } })
    expect(wrapper.text()).toContain('3 个会话')
    expect(wrapper.text()).toContain('2 份资料')
  })

  it('provides direct Chat and Knowledge entries', async () => {
    const wrapper = await mountProjects()

    await wrapper.get('.back-chat-button').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/chat')

    await wrapper.get('.knowledge-button').trigger('click')
    expect(routerMock.push).toHaveBeenLastCalledWith('/knowledge')
  })

  it('filters projects locally and keeps a recent-project section', async () => {
    listProjects.mockResolvedValue([project, { ...project, id: 8, name: '学习资料', description: '课程笔记' }])
    const wrapper = await mountProjects()

    expect(wrapper.text()).toContain('最近项目')
    await wrapper.get('.project-search input').setValue('学习')
    expect(wrapper.text()).toContain('学习资料')
    expect(wrapper.text()).not.toContain('产品发布')
  })

  it('applies a lightweight template in the project sheet', async () => {
    listProjects.mockResolvedValue([])
    const wrapper = await mountProjects()
    expect(wrapper.find('.header-actions .primary-button').exists()).toBe(false)
    await wrapper.get('.quick-create-options').trigger('click')
    await wrapper.get('.template-list button:first-child').trigger('click')

    expect(wrapper.get('.project-editor textarea').element.value).toContain('整理研究问题')
    expect(wrapper.findAll('.project-editor textarea')[1].element.value).toContain('研究问题')
  })

  it('shows the Omnixa empty state', async () => {
    listProjects.mockResolvedValue([])
    const wrapper = await mountProjects()

    expect(wrapper.text()).toContain('创建第一个项目')
    expect(wrapper.text()).toContain('Omnixa')
    await wrapper.get('.empty-state .primary-button').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('.quick-create input').element)
  })

  it('focuses the existing quick-create field when opened from the sidebar plus action', async () => {
    routeMock.query = { create: '1' }
    const wrapper = await mountProjects()

    expect(document.activeElement).toBe(wrapper.get('.quick-create input').element)
  })

  it('creates a project from the new-project form', async () => {
    listProjects
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...project, id: 8, name: '研究计划' }])
    createProject.mockResolvedValue({ ...project, id: 8 })
    const wrapper = await mountProjects()
    await wrapper.get('.quick-create input').setValue('研究计划')
    await wrapper.get('.quick-create').trigger('submit')
    await flushPromises()
    expect(createProject).toHaveBeenCalledWith({ name: '研究计划' })
    expect(listProjects).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.quick-create input').element.value).toBe('')
    expect(wrapper.text()).toContain('研究计划')
  })

  it('renames a project and refreshes the list', async () => {
    updateProject.mockResolvedValue({ ...project, name: '新版产品发布' })
    const wrapper = await mountProjects()
    await wrapper.findAll('.project-actions .quiet-button')[1].trigger('click')
    await wrapper.get('.project-editor input').setValue('新版产品发布')
    await wrapper.get('.project-editor form').trigger('submit')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(7, {
      name: '新版产品发布',
      description: '整理发布素材',
      instructions: '保持简洁',
    })
    expect(listProjects).toHaveBeenCalledTimes(2)
  })

  it('submits empty description and Instructions fields while editing', async () => {
    updateProject.mockResolvedValue({ ...project, description: '', instructions: '' })
    const wrapper = await mountProjects()
    await wrapper.findAll('.project-actions .quiet-button')[1].trigger('click')
    const textareas = wrapper.findAll('.project-editor textarea')
    await textareas[0].setValue('')
    await textareas[1].setValue('   ')
    await wrapper.get('.project-editor form').trigger('submit')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(7, {
      name: '产品发布',
      description: '',
      instructions: '',
    })
  })

  it('pins a project and sorts pinned projects before newer activity', async () => {
    const pinnedProject = { ...project, id: 8, name: '置顶研究', pinned: true, last_activity_at: '2020-01-01T00:00:00Z' }
    listProjects.mockResolvedValue([project, pinnedProject])
    updateProject.mockResolvedValue({ ...project, pinned: true })
    const wrapper = await mountProjects()

    expect(wrapper.findAll('.recent-grid .project-card strong')[0].text()).toBe('置顶研究')
    await wrapper.get('.project-card .pin-button').trigger('click')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(8, { pinned: false })
  })

  it('requires confirmation before deleting a project', async () => {
    deleteProject.mockResolvedValue()
    const wrapper = await mountProjects()
    await wrapper.find('.delete-button').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('产品发布')
    await wrapper.get('[role="dialog"] .delete-button').trigger('click')
    await flushPromises()
    expect(deleteProject).toHaveBeenCalledWith(7)
    expect(listProjects).toHaveBeenCalledTimes(2)
  })
})
