import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WorkflowPanelHeader from '../WorkflowPanelHeader.vue'

const BASE_PROPS = {
  run: {
    name: 'test-run',
    id: 'run-1',
    status: 'completed',
    shortRunId: 'run-1',
    progress: 100,
    isRunning: false,
  },
  logSyncText: 'synced',
  loadedCount: 10,
  totalCount: 10,
  issueCount: 0,
  foldedProgressCount: 0,
}

function mountHeader(overrides: Record<string, unknown> = {}) {
  return mount(WorkflowPanelHeader, {
    props: { ...BASE_PROPS, ...overrides },
    global: {
      stubs: {
        CatppuccinIcon: true,
        'el-button': true,
      },
    },
  })
}

describe('WorkflowPanelHeader — explore button', () => {
  it('shows the explore button when run status is completed', () => {
    const wrapper = mountHeader()

    expect(wrapper.find('[data-testid="panel-header-explore"]').exists()).toBe(true)
  })

  it('hides the explore button when run is still running', () => {
    const wrapper = mountHeader({
      run: { ...BASE_PROPS.run, status: 'running', isRunning: true, progress: 45 },
    })

    expect(wrapper.find('[data-testid="panel-header-explore"]').exists()).toBe(false)
  })

  it('hides the explore button when run has failed', () => {
    const wrapper = mountHeader({
      run: { ...BASE_PROPS.run, status: 'failed' },
    })

    expect(wrapper.find('[data-testid="panel-header-explore"]').exists()).toBe(false)
  })

  it('emits explore when the button is clicked', async () => {
    const wrapper = mountHeader()

    await wrapper.find('[data-testid="panel-header-explore"]').trigger('click')

    expect(wrapper.emitted('explore')).toBeTruthy()
    expect(wrapper.emitted('explore')!.length).toBe(1)
  })
})
