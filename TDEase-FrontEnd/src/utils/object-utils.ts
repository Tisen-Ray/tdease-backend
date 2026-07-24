import { asRecord } from '@/services/shared/helpers'

export function getNestedValue(obj: Record<string, unknown> | null, path: string[]): unknown {
  let current: unknown = obj
  for (const segment of path) {
    const record = asRecord(current)
    if (!record || !(segment in record)) {
      return undefined
    }
    current = record[segment]
  }
  return current
}

export function getNestedNumber(obj: Record<string, unknown> | null, path: string[]): number | null {
  const value = getNestedValue(obj, path)
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function getNestedString(obj: Record<string, unknown> | null, path: string[]): string | null {
  const value = getNestedValue(obj, path)
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}
