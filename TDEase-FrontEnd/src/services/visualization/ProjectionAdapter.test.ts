import { describe, expect, it } from 'vitest'
import { projectFromConfig } from './ProjectionAdapter'
import type { ProjectionConfig } from '@/types/visualization'

describe('projectFromConfig', () => {
  it('maps fragment_spectrum dataMapping.datasets into role-specific datasets', () => {
    const config: ProjectionConfig = {
      viewer: 'fragment_spectrum',
      version: 1,
      dataMapping: {
        datasets: [
          {
            source: 'peaks',
            kind: 'peak_table',
            mapping: { x: 'mass', y: 'intensity' },
            direction: 'up',
            color: '#1e66f5',
            label: 'Observed peaks',
          },
          {
            source: 'ions',
            kind: 'annotation_table',
            mapping: {},
          },
          {
            source: 'ions',
            kind: 'error_scatter',
            mapping: { x: 'position', y: 'ppm_error' },
            direction: 'down',
          },
        ],
      },
      viewSpec: { activationType: 'ETD', tolerancePpm: 10 },
    }

    const viewerInput = projectFromConfig(config, {
      tables: [
        {
          id: 'peaks',
          columns: [
            { name: 'mass', type: 'number' },
            { name: 'intensity', type: 'number' },
          ],
          rows: [{ mass: 501.2, intensity: 1000 }],
        },
        {
          id: 'ions',
          columns: [
            { name: 'ion_type', type: 'string' },
            { name: 'position', type: 'integer' },
            { name: 'ppm_error', type: 'number' },
          ],
          rows: [{ ion_type: 'b', position: 4, ppm_error: -1.2 }],
        },
      ],
    })

    expect(viewerInput.viewer).toBe('fragment_spectrum')
    expect(viewerInput.viewSpec).toEqual({ activationType: 'ETD', tolerancePpm: 10 })
    expect(viewerInput.datasets).toHaveLength(3)
    expect(viewerInput.datasets[0]).toMatchObject({
      id: 'peaks',
      kind: 'peak_table',
      direction: 'up',
      color: '#1e66f5',
      label: 'Observed peaks',
      columns: [
        { name: 'mass', type: 'number' },
        { name: 'intensity', type: 'number' },
        { name: 'x', type: 'number' },
        { name: 'y', type: 'integer' },
      ],
      rows: [{ mass: 501.2, intensity: 1000, x: 501.2, y: 1000 }],
    })
    expect(viewerInput.datasets[1]).toMatchObject({
      id: 'ions',
      kind: 'annotation_table',
      columns: [
        { name: 'ion_type', type: 'string' },
        { name: 'position', type: 'integer' },
        { name: 'ppm_error', type: 'number' },
      ],
      rows: [{ ion_type: 'b', position: 4, ppm_error: -1.2 }],
    })
    expect(viewerInput.datasets[2]).toMatchObject({
      id: 'ions',
      kind: 'error_scatter',
      direction: 'down',
      columns: [
        { name: 'ion_type', type: 'string' },
        { name: 'position', type: 'integer' },
        { name: 'ppm_error', type: 'number' },
        { name: 'x', type: 'integer' },
        { name: 'y', type: 'number' },
      ],
      rows: [{ ion_type: 'b', position: 4, ppm_error: -1.2, x: 4, y: -1.2 }],
    })
  })

  it('maps two-dataset spectrum mirrors from source table names', () => {
    const config: ProjectionConfig = {
      viewer: 'spectrum',
      version: 1,
      dataMapping: {
        datasets: [
          {
            source: 'experimental_peaks',
            kind: 'peak_table',
            mapping: { x: 'mz', y: 'intensity' },
            direction: 'up',
            label: 'Experimental',
          },
          {
            source: 'theoretical_peaks',
            kind: 'peak_table',
            mapping: { x: 'theoretical_mz', y: 'relative_intensity' },
            direction: 'down',
            label: 'Theoretical',
          },
        ],
      },
      viewSpec: { title: 'Envelope mirror' },
    }

    const viewerInput = projectFromConfig(config, {
      tables: [
        {
          name: 'experimental_peaks',
          rows: [{ mz: 600.1, intensity: 900 }],
        },
        {
          name: 'theoretical_peaks',
          rows: [{ theoretical_mz: 600.2, relative_intensity: 0.9 }],
        },
      ],
    })

    expect(viewerInput.datasets).toEqual([
      {
        id: 'experimental_peaks',
        kind: 'peak_table',
        columns: [
          { name: 'mz', type: 'number' },
          { name: 'intensity', type: 'number' },
          { name: 'x', type: 'number' },
          { name: 'y', type: 'number' },
        ],
        rows: [{ mz: 600.1, intensity: 900, x: 600.1, y: 900 }],
        direction: 'up',
        label: 'Experimental',
      },
      {
        id: 'theoretical_peaks',
        kind: 'peak_table',
        columns: [
          { name: 'theoretical_mz', type: 'number' },
          { name: 'relative_intensity', type: 'number' },
          { name: 'x', type: 'number' },
          { name: 'y', type: 'number' },
        ],
        rows: [{ theoretical_mz: 600.2, relative_intensity: 0.9, x: 600.2, y: 0.9 }],
        direction: 'down',
        label: 'Theoretical',
      },
    ])
    expect(viewerInput.viewSpec).toEqual({ title: 'Envelope mirror' })
  })

  it('preserves existing table fallback behavior for simple mappings', () => {
    const viewerInput = projectFromConfig({
      viewer: 'spectrum',
      version: 1,
      dataMapping: { x: 'mz', y: 'intensity' },
      viewSpec: {},
    }, {
      tables: [
        {
          id: 'default',
          columns: [{ name: 'mz', type: 'number' }],
          rows: [{ mz: 500, intensity: 100 }],
        },
      ],
    })

    expect(viewerInput.datasets).toEqual([
      {
        id: 'default',
        kind: 'table',
        columns: [{ name: 'mz', type: 'number' }],
        rows: [{ mz: 500, intensity: 100 }],
      },
    ])
  })
})
