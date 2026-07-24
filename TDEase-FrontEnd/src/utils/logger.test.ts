import { describe, expect, it } from 'vitest'
import { createRunLogCollapser, parseProgressLogSignature, type RunLogEntry } from './logger'

describe('logger progress folding', () => {
  it('parses tool progress lines and normalizes operation name', () => {
    const signature = parseProgressLogSignature('Additional feature search MS1 spectrum scan 2215 ...       53% finished.')
    expect(signature).toEqual({
      operation: 'Additional feature search MS1 spectrum scan',
      percent: 53,
    })
  })

  it('folds repeated same-percent progress updates', () => {
    const collapser = createRunLogCollapser()
    const logs: RunLogEntry[] = []

    collapser.append(logs, {
      timestamp: '2026-04-09T12:38:47.970177Z',
      level: 'info',
      message: 'Additional feature search MS1 spectrum scan 2215 ...       53% finished.',
    })
    collapser.append(logs, {
      timestamp: '2026-04-09T12:38:47.981079Z',
      level: 'info',
      message: 'Additional feature search MS1 spectrum scan 2216 ...       53% finished.',
    })

    expect(logs).toHaveLength(1)
    expect(logs[0]?.message).toContain('53% finished.')
    expect(logs[0]?.message).toContain('(2 updates folded)')
    expect(logs[0]?.timestamp).toBe('2026-04-09T12:38:47.981079Z')
  })

  it('keeps a single folded line when percentage changes and never folds errors', () => {
    const collapser = createRunLogCollapser()
    const logs: RunLogEntry[] = []

    collapser.append(logs, {
      timestamp: '2026-04-09T12:38:47.970177Z',
      level: 'info',
      message: 'Additional feature search MS1 spectrum scan 2215 ... 53% finished.',
    })
    collapser.append(logs, {
      timestamp: '2026-04-09T12:39:47.970177Z',
      level: 'info',
      message: 'Additional feature search MS1 spectrum scan 3215 ... 54% finished.',
    })
    collapser.append(logs, {
      timestamp: '2026-04-09T12:39:48.970177Z',
      level: 'error',
      message: 'Additional feature search failed.',
    })

    expect(logs).toHaveLength(2)
    expect(logs[0]?.message).toContain('54% finished.')
    expect(logs[0]?.message).toContain('(2 updates folded)')
    expect(logs[1]?.level).toBe('error')
  })

  it('caps log list size to avoid unbounded growth', () => {
    const collapser = createRunLogCollapser()
    const logs: RunLogEntry[] = []

    for (let i = 0; i < 2050; i += 1) {
      collapser.append(logs, {
        timestamp: `2026-04-09T12:39:${String(i % 60).padStart(2, '0')}.000Z`,
        level: 'info',
        message: `plain log ${i}`,
      })
    }

    expect(logs).toHaveLength(2000)
    expect(logs[0]?.message).toBe('plain log 50')
    expect(logs[1999]?.message).toBe('plain log 2049')
  })

  it('parses "processing X%" progress lines from TopPIC', () => {
    const signature = parseProgressLogSignature('Zero unexpected shift filtering - processing 0.0393%.')
    expect(signature).toEqual({
      operation: 'Zero unexpected shift filtering',
      percent: 0,
    })
  })

  it('parses "processing X%" with integer percent', () => {
    const signature = parseProgressLogSignature('Matching spectra - processing 50%.')
    expect(signature).toEqual({
      operation: 'Matching spectra',
      percent: 50,
    })
  })

  it('folds repeated "processing X%" updates', () => {
    const collapser = createRunLogCollapser()
    const logs: RunLogEntry[] = []

    collapser.append(logs, {
      timestamp: '2026-04-09T12:38:47.970177Z',
      level: 'info',
      message: 'Zero unexpected shift filtering - processing 0.0393%.',
    })
    collapser.append(logs, {
      timestamp: '2026-04-09T12:38:47.981079Z',
      level: 'info',
      message: 'Zero unexpected shift filtering - processing 0.0395%.',
    })

    expect(logs).toHaveLength(1)
    expect(logs[0]?.message).toContain('0% finished')
    expect(logs[0]?.message).toContain('(2 updates folded)')
    expect(logs[0]?.message).toContain('Zero unexpected shift filtering')
  })
})
