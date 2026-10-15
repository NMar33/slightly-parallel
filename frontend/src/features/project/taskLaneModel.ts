/**
 * The task timeline's data, shared by the panel and its lane variants:
 * the payload types, the window, the status bands a task sat in, and
 * which edits are worth drawing.
 */

import type { MentionAgent } from './mentions'
import { locale } from '../../i18n/scope/project'
import { dayMonth } from '../../lib/months'

export type Ev = {
  at: string
  kind: 'created' | 'status' | 'edit' | 'mention'
  field?: string
  from?: string
  to?: string
  actor?: string
  role?: 'user' | 'agent'
  agent_id?: string
  session_id?: string
  turn?: number
  excerpt?: string
  /** Who the agent is, when the server carries it; the label falls back
   *  to the tool and the id when it does not. */
  agent?: MentionAgent | null
}

export type TimelineTask = {
  id: string
  title: string
  status: string
  priority?: string
  impact?: string
  effort?: string
  novelty?: string
  assignee?: string
  project?: string
  projects?: string
  events: Ev[]
  last_at: string
}

export type Payload = { window: string; since: string; tasks: TimelineTask[] }

export type Window = 'day' | 'week' | 'month'
export const WINDOWS: Window[] = ['day', 'week', 'month']

export function parseIso(s: string): number {
  const ms = Date.parse(s)
  return Number.isFinite(ms) ? ms : 0
}

export function fmt(ms: number, window: Window): string {
  const d = new Date(ms)
  return window === 'day'
    ? d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', hour12: false })
    : dayMonth(d) +
        (window === 'week' ? ' ' + d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', hour12: false }) : '')
}

export type Band = { from: number; to: number; status: string }

/** The statuses a task was in across the window, from its change log.
 *  The status in force when the window opens is the last change before
 *  it, else what the first change in the window started from, else the
 *  current one. A task created inside the window starts there. */
export function bandsOf(task: TimelineTask, since: number, now: number): Band[] {
  const evs = task.events.map((e) => ({ ...e, ms: parseIso(e.at) })).filter((e) => e.ms > 0)
  const statusEvs = evs.filter((e) => e.kind === 'status')
  const before = statusEvs.filter((e) => e.ms < since)
  const initial =
    before.length ? String(before[before.length - 1]!.to || '') :
    statusEvs.length ? String(statusEvs[0]!.from || '') : String(task.status || '')
  const bands: Band[] = []
  let cursor = since
  let cur = initial
  const createdMs = evs.find((e) => e.kind === 'created')?.ms
  if (createdMs && createdMs > since) cursor = createdMs
  for (const e of statusEvs.filter((e) => e.ms >= since)) {
    if (e.ms > cursor) bands.push({ from: cursor, to: e.ms, status: cur })
    cursor = e.ms
    cur = String(e.to || '')
  }
  bands.push({ from: cursor, to: now, status: cur })
  return bands
}

/** Edits that change what the task is. Planning moves (today, position,
 *  sprint) happen to many cards at once and say nothing about one. */
const QUIET_FIELDS = new Set(['today_on', 'position', 'sprint_id', 'stack_id', 'stack_head_at', 'lane', 'agent_moved_at'])
export const meaningfulEdit = (e: Ev) => e.kind === 'edit' && !QUIET_FIELDS.has(String(e.field || ''))

/** Status → colour for the variants: the board's hues, with done calm
 *  (it is over) so doing, the live state, is the one that stands out. */
const TONE: Record<string, string> = {
  unclassified: 'var(--border-default)',
  backlog: 'color-mix(in oklab, var(--text-tertiary) 35%, transparent)',
  next: 'color-mix(in oklab, var(--text-tertiary) 55%, transparent)',
  parked: 'color-mix(in oklab, var(--text-tertiary) 35%, transparent)',
  todo: 'var(--status-amber)',
  doing: 'var(--brand)',
  agent: 'var(--brand)',
  review: 'var(--status-purple)',
  done: 'color-mix(in oklab, var(--status-green) 45%, var(--bg-surface))',
  'done-archived': 'color-mix(in oklab, var(--status-green) 30%, var(--bg-surface))',
}
export const toneOf = (status: string) => TONE[status] ?? TONE.unclassified!
