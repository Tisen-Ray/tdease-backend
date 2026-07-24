import { describe, expect, it } from 'vitest'

import {
  getDefaultConfig,
  getVisualization,
  getVisualizationComponent,
  getVisualizationTypes,
  hasVisualization,
  listVisualizations,
  listVisualizationsByCategory,
  registerVisualization,
  unregisterVisualization,
  validateConfig,
} from './registry'

describe('visualization registry', () => {
  it('exposes built-in visualizations through the registry', () => {
    const table = getVisualization('table')

    expect(table?.id).toBe('builtin.table')
    expect(table?.kind).toBe('frontend-view')
    expect(table?.slot).toBe('visualization')
  })

  it('returns visualization metadata helpers', () => {
    expect(getVisualizationTypes()).toContain('featuremap')
    expect(listVisualizationsByCategory('scientific').length).toBeGreaterThan(0)
    expect(getDefaultConfig('table')).toMatchObject({ pageSize: 50 })
    expect(getVisualizationComponent('spectrum')).toBeTruthy()
  })

  it('hasVisualization returns boolean presence', () => {
    expect(hasVisualization('table')).toBe(true)
    expect(hasVisualization('non-existent')).toBe(false)
  })

  it('listVisualizations returns all built-in visualizations', () => {
    const all = listVisualizations()
    expect(all.length).toBeGreaterThanOrEqual(7)
    expect(all.map((v) => v.type)).toContain('featuremap')
    expect(all.map((v) => v.type)).toContain('spectrum')
  })

  it('validateConfig with unknown type returns invalid', () => {
    const result = validateConfig('non-existent' as any, {})
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toMatch(/Unknown visualization type/)
  })

  it('validateConfig with known type returns valid by default', () => {
    const result = validateConfig('table', { pageSize: 100 })
    expect(result.valid).toBe(true)
  })

  it('registerVisualization adds and can override', () => {
    const custom = {
      id: 'custom.table',
      version: '1.0.0',
      kind: 'frontend-view' as const,
      slot: 'visualization' as const,
      type: 'table' as const,
      label: 'Custom Table',
      component: {} as any,
    }

    registerVisualization(custom)
    const retrieved = getVisualization('table')
    expect(retrieved?.id).toBe('custom.table')
    expect(retrieved?.label).toBe('Custom Table')

    // Cleanup: restore built-in
    unregisterVisualization('table')
  })

  it('unregisterVisualization removes and returns success', () => {
    expect(unregisterVisualization('non-existent')).toBe(false)
  })

  it('getVisualization returns undefined for unknown type', () => {
    expect(getVisualization('non-existent')).toBeUndefined()
  })

  it('getDefaultConfig returns undefined for unknown type', () => {
    expect(getDefaultConfig('non-existent' as any)).toBeUndefined()
  })

  it('getVisualizationComponent returns undefined for unknown type', () => {
    expect(getVisualizationComponent('non-existent' as any)).toBeUndefined()
  })
})
