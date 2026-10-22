/**
 * What the Timer page's parts share: the data in hand (TimeCtx), the rows
 * of the ledger, the tint of a cell, and the pill that starts a block.
 */

import { Pause, Play, Square } from 'lucide-react'

import type { TimeMode } from '../../lib/timer'
import type { TimeEntry } from '../project/timeEntry'
import { blockKey, blockTimes, type BlockTime, type Period, type ProjectTime, type TimeModel } from './model'

import { t, tc } from '../../i18n/scope/views'
import { weekdayShort } from '../../lib/months'
export interface Block { id: string; name: string }

export interface TimeCtx {
  m: TimeModel
  period: Period
  nowMs: number
  entries: TimeEntry[]
  mode: (code: string) => TimeMode
  /** The blocks a timer can start on: the project's running sprints, then "Everything else". */
  blocks: (code: string) => Block[]
  sprintName: (id: string) => string
  taskTitle: (id: string) => string
  start: (code: string, sprintId?: string) => void
  stop: (ids: string[]) => void
  pauseResume: (e: TimeEntry) => void
  setMode: (code: string, mode: TimeMode) => void
}

export { LABEL } from '../../components/ui'
export const projectTab = (code: string) => `/project/${encodeURIComponent(code)}#tools`
export const hh = (h: number) => String(h).padStart(2, '0')
export const isOn = (p: ProjectTime) => p.running.length > 0 || !!p.auto

export const MODE_OPTIONS = [
  ['remind', tc('timer mode', 'remind'), t('Opening a task or starting an agent with no timer asks whether to track')],
  ['auto', tc('timer mode', 'auto'), t('Counts by itself while you work on this project: its pages, its terminals, its files')],
  ['manual', tc('timer mode', 'manual'), t('Only the timers you start')],
] as const

/** The 26-week grid's tints, for any cell that says "how much" (0 to 1). */
export const tint = (share: number) =>
  share <= 0 ? 'var(--bg-elevated)' : `color-mix(in oklab, var(--brand) ${Math.round(14 + 60 * Math.min(1, share))}%, var(--bg-elevated))`

export const weekdayOf = (key: string) => {
  const [y, m, d] = key.split('-').map(Number)
  return weekdayShort((new Date(y, m - 1, d).getDay() + 6) % 7)
}

interface BlockRow { project: string; id: string; name: string; t: BlockTime }

/** Every block a timer can run on, project by project, plus ended sprints that still have time in the period. */
export function blockRows(c: TimeCtx): BlockRow[] {
  const times = blockTimes(c.entries, c.nowMs, c.m.days)
  const empty = (project: string, sprintId: string): BlockTime =>
    ({ project, sprintId, todaySec: 0, weekSec: 0, periodSec: 0, perDay: {}, open: null })
  const out: BlockRow[] = []
  for (const p of c.m.projects) {
    const listed = c.blocks(p.code)
    for (const b of listed) out.push({ project: p.code, id: b.id, name: b.name, t: times.get(blockKey(p.code, b.id)) ?? empty(p.code, b.id) })
    for (const tv of times.values()) {
      if (tv.project === p.code && !listed.some((b) => b.id === tv.sprintId)) {
        out.push({ project: p.code, id: tv.sprintId, name: c.sprintName(tv.sprintId), t: tv })
      }
    }
  }
  return out
}

/** Start or stop a block, and pause it while it runs: the Sprints page's pills. */
export function StartPill({ row, c }: { row: BlockRow; c: TimeCtx }) {
  const open = row.t.open
  return (
    <span className="inline-flex items-center gap-6">
      <button type="button" onClick={() => (open ? c.stop([open.id]) : c.start(row.project, row.id))}
        aria-label={open ? t('Stop {name} on {project}', { name: row.name, project: row.project }) : t('Start {name} on {project}', { name: row.name, project: row.project })}
        title={open ? t('Stop the clock on this block') : t('Start a timer on this block. Several blocks can run at once')}
        className={`h-20 px-8 text-10 rounded-pill font-mono font-semibold inline-flex items-center gap-4 ${open ? 'bg-brand text-on-brand' : 'border border-border-default text-secondary hover:border-brand hover:text-brand'}`}>
        {open ? <><Square size={10} aria-hidden /> {t('stop')}</> : <><Play size={10} aria-hidden /> {t('start')}</>}
      </button>
      {open && (
        <button type="button" onClick={() => c.pauseResume(open)} aria-label={open.paused_at ? t('Resume {name} on {project}', { name: row.name, project: row.project }) : t('Pause {name} on {project}', { name: row.name, project: row.project })}
          title={open.paused_at ? 'Resume' : 'Pause'}
          className="h-20 w-20 rounded-pill border border-border-default inline-flex items-center justify-center text-secondary hover:text-primary">
          {open.paused_at ? <Play size={10} aria-hidden /> : <Pause size={10} aria-hidden />}
        </button>
      )}
    </span>
  )
}
