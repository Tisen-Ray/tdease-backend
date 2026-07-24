import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import VisContainer from '@/components/visualization/VisContainer.vue'
import type { TableData } from '@/types/visualization'

function buildTableData(): TableData {
  return {
    columns: [
      {
        id: 'value',
        name: 'value',
        type: 'number',
        visible: true,
        sortable: true,
        filterable: true,
      },
    ],
    rows: [{ value: 1 }],
    totalRows: 1,
    sourceFile: 'node.tsv',
  }
}

describe('VisContainer', () => {
  it('isolates viewer crash with boundary fallback and supports retry', async () => {
    const CrashViewer = defineComponent({
      name: 'CrashViewer',
      // eslint-disable-next-line vue/require-render-return
      render() {
        throw new Error('viewer crash')
      },
    })

    const wrapper = mount(VisContainer, {
      props: {
        label: 'Node',
        visualizationType: 'table',
        data: buildTableData(),
        loadingState: { status: 'success' },
        hasUpstreamConnection: true,
      },
      global: {
        stubs: {
          teleport: true,
          transition: false,
          ColumnConfigPanel: true,
          'el-tag': true,
          'el-icon': true,
          'el-tooltip': { template: '<div><slot /></div>' },
          'el-drawer': { template: '<div><slot /></div>' },
          'el-button': { template: '<button><slot /></button>' },
        },
      },
      slots: {
        default: () => h(CrashViewer),
      },
    })

    await nextTick()
    // Fallback message comes from i18n key visualization.viewer.renderFailed
    expect(wrapper.text()).toContain('此可视化渲染失败。')

    const retryButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('重试'))
    expect(retryButton).toBeDefined()
    await retryButton?.trigger('click')

    const emitted = wrapper.emitted('reload') || []
    expect(emitted.length).toBeGreaterThan(0)
  })
})
