import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskDetailView from './TaskDetailView.vue'

const routeMock = vi.hoisted(() => ({ params: { id: '12' } }))
const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('../api/modules/project', () => ({ getProject: vi.fn() }))
vi.mock('../api/modules/workflow', () => ({
  approveTask: vi.fn(),
  cancelTask: vi.fn(),
  getTask: vi.fn(),
  listArtifacts: vi.fn(),
  rejectTask: vi.fn(),
  retryTask: vi.fn(),
  startTask: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => routeMock, useRouter: () => routerMock }))

import { getProject } from '../api/modules/project'
import {
  approveTask,
  getTask,
  listArtifacts,
  rejectTask,
  retryTask,
} from '../api/modules/workflow'

const baseTask = {
  id: 12,
  project_id: 7,
  workflow_type: 'research',
  title: '发布研究',
  status: 'failed',
  current_step: 'review',
  error: '审核未通过',
  created_at: '2026-08-30T08:00:00Z',
  steps: [
    { step_name: 'research', status: 'succeeded', attempt: 1, started_at: '2026-08-30T08:01:00Z', completed_at: '2026-08-30T08:02:00Z' },
    { step_name: 'summary', status: 'succeeded', attempt: 1 },
    { step_name: 'review', status: 'failed', attempt: 2, error: '缺少来源' },
  ],
  approvals: [],
  artifacts: [],
}
const artifact = {
  artifact_type: 'final_report',
  title: '最终报告',
  content: '# 发布结论\n\n可以进入发布阶段。',
  created_at: '2026-08-30T09:00:00Z',
}

async function mountDetail() {
  const wrapper = mount(TaskDetailView)
  await flushPromises()
  return wrapper
}

describe('TaskDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeMock.params.id = '12'
    getTask.mockResolvedValue(baseTask)
    getProject.mockResolvedValue({ id: 7, name: '产品发布' })
    listArtifacts.mockResolvedValue([artifact])
  })

  it('renders all workflow steps with attempts and errors', async () => {
    const wrapper = await mountDetail()
    const timeline = wrapper.get('.timeline')

    expect(timeline.text()).toContain('调研')
    expect(timeline.text()).toContain('总结')
    expect(timeline.text()).toContain('审核')
    expect(timeline.text()).toContain('定稿')
    expect(timeline.text()).toContain('尝试次数：2')
    expect(timeline.text()).toContain('缺少来源')
  })

  it('shows task errors as alerts and renders Markdown artifacts', async () => {
    const wrapper = await mountDetail()

    expect(wrapper.get('.task-error[role="alert"]').text()).toContain('审核未通过')
    expect(wrapper.get('.artifact-card').text()).toContain('最终报告')
    expect(wrapper.get('.artifact-card h1').text()).toBe('发布结论')
  })

  it('retries a failed task and refreshes its detail', async () => {
    retryTask.mockResolvedValue({ ...baseTask, status: 'queued' })
    const wrapper = await mountDetail()

    await wrapper.get('.retry-button').trigger('click')
    await flushPromises()

    expect(retryTask).toHaveBeenCalledWith(12)
    expect(getTask).toHaveBeenCalledTimes(2)
  })

  it('refreshes from waiting approval to succeeded and shows artifacts after approval', async () => {
    const waitingTask = { ...baseTask, status: 'waiting_approval', current_step: null, error: null }
    const succeededTask = { ...baseTask, status: 'succeeded', current_step: null, error: null }
    getTask.mockResolvedValueOnce(waitingTask).mockResolvedValueOnce(succeededTask)
    listArtifacts.mockResolvedValueOnce([]).mockResolvedValueOnce([artifact])
    approveTask.mockResolvedValue({})
    const wrapper = await mountDetail()

    await wrapper.get('#approval-comment').setValue('  可以发布  ')
    await wrapper.get('.approve-button').trigger('click')
    await flushPromises()

    expect(approveTask).toHaveBeenCalledWith(12, { comment: '可以发布' })
    expect(getTask).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.summary-copy').text()).toContain('已完成')
    expect(wrapper.get('.artifact-card h1').text()).toBe('发布结论')
    expect(wrapper.find('.approval-card').exists()).toBe(false)
  })

  it('rejects a waiting task with an optional comment', async () => {
    getTask.mockResolvedValue({ ...baseTask, status: 'waiting_approval', error: null })
    rejectTask.mockResolvedValue({})
    const wrapper = await mountDetail()

    await wrapper.get('#approval-comment').setValue('  请补充来源  ')
    await wrapper.get('.reject-button').trigger('click')
    await flushPromises()
    expect(rejectTask).toHaveBeenCalledWith(12, { comment: '请补充来源' })
  })

  it('keeps task details and artifacts when the task has no project', async () => {
    getTask.mockResolvedValue({ ...baseTask, project_id: null })
    const wrapper = await mountDetail()

    expect(wrapper.get('h1').text()).toBe('发布研究')
    expect(wrapper.get('.project-unavailable').text()).toBe('项目已删除')
    expect(wrapper.get('.artifact-card h1').text()).toBe('发布结论')
    expect(wrapper.find('.back-project-button').exists()).toBe(false)
    expect(getProject).not.toHaveBeenCalled()
  })

  it('keeps task details and artifacts when loading its project fails', async () => {
    getProject.mockRejectedValue({ status: 404 })
    const wrapper = await mountDetail()

    expect(wrapper.get('h1').text()).toBe('发布研究')
    expect(wrapper.get('.project-unavailable').text()).toBe('项目已删除')
    expect(wrapper.get('.timeline').exists()).toBe(true)
    expect(wrapper.get('.artifact-card h1').text()).toBe('发布结论')
    expect(wrapper.find('.back-project-button').exists()).toBe(false)
    expect(wrapper.find('.load-error').exists()).toBe(false)
  })

  it.each([
    ['succeeded', '已完成'],
    ['cancelled', '已取消'],
    ['waiting_approval', '等待审批'],
    ['running', '执行中'],
    ['queued', '排队中'],
    ['failed', '失败'],
  ])('shows %s wording when there is no current step', async (status, expected) => {
    getTask.mockResolvedValue({ ...baseTask, status, current_step: null, error: null })
    const wrapper = await mountDetail()

    expect(wrapper.get('.summary-copy dd').text()).toBe(expected)
    wrapper.unmount()
  })

  it('polls a running task without overlap and stops at a terminal status', async () => {
    vi.useFakeTimers()
    const runningTask = { ...baseTask, status: 'running', current_step: null, error: null }
    const succeededTask = { ...baseTask, status: 'succeeded', current_step: null, error: null }
    let resolvePoll
    const pendingPoll = new Promise((resolve) => { resolvePoll = resolve })
    getTask
      .mockResolvedValueOnce(runningTask)
      .mockReturnValueOnce(pendingPoll)
      .mockResolvedValue(succeededTask)

    let wrapper
    try {
      wrapper = await mountDetail()
      expect(getTask).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(3000)
      expect(getTask).toHaveBeenCalledTimes(2)
      await vi.advanceTimersByTimeAsync(6000)
      expect(getTask).toHaveBeenCalledTimes(2)

      resolvePoll(succeededTask)
      await flushPromises()
      expect(wrapper.get('.summary-copy').text()).toContain('已完成')

      await vi.advanceTimersByTimeAsync(6000)
      expect(getTask).toHaveBeenCalledTimes(2)
    } finally {
      wrapper?.unmount()
      vi.useRealTimers()
    }
  })

  it('clears polling when the component unmounts', async () => {
    vi.useFakeTimers()
    getTask.mockResolvedValue({ ...baseTask, status: 'running', current_step: null, error: null })

    let wrapper
    try {
      wrapper = await mountDetail()
      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(6000)

      expect(getTask).toHaveBeenCalledTimes(1)
    } finally {
      wrapper?.unmount()
      vi.useRealTimers()
    }
  })

  it('supports a manual refresh', async () => {
    const wrapper = await mountDetail()

    await wrapper.get('.refresh-button').trigger('click')
    await flushPromises()

    expect(getTask).toHaveBeenCalledTimes(2)
  })

  it('shows action failures in an accessible alert', async () => {
    retryTask.mockRejectedValue(new Error('offline'))
    const wrapper = await mountDetail()

    await wrapper.get('.retry-button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.error-banner[role="alert"]').text()).toContain('重试任务失败')
  })

  it('402 积分不足显示专用文案并提供查看用量', async () => {
    retryTask.mockRejectedValue({ status: 402 })
    const wrapper = await mountDetail()

    await wrapper.get('.retry-button').trigger('click')
    await flushPromises()

    const banner = wrapper.get('.error-banner[role="alert"]')
    expect(banner.text()).toContain('积分不足，无法执行任务')
    const usageBtn = wrapper
      .findAll('button')
      .find((b) => b.text().trim() === '查看用量')
    expect(usageBtn).toBeTruthy()
    await usageBtn.trigger('click')
    expect(routerMock.push).toHaveBeenCalledWith('/usage')
  })

  it('shows a load error instead of an empty detail', async () => {
    getTask.mockRejectedValue({ status: 404 })
    const wrapper = await mountDetail()

    expect(wrapper.get('.load-error[role="alert"]').text()).toContain('任务不存在')
    expect(wrapper.find('.timeline').exists()).toBe(false)
  })
})
