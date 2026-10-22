/**
 * A time entry and the two clocks read from it — small on purpose: the app
 * shell's running-timer chip needs these, and importing them from the
 * tracker page pulled the whole tracker into every page load.
 */

import { isoDay } from '../../utils/dateUtils'
import { hMin } from '../../utils/format'

export interface TimeEntry {
  id: string
  project: string
  created_date?: string
  started_at?: string
  ended_at?: string
  paused_at?: string
  paused_total_sec?: number
  duration_min?: number
  share_pct?: number
  goal_id?: string
  sprint_id?: string
  note?: string
  status?: 'running' | 'paused' | 'done'
  elapsed_sec?: number
  attributed_sec?: number
  runaway?: boolean
  /** The task the time went to. */
  task_id?: string
  /** "auto": written by the smart timer (its share tops manual time up to 100%). */
  source?: string
}

/**
 * Seconds → "1:04:33" / "12:34" / "0:05" — the live clock, where the
 * seconds hand is the proof it is actually running.
 */
export function formatClock(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  return h > 0
    ? `${h}:${mm}:${String(sec).padStart(2, '0')}`
    : `${mm}:${String(sec).padStart(2, '0')}`
}

/** Live seconds for an entry, computed from server timestamps. A finished
 *  entry (status done, or simply an ended_at — the list endpoint sends no
 *  status) measures start→end minus banked pauses; a running one start→now. */
export function liveElapsed(entry: TimeEntry, nowMs: number): number {
  const started = Date.parse(entry.started_at ?? '')
  const ended = Date.parse(entry.ended_at ?? '')
  const banked = (entry.paused_total_sec ?? 0) * 1000
  if (entry.status === 'done' || !Number.isNaN(ended)) {
    if (!Number.isNaN(started) && !Number.isNaN(ended)) return Math.max(0, Math.round((ended - started - banked) / 1000))
    return (entry.duration_min ?? 0) * 60
  }
  if (Number.isNaN(started)) return entry.elapsed_sec ?? 0
  const pausedAt = entry.paused_at ? Date.parse(entry.paused_at) : NaN
  const edge = Number.isNaN(pausedAt) ? nowMs : pausedAt
  return Math.max(0, Math.round((edge - started - banked) / 1000))
}

/** Seconds → "1h 04m" / "12m" / "0m" — compact totals for logged time. */
export const formatDuration = (totalSec: number): string => hMin(Math.floor(Math.max(0, totalSec) / 60), '0m')

/** A block a timer runs on: a sprint (its id), or 'other' for time outside any sprint. `tone` overrides the ring colour. */
export type BlockDef = { key: string; name: string; tone?: string }
/** The colours of the blocks, in order; the fourth and later share the last. */
export const RING_TONES = ['var(--brand)', 'var(--status-amber)', 'var(--status-green)', 'var(--text-tertiary)']
export const keyOf = (e: TimeEntry) => (e.sprint_id ? e.sprint_id : 'other')
export const dateKey = isoDay
export const startDate = (e: TimeEntry): Date | null => {
  const t = Date.parse(e.started_at ?? '')
  return Number.isNaN(t) ? null : new Date(t)
}
/** Active seconds times the share: what the entries book. */
export const weightedSec = (es: TimeEntry[], nowMs: number) =>
  es.reduce((a, e) => a + liveElapsed(e, nowMs) * ((e.share_pct ?? 100) / 100), 0)
