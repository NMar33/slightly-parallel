import { useCallback, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../lib/getJson'
import { toast } from '../../components/primitives'
import { useNow } from '../../lib/clock'
import { OPERATOR_ACTOR } from '../project/types'
import { formatClock } from '../project/timeEntry'

/**
 * The sprint deck — one cross-project read, one set of actions, shared by
 * every /sprints design. The pages differ in what they make of it; none of
 * them owns the data or the writes.
 */

export type DeckTask = {
  id: string
  title: string
  status: string
  today_on?: string | null
  stack_id?: string | null
  priority?: string | null
  assignee?: string | null
  /** When it joined the block, and when it landed — lead time is the gap. */
  joined?: string | null
  done_on?: string | null
  /** Last status change: how long it has sat where it is. */
  status_since?: string | null
}

type DeckTimer = {
  id: string
  started_at?: string | null
  paused_at?: string | null
  paused_total_sec?: number | null
  share_pct?: number | null
  note?: string | null
}

export type Block = {
  id: string
  name: string
  project: string
  started_date: string
  bet_days?: number | null
  days_left: number | null
  ran_days: number | null
  budget_h?: number | null
  tasks_total: number
  tasks_done: number
  tasks_doing: number
  today_n: number
  human_min: number
  agent_min: number
  last_event_at?: string | null
  /** Per-day rhythm, when the deck was asked for a range. */
  series?: Array<{ date: string; done: number; human_min: number; agent_min: number; events: number }>
  tasks: DeckTask[]
  timer: DeckTimer | null
}

export type Deck = {
  today: string
  projects: string[]
  backlog: Record<string, number>
  blocks: Block[]
  running_elsewhere: Array<{ id: string; project?: string; sprint_id?: string; started_at?: string; paused_at?: string | null; paused_total_sec?: number | null; share_pct?: number | null }>
  settled: Array<{ id: string; name: string; project: string; started_date: string; ended_date: string; bet_days?: number | null; budget_h?: number | null }>
}

const post = async (url: string, body?: unknown): Promise<boolean> => {
  try {
    await postJson(url, body)
    return true
  } catch (e) {
    // The server's own sentence, not a bare 'did not save'.
    toast.error(t('Could not save: {message}', { message: (e as Error).message }))
    return false
  }
}

/** Live seconds on a running entry, from the server's timestamps. */
export function timerSec(it: DeckTimer, nowMs: number): number {
  const started = Date.parse(it.started_at ?? '')
  if (Number.isNaN(started)) return 0
  const pausedAt = it.paused_at ? Date.parse(it.paused_at) : NaN
  const edge = Number.isNaN(pausedAt) ? nowMs : pausedAt
  return Math.max(0, Math.round((edge - started - (it.paused_total_sec ?? 0) * 1000) / 1000))
}

/** Seconds as a running clock — the timer's own (`timeEntry.formatClock`). */
export const clock = formatClock
import { hm } from '../../utils/format'
import { t } from '../../i18n/scope/views'
export { hm }

/** Done in any form — the board's two done columns count as one here. */
export const isDone = (s?: string | null): boolean =>
  ['done', 'done-archived'].includes(String(s || '').toLowerCase())
export const isDoing = (s?: string | null): boolean =>
  ['doing', 'review'].includes(String(s || '').toLowerCase())

type Verdict = 'ahead' | 'on pace' | 'behind' | 'overdue' | 'idle'

/** Pace: work done against time spent, both as fractions of their limits. */
export function verdictOf(b: Block): Verdict {
  if (b.days_left != null && b.days_left < 0) return 'overdue'
  if (b.tasks_total === 0) return 'idle'
  const bet = Number(b.bet_days) || 0
  const timeF = bet > 0 && b.days_left != null ? (bet - b.days_left) / bet : 0
  const workF = b.tasks_done / b.tasks_total
  if (workF - timeF > 0.15) return 'ahead'
  if (timeF - workF > 0.15) return 'behind'
  return 'on pace'
}

export const VERDICT_TONE: Record<Verdict, string> = {
  ahead: 'var(--status-green)',
  'on pace': 'var(--text-tertiary)',
  behind: 'var(--status-amber)',
  overdue: 'var(--status-red)',
  idle: 'var(--text-tertiary)',
}

/** Whole days since anything happened to the block's tasks. */
export function silentDays(b: Block, nowMs: number): number | null {
  const tv = Date.parse(String(b.last_event_at || ''))
  if (Number.isNaN(tv)) return null
  return Math.floor((nowMs - tv) / 86400e3)
}

/** Hours booked against the budget, 0–1+, or null when no budget was set. */
export function budgetFrac(b: Block): number | null {
  const budget = Number(b.budget_h) || 0
  if (budget <= 0) return null
  return b.human_min / 60 / budget
}

export function useDeck(days = 0) {
  const qc = useQueryClient()
  // The page's clock is coarse (quiet days, the week): a running block's
  // seconds are drawn by `Live` where they show, not by redrawing the page.
  const nowMs = useNow(60_000)
  // Through react-query: the freshness stamp (area "tasks") keeps it honest
  // when agents write in the background — no poll of its own.
  const q = useQuery({
    queryKey: ['sprints', 'deck', days],
    queryFn: ({ signal }) => getJson<Deck>(days > 0 ? `/api/sprints/deck?days=${days}` : '/api/sprints/deck', signal),
  })
  const deck = q.data ?? null
  const err = q.isError
  const refresh = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['sprints'] })
    // A timer started or stopped shows in the sidebar chip and the tracker too.
    void qc.invalidateQueries({ queryKey: ['time-running'] })
    void qc.invalidateQueries({ queryKey: ['time-entries'] })
  }, [qc])


  const actions = useMemo(() => ({
    /** Start a timer on the block; a block already running is stopped. */
    async toggleTimer(b: Block) {
      if (b.timer) {
        await post(`/api/time/${encodeURIComponent(b.timer.id)}/stop`)
      } else {
        await post('/api/time/start', {
          project: b.project, agent_id: OPERATOR_ACTOR, sprint_id: b.id,
          share_pct: 100, note: '',
        })
      }
      refresh()
    },
    async pauseTimer(b: Block) {
      if (!b.timer) return
      await post(`/api/time/${encodeURIComponent(b.timer.id)}/${b.timer.paused_at ? 'resume' : 'pause'}`)
      refresh()
    },
    async setShare(b: Block, share: number) {
      if (!b.timer) return
      await post(`/api/time-entries/${encodeURIComponent(b.timer.id)}/update`, { share_pct: share })
      refresh()
    },
    /** Plan (or unplan) a task for today — the board's own today lens. */
    async toggleToday(it: DeckTask, today: string) {
      await post(`/api/tasks/${encodeURIComponent(it.id)}/update`, {
        today_on: String(it.today_on || '') === today ? '' : today, actor: OPERATOR_ACTOR,
      })
      refresh()
    },
    async setStatus(it: DeckTask, status: string) {
      await post(`/api/tasks/${encodeURIComponent(it.id)}/update`, { status, actor: OPERATOR_ACTOR })
      refresh()
    },
    async addTask(b: Block, title: string) {
      const now = new Date()
      const yy = String(now.getFullYear()).slice(-2)
      const dateStr = `${yy}${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
      const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
      await post('/api/tasks', {
        project: b.project, agent_id: OPERATOR_ACTOR, created_date: dateStr, created_time: timeStr,
        title, status: 'todo', sprint_id: b.id, position: '999',
      })
      refresh()
    },
    /** Move the bet: a new day count from the same start. */
    async rebet(b: Block, days: number) {
      await post(`/api/sprints/${encodeURIComponent(b.id)}/update`, { bet_days: days })
      refresh()
    },
    async finish(b: Block, retro: string) {
      const now = new Date()
      const yy = String(now.getFullYear()).slice(-2)
      const dateStr = `${yy}${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
      const over = b.days_left != null && b.days_left < 0 ? t('ran {v}d over', { v: -b.days_left }) : t('in time')
      const facts = b.budget_h
        ? t('planned {v}d, {over} · done {tasks_done}/{tasks_total} · {hm} human of {budget}h · {hm2} agent', { v: b.bet_days ?? '—', over, tasks_done: b.tasks_done, tasks_total: b.tasks_total, hm: hm(b.human_min), budget: b.budget_h, hm2: hm(b.agent_min) })
        : t('planned {v}d, {over} · done {tasks_done}/{tasks_total} · {hm} human · {hm2} agent', { v: b.bet_days ?? '—', over, tasks_done: b.tasks_done, tasks_total: b.tasks_total, hm: hm(b.human_min), hm2: hm(b.agent_min) })
      await post(`/api/sprints/${encodeURIComponent(b.id)}/update`, {
        status: 'ended', ended_date: dateStr, goals_shipped_n: b.tasks_done,
        l2: `${facts}\n\n${retro}`,
      })
      refresh()
    },
  }), [refresh])

  return { deck, err, nowMs, refresh, actions }
}
