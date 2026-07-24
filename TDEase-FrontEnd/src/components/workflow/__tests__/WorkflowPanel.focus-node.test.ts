import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WorkflowPanel from '../WorkflowPanel.vue'
import type { WorkflowFailureLogTarget } from '@/utils/workflow-diagnostics'

/**
 * Lightweight factory that stubs every child component so we can isolate
 * the emit-forwarding behavior of WorkflowPanel itself.
 *
 * The test simulates WorkflowDiagnosticsList emitting `focus-target`,
 * then asserts WorkflowPanel re-emits `focus-node` with the node id so the
 * parent page can select the failed node on the canvas.
 */
function mountPanel() {
  return mount(WorkflowPanel, {
    props: {
      visible: true,
      height: 300,
      run: {
        name: 'test-run',
        id: 'run-1',
        status: 'failed',
        optimisticStatus: null,
        progress: 0,
        isRunning: false,
      },
      runProgressItems: [],
      runLogs: [],
      runLogTotal: 0,
      hasMoreLogs: false,
      isLoadingMoreLogs: false,
    },
    global: {
      stubs: {
        WorkflowPanelHeader: true,
        WorkflowDebugConsole: true,
        WorkflowProgressFolds: true,
        WorkflowDiagnosticsList: true,
        WorkflowCollapsedLogGroup: true,
        CatppuccinIcon: true,
        // Element Plus
        'el-button': true,
        'el-alert': true,
      },
    },
  })
}

describe('WorkflowPanel — focus-node forwarding', () => {
  it('emits focus-node with nodeId when a failure target is focused', async () => {
    const wrapper = mountPanel()

    const target: WorkflowFailureLogTarget = {
      nodeId: 'node-topfic',
      section: 'diagnostics',
      key: 'diag-node-toppic',
      timestamp: '2026-07-10T12:00:00Z',
    }

    // WorkflowDiagnosticsList emits `focus-target` upward
    wrapper.findComponent({ name: 'WorkflowDiagnosticsList' }).vm.$emit('focus-target', target)

    await wrapper.vm.$nextTick()

    const focusNodeEvents = wrapper.emitted('focus-node')
    expect(focusNodeEvents).toBeTruthy()
    expect(focusNodeEvents![0]).toEqual(['node-topfic'])
  })

  it('does not emit focus-node when target has no nodeId', async () => {
    const wrapper = mountPanel()

    const target: WorkflowFailureLogTarget = {
      nodeId: undefined,
      section: 'diagnostics',
      key: 'diag-generic',
      timestamp: '2026-07-10T12:00:00Z',
    }

    wrapper.findComponent({ name: 'WorkflowDiagnosticsList' }).vm.$emit('focus-target', target)

    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('focus-node')).toBeFalsy()
  })
})
