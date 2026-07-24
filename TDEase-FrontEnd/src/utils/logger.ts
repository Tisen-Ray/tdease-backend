/**
 * Structured logger utility built on loglevel.
 *
 * Usage:
 *   import { createLogger } from '@/utils/logger'
 *   const log = createLogger('visualization')
 *   log.debug('chart ready')
 *   log.warn('missing mapping')
 *   log.error('load failed', err)
 *
 * Log level is controlled by the VITE_LOG_LEVEL env variable.
 * Defaults to 'warn' in production and 'debug' in development.
 */

import loglevel from 'loglevel'

const isDev = import.meta.env.DEV

// Global default: warn in prod, debug in dev
const globalLevel = (import.meta.env.VITE_LOG_LEVEL as loglevel.LogLevelDesc | undefined)
  ?? (isDev ? 'debug' : 'warn')

loglevel.setDefaultLevel(globalLevel)

export interface RunLogEntry {
  id?: number
  timestamp: string
  level: string
  message: string
  node_id?: string
  metadata?: Record<string, unknown>
}

interface ProgressLogSignature {
  operation: string
  percent: number
}

interface ProgressGroupState {
  index: number
  count: number
}

const PROGRESS_FINISHED_PATTERN = /(?:(?:processing|running|working)\s+(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%\s*(?:finished|done|complete|completed))\.?\s*(?:\(\d+\s+updates?\s+folded\))?\s*$/i
const MAX_RUN_LOG_ENTRIES = 2000

function clampPercent(percent: number): number {
  return Math.max(0, Math.min(100, percent))
}

/**
 * Parse logs like:
 * "Additional feature search MS1 spectrum scan 2215 ... 53% finished."
 * and normalize operation to:
 * "Additional feature search MS1 spectrum scan"
 */
export function parseProgressLogSignature(message: string): ProgressLogSignature | null {
  const trimmed = message.trim()
  const match = PROGRESS_FINISHED_PATTERN.exec(trimmed)
  if (!match) return null

  // Group 1 captures percent from "processing 50%" format,
  // Group 2 captures percent from "50% finished" format.
  const percentStr = match[1] || match[2]
  if (!percentStr) return null

  const percent = Number.parseInt(percentStr, 10)
  if (!Number.isFinite(percent)) return null

  const prefix = trimmed.slice(0, match.index).trimEnd()
  if (!prefix) return null

  const normalizedOperation = prefix
    .replace(/\.\.\.\s*$/, '')
    // Strip trailing ", NNN" or ", NNN." sub-step numbers that vary per
    // line (e.g. "Writing product chromatogram, 94." → "Writing product
    // chromatogram") so the collapser can fold them into one group.
    .replace(/, \d+\.?\s*$/, '')
    .replace(/\s+\d+\s*$/, '')
    // Strip trailing " -" or " –" from "processing X%" prefix format
    // (e.g. "Zero unexpected shift filtering -" → "Zero unexpected shift filtering")
    .replace(/\s*[-–]\s*$/, '')
    .trim()

  if (!normalizedOperation) return null

  return {
    operation: normalizedOperation,
    percent: clampPercent(percent),
  }
}

function formatCollapsedProgressMessage(operation: string, percent: number, count: number): string {
  if (count <= 1) return `${operation} ... ${percent}% finished.`
  return `${operation} ... ${percent}% finished. (${count} updates folded)`
}

/**
 * Fold high-frequency tool progress logs to reduce render pressure in log panes.
 * Error-level entries are never folded.
 */
export function createRunLogCollapser() {
  const progressGroups = new Map<string, ProgressGroupState>()
  const seenIds = new Set<number>()

  const trimLogs = (logs: RunLogEntry[]): void => {
    if (logs.length <= MAX_RUN_LOG_ENTRIES) return
    const overflow = logs.length - MAX_RUN_LOG_ENTRIES
    const removed = logs.splice(0, overflow)

    // Clean seenIds for removed entries that had ids.
    for (const entry of removed) {
      if (entry.id != null) {
        seenIds.delete(entry.id)
      }
    }

    // Re-index collapsed groups after trimming.
    for (const [key, state] of progressGroups.entries()) {
      const nextIndex = state.index - overflow
      if (nextIndex < 0 || nextIndex >= logs.length) {
        progressGroups.delete(key)
      } else {
        state.index = nextIndex
      }
    }
  }

  return {
    append(logs: RunLogEntry[], entry: RunLogEntry): void {
      // Dedup by id: if we've already seen this id, skip entirely.
      if (entry.id != null) {
        if (seenIds.has(entry.id)) return
        seenIds.add(entry.id)
      }

      if (entry.level === 'error') {
        logs.push(entry)
        trimLogs(logs)
        return
      }

      const signature = parseProgressLogSignature(entry.message)
      if (!signature) {
        logs.push(entry)
        trimLogs(logs)
        return
      }

      // Use backend dedupe_key (template hash) when available; fall back
      // to regex-extracted operation name for entries produced before the
      // backend upsert path was introduced.
      const dedupeKey = (entry.metadata?.dedupe_key as string) || ''
      const groupKey = dedupeKey
        ? `${entry.level}|${entry.node_id || ''}|${dedupeKey}`
        : `${entry.level}|${entry.node_id || ''}|${signature.operation}`

      // Prefer fold_count from backend metadata; otherwise tally locally.
      const backendFold = (entry.metadata?.fold_count as number) || 0

      const existing = progressGroups.get(groupKey)
      if (existing && existing.index < logs.length) {
        const nextCount = backendFold || existing.count + 1
        logs[existing.index] = {
          ...logs[existing.index],
          id: entry.id,
          timestamp: entry.timestamp,
          message: formatCollapsedProgressMessage(signature.operation, signature.percent, nextCount),
        }
        existing.count = nextCount
        return
      }

      logs.push({
        ...entry,
        message: formatCollapsedProgressMessage(signature.operation, signature.percent, backendFold || 1),
      })
      progressGroups.set(groupKey, {
        index: logs.length - 1,
        count: backendFold || 1,
      })
      trimLogs(logs)
    },
    reset(): void {
      progressGroups.clear()
      seenIds.clear()
    },
  }
}

/**
 * Create a namespaced child logger.
 * Each module gets its own logger instance so levels can be tuned individually.
 */
export function createLogger(name: string): loglevel.Logger {
  const logger = loglevel.getLogger(name)
  // Inherit global level unless already overridden
  if (logger.getLevel() > loglevel.getLevel()) {
    logger.setLevel(loglevel.getLevel())
  }
  return logger
}

/** Root logger for one-off usages */
export const rootLogger = loglevel
