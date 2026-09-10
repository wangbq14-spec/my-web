import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TasksView from './TasksView.vue'

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('../api/modules/workflow', () => ({ listTasks: vi.fn() }))
vi.mock('../api/modules/project', () => ({ listProjects: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => routerMock }))

import { listProjects } from '../api/modules/project'
import { listTasks } from '../api/modules/workflow'

const task = {
  id: 12,
  project_id: 7,
  title: '发布研究',
  status: 'running',
  current_step: 'summary',
  created_at: '2026-08-30T08:00:00Z',
}

async function mountTasks() {
  const wrapper = mount(TasksView)
  await flushPromises()
  return wrapper
}

describe('TasksView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listTasks.mockResolvedValue([task])
    listProjects.mockResolvedValue([{ id: 7, name: '产品发布' }])
  })

  it('renders task, project, Chinese status, current step, and creation time', async () => {
    const wrapper = await mountTasks()

    expect(wrapper.text()).toContain('发布研究')
    expect(wrapper.text()).toContain('产品发布')
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('总结')
    expect(wrapper.text()).toContain('2026')
  })

  it('filters tasks by status and opens a task detail', async () => {
    const wrapper = await mountTasks()

    await wrapper.get('#task-status-filter').setValue('failed')
    await flushPromises()
    expect(listTasks).toHaveBeenLastCalledWith('failed')

    await wrapper.get('.task-link').trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith({ name: 'task-detail', params: { id: 12 } })
  })

  it('shows the empty state when no tasks match', async () => {
    listTasks.mockResolvedValue([])
    const wrapper = await mountTasks()

    expect(wrapper.text()).toContain('还没有任务')
    expect(wrapper.get('.empty-state').text()).toContain('前往项目')
  })

  it('shows cancelled when a cancelled task has no current step', async () => {
    listTasks.mockResolvedValue([{ ...task, status: 'cancelled', current_step: null }])
    const wrapper = await mountTasks()

    expect(wrapper.get('.task-meta').text()).toContain('当前步骤已取消')
  })

  it('shows an accessible error and can retry loading', async () => {
    listTasks.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([task])
    const wrapper = await mountTasks()

    expect(wrapper.get('[role="alert"]').text()).toContain('加载任务失败')
    await wrapper.get('.error-state button').trigger('click')
    await flushPromises()

    expect(listTasks).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('发布研究')
  })
})
