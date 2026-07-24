import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

const { ms2SequenceProps } = vi.hoisted(() => ({
  ms2SequenceProps: [] as Array<Record<string, unknown>>,
}))

vi.mock('@/components/visualization/MS2SequenceViewer.vue', () => ({
  default: defineComponent({
    name: 'MS2SequenceViewerStub',
    props: ['data', 'config', 'selection'],
    emits: ['selectionChange', 'configChange'],
    setup(props) {
      ms2SequenceProps.push(props as unknown as Record<string, unknown>)
      return () => h('div', { class: 'ms2-sequence-viewer-stub' })
    },
  }),
}))

describe('MS2SpectrumViewer', () => {
  beforeEach(() => {
    ms2SequenceProps.length = 0
  })

  it('adapts unified PRSM datasets into the fixed D3 MS2 sequence viewer', async () => {
    const MS2SpectrumViewer = (await import('@/components/visualization/MS2SpectrumViewer.vue')).default
    mount(MS2SpectrumViewer, {
      props: {
        datasets: [
          {
            id: 'prsm',
            kind: 'table',
            columns: [
              { name: 'Prsm ID', type: 'integer' as const },
              { name: 'Spectrum ID', type: 'integer' as const },
              { name: 'Proteoform', type: 'string' as const },
            ],
            rows: [
              { 'Prsm ID': 12, 'Spectrum ID': 88, Proteoform: 'PEPTIDE' },
            ],
          },
        ],
      },
    })

    await nextTick()
    const data = ms2SequenceProps.at(-1)?.data as Record<string, unknown>
    expect(data).toMatchObject({
      totalRows: 1,
      sourceFile: 'prsm',
      rows: [{ 'Prsm ID': 12, 'Spectrum ID': 88, Proteoform: 'PEPTIDE' }],
    })
  })
})
