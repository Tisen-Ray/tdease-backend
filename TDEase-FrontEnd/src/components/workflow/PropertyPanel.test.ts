import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PropertyPanel from './PropertyPanel.vue'

const updateNodeMock = vi.fn()

vi.mock('@/stores/workflow', () => ({
  useWorkflowStore: () => ({
    updateNode: updateNodeMock,
  }),
}))

const registry = ref([
  {
    id: 'topfd',
    name: 'TopFD',
    command: { executable: 'topfd' },
    ports: {
      inputs: [{ id: 'input_files', name: 'mzML Files', dataType: 'mzml', required: true }],
      outputs: [{ id: 'ms1feature', name: 'MS1 Feature', dataType: 'feature', pattern: '{sample}_ms1.feature' }],
    },
    parameters: {
      activation: {
        type: 'choice',
        label: 'Activation',
        group: 'basic',
        choices: ['FILE', 'HCD'],
        default: 'FILE',
      },
      thread_number: {
        type: 'value',
        label: 'Thread Number',
        group: 'basic',
        default: '16',
      },
      verbose: {
        type: 'boolean',
        label: 'Verbose',
        group: 'advanced',
        default: false,
      },
      runtime_path: {
        type: 'value',
        label: 'Runtime path',
        group: 'system',
        materialized: true,
      },
    },
    output: { flagSupported: false },
  },
])

vi.mock('@/services/tools/registry', () => ({
  useToolsRegistry: () => registry,
  isToolsRegistryLoaded: ref(true),
  ensureToolsLoaded: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    currentWorkspaceId: null,
  }),
}))

vi.mock('@/services/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ command: 'topfd -u 16' }),
  },
}))

const passthrough = (tag: string) =>
  defineComponent({
    name: `${tag}-stub`,
    setup(_, { slots }) {
      return () => h(tag, slots.default?.())
    },
  })

describe('PropertyPanel', () => {
  afterEach(() => {
    updateNodeMock.mockReset()
    vi.useRealTimers()
  })

  it('renders a human-readable summary and autosaves edits', async () => {
    vi.useFakeTimers()

    const wrapper = mount(PropertyPanel, {
      props: {
        selectedNode: {
          id: 'node-1',
          type: 'tool',
          position: { x: 0, y: 0 },
          displayProperties: { label: 'TopFD step', color: '#409eff' },
          inputs: [],
          outputs: [],
          params: {
            activation: 'HCD',
            thread_number: '16',
            verbose: false,
            runtime_path: '/workspace/private.raw',
          },
          nodeConfig: {
            toolId: 'topfd',
          },
        },
      },
      global: {
        stubs: {
          CatppuccinIcon: true,
          VariantListParam: true,
          'el-form': passthrough('form'),
          'el-form-item': defineComponent({
            name: 'ElFormItemStub',
            setup(_, { slots }) {
              return () => h('label', [slots.label?.(), slots.default?.()])
            },
          }),
          'el-collapse': passthrough('div'),
          'el-collapse-item': passthrough('div'),
          'el-button': passthrough('button'),
          'el-tag': passthrough('span'),
          'el-text': passthrough('span'),
          'el-select': defineComponent({
            name: 'ElSelectStub',
            props: ['modelValue'],
            emits: ['update:modelValue'],
            setup(props, { emit, slots }) {
              return () =>
                h(
                  'select',
                  {
                    value: props.modelValue,
                    onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value),
                  },
                  slots.default?.(),
                )
            },
          }),
          'el-option': defineComponent({
            name: 'ElOptionStub',
            props: ['label', 'value'],
            setup(props) {
              return () => h('option', { value: props.value }, props.label)
            },
          }),
          'el-input': defineComponent({
            name: 'ElInputStub',
            props: ['modelValue', 'type', 'rows', 'placeholder', 'readonly'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () =>
                props.type === 'textarea'
                  ? h('textarea', {
                      value: props.modelValue,
                      placeholder: props.placeholder,
                      readOnly: props.readonly,
                      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
                    })
                  : h('input', {
                      value: props.modelValue,
                      placeholder: props.placeholder,
                      readOnly: props.readonly,
                      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
                    })
            },
          }),
          'el-input-number': defineComponent({
            name: 'ElInputNumberStub',
            props: ['modelValue'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () =>
                h('input', {
                  type: 'number',
                  value: props.modelValue,
                  onInput: (event: Event) => emit('update:modelValue', Number((event.target as HTMLInputElement).value)),
                })
            },
          }),
          'el-switch': defineComponent({
            name: 'ElSwitchStub',
            props: ['modelValue'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () =>
                h('input', {
                  type: 'checkbox',
                  checked: props.modelValue,
                  onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
                })
            },
          }),
          'el-color-picker': defineComponent({
            name: 'ElColorPickerStub',
            props: ['modelValue'],
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () =>
                h('input', {
                  type: 'color',
                  value: props.modelValue,
                  onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
                })
            },
          }),
          'el-slider': true,
        },
      },
    })

    vi.runAllTimers()
    await Promise.resolve()

    expect(wrapper.text()).toContain('TopFD 已设置 3 项参数')
    expect(wrapper.text()).toContain('Activation HCD')
    expect(wrapper.text()).toContain('Thread Number 16')
    expect(wrapper.text()).not.toContain('Runtime path')

    const labelInput = wrapper.find('input[placeholder="默认继承工具名称"]')
    await labelInput.setValue('TopFD stage A')
    vi.runAllTimers()
    await Promise.resolve()

    expect(updateNodeMock).toHaveBeenCalled()
    expect(updateNodeMock.mock.calls[updateNodeMock.mock.calls.length - 1]?.[1]).toMatchObject({
      displayProperties: expect.objectContaining({
        label: 'TopFD stage A',
      }),
      params: expect.objectContaining({ thread_number: '16' }),
    })
    expect(updateNodeMock.mock.calls[updateNodeMock.mock.calls.length - 1]?.[1]?.params)
      .not.toHaveProperty('runtime_path')
    expect(updateNodeMock.mock.calls[updateNodeMock.mock.calls.length - 1]?.[1])
      .not.toHaveProperty('data')
  })
})
