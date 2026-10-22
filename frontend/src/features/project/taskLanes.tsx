/**
 * Task timeline lanes, in the grid language the agent timeline took:
 * GitHub-style, the window cut into cells (an hour, six hours or a day),
 * each cell the status it ended in, a dot where the task was handed or
 * answered, the status now on the right.
 */

import { mentionWho, type Mention } from './mentions'
import {
  bandsOf, fmt, meaningfulEdit, parseIso, toneOf,
  type Band, type Ev, type TimelineTask, type Window,
} from './taskLaneModel'
import { t, tn } from '../../i18n/scope/project'

type LaneProps = {
  task: TimelineTask
  since: number
  now: number
  window: Window
  onOpen: () => void
  onMention: (m: Mention) => void
}

/** The lane's columns: title · lane · status now. */
export const LANE_COLS = '220px 1fr 72px'

const HOUR = 3600e3
/** Cell size per window: 24 hours, 28 quarter-days, 30 days. */
const SLOT: Record<Window, number> = { day: HOUR, week: 6 * HOUR, month: 24 * HOUR }

function slotsOf(window: Window, since: number, now: number): Array<{ from: number; to: number }> {
  const size = SLOT[window]
  const n = Math.max(1, Math.ceil((now - since) / size))
  return Array.from({ length: n }, (_, i) => ({ from: since + i * size, to: Math.min(now, since + (i + 1) * size) }))
}

function toMention(e: Ev, task: TimelineTask): Mention | null {
  if (!e.session_id) return null
  return {
    at: e.at, role: e.role === 'user' ? 'user' : 'agent', agent_id: e.agent_id || '',
    session_id: e.session_id, turn: Number(e.turn || 0), excerpt: e.excerpt,
    project: task.project, agent: e.agent,
  }
}

function describe(e: Ev, window: Window): string {
  const at = fmt(parseIso(e.at), window)
  if (e.kind === 'created') return `created · ${at}`
  if (e.kind === 'status') return `${e.from || '—'} → ${e.to || '—'} · ${at}`
  if (e.kind === 'edit') return `${e.field}: ${e.from || '—'} → ${e.to || '—'} · ${at}`
  const who = mentionWho({ agent_id: e.agent_id || '', agent: e.agent })
  return `${e.role === 'user' ? 'sent to' : 'reply from'} ${who} · ${at}${e.excerpt ? `\n“${e.excerpt}”` : ''}`
}

/** The status a task ended a stretch of time in, or '' before it existed. */
function statusAt(bands: Band[], at: number): string {
  let s = ''
  for (const b of bands) if (b.from < at) s = b.status
  return s
}

function StatusNow({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-4 justify-end text-10 font-mono text-tertiary truncate pl-8">
      <span className="h-8 w-8 rounded-[2px] shrink-0" style={{ backgroundColor: toneOf(status) }} aria-hidden />
      {status || '—'}
    </span>
  )
}

function Title({ task, onOpen }: { task: TimelineTask; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="text-left text-12 text-secondary hover:text-primary truncate pr-12"
      title={`${task.id} · ${task.title} · ${task.status}`}>
      {task.title}
    </button>
  )
}

export function Lane({ task, since, now, window, onOpen, onMention }: LaneProps) {
  const bands = bandsOf(task, since, now)
  const created = parseIso(task.events.find((e) => e.kind === 'created')?.at ?? '')
  const evs = task.events.map((e) => ({ ...e, ms: parseIso(e.at) })).filter((e) => e.ms >= since)
  const slots = slotsOf(window, since, now)
  return (
    <div className="grid items-center" style={{ gridTemplateColumns: LANE_COLS }}>
      <Title task={task} onOpen={onOpen} />
      <div className="flex gap-2 h-14">
        {slots.map((s, i) => {
          const status = created && s.to <= created ? '' : statusAt(bands, s.to)
          const inside = evs.filter((e) => e.ms >= s.from && e.ms < s.to && (e.kind !== 'edit' || meaningfulEdit(e)))
          const mentions = inside.filter((e) => e.kind === 'mention')
          const handed = mentions.some((e) => e.role === 'user')
          const moved = inside.some((e) => e.kind === 'status' || e.kind === 'created')
          const first = mentions.map((e) => toMention(e, task)).find(Boolean)
          return (
            <button key={i} type="button"
              onClick={() => first && onMention(first)}
              className={`relative flex-1 min-w-0 rounded-[2px] ${first ? 'cursor-pointer' : 'cursor-default'}`}
              style={{
                // Idle cells are soft; a cell where something happened is
                // full — the eye goes to the work, as on GitHub.
                backgroundColor: !status ? 'var(--bg-elevated)'
                  : inside.length ? toneOf(status)
                  : `color-mix(in oklab, ${toneOf(status)} 35%, var(--bg-elevated))`,
                boxShadow: moved ? 'inset 0 0 0 1px var(--text-primary)' : undefined,
              }}
              title={[`${fmt(s.from, window)} – ${fmt(s.to, window)} · ${status || 'not yet'}`, ...inside.map((e) => describe(e, window))].join('\n')}
              aria-label={`${fmt(s.from, window)}: ${status || t('not yet')}${mentions.length ? `, ${tn(mentions.length, '{n} chat', '{n} chats')}` : ''}`}
            >
              {mentions.length > 0 && (
                <span className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-4 w-4 rounded-pill ${handed ? 'bg-status-amber ring-1 ring-surface' : 'bg-surface'}`} aria-hidden />
              )}
            </button>
          )
        })}
      </div>
      <StatusNow status={task.status} />
    </div>
  )
}

const sw = (bg: string, extra = '') => <span className={`inline-block h-8 w-8 rounded-[2px] ${extra}`} style={{ backgroundColor: bg }} aria-hidden />

export function LaneLegend() {
  const statuses = ['todo', 'doing', 'review', 'done'] as const
  return (
    <div className="flex items-center gap-12 flex-wrap text-10 font-mono text-tertiary pt-6 border-t border-border-subtle mt-4">
      <span>{t('a cell is an hour (day view), six hours (week) or a day (month); filled means something happened')}</span>
      <span className="inline-flex items-center gap-4"><span className="h-8 w-8 rounded-[2px] bg-elevated ring-1 ring-inset ring-primary" /> {t('status changed')}</span>
      <span className="inline-flex items-center gap-4"><span className="h-4 w-4 rounded-pill bg-status-amber" /> {t('sent ·')} <span className="h-4 w-4 rounded-pill bg-surface ring-1 ring-border-default" /> {t('reply')}</span>
      <span className="ml-auto inline-flex items-center gap-8">
        {statuses.map((s) => <span key={s} className="inline-flex items-center gap-4">{sw(toneOf(s))} {s}</span>)}
      </span>
    </div>
  )
}
