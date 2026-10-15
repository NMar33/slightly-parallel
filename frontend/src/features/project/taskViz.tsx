import { useMemo } from 'react'
import { LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'
import { dayMonth } from '../../lib/months'

/**
 * taskViz — the shared task-over-time visualisations: the data model, the
 * status spine (intervals), and the three panels that graduated from the
 * variants gallery (River, Chronicle, Ledger), which the project Overview
 * mounts.
 */

type Ev = {
  at: string
  kind: 'created' | 'status' | 'edit' | 'mention'
  field?: string
  from?: string
  to?: string
  actor?: string
  role?: 'user' | 'agent'
  agent_id?: string
  excerpt?: string
}
export type TTask = {
  id: string
  title: string
  status: string
  impact?: string
  effort?: string
  assignee?: string
  events: Ev[]
  last_at: string
}

export const ORDER = ['unclassified', 'backlog', 'next', 'todo', 'doing', 'review', 'done'] as const
export const COLOR: Record<string, string> = {
  unclassified: 'var(--border-default)',
  backlog: 'color-mix(in oklab, var(--text-tertiary) 45%, transparent)',
  next: 'color-mix(in oklab, var(--text-tertiary) 65%, transparent)',
  todo: 'color-mix(in oklab, var(--status-amber) 60%, transparent)',
  doing: 'var(--brand)',
  review: 'var(--status-purple)',
  done: 'var(--status-green)',
}
export const norm = (s?: string) => (ORDER as readonly string[]).includes(String(s || '')) ? String(s) : 'unclassified'
export const ms = (s: string) => { const n = Date.parse(s); return Number.isFinite(n) ? n : 0 }
export const DAY = 86400e3

/** Status in force over [since, now] as segments — the shared spine. */
function intervals(t: TTask, since: number, now: number): Array<{ from: number; to: number; status: string }> {
  const evs = t.events.map((e) => ({ ...e, ms: ms(e.at) })).filter((e) => e.ms > 0).sort((a, b) => a.ms - b.ms)
  const created = evs.find((e) => e.kind === 'created')?.ms ?? since
  const changes = evs.filter((e) => e.kind === 'status')
  const start = Math.max(since, created)
  const before = changes.filter((e) => e.ms <= start)
  let cur = before.length ? norm(before[before.length - 1]!.to) : changes.length ? norm(changes[0]!.from) : norm(t.status)
  let cursor = start
  const out: Array<{ from: number; to: number; status: string }> = []
  for (const c of changes.filter((e) => e.ms > start)) {
    if (c.ms > cursor) out.push({ from: cursor, to: Math.min(c.ms, now), status: cur })
    cursor = c.ms
    cur = norm(c.to)
    if (cursor >= now) break
  }
  if (cursor < now) out.push({ from: cursor, to: now, status: cur })
  return out
}

export function dayList(since: number, now: number): number[] {
  const out: number[] = []
  const d0 = new Date(since); d0.setHours(0, 0, 0, 0)
  for (let t = d0.getTime(); t <= now; t += DAY) out.push(t)
  return out
}
const dayLabel = (t: number) => dayMonth(new Date(t))

function LegendRow({ statuses }: { statuses?: readonly string[] }) {
  return (
    <div className="flex items-center gap-10 flex-wrap text-10 font-mono text-tertiary pt-8">
      {(statuses ?? ORDER).map((s) => (
        <span key={s} className="inline-flex items-center gap-3">
          <span className="w-10 h-6 rounded-bar inline-block" style={{ backgroundColor: COLOR[s] }} /> {s}
        </span>
      ))}
    </div>
  )
}


/* ------------------------------- River ------------------------------ */

export function River({ tasks, since, now }: { tasks: TTask[]; since: number; now: number }) {
  const days = dayList(since, now)
  const series = useMemo(() => {
    const per = tasks.map((t) => ({ created: t.events.find((e) => e.kind === 'created') ? ms(t.events.find((e) => e.kind === 'created')!.at) : since, iv: intervals(t, since, now) }))
    return days.map((d) => {
      const at = d + DAY / 2
      const counts: Record<string, number> = {}
      for (const p of per) {
        if (at < p.created) continue
        const seg = p.iv.find((s) => at >= s.from && at < s.to) ?? p.iv[p.iv.length - 1]
        if (!seg || at < p.iv[0]!.from) continue
        counts[seg.status] = (counts[seg.status] ?? 0) + 1
      }
      return counts
    })
  }, [tasks, since, now, days])
  const W = 900, H = 240, PAD = 4
  const max = Math.max(1, ...series.map((c) => Object.values(c).reduce((a, b) => a + b, 0)))
  const x = (i: number) => (i / Math.max(1, days.length - 1)) * (W - PAD * 2) + PAD
  const areas = ORDER.map((status) => {
    let path = ''
    const tops: number[] = []
    series.forEach((c, i) => {
      let below = 0
      for (const s of ORDER) { if (s === status) break; below += c[s] ?? 0 }
      tops.push(below + (c[status] ?? 0))
      const y0 = H - (below / max) * (H - 20)
      path += `${i === 0 ? 'M' : 'L'} ${x(i)} ${y0} `
    })
    for (let i = series.length - 1; i >= 0; i--) {
      const y1 = H - (tops[i]! / max) * (H - 20)
      path += `L ${x(i)} ${y1} `
    }
    return { status, d: path + 'Z' }
  })
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H + 24}`} className="w-full" style={{ minWidth: 600 }} role="img" aria-label={t('Cumulative flow of tasks by status')}>
        {areas.map((a) => (
          <path key={a.status} d={a.d} fill={COLOR[a.status]} opacity={0.85} stroke="var(--bg-surface)" strokeWidth={0.5}>
            <title>{a.status}</title>
          </path>
        ))}
        {days.map((d, i) => (i % Math.ceil(days.length / 10) === 0 ? (
          <text key={d} x={x(i)} y={H + 16} fontSize={10} fill="var(--text-tertiary)" textAnchor="middle" fontFamily="monospace">{dayLabel(d)}</text>
        ) : null))}
        <text x={PAD} y={12} fontSize={10} fill="var(--text-tertiary)" fontFamily="monospace">{max} {t('tasks')}</text>
      </svg>
      <LegendRow />
      <p className="text-11 text-tertiary pt-4">{t('Band height is the number of tasks in that status that day.')}</p>
    </div>
  )
}

/* ----------------------------- Chronicle ---------------------------- */

const KIND_LABEL: Record<string, [string, string]> = {
  created: ['●', 'var(--text-primary)'],
  status: ['▮', 'var(--brand)'],
  edit: ['┃', 'var(--text-tertiary)'],
  mention: ['◆', 'var(--status-amber)'],
}

export function Chronicle({ tasks, since }: { tasks: TTask[]; since: number }) {
  const byDay = useMemo(() => {
    const all: Array<Ev & { task: TTask; ms: number }> = []
    for (const t of tasks) for (const e of t.events) {
      const m = ms(e.at); if (m >= since) all.push({ ...e, task: t, ms: m })
    }
    all.sort((a, b) => b.ms - a.ms)
    const groups = new Map<string, typeof all>()
    for (const e of all) {
      const k = new Date(e.ms).toDateString()
      groups.set(k, [...(groups.get(k) ?? []), e])
    }
    return [...groups.entries()]
  }, [tasks, since])
  const line = (e: Ev & { task: TTask; ms: number }, i: number) => {
    const [g, c] = KIND_LABEL[e.kind] ?? ['·', 'var(--text-tertiary)']
    const what = e.kind === 'status' ? `${e.from || '—'} → ${e.to}`
      : e.kind === 'edit' ? `${e.field} changed`
      : e.kind === 'mention' ? (e.role === 'user' ? `sent to ${e.agent_id}` : `reply from ${e.agent_id}`)
      : 'created'
    return (
      <li key={i} className="grid items-baseline gap-8 px-6 py-2 rounded-input hover:bg-hover" style={{ gridTemplateColumns: '44px 14px 180px 1fr auto' }}>
        <span className="text-11 font-mono text-tertiary tabular">{new Date(e.ms).toTimeString().slice(0, 5)}</span>
        <span style={{ color: c }} aria-hidden>{g}</span>
        <span className="text-11 font-mono" style={{ color: e.kind === 'status' && e.to === 'done' ? 'var(--status-green)' : 'var(--text-secondary)' }}>{what}</span>
        <span className="text-12 text-primary truncate">{e.task.title}</span>
        <span className="text-10 font-mono text-tertiary">{e.actor || e.agent_id || ''}</span>
      </li>
    )
  }
  return (
    <div className="flex flex-col gap-12 max-w-[860px]">
      {byDay.map(([day, evs]) => (
        <section key={day}>
          <h3 className={`${LABEL} border-b border-border-subtle pb-3 mb-3`}>
            {day} <span className="text-tertiary/70">· {evs.length} {t('events')}</span>
          </h3>
          <ul className="flex flex-col">
            {evs.slice(0, 14).map(line)}
            {evs.length > 14 && (
              <details>
                <summary className="text-11 font-mono text-brand cursor-pointer px-6 py-2">+ {evs.length - 14} {t('more')}</summary>
                <ul className="flex flex-col">{evs.slice(14).map(line)}</ul>
              </details>
            )}
          </ul>
        </section>
      ))}
    </div>
  )
}
