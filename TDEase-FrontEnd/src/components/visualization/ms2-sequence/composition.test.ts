import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadMs2CompositionInput, resolveMs2SelectionContext } from './composition'

const { getArtifactEntriesMock } = vi.hoisted(() => ({
  getArtifactEntriesMock: vi.fn(),
}))

vi.mock('@/services/api/interactive-artifacts', () => ({
  getArtifactEntries: getArtifactEntriesMock,
}))

const peaksResponse = () => ({
  entries: [
    {
      peaks: [
        { mass: 100.1, intensity: 50, charge: 1 },
        { mass: 101.2, intensity: 75, charge: 2 },
      ],
    },
  ],
})

beforeEach(() => {
  getArtifactEntriesMock.mockReset()
  getArtifactEntriesMock.mockResolvedValue(peaksResponse())
})

describe('resolveMs2SelectionContext', () => {
  it('prefers identity-first selectedRefs', () => {
    const context = resolveMs2SelectionContext(
      [
        { 'Prsm ID': '1', Proteoform: 'A' },
        { 'Prsm ID': '2', Proteoform: 'B' },
      ],
      { selectedRefs: [{ field: 'Prsm ID', value: '2' }], selectedIndices: new Set<number>() } as any,
    )

    expect(context.selectedPrsmId).toBe(2)
    expect(context.selectedRow).toMatchObject({ 'Prsm ID': '2' })
  })

  it('falls back to row-index selections for compatibility', () => {
    const context = resolveMs2SelectionContext(
      [
        { 'Prsm ID': '10' },
        { 'Prsm ID': '20' },
      ],
      { selectedIndices: new Set<number>([1]), selectedRefs: [] } as any,
    )

    expect(context.selectedPrsmId).toBe(20)
    expect(context.selectedRow).toMatchObject({ 'Prsm ID': '20' })
  })

  it('treats out-of-range numeric selections as PrSM IDs', () => {
    const context = resolveMs2SelectionContext(
      [
        { 'Prsm ID': '10' },
        { 'Prsm ID': '20' },
      ],
      { selectedIndices: new Set<number>([20]), selectedRefs: [] } as any,
    )

    expect(context.selectedPrsmId).toBe(20)
    expect(context.selectedRow).toMatchObject({ 'Prsm ID': '20' })
  })

  it('accepts legacy selectedRef val fields', () => {
    const context = resolveMs2SelectionContext(
      [
        { 'Prsm ID': '1', Proteoform: 'A' },
        { 'Prsm ID': '2', Proteoform: 'B' },
      ],
      { selectedRefs: [{ field: 'Prsm ID', val: '2' }], selectedIndices: new Set<number>() } as any,
    )

    expect(context.selectedPrsmId).toBe(2)
    expect(context.selectedRow).toMatchObject({ 'Prsm ID': '2' })
  })

  it('defaults to the first PRSM row when nothing is selected', () => {
    const context = resolveMs2SelectionContext(
      [
        { 'Prsm ID': '10', Proteoform: 'A' },
        { 'Prsm ID': '20', Proteoform: 'B' },
      ],
      null,
    )

    expect(context.selectedPrsmId).toBe(10)
    expect(context.selectedRow).toMatchObject({ 'Prsm ID': '10' })
  })
})

describe('loadMs2CompositionInput', () => {
  it('loads peaks and parses proteoform context', async () => {
    const payload = await loadMs2CompositionInput({} as any, 'run-1', {
      'Proteoform': 'AC(D)[+15.9900]EF',
      'Protein accession': 'P12345',
      'Fragmentation': 'CID',
      'Spectrum ID': '42',
      'MS2 Artifact ID': 'artifact-77',
    })

    expect(payload.sequence).toBe('ACDEF')
    expect(payload.proteinAccession).toBe('P12345')
    expect(payload.activationMethod).toBe('CID')
    expect(payload.modifications).toHaveLength(1)
    expect(payload.peaks).toEqual([
      { index: 0, mz: 100.1, intensity: 50, charge: 1 },
      { index: 1, mz: 101.2, intensity: 75, charge: 2 },
    ])
    expect(payload.proforma).toContain('AC')
  })

  it('falls back to run-owned file paths when explicit artifact ids are stale', async () => {
    getArtifactEntriesMock
      .mockRejectedValueOnce(new Error('Artifact not found.'))
      .mockResolvedValueOnce(peaksResponse())

    await loadMs2CompositionInput({} as any, 'run-1', {
      'Proteoform': 'ACDEF',
      'Spectrum ID': '42',
      'MS2 Artifact ID': 'stale-artifact',
      'Data file name': 'runs/run-1/5_ms2.msalign',
    })

    expect(getArtifactEntriesMock).toHaveBeenNthCalledWith(1, expect.anything(), expect.objectContaining({
      artifact_id: 'stale-artifact',
      file_path: 'runs/run-1/5_ms2.msalign',
    }))
    expect(getArtifactEntriesMock).toHaveBeenNthCalledWith(2, expect.anything(), expect.objectContaining({
      artifact_id: '__by_path__',
      file_path: 'runs/run-1/5_ms2.msalign',
    }))
  })
})
