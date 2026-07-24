/**
 * Locale-independent date formatting utilities.
 * All functions produce unified MM/DD/YYYY output regardless of the
 * current vue-i18n locale — dates look the same in en-US and zh-CN.
 */

const pad = (n: number): string => String(n).padStart(2, '0')

const toDate = (iso: string): Date | null => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "06/22/2026" */
export const formatDate = (iso: string): string => {
  const d = toDate(iso)
  return d ? `${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()}` : iso
}

/** "06/22" */
export const formatMonthDay = (iso: string): string => {
  const d = toDate(iso)
  return d ? `${pad(d.getMonth() + 1)}/${pad(d.getDate())}` : iso
}

/** "14:30" (24h) */
export const formatTime = (iso: string): string => {
  const d = toDate(iso)
  return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : iso
}

/** "14:30:05" (24h) */
export const formatTimeSec = (iso: string): string => {
  const d = toDate(iso)
  return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` : iso
}

/** "06/22/2026 14:30" */
export const formatDateTime = (iso: string): string => {
  const d = toDate(iso)
  return d
    ? `${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    : iso
}

/** Days between two dates (midnight-aligned for consistent day boundaries). */
export const daysBetween = (a: Date, b: Date): number => {
  const msPerDay = 86_400_000
  return Math.floor((b.getTime() - a.getTime()) / msPerDay)
}
