import type { SelectionState, TableData } from '@/types/visualization'
import type { Modification, SpectrumPeak } from '@/composables/ms2-sequence'
import { getArtifactEntries } from '@/services/api/interactive-artifacts'
import type { APIClientLike } from '@/services/api/client'
import { resolveMsalignSource } from './artifactSource'
import { parseProteoformAnnotation, buildProformaString } from '@/utils/proforma'

export interface Ms2SelectionContext {
  selectedPrsmId: number | null
  selectedRow: Record<string, unknown> | null
}

export interface Ms2CompositionInput {
  sequence: string
  proteinAccession: string
  activationMethod: string
  peaks: SpectrumPeak[]
  modifications: Modification[]
  proforma: string
}

function toNumericId(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function resolveMs2SelectionContext(
  rows: Record<string, unknown>[],
  selection?: SelectionState | null,
): Ms2SelectionContext {
  const selectedRefs = selection?.selectedRefs || []
  let selectedPrsmId: number | null = null

  // Strategy 1: Find a matching ref whose field is 'Prsm ID' or 'prsm_id'.
  for (const ref of [...selectedRefs].reverse()) {
    if (ref.field !== 'Prsm ID' && ref.field !== 'prsm_id') continue
    const record = ref as typeof ref & { val?: unknown }
    const parsed = toNumericId(ref.value ?? record.val)
    if (parsed !== null) {
      selectedPrsmId = parsed
      break
    }
  }

  // Strategy 2: No direct 'Prsm ID' ref — search ALL refs by value against
  // the rows' 'Prsm ID' column.  This bridges viewers (e.g. FeatureMap) that
  // emit refs under a different field name (feature_id, id, …) but whose
  // underlying data rows do carry a Prsm ID.
  if (selectedPrsmId === null && selectedRefs.length > 0) {
    for (const ref of [...selectedRefs].reverse()) {
      const refValue = String(ref.value).trim()
      if (!refValue) continue
      const matched = rows.find((row) => {
        const prsmVal = row['Prsm ID'] ?? row.prsm_id
        return prsmVal !== undefined && prsmVal !== null && String(prsmVal).trim() === refValue
      })
      if (matched) {
        selectedPrsmId = toNumericId(ref.value) ?? toNumericId(matched['Prsm ID'] ?? matched.prsm_id)
        break
      }
    }
  }

  if (selectedPrsmId === null) {
    const indices = selection?.selectedIndices
    if (indices?.size) {
      const rowIndex = [...indices].reverse().map((value) => toNumericId(value)).find((value) => value !== null)
      if (rowIndex !== undefined && rowIndex !== null && rowIndex >= 0 && rowIndex < rows.length) {
        const row = rows[rowIndex]
        selectedPrsmId = toNumericId(row?.['Prsm ID']) ?? toNumericId(row?.prsm_id)
      }
      if (selectedPrsmId === null && rowIndex !== undefined && rowIndex !== null) {
        selectedPrsmId = rows.some((row) => (
          toNumericId(row['Prsm ID']) === rowIndex || toNumericId(row.prsm_id) === rowIndex
        ))
          ? rowIndex
          : null
      }
    }
  }

  if (selectedPrsmId === null) {
    const firstPrsmRow = rows.find((row) => (
      toNumericId(row['Prsm ID']) !== null || toNumericId(row.prsm_id) !== null
    ))
    selectedPrsmId = firstPrsmRow
      ? toNumericId(firstPrsmRow['Prsm ID']) ?? toNumericId(firstPrsmRow.prsm_id)
      : null
  }

  const selectedRow = selectedPrsmId === null
    ? null
    : rows.find((row) => toNumericId(row['Prsm ID']) === selectedPrsmId || toNumericId(row.prsm_id) === selectedPrsmId) ?? null

  return {
    selectedPrsmId,
    selectedRow,
  }
}

export async function loadMs2CompositionInput(
  client: APIClientLike,
  runId: string,
  row: Record<string, unknown>,
): Promise<Ms2CompositionInput> {
  const rawProteoform = String(row['Proteoform'] || row.proteoform || '')
  const parsed = parseProteoformAnnotation(rawProteoform)
  const proteinAccession = String(row['Protein accession'] || row.protein_accession || '')
  const activationMethod = String(row['Fragmentation'] || row.activation || row.Activation || '').trim()
  const spectrumId = String(row['Spectrum ID'] || row.spectrum_id || '')
  const msalignSource = resolveMsalignSource(row)

  if (!spectrumId || !runId) {
    throw new Error(spectrumId ? 'Run ID is not available.' : 'Spectrum ID not found in selected row.')
  }
  if (!msalignSource) {
    throw new Error('MS2 source reference not found in selected row.')
  }

  let peaksResponse
  try {
    peaksResponse = await getArtifactEntries(client, {
      run_id: runId,
      artifact_id: msalignSource.artifactId,
      file_path: msalignSource.filePath,
      key: 'SPECTRUM_ID',
      value: spectrumId,
      mode: 'peaks',
    })
  } catch (error) {
    if (!msalignSource.filePath || msalignSource.artifactId === '__by_path__') throw error
    peaksResponse = await getArtifactEntries(client, {
      run_id: runId,
      artifact_id: '__by_path__',
      file_path: msalignSource.filePath,
      key: 'SPECTRUM_ID',
      value: spectrumId,
      mode: 'peaks',
    })
  }

  const peaks: SpectrumPeak[] = []
  for (const entry of peaksResponse.entries) {
    for (const peak of entry.peaks) {
      peaks.push({
        index: peaks.length,
        mz: peak.mass,
        intensity: peak.intensity,
        charge: peak.charge ?? 1,
      })
    }
  }

  return {
    sequence: parsed.sequence,
    proteinAccession,
    activationMethod,
    peaks,
    modifications: parsed.modifications,
    proforma: buildProformaString(parsed.sequence, parsed.modifications),
  }
}

export function tableRows(data: TableData | null | undefined): Record<string, unknown>[] {
  return ((data?.rows as Record<string, unknown>[] | undefined) ?? [])
}
