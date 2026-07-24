import { safeSerialize } from './string-utils'

/**
 * Formats a value as a JSON string
 * @param value - The value to format
 * @returns Formatted JSON string or default value
 */
export function formatJsonValue(value: unknown): string {
  const text = safeSerialize(value)
  return text || '{}'
}