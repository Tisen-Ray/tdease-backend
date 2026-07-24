import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import WorkflowToolbar from '../WorkflowToolbar.vue'
import type { ExecutionStatus } from '@/utils/state-machine'
import { mount } from '@vue/test-utils'

const SOURCE = readFileSync(
  resolve(__dirname, '../WorkflowToolbar.vue'),
  'utf-8',
)

const BASE_PROPS = {
  isExecuting: false,
  isAdmin: false,
  status: 'idle' as ExecutionStatus,
  skipCompletedNodes: true,
  canStartExecution: true,
  canStopExecution: false,
  canToggleSkipCompletedNodes: true,
  runName: 'test-run',
  workspaceId: 'ws-1',
  availableWorkspaces: [],
}

function mountToolbar(overrides: Record<string, unknown> = {}) {
  return mount(WorkflowToolbar, {
    props: { ...BASE_PROPS, ...overrides },
    global: {
      stubs: {
        ThemeSwitcher: true,
        LangSwitcher: true,
        ExecutionStatusBadge: true,
        CatppuccinIcon: true,
        // el-button stub that forwards attrs (including data-testid) to the DOM
        'el-button': {
          inheritAttrs: true,
          template: '<button v-bind="$attrs"><slot /></button>',
        },
        'el-select': true,
        'el-option': true,
        'el-divider': true,
        'el-switch': true,
        'el-dropdown': {
          inheritAttrs: true,
          template: '<div v-bind="$attrs"><slot /><slot name="dropdown" /></div>',
        },
        'el-dropdown-menu': { template: '<div><slot /></div>' },
        'el-dropdown-item': {
          inheritAttrs: true,
          props: ['command'],
          template: '<div v-bind="$attrs"><slot /></div>',
        },
      },
    },
  })
}

describe('WorkflowToolbar — Copilot single-button (source contract)', () => {
  it('declares the toggle-copilot emit', () => {
    expect(SOURCE).toContain("'toggle-copilot': []")
  })

  it('has a single copilot toggle button (no dropdown split)', () => {
    expect(SOURCE).toContain('data-testid="copilot-toggle"')
    // The old dropdown design has been removed.
    expect(SOURCE).not.toContain('data-testid="copilot-dropdown"')
    expect(SOURCE).not.toContain('copilot-option-docked')
    expect(SOURCE).not.toContain('copilot-option-fullscreen')
  })

  it('uses the i18n label for the copilot toggle', () => {
    expect(SOURCE).toContain("$t('workflow.toolbar.toggleCopilot')")
  })

  it('reflects rightPanelVisible in the active class', () => {
    expect(SOURCE).toContain("'copilot-btn--active': rightPanelVisible")
  })
})

describe('WorkflowToolbar — Explore first-class entry (source contract)', () => {
  it('declares the explore emit', () => {
    expect(SOURCE).toContain('explore: []')
  })

  it('has a dedicated, always-visible Explore button with testid', () => {
    expect(SOURCE).toContain('data-testid="explore-toggle"')
    expect(SOURCE).toContain("$emit('explore')")
  })

  it('no longer hides Explore inside the More dropdown', () => {
    // The dropdown duplicate was removed to avoid two entry points.
    expect(SOURCE).not.toMatch(/command="explore"/)
  })
})

describe('WorkflowToolbar — left zone stripped of workflow ops (source contract)', () => {
  it('does not render undo/redo/auto-layout/toggle-sidebar/toggle-panel buttons', () => {
    // These moved to the canvas floating toolbar and per-panel affordances.
    expect(SOURCE).not.toContain("'$emit('undo')'")
    expect(SOURCE).not.toContain("'$emit('redo')'")
    expect(SOURCE).not.toContain("'$emit('auto-layout')'")
    expect(SOURCE).not.toContain("'$emit('toggle-sidebar')'")
    expect(SOURCE).not.toContain("'$emit('toggle-panel')'")
  })

  it('no longer accepts canUndo/canRedo props', () => {
    expect(SOURCE).not.toMatch(/\bcanUndo\b/)
    expect(SOURCE).not.toMatch(/\bcanRedo\b/)
  })
})

describe('WorkflowToolbar — right zone grouping (mounted)', () => {
  it('renders the copilot toggle button', () => {
    const wrapper = mountToolbar()
    expect(wrapper.find('[data-testid="copilot-toggle"]').exists()).toBe(true)
  })

  it('renders the explore toggle button', () => {
    const wrapper = mountToolbar()
    expect(wrapper.find('[data-testid="explore-toggle"]').exists()).toBe(true)
  })

  it('has multiple el-divider components for button group separation', () => {
    const wrapper = mountToolbar()
    const dividers = wrapper.findAllComponents({ name: 'ElDivider' })
    // At least 2 dividers separating the execution / explore+copilot / more groups
    expect(dividers.length).toBeGreaterThanOrEqual(2)
  })

  it('does not have the old hardcoded Protocol Assistant text button', () => {
    expect(SOURCE).not.toContain('>Protocol Assistant<')
  })
})
