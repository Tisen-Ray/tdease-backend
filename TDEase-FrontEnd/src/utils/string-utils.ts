/**
 * Serializes a value to string format, handling various data types safely
 * @param value - The value to serialize
 * @returns A string representation of the value
 */
export function safeSerialize(value: unknown): string {
  if (value === undefined || value === null) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/**
 * Truncates text to a maximum length with ellipsis
 * @param text - The text to truncate
 * @param maxLength - Maximum length of the text
 * @returns Truncated text with ellipsis if needed
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text
  }
  return `${text.slice(0, maxLength - 3)}...`
}

/**
 * Mirrors the backend run_name validator (src/infrastructure/validation.py
 * SAFE_ID_RE = ^[\w._:\- ]{1,128}$). Strips characters outside that set and
 * caps length, so a user-supplied or template-derived name never trips a 400
 * "Invalid run_name format" at creation time.
 *
 * Returns a fallback when the result would be empty.
 */
const RUN_NAME_ALLOWED = /[\w._:\- ]/gu
const RUN_NAME_MAX = 128

export function sanitizeRunName(raw: string, fallback = 'Untitled Run'): string {
  const cleaned = (raw.match(RUN_NAME_ALLOWED) ?? []).join('').trim().slice(0, RUN_NAME_MAX)
  return cleaned || fallback
}

/**
 * Reports whether a name already passes the backend run_name validator as-is.
 * Use to show inline validation feedback before submission.
 */
const RUN_NAME_VALID = /^[\w._:\- ]{1,128}$/

export function isValidRunName(raw: string): boolean {
  return RUN_NAME_VALID.test(raw.trim())
}