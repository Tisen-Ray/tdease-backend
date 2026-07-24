import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import PlotlyViewer from './PlotlyViewer.vue'

const { newPlotMock, reactMock, purgeMock } = vi.hoisted(() => ({
  newPlotMock: vi.fn(),
  reactMock: vi.fn(),
  purgeMock: vi.fn(),
}))

vi.mock('plotly.js-dist-min', () => ({
  default: {
    newPlot: newPlotMock,
    react: reactMock,
    purge: purgeMock,
  },
}))

describe('PlotlyViewer', () => {
  beforeEach(() => {
    newPlotMock.mockClear()
    reactMock.mockClear()
    purgeMock.mockClear()
  })

  it('renders the backend-provided Plotly figure verbatim', async () => {
    const figure = {
      data: [{ type: 'scatter', x: [1, 2], y: [2, 4], name: 'Observed' }],
      layout: { title: 'Points' },
      config: { scrollZoom: true },
    }

    const wrapper = mount(PlotlyViewer, {
      props: { viewSpec: { figure } },
    })

    expect(wrapper.find('[data-testid="plotly-viewer"]').exists()).toBe(true)
    // No header chrome: the figure title is passed to Plotly itself, never
    // rendered as DOM text (VisContainer owns the panel title).
    expect(wrapper.text()).not.toContain('Points')
    expect(wrapper.text()).not.toContain('Plotly')
    expect(wrapper.text()).not.toContain('trace')

    await nextTick()
    await flushPromises()

    expect(newPlotMock).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      figure.data,
      expect.objectContaining({ title: 'Points' }),
      expect.objectContaining({
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
      }),
    )
  })

  it('compiles chart sugar with datasets when no figure is provided', async () => {
    mount(PlotlyViewer, {
      props: {
        viewSpec: {
          chart: { type: 'scatter', x: 'mz', y: 'intensity' },
        },
        datasets: [
          {
            id: 'peaks',
            kind: 'peak_table',
            columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
            rows: [{ mz: 500.1, intensity: 1000 }],
            label: 'Peaks',
          },
        ],
      },
    })

    await nextTick()
    await flushPromises()

    expect(newPlotMock).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      [expect.objectContaining({
        type: 'scatter',
        mode: 'markers',
        x: [500.1],
        y: [1000],
        customdata: [0],
      })],
      expect.objectContaining({
        xaxis: { title: { text: 'mz' } },
        yaxis: { title: { text: 'intensity' } },
      }),
      expect.objectContaining({ responsive: true, displaylogo: false }),
    )
  })

  it('shows empty state when no figure is provided', () => {
    const wrapper = mount(PlotlyViewer, {
      props: { viewSpec: {} },
    })

    expect(wrapper.text()).toContain('No data available for this view.')
    expect(wrapper.text()).not.toContain('Plotly')
  })

  it('updates with Plotly.react and purges on unmount', async () => {
    const wrapper = mount(PlotlyViewer, {
      props: {
        viewSpec: {
          figure: {
            data: [{ type: 'scatter', x: [1], y: [2] }],
            layout: { title: 'Initial' },
          },
        },
      },
    })
    await nextTick()
    await flushPromises()
    expect(newPlotMock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({
      viewSpec: {
        figure: {
          data: [{ type: 'scatter', x: [1, 2], y: [2, 3] }],
          layout: { title: 'Updated' },
        },
      },
    })
    await nextTick()
    await flushPromises()

    expect(reactMock).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      [{ type: 'scatter', x: [1, 2], y: [2, 3] }],
      expect.objectContaining({ title: 'Updated' }),
      expect.objectContaining({ responsive: true, displaylogo: false }),
    )

    wrapper.unmount()
    expect(purgeMock).toHaveBeenCalledWith(expect.any(HTMLElement))
  })
})
