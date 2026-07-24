/**
 * Proof of frontend diagnostics/render projection contracts from
 * `docs/specs/PRODUCT_DETAIL_CONTRACTS.md` §7.
 *
 * Primary contracts proved here:
 * - backend execution/log state is projected into actionable diagnostics
 * - failure context is rendered with copy/focus/raw-log affordances
 * - progress compaction avoids raw log spam on the workflow surface
 */
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkflowPanel from './WorkflowPanel.vue'

const { successMock, errorMock } = vi.hoisted(() => ({
  successMock: vi.fn(),
  errorMock: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: successMock,
    error: errorMock,
  },
}))

vi.mock('@/utils/error-taxonomy', () => ({
  categorizeError: vi.fn((error: { message: string; nodeId?: string }) => ({
    category: error.message.toLowerCase().includes('timeout') ? 'network' : 'execution',
    message: error.message,
    recovery: 'Retry the failed node',
    nodeId: error.nodeId,
  })),
}))

const ErrorDiagnosticEntryStub = defineComponent({
  name: 'ErrorDiagnosticEntry',
  props: {
    category: { type: String, required: true },
    message: { type: String, required: true },
    recovery: { type: String, required: true },
  },
  setup(props, { slots }) {
    return () => h('div', { class: 'error-diagnostic-entry' }, [
      `${props.category} | ${props.message} | ${props.recovery}`,
      slots.default?.(),
    ])
  },
})

const ElCollapseStub = defineComponent({
  name: 'ElCollapseStub',
  setup(_, { slots }) {
    return () => h('div', { class: 'el-collapse' }, slots.default?.())
  },
})

const ElCollapseItemStub = defineComponent({
  name: 'ElCollapseItemStub',
  props: { title: { type: String, default: '' } },
  setup(props, { slots }) {
    return () => h('div', { class: 'el-collapse-item' }, [
      h('div', { class: 'el-collapse-item__header' }, props.title),
      h('div', { class: 'el-collapse-item__content' }, slots.default?.()),
    ])
  },
})

type WorkflowLog = {
  timestamp: string
  level: string
  message: string
  node_id?: string
  metadata?: Record<string, unknown>
}

const defaultRun = { name: 'run-1', id: 'r78', status: 'running', optimisticStatus: null, progress: 0, isRunning: true }

function mountWorkflowPanel(runLogs: WorkflowLog[], extraProps: Record<string, unknown> = {}) {
  const { run: runOverrides, ...otherProps } = extraProps
  return mount(WorkflowPanel, {
    props: {
      visible: true,
      height: 240,
      run: { ...defaultRun, ...(runOverrides as Record<string, unknown> | undefined) },
      runLogTotal: runLogs.length,
      runProgressItems: [],
      hasMoreLogs: false,
      isLoadingMoreLogs: false,
      monitorTransportState: 'live',
      runLogs,
      ...otherProps,
    },
    attachTo: document.body,
    global: {
      stubs: {
        'el-button': defineComponent({
          name: 'ElButtonStub',
          emits: ['click'],
          setup(_, { slots, emit, attrs }) {
            return () => h('button', { ...attrs, onClick: () => emit('click') }, slots.default?.())
          },
        }),
        'el-tag': defineComponent({
          name: 'ElTagStub',
          setup(_, { slots }) {
            return () => h('span', { class: 'el-tag' }, slots.default?.())
          },
        }),
        'el-collapse': ElCollapseStub,
        'el-collapse-item': ElCollapseItemStub,
        CatppuccinIcon: true,
        ErrorDiagnosticEntry: ErrorDiagnosticEntryStub,
      },
    },
  })
}

describe('WorkflowPanel diagnostics rendering', () => {
  const clipboardWriteText = vi.fn()

  beforeEach(() => {
    clipboardWriteText.mockReset()
    successMock.mockReset()
    errorMock.mockReset()
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWriteText,
      },
    })
  })

  it('renders empty diagnostics state when run logs have no error entries', () => {
    const wrapper = mountWorkflowPanel([
      { timestamp: '2026-01-01T00:00:00Z', level: 'info', message: 'Started' },
    ])

    expect(wrapper.text()).toContain('No errors detected')
    expect(wrapper.findAll('.error-diagnostic-entry')).toHaveLength(0)
  })

  it('renders compacted progress phases without raw log spam', () => {
    const wrapper = mountWorkflowPanel([], {
      runProgressItems: [
        {
          key: 'node-1:sample-1:search',
          nodeId: 'node-1',
          rowId: 'sample-1',
          phase: 'Searching spectra',
          current: 120,
          total: 300,
          percent: 40,
          foldCount: 38,
        },
      ],
    })

    expect(wrapper.text()).toContain('Searching spectra')
    expect(wrapper.text()).toContain('node-1')
    expect(wrapper.text()).toContain('sample-1')
    expect(wrapper.text()).toContain('40%')
    expect(wrapper.text()).toContain('38 folded')
    expect(wrapper.findAll('.log-line')).toHaveLength(0)
  })

  it('renders actionable failure cards with category, impact, next action, and scope', () => {
    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'error',
        message: 'Command failed with exit code 2; stderr tail: missing input file',
        node_id: 'node-cli',
        metadata: {
          row_id: 'sample-1',
        command: 'td-ease-cli run --input workspace://data/raw/a.raw',
          stderr: 'missing input file',
        },
      },
    ], { run: { status: 'failed', isRunning: false } })

    expect(wrapper.text()).toContain('Failed')
    expect(wrapper.text()).toContain('Missing path')
    expect(wrapper.text()).toContain('Impact')
    expect(wrapper.text()).toContain('Next')
    expect(wrapper.text()).toContain('run run-1')
    expect(wrapper.text()).toContain('row sample-1')
    expect(wrapper.text()).toContain('Executable failure')
    expect(wrapper.text()).toContain('exit 2')
    expect(wrapper.find('.debug-console').exists()).toBe(true)
    expect(wrapper.text()).toContain('Command')
    expect(wrapper.text()).toContain('stderr tail')
  })

  it('distinguishes retryable and cancelled states in the card surface', async () => {
    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'error',
        message: 'Timeout while contacting worker; will retry',
        node_id: 'node-1',
      },
    ], { run: { status: 'failed', isRunning: false } })

    expect(wrapper.text()).toContain('Retryable')
    expect(wrapper.find('.failure-card').classes()).toContain('failure-card--retryable')

    await wrapper.setProps({ run: { status: 'cancelled', isRunning: false, name: 'run-1', id: 'r78', optimisticStatus: null, progress: 0 } })
    expect(wrapper.text()).toContain('Cancelled')
    expect(wrapper.find('.failure-card').classes()).toContain('failure-card--cancelled')
  })

  it('focuses the failure card when the user requests log focus', async () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'error',
        message: 'Command failed with exit code 2; stderr tail: missing input file',
        node_id: 'node-cli',
        metadata: {
          row_id: 'sample-1',
          stderr: 'missing input file',
        },
      },
      {
        timestamp: '2026-01-01T00:00:01Z',
        level: 'info',
        message: 'raw stderr follows',
        node_id: 'node-cli',
      },
    ], { run: { status: 'failed', isRunning: false } })

    const focusButton = wrapper.findAll('button').find((candidate) => candidate.text() === 'Focus logs')
    expect(focusButton).toBeTruthy()
    await focusButton!.trigger('click')

    expect(scrollIntoView).toHaveBeenCalled()
    expect(wrapper.find('.failure-card').attributes('data-log-target')).toBe('details:node-cli:2026-01-01T00:00:00Z')
  })

  it('expands raw log context for the current failure', async () => {
    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'error',
        message: 'Command failed with exit code 2; stderr tail: missing input file',
        node_id: 'node-cli',
        metadata: {
          row_id: 'sample-1',
        command: 'td-ease-cli run --input workspace://data/raw/a.raw',
          stderr: 'missing input file',
          execution_epoch: 3,
        },
      },
    ], { run: { status: 'failed', isRunning: false } })

    const rawButton = wrapper.findAll('button').find((candidate) => candidate.text() === 'Raw log')
    expect(rawButton).toBeTruthy()
    await rawButton!.trigger('click')

    expect(wrapper.text()).toContain('Hide raw log')
    expect(wrapper.text()).toContain('"execution_epoch": 3')
    expect(wrapper.text()).toContain('Command failed with exit code 2; stderr tail: missing input file')
  })

  it('shows the latest command trace on the current run surface', () => {
    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'info',
        message: '[command_trace] trace',
        node_id: 'node-cli',
        metadata: {
          kind: 'input',
          visibility: 'collapsed',
          source: 'cmd_trace',
          command_trace: {
            cmd_parts: ['td-ease-cli', 'run'],
            node_id: 'node-cli',
          },
        },
      },
      {
        timestamp: '2026-01-01T00:00:01Z',
        level: 'error',
        message: 'Command failed with exit code 2; stderr tail: missing input file',
        node_id: 'node-cli',
        metadata: {
          row_id: 'sample-1',
        command: 'td-ease-cli run --input workspace://data/raw/a.raw',
          stderr: 'missing input file',
        },
      },
    ], { run: { status: 'failed', isRunning: false } })

    expect(wrapper.text()).toContain('Command trace')
    expect(wrapper.text()).toContain('td-ease-cli run')
    expect(wrapper.text()).toContain('trace json')
  })

  it('copies a diagnostic bundle with run, node, sample, and transport metadata', async () => {
    clipboardWriteText.mockResolvedValue(undefined)

    const wrapper = mountWorkflowPanel([
      {
        timestamp: '2026-01-01T00:00:00Z',
        level: 'error',
        message: 'Command failed with exit code 2; stderr tail: missing input file',
        node_id: 'node-cli',
        metadata: {
          row_id: 'sample-1',
        command: 'td-ease-cli run --input workspace://data/raw/a.raw',
          stderr: 'missing input file',
        },
      },
    ], {
      run: { status: 'failed', isRunning: false },
      monitorTransportState: 'terminal-flush',
    })

    const copyButton = wrapper.findAll('button').find((candidate) => candidate.text() === 'Copy bundle')
    expect(copyButton).toBeTruthy()
    await copyButton!.trigger('click')

    expect(clipboardWriteText).toHaveBeenCalledTimes(1)
    const bundle = clipboardWriteText.mock.calls[0][0] as string
    expect(bundle).toContain('run_id: r78')
    expect(bundle).toContain('node_id: node-cli')
    expect(bundle).toContain('row_id: sample-1')
    expect(bundle).toContain('monitor_transport: terminal-flush')
    expect(successMock).toHaveBeenCalledWith('已复制到剪贴板')
  })
})
