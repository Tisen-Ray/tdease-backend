import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it } from 'vitest'

import type { RunConfigDocument, RunInputsDocument, RunPreflightResult } from '@/services/api/run'
import RunSetupView from './RunSetupView.vue'

const passthrough = (tag: string) => defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h(tag, attrs, slots.default?.())
  },
})

const allSlotsPassthrough = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('div', attrs, Object.values(slots).flatMap((slot) => slot?.() ?? []))
  },
})

const FilePickerStub = defineComponent({
  name: 'RunInputFilePicker',
  props: {
    modelValue: { type: String, required: true },
    accept: { type: Array, default: () => [] },
  },
  setup(props) {
    return () => h('div', { class: 'file-picker-stub' }, props.modelValue)
  },
})

const inputs: RunInputsDocument = {
  schema: 'tdease.run-inputs/v1',
  revision: 1,
  workflowDigest: 'sha256:workflow',
  requirements: [{
    requirementId: 'loader-primary',
    instancePath: [],
    nodeId: 'loader-primary',
    alias: 'Primary spectra',
    dataType: 'raw',
    accept: ['raw'],
  }],
  rows: [{
    rowId: 'default',
    label: 'Default',
    coordinates: {},
    configVariantId: 'default',
    bindings: {
      'loader-primary': { source: { kind: 'workspace-file', path: 'data/sample.raw' } },
    },
  }],
  orphans: [],
  frozenAt: null,
}

const config: RunConfigDocument = {
  schema: 'tdease.run-config/v2',
  defaultVariantId: 'default',
  variants: [{ variantId: 'default', label: 'Default', params: {} }],
}

const preflight: RunPreflightResult = {
  schema: 'tdease.run-preflight/v1',
  ok: true,
  revision: 1,
  issues: [],
}

describe('RunSetupView', () => {
  it('renders one rows-by-loader table with scalar bindings', async () => {
    const wrapper = mount(RunSetupView, {
      props: {
        runId: 'run-1',
        runName: 'Run 1',
        description: '',
        templateName: 'Template',
        workspaceId: 'workspace-1',
        userId: 'user-1',
        inputs,
        config,
        preflight,
        loading: false,
        saveState: 'saved',
        error: null,
        readOnly: false,
      },
      global: {
        stubs: {
          RunInputFilePicker: FilePickerStub,
          'el-input': passthrough('div'),
          'el-button': passthrough('button'),
          'el-option': passthrough('option'),
          'el-select': passthrough('select'),
          'el-dropdown': allSlotsPassthrough,
          'el-dropdown-menu': passthrough('div'),
          'el-dropdown-item': passthrough('el-dropdown-item'),
          'el-dialog': allSlotsPassthrough,
        },
      },
    })

    expect(wrapper.findComponent({ name: 'RequirementLabel' }).props('requirement'))
      .toMatchObject({ alias: 'Primary spectra' })
    expect(wrapper.find('.run-setup__shared-grid').exists()).toBe(false)
    expect(wrapper.find('.run-setup__requirement-strip').exists()).toBe(false)
    expect(wrapper.find('.run-setup__coordinates-column').exists()).toBe(false)
    expect(wrapper.find('.run-setup__variant-column').exists()).toBe(false)
    expect(wrapper.find('.run-setup__preflight').exists()).toBe(false)
    expect(wrapper.get('[data-testid="run-input-status"]').classes())
      .toContain('run-setup__preflight-chip--ready')

    const picker = wrapper.findComponent({ name: 'RunInputFilePicker' })
    expect(picker.props('modelValue')).toBe('data/sample.raw')
    expect(picker.props()).not.toHaveProperty('multiple')

    const rowActions = wrapper.findAll('el-dropdown-item')
    expect(rowActions).toHaveLength(3)
    expect(rowActions.at(-1)?.attributes('disabled')).toBeDefined()
    await rowActions.at(-1)!.trigger('click')
    expect(wrapper.emitted('update:inputs')).toBeUndefined()

    await wrapper.setProps({ inputs: { ...inputs, requirements: [] } })
    const emptyStatus = wrapper.get('[data-testid="run-input-status"]')
    expect(emptyStatus.classes()).not.toContain('run-setup__preflight-chip--ready')
    expect(emptyStatus.text()).toContain('没有数据加载节点')

    await wrapper.setProps({ inputs: null, error: 'inputs request failed' })
    expect(wrapper.get('[role="alert"]').text()).toContain('inputs request failed')
  })
})
