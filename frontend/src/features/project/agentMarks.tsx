/**
 * Task marks on the agent timeline, drawn from what the tasks are now:
 * status as the fill, and two extras — important (impact or priority
 * high) and novel (novelty killer or fresh). Up to nine tasks as a
 * 3 × 3 of cells, GitHub-style.
 */

import type { ReactNode } from 'react'

import type { LaneMark } from '../../components/AgentTimeline/AgentTimeline'
import { normalizeStatus, type TaskLink, type TaskRow } from './kanban/model'
import { t } from '../../i18n/scope/project'

/** What a mark needs to know about one task. */
export type MarkTask = {
  id: string
  title: string
  tone: Tone
  important: boolean
  novel: boolean
}

type Tone = 'blocked' | 'doing' | 'review' | 'todo' | 'shelf' | 'done' | 'gone'

/** The board's colours, so a task reads the same here and there. */
const TONE: Record<Tone, { color: string; label: string }> = {
  blocked: { color: 'var(--status-red)', label: t('blocked') },
  doing: { color: 'var(--brand)', label: t('doing') },
  review: { color: 'var(--status-purple)', label: t('review') },
  todo: { color: 'var(--status-amber)', label: t('to do') },
  shelf: { color: 'var(--status-neutral)', label: t('parked') },
  done: { color: 'var(--status-green)', label: t('done') },
  gone: { color: 'var(--border-default)', label: t('deleted') },
}
/** Most urgent first: the order cells fill in. */
const ORDER: Tone[] = ['blocked', 'doing', 'review', 'todo', 'shelf', 'done', 'gone']

function toneOf(status: string | undefined, blocked: boolean): Tone {
  const s = normalizeStatus(status)
  if (s === 'done' || s === 'done-archived') return 'done'
  if (blocked) return 'blocked'
  if (s === 'doing' || s === 'agent') return 'doing'
  if (s === 'review') return 'review'
  if (s === 'todo') return 'todo'
  return 'shelf'
}

/** Tasks by id, with the blocked flag from the links (blocked by an open task). */
export function markTasks(tasks: TaskRow[], links: TaskLink[]): Map<string, MarkTask> {
  const open = new Set(tasks.filter((t) => !['done', 'done-archived'].includes(normalizeStatus(t.status))).map((t) => t.id))
  const blocked = new Set(links.filter((l) => l.kind === 'blocks' && open.has(l.from_id)).map((l) => l.to_id))
  const out = new Map<string, MarkTask>()
  for (const t of tasks) {
    out.set(t.id, {
      id: t.id,
      title: String(t.title || t.id),
      tone: toneOf(t.status, blocked.has(t.id)),
      important: String(t.impact || '').toLowerCase() === 'high' || String(t.priority || '').toLowerCase() === 'high',
      novel: ['killer', 'fresh'].includes(String(t.novelty || '').toLowerCase()),
    })
  }
  return out
}

type Cell = MarkTask & { handed: boolean }

/** One hour's marks → its distinct tasks, most urgent first. A task
 *  only named in a reply (not handed over) is drawn fainter. */
function cells(group: LaneMark[], tasks: Map<string, MarkTask>): Cell[] {
  const by = new Map<string, Cell>()
  for (const m of group) {
    const t = tasks.get(m.task_id) ?? { id: m.task_id, title: m.title || m.task_id, tone: 'gone' as Tone, important: false, novel: false }
    const c = by.get(m.task_id) ?? { ...t, handed: false }
    if (m.role === 'user') c.handed = true
    by.set(m.task_id, c)
  }
  return [...by.values()].sort((a, b) => ORDER.indexOf(a.tone) - ORDER.indexOf(b.tone))
}

const faint = (c: Cell) => (c.handed ? 1 : 0.5)

/** A cell: the fill is the status; important gets an ink ring; novel a
 *  hole in the middle. */
function Square({ c, x, y, s }: { c: Cell; x: number; y: number; s: number }) {
  return (
    <g opacity={faint(c)}>
      <rect x={x} y={y} width={s} height={s} rx={1} fill={TONE[c.tone].color}
        stroke={c.important ? 'var(--text-primary)' : 'none'} strokeWidth={c.important ? 1 : 0} />
      {c.novel && <circle cx={x + s / 2} cy={y + s / 2} r={s / 5} fill="var(--bg-surface)" />}
    </g>
  )
}

function More({ n, x }: { n: number; x: number }) {
  return n > 0 ? <text x={x} y={3.5} fontSize={9} fontWeight={600} fill="var(--text-secondary)">+{n}</text> : null
}

/** 3 × 3: nine cells, empty ones faint; more than nine → +n beside it. */
function Grid({ cs }: { cs: Cell[] }) {
  const s = 5, g = 1, w = 3 * s + 2 * g
  return (
    <g>
      <rect x={-w / 2 - 1.5} y={-w / 2 - 1.5} width={w + 3} height={w + 3} rx={2.5} fill="var(--bg-surface)" stroke="var(--border-subtle)" strokeWidth={0.75} />
      {Array.from({ length: 9 }, (_, i) => {
        const x = -w / 2 + (i % 3) * (s + g), y = -w / 2 + Math.floor(i / 3) * (s + g)
        const c = cs[i]
        return c
          ? <Square key={i} c={c} x={x} y={y} s={s} />
          : <rect key={i} x={x} y={y} width={s} height={s} rx={1} fill="var(--border-subtle)" opacity={0.7} />
      })}
      <More n={cs.length - 9} x={w / 2 + 4} />
    </g>
  )
}

export function renderMarkWith(tasks: Map<string, MarkTask>) {
  return (group: LaneMark[]): ReactNode => {
    const cs = cells(group, tasks)
    return cs.length === 0 ? null : <Grid cs={cs} />
  }
}

/** The hover list's swatch for one task. */
export function swatchWith(tasks: Map<string, MarkTask>) {
  return (id: string) => {
    const t = tasks.get(id)
    const tone = t?.tone ?? 'gone'
    return {
      node: (
        <svg width={10} height={10} aria-hidden>
          <rect x={1} y={1} width={8} height={8} rx={1.5} fill={TONE[tone].color}
            stroke={t?.important ? 'var(--text-primary)' : 'none'} strokeWidth={1} />
          {t?.novel && <circle cx={5} cy={5} r={1.6} fill="var(--bg-surface)" />}
        </svg>
      ),
      label: [TONE[tone].label, t?.important ? 'important' : '', t?.novel ? 'novel' : ''].filter(Boolean).join(' · '),
    }
  }
}

/** The key under the timeline: every colour and the two extras. */
export function MarkLegend() {
  const tones: Tone[] = ['doing', 'todo', 'review', 'blocked', 'done', 'shelf']
  return (
    <span className="inline-flex items-center gap-10 flex-wrap">
      {tones.map((t) => (
        <span key={t} className="inline-flex items-center gap-4">
          <span className="inline-block h-8 w-8 rounded-[2px]" style={{ backgroundColor: TONE[t].color }} aria-hidden />
          {TONE[t].label}
        </span>
      ))}
      <span>{t('ring: important · hole: new')}</span>
      <span>{t('faint: mentioned only in a reply')}</span>
    </span>
  )
}
