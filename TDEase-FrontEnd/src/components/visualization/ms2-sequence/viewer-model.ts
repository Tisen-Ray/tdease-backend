import type { MatchedFragment, Modification, SpectrumPeak } from '@/composables/ms2-sequence'

export interface ModificationSummaryItem {
  id: string
  text: string
}

export function formatNumber(value: unknown, digits: number): string {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return ''
  return parsed.toFixed(digits)
}

export function formatMassShift(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `Δ${sign}${value.toFixed(4)}`
}

export function buildModificationSummary(modifications: Modification[]): ModificationSummaryItem[] {
  return modifications.map((mod) => {
    const positionText = mod.positionEnd && mod.positionEnd !== mod.position
      ? `${mod.position}-${mod.positionEnd}`
      : `${mod.position}`
    const massText = formatMassShift(Number(mod.massShift || 0))
    return {
      id: mod.id,
      text: `${mod.name} @${positionText} ${massText}`,
    }
  })
}

export function toMatchedFragment(
  annotation: Record<string, unknown>,
  seqLength: number,
  peaks: SpectrumPeak[],
): MatchedFragment | null {
  const ionToken = String(annotation.type || annotation.ion_type || '').trim()
  const parsed = /^([abcxyz])(\d+)/i.exec(ionToken)
  if (!parsed) return null
  const ionType = parsed[1].toLowerCase() as MatchedFragment['ionType']
  const position = Number(annotation.position ?? parsed[2])
  const charge = Number(annotation.charge ?? 1)
  const matchedPeakIndex = Number(annotation.matchedPeakIndex ?? -1)
  const mz = Number(annotation.mz)
  const matchedMz = Number(annotation.matchedMz)
  const errorPpm = Number(annotation.error)
  const lossText = annotation.neutral_loss ? String(annotation.neutral_loss).toUpperCase() : ''
  const neutralLoss = lossText === 'H2O' || lossText === 'NH3' ? lossText : undefined
  const sequenceRangeRaw = Array.isArray(annotation.sequence_range) ? annotation.sequence_range : []
  const start = Number(sequenceRangeRaw[0])
  const end = Number(sequenceRangeRaw[1])
  const sequenceRange: [number, number] = Number.isFinite(start) && Number.isFinite(end)
    ? [start, end]
    : (ionType === 'a' || ionType === 'b' || ionType === 'c'
      ? [1, Math.min(position, seqLength)]
      : [Math.max(seqLength - position + 1, 1), seqLength])
  if (!Number.isFinite(mz) || !Number.isFinite(matchedMz) || !Number.isFinite(errorPpm)) return null
  const matchedPeak = peaks.find((peak) => peak.index === matchedPeakIndex)
    || peaks.reduce<SpectrumPeak | null>((best, peak) => {
      const currentError = Math.abs(peak.mz - matchedMz)
      if (!best) return peak
      return currentError < Math.abs(best.mz - matchedMz) ? peak : best
    }, null)
  return {
    ionType,
    position,
    charge: Number.isFinite(charge) ? charge : 1,
    theoreticalMass: 0,
    theoreticalMz: mz,
    sequenceRange,
    neutralLoss,
    matchedPeak: matchedPeak || undefined,
    matchErrorPpm: errorPpm,
    matchErrorDa: matchedPeak ? Math.abs(matchedPeak.mz - mz) : undefined,
    isMatched: true,
    peakIntensity: matchedPeak?.intensity,
    relativeIntensity: undefined,
  }
}

export function buildMatchTableData(matchedFragments: MatchedFragment[]) {
  return matchedFragments.map((fragment) => ({
    ion: `${fragment.ionType}${fragment.position}`,
    ionType: fragment.ionType,
    position: fragment.position,
    charge: fragment.charge,
    theoreticalMz: fragment.theoreticalMz,
    observedMz: fragment.matchedPeak?.mz,
    errorPpm: fragment.matchErrorPpm,
    intensity: fragment.peakIntensity,
    matched: fragment.isMatched,
  }))
}

export function buildMatchTableColumnDefs() {
  return [
    { field: 'ion', headerName: 'Ion', minWidth: 90, sortable: true, filter: true },
    { field: 'ionType', headerName: 'Type', minWidth: 80, sortable: true, filter: true },
    { field: 'position', headerName: 'Pos', minWidth: 80, sortable: true, filter: true },
    { field: 'charge', headerName: 'Z', minWidth: 70, sortable: true, filter: true },
    {
      field: 'theoreticalMz',
      headerName: 'Theo. m/z',
      minWidth: 140,
      sortable: true,
      filter: true,
      valueFormatter: (params: { value: unknown }) => formatNumber(params.value, 4),
    },
    {
      field: 'observedMz',
      headerName: 'Obs. m/z',
      minWidth: 140,
      sortable: true,
      filter: true,
      valueFormatter: (params: { value: unknown }) => (params.value ? formatNumber(params.value, 4) : '-'),
    },
    {
      field: 'errorPpm',
      headerName: 'Error (ppm)',
      minWidth: 140,
      sortable: true,
      filter: true,
      valueFormatter: (params: { value: unknown }) => (params.value !== undefined ? formatNumber(params.value, 2) : '-'),
    },
    {
      field: 'intensity',
      headerName: 'Intensity',
      minWidth: 130,
      sortable: true,
      filter: true,
      valueFormatter: (params: { value: unknown }) => (params.value ? formatNumber(params.value, 0) : '-'),
    },
    { field: 'matched', headerName: 'Matched', minWidth: 110, sortable: true, filter: true },
  ]
}
