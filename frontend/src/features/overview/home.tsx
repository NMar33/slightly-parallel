/*
 * The home page (tk_f5eb92ff): a line on the state of things, a box that
 * starts an agent, the day's agent time drawn against a usual working day,
 * what runs now, the latest standups, what waits on the operator, the year
 * with agents and the projects. Colour only for state and the one accent;
 * numbers large and tabular; every line links to where it is acted on.
 */
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { toast } from '../../components/primitives'
import { postJson } from '../../lib/getJson'
import { showTerminal, useTerminalActions, useTerminals, type TermSession } from '../../lib/terminal'
import { StateDot } from '../terminal/parts'
import { OVERVIEW_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import { OPERATOR_ACTOR, nowStamp } from '../project/types'
import { ProjectDot } from '../../components/ProjectDot'
import { ago, hMin, hm } from '../../utils/format'
import { dayHeading, isoDay } from '../../utils/dateUtils'
import { locale } from '../../i18n'
import { t, tn } from '../../i18n/scope/pages'
import type { OverviewData } from './data'
import { workingNow } from './data'
import {
  STEP, YEAR_LIMIT, countsOf, dayCurve, dayKey, period, streak, usualDay, useYear, yearGrid,
  type Year, type YearSession,
} from './home-data'
import { monthLabel } from '../../lib/months'

function reduced(): boolean {
  try { return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches } catch { return false }
}

/** A number that counts up to its value when it first shows or changes. */
function useCountUp(value: number, ms = 700): number {
  const [shown, setShown] = useState(() => (reduced() ? value : 0))
  const from = useRef(0)
  useEffect(() => {
    if (reduced()) { setShown(value); return }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms)
      const v = a + (value - a) * (1 - (1 - k) ** 3)
      setShown(v)
      if (k < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, ms])
  return shown
}

function Heading({ label, aside, to, toLabel }: { label: string; aside?: ReactNode; to?: string; toLabel?: string }) {
  return (
    <div className="flex items-baseline gap-10 min-h-[20px]">
      <h2 className="text-13 font-semibold text-primary">{label}</h2>
      {aside && <span className="text-12 text-tertiary tabular">{aside}</span>}
      <span className="flex-1" />
      {to && <Link to={to} className="text-12 text-tertiary hover:text-brand no-underline">{toLabel ?? t('all')} →</Link>}
    </div>
  )
}

/** "+38%" against a usual amount, or nothing when there is no usual to compare with. */
function delta(value: number, usual: number): { text: string; up: boolean } | null {
  if (usual < 1) return null
  const pct = Math.round(((value - usual) / usual) * 100)
  return { text: `${pct >= 0 ? '+' : '−'}${Math.abs(pct)}%`, up: pct >= 0 }
}

function DeltaChip({ value, usual, against }: { value: number; usual: number; against: string }) {
  const d = delta(value, usual)
  if (!d) return null
  return (
    <span className="inline-flex items-center gap-6 text-12 text-secondary">
      <span className={`inline-flex items-center h-20 px-6 rounded-pill font-medium tabular ${d.up ? 'bg-brand/10 text-[var(--brand-ink)]' : 'bg-hover text-secondary'}`}>
        {d.up ? '▲' : '▼'} {d.text}
      </span>
      {against}
    </span>
  )
}

/* --------------------------------------------------------- waiting */

/** What waits on the operator: open problems (the urgent first) and tasks in review. */
export interface Waiting { key: string; kind: 'problem' | 'review'; text: string; project: string; to: string; tone: 'red' | 'amber'; why: string }

/** What waits for the operator: open high problems, then tasks in review. */
export function waitingOn(data: OverviewData): Waiting[] {
  const out: Waiting[] = []
  for (const p of data.problems) {
    const sev = String(p.severity ?? '').toLowerCase()
    out.push({
      key: `p-${p.id}`, kind: 'problem', text: String(p.l1 ?? p.id), project: String(p.project ?? ''),
      to: `/problems#sel=${encodeURIComponent(String(p.id))}`,
      tone: sev === 'high' || sev === 'critical' ? 'red' : 'amber', why: sev || t('open'),
    })
  }
  for (const r of data.review) {
    if (String(r.archived_at ?? '')) continue
    out.push({
      key: `r-${r.id}`, kind: 'review', text: String(r.title ?? r.id), project: String(r.project ?? ''),
      to: `/project/${encodeURIComponent(String(r.project ?? ''))}#tasks&task=${encodeURIComponent(String(r.id))}`,
      tone: 'amber', why: t('review'),
    })
  }
  return out.sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'red' ? -1 : 1))
}

/* ------------------------------------------------------------- header */

function stateSentence(data: OverviewData, live: number): string {
  const waiting = waitingOn(data).filter((w) => w.kind === 'review' || w.tone === 'red').length
  const a = live ? tn(live, '{n} agent is working', '{n} agents are working') : t('No agent is working')
  const b = waiting ? tn(waiting, '{n} thing waits for you', '{n} things wait for you') : t('nothing waits for you')
  return `${a} · ${b}`
}

function Greeting({ data, live }: { data: OverviewData; live: number }) {
  const now = new Date()
  const date = now.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <header className="flex flex-col gap-4">
      <span className="text-13 text-tertiary first-letter:uppercase">{date}</span>
      <h1 className="text-28 font-semibold text-primary tracking-tight text-balance">{stateSentence(data, live)}</h1>
    </header>
  )
}

/* ----------------------------------------------------------- composer */

/** "Start an agent on a task" — a task on the project's board and an agent started on it. */
function Composer({ data, year }: { data: OverviewData; year: Year }) {
  const act = useTerminalActions()
  const projects = useMemo(() => {
    const recent = new Map<string, number>()
    for (const s of year.sessions) recent.set(s.project, Math.max(recent.get(s.project) ?? 0, Date.parse(`20${s.created_date.slice(0, 2)}-${s.created_date.slice(2, 4)}-${s.created_date.slice(5, 7)}`) || 0))
    return (data.snapshot?.projects ?? []).map((p) => p.code).sort((a, b) => (recent.get(b) ?? 0) - (recent.get(a) ?? 0))
  }, [data.snapshot, year.sessions])
  const [project, setProject] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const chosen = project || projects[0] || ''
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const title = text.trim()
    if (!title || !chosen || busy) return
    setBusy(true)
    try {
      const { dateStr, timeStr } = nowStamp()
      const answer = await postJson<{ metadata?: { id?: string } }>('/api/tasks', {
        project: chosen, projects: chosen, agent_id: OPERATOR_ACTOR, created_date: dateStr, created_time: timeStr,
        title, status: 'doing', priority: 'med', assignee: '', lane: 'unassigned', actor: OPERATOR_ACTOR,
      })
      const id = answer.metadata?.id
      if (!id) throw new Error(t('the task was not created'))
      act.open({ kind: 'start', task_id: id, project: chosen, label: title })
      setText('')
    } catch (err) {
      toast.error(t('Could not start the agent: {error}', { error: err instanceof Error ? err.message : String(err) }))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="flex items-center gap-8 rounded-card border border-border-default bg-surface pl-16 pr-6 h-[52px] shadow-sm focus-within:border-brand transition-colors">
      <span aria-hidden className="text-brand text-16">›</span>
      <input id="home-composer" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off"
        placeholder={t('The work for an agent, in one line')} aria-label={t('Start an agent on a task')}
        className="flex-1 min-w-0 bg-transparent outline-none text-16 text-primary placeholder:text-tertiary" />
      <select id="home-composer-project" value={chosen} onChange={(e) => setProject(e.target.value)} aria-label={t('Project')}
        className="h-32 max-w-[140px] rounded-pill border border-border-subtle bg-base px-10 text-12 font-mono text-secondary hover:border-border-default">
        {projects.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <button type="submit" disabled={!text.trim() || busy}
        className="h-[40px] px-16 rounded-[8px] bg-brand text-on-brand text-13 font-medium disabled:opacity-40 hover:bg-brand-hover transition-colors">
        {t('Start an agent')}
      </button>
    </form>
  )
}

/* --------------------------------------------------------------- hero */

function useHeroDay(year: Year) {
  const today = dayKey(0)
  const todayRows = year.days.get(today) ?? []
  const todayMin = countsOf(todayRows).minutes
  // Early in the day, before the work starts, the full day before is the better picture.
  const defaultDay: 'today' | 'yesterday' = todayMin >= 15 || new Date().getHours() >= 11 ? 'today' : 'yesterday'
  const [which, setWhich] = useState<'today' | 'yesterday' | null>(null)
  const shown = which ?? defaultDay
  const day = shown === 'today' ? today : dayKey(-1)
  // The usual day walks weeks of rows: read once per year and day, not per render.
  const picture = useMemo(() => {
    const rows = year.days.get(day) ?? []
    return { rows, counts: countsOf(rows), curve: dayCurve(rows), usual: usualDay(year.days, day) }
  }, [year.days, day])
  return { shown, setWhich, day, ...picture }
}

function DaySwitch({ shown, set }: { shown: 'today' | 'yesterday'; set: (v: 'today' | 'yesterday') => void }) {
  return (
    <div role="radiogroup" aria-label={t('Day')} className="inline-flex p-2 rounded-pill bg-hover">
      {(['today', 'yesterday'] as const).map((k) => (
        <button key={k} type="button" role="radio" aria-checked={shown === k} onClick={() => set(k)}
          className={`h-24 px-10 rounded-pill text-12 transition-colors ${shown === k ? 'bg-surface text-primary shadow-sm' : 'text-tertiary hover:text-primary'}`}>
          {k === 'today' ? t('Today') : t('Yesterday')}
        </button>
      ))}
    </div>
  )
}

function nowStep(): number { const d = new Date(); return Math.floor((d.getHours() * 60 + d.getMinutes()) / STEP) }

function clockOf(step: number): string {
  const m = step * STEP
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

const W = 640
const H = 190
const PAD = { l: 34, r: 8, t: 10, b: 22 }

function niceStep(max: number): number {
  const hours = max / 60
  const s = [0.5, 1, 2, 3, 4, 6, 8, 12].find((x) => hours / x <= 4) ?? 12
  return s * 60
}

function DayChart({ curve, usual, live }: { curve: number[]; usual: number[]; live: boolean }) {
  const end = live ? nowStep() : curve.length - 1
  const max = Math.max(60, curve[curve.length - 1] ?? 0, usual[usual.length - 1] ?? 0) * 1.08
  const x = (i: number) => PAD.l + (i / (curve.length - 1)) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b)
  const line = curve.slice(0, end + 1).map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(end).toFixed(1)} ${y(0)} L${x(0)} ${y(0)} Z`
  const ghost = usual.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const step = niceStep(max)
  const grid: number[] = []
  for (let v = step; v < max; v += step) grid.push(v)
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const onMove = (e: React.PointerEvent) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r) return
    const px = ((e.clientX - r.left) / r.width) * W
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (curve.length - 1))
    setHover(Math.max(0, Math.min(curve.length - 1, i)))
  }
  const h = hover
  return (
    <div className="relative">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block overflow-visible" role="img"
        aria-label={t('Agent time through the day, against a usual working day')}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="home-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {grid.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--border-subtle)" />
            <text x={PAD.l - 8} y={y(v) + 3} textAnchor="end" fontSize={10} fill="var(--text-tertiary)" fontFamily="var(--font-mono)">{hm(v)}</text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} stroke="var(--border-default)" />
        {[0, 6, 12, 18, 24].map((hr) => (
          <text key={hr} x={x((hr * 60) / STEP)} y={H - 6} textAnchor={hr === 0 ? 'start' : hr === 24 ? 'end' : 'middle'} fontSize={10} fill="var(--text-tertiary)" fontFamily="var(--font-mono)">
            {String(hr).padStart(2, '0')}:00
          </text>
        ))}
        <path d={ghost} fill="none" stroke="var(--text-tertiary)" strokeWidth={1.5} strokeDasharray="3 4" opacity={0.7} />
        <path d={area} fill="url(#home-area)" className="home-fade" />
        <path d={line} fill="none" stroke="var(--brand)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className="home-draw" pathLength={1} />
        {live && (
          <g>
            <circle cx={x(end)} cy={y(curve[end] ?? 0)} r={8} fill="var(--brand)" opacity={0.25} className="home-ping" />
            <circle cx={x(end)} cy={y(curve[end] ?? 0)} r={4} fill="var(--brand)" stroke="var(--bg-surface)" strokeWidth={2} />
          </g>
        )}
        {h !== null && (
          <g pointerEvents="none">
            <line x1={x(h)} x2={x(h)} y1={PAD.t} y2={y(0)} stroke="var(--border-strong)" />
            {h <= end && <circle cx={x(h)} cy={y(curve[h] ?? 0)} r={4} fill="var(--brand)" stroke="var(--bg-surface)" strokeWidth={2} />}
            <circle cx={x(h)} cy={y(usual[h] ?? 0)} r={3} fill="var(--text-tertiary)" />
          </g>
        )}
      </svg>
      {h !== null && (
        <div className="absolute top-0 pointer-events-none rounded-[8px] border border-border-default bg-elevated shadow-md px-10 py-6 text-12 flex flex-col gap-2 tabular"
          style={{ left: `${(x(h) / W) * 100}%`, transform: `translateX(${x(h) > W * 0.7 ? 'calc(-100% - 10px)' : '10px'})` }}>
          <span className="font-mono text-tertiary">{clockOf(h + 1)}</span>
          {h <= end && <span className="text-primary"><span className="inline-block w-8 h-2 mr-6 align-middle bg-brand rounded-pill" />{hMin(curve[h] ?? 0, '0m')}</span>}
          <span className="text-secondary"><span className="inline-block w-8 h-2 mr-6 align-middle bg-tertiary rounded-pill opacity-70" />{t('usual')} {hMin(usual[h] ?? 0, '0m')}</span>
        </div>
      )}
    </div>
  )
}

function TodayCard({ year }: { year: Year }) {
  const d = useHeroDay(year)
  const live = d.shown === 'today'
  const usualNow = live ? d.usual.curve[nowStep()] ?? 0 : d.usual.counts.minutes
  const big = useCountUp(d.counts.minutes)
  const minor: Array<[string, number, number]> = [
    [t('commits'), d.counts.commits, d.usual.counts.commits],
    [t('tasks worked on'), d.counts.tasks, d.usual.counts.tasks],
    [t('entries written'), d.counts.entries, d.usual.counts.entries],
    [t('chats'), d.counts.chats, d.usual.counts.chats],
  ]
  return (
    <section aria-label={t('The day')} data-testid="home-day" className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-20 min-w-0">
      <div className="flex items-center gap-12 flex-wrap">
        <DaySwitch shown={d.shown} set={d.setWhich} />
        <span className="flex-1" />
        {(
          <span className="flex items-center gap-12 text-12 text-tertiary">
            <span className="flex items-center gap-6"><span className="w-12 h-2 rounded-pill bg-brand" />{live ? t('today') : dayHeading(d.day)}</span>
            <span className="flex items-center gap-6"><svg width="14" height="2" aria-hidden><line x1="0" x2="14" y1="1" y2="1" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeDasharray="3 3" /></svg>{t('usual working day')}</span>
          </span>
        )}
      </div>
      <div className="flex flex-col gap-6">
        <span className="text-13 text-secondary">{live ? t('Agents worked today') : t('Agents worked yesterday')}</span>
        <span className="flex items-baseline gap-16 flex-wrap">
          <span className="text-56 font-semibold text-primary tracking-tight tabular">{hMin(big, '0m')}</span>
          <DeltaChip value={d.counts.minutes} usual={usualNow}
            against={live ? t('against a usual day by {time}', { time: clockOf(nowStep()) }) : t('against a usual working day')} />
        </span>
      </div>
      <DayChart curve={d.curve} usual={d.usual.curve} live={live} />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-16 pt-16 border-t border-border-subtle">
        {minor.map(([label, v, u]) => (
          <div key={label} className="flex flex-col gap-2 min-w-0">
            <span className="text-12 text-tertiary">{label}</span>
            <span className="flex items-baseline gap-6">
              <span className="text-20 font-semibold text-primary tabular">{Math.round(v)}</span>
              {u >= 0.5 && <span className={`text-12 tabular ${v >= u ? 'text-[var(--brand-ink)]' : 'text-tertiary'}`}>{t('usual {n}', { n: u < 10 ? u.toFixed(1).replace(/\.0$/, '') : Math.round(u) })}</span>}
            </span>
          </div>
        ))}
      </div>
      <p className="text-11 text-tertiary -mt-8">{tn(d.usual.days, 'A usual working day: the mean of {n} day with agent time in the 30 days before.', 'A usual working day: the mean of {n} days with agent time in the 30 days before.')}</p>
    </section>
  )
}

/* ---------------------------------------------------------- yesterday */

function YesterdayColumn({ data }: { data: OverviewData }) {
  const y = dayKey(-1)
  const items = [...data.latestStandup.values()]
    .filter((s) => (s.for_date || s.created_date) >= dayKey(-7))
    .sort((a, b) => String(b.for_date || '').localeCompare(String(a.for_date || '')))
  const day = items[0]?.for_date
  return (
    <section aria-label={t('What happened')} className="flex flex-col gap-14 min-w-0">
      <Heading label={day === y ? t('Yesterday') : t('Latest standups')} to="/standups" toLabel={t('standups')} />
      {items.length === 0 && <p className="text-13 text-tertiary">{t('No standup this week. One is written the morning after a day of work.')}</p>}
      <ol className="flex flex-col gap-16">
        {items.slice(0, 4).map((s) => (
          <li key={s.id}>
            <NavLink to={`/standups#project=${encodeURIComponent(s.project)}`} className="group flex flex-col gap-4 no-underline">
              <span className="flex items-center gap-6 text-12 text-tertiary">
                <ProjectDot code={s.project} size={7} /><span className="font-mono text-secondary">{s.project}</span>
                {(s.for_date || '') !== y && <span>· {dayHeading(s.for_date || s.created_date)}</span>}
              </span>
              <span className="text-14 leading-[1.5] text-primary line-clamp-3 group-hover:text-brand transition-colors">{s.l1}</span>
            </NavLink>
          </li>
        ))}
      </ol>
    </section>
  )
}

/* ---------------------------------------------------------------- now */

interface Live { key: string; title: string; project: string; since: string; state: string; termState?: TermSession['state']; to?: string; term?: string }

function chatTitle(raw: string): string {
  return raw.replace(/\s*\((Branch|Fork)\)\s*$/i, '').replace(/^tk_[0-9a-f]{6,}\s*·\s*/, '').trim()
}

function useLive(data: OverviewData, year: Year): { live: Live[]; last?: { title: string; at: number; to: string } } {
  const terms = useTerminals().data?.sessions ?? []
  const todayKey = dayKey(0)
  const firstToday = useMemo(() => {
    const out = new Map<string, YearSession>()
    for (const s of year.days.get(todayKey) ?? []) { const f = out.get(s.agent_id); if (!f || s.start_time < f.start_time) out.set(s.agent_id, s) }
    return out
  }, [year.days, todayKey])
  // Each agent's newest session, in one pass over the year instead of a filter and sort per agent.
  const latest = useMemo(() => {
    const out = new Map<string, YearSession>()
    for (const s of year.sessions) {
      const have = out.get(s.agent_id)
      if (!have || (s.created_date + s.end_time).localeCompare(have.created_date + have.end_time) > 0) out.set(s.agent_id, s)
    }
    return out
  }, [year.sessions])
  const latestOf = (agentId: string) => latest.get(agentId)
  const out: Live[] = []
  const seen = new Set<string>()
  for (const term of terms) {
    if (term.state !== 'working' && term.state !== 'waiting') continue
    // A terminal left waiting for days is not work going on now.
    const quietMs = Date.now() - term.last_output * 1000
    if (term.state === 'waiting' && quietMs > 2 * 3600_000) continue
    const first = term.agent_id ? firstToday.get(term.agent_id) : undefined
    out.push({
      key: term.id, title: term.label, project: term.project,
      since: first ? first.start_time : startedToday(term.created),
      state: term.state === 'working' ? t('working') : t('waits for you since {ago}', { ago: ago(quietMs) }), termState: term.state, term: term.id,
    })
    if (term.agent_id) seen.add(term.agent_id)
  }
  for (const a of workingNow(data)) {
    if (seen.has(a.agent_id)) continue
    const s = latestOf(a.agent_id)
    const first = firstToday.get(a.agent_id)
    out.push({
      key: a.agent_id, title: chatTitle(a.chat_title || s?.l1.split(' → ')[0] || a.agent_id), project: a.project,
      since: first ? first.start_time : '', state: t('answered {ago}', { ago: ago(Date.now() - Date.parse(String(a.last_active))) }),
      to: `/agent/${encodeURIComponent(a.agent_id)}`,
    })
  }
  const lastAgent = [...(data.snapshot?.agents ?? [])].sort((a, b) => String(b.last_active).localeCompare(String(a.last_active)))[0]
  const last = lastAgent ? { title: chatTitle(lastAgent.chat_title || latestOf(lastAgent.agent_id)?.l1.split(' → ')[0] || lastAgent.agent_id), at: Date.parse(String(lastAgent.last_active)), to: `/agent/${encodeURIComponent(lastAgent.agent_id)}` } : undefined
  return { live: out, last }
}

/**
 * A terminal's start when it was today, else ''. `created` is the server's
 * local time on this same machine, so it is compared with the local day —
 * not the UTC one, which differs for hours around midnight.
 */
export function startedToday(created: string, now = new Date()): string {
  return created.slice(0, 10) === isoDay(now) ? created : ''
}

function sinceText(since: string): string {
  if (!since) return ''
  let start: number
  if (/^\d\d:\d\d$/.test(since)) { const d = new Date(); const [h, m] = since.split(':').map(Number); d.setHours(h!, m!, 0, 0); start = d.getTime() } else start = Date.parse(since)
  if (!Number.isFinite(start)) return ''
  return hMin((Date.now() - start) / 60000, t('just started'))
}

function NowSection({ live, last }: ReturnType<typeof useLive>) {
  const [, tick] = useState(0)
  useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 30_000); return () => clearInterval(id) }, [])
  return (
    <section aria-label={t('Now')} className="flex flex-col gap-10 min-w-0">
      <Heading label={t('Now')} aside={live.length ? live.length : undefined} to="/agent" toLabel={t('agents')} />
      {live.length === 0 ? (
        <div className="rounded-card border border-dashed border-border-default px-16 py-14 flex flex-col gap-4">
          <span className="text-13 text-secondary">{t('No agent is working right now.')}</span>
          {last && Number.isFinite(last.at) && (
            <NavLink to={last.to} className="text-12 text-tertiary hover:text-brand no-underline truncate">{t('Last: {title} · {ago}', { title: last.title, ago: ago(Date.now() - last.at) })}</NavLink>
          )}
        </div>
      ) : (
        <ul className="flex flex-col rounded-card border border-border-subtle bg-surface divide-y divide-[var(--border-subtle)]">
          {live.map((l) => {
            const inner = (
              <>
                <span className="w-10 flex justify-center">
                  {l.termState ? <StateDot state={l.termState} size={8} /> : (
                    <span className="relative inline-flex w-8 h-8"><span className="absolute inset-0 rounded-pill bg-brand animate-ping opacity-40" /><span className="relative w-8 h-8 rounded-pill bg-brand" /></span>
                  )}
                </span>
                <span className="flex-1 min-w-0 flex flex-col gap-2">
                  <span className="text-14 text-primary truncate group-hover:text-brand transition-colors">{l.title}</span>
                  <span className="flex items-center gap-6 text-12 text-tertiary"><ProjectDot code={l.project} size={6} /><span className="font-mono">{l.project}</span><span>· {l.state}</span></span>
                </span>
                <span className="text-12 font-mono text-secondary tabular shrink-0">{sinceText(l.since)}</span>
              </>
            )
            return (
              <li key={l.key}>
                {l.term
                  ? <button type="button" onClick={() => showTerminal(l.term)} className="group w-full text-left flex items-center gap-12 px-14 py-10 hover:bg-hover transition-colors">{inner}</button>
                  : <NavLink to={l.to!} className="group flex items-center gap-12 px-14 py-10 no-underline hover:bg-hover transition-colors">{inner}</NavLink>}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/* ---------------------------------------------------------- needs you */

export function NeedsYou({ data }: { data: OverviewData }) {
  const qc = useQueryClient()
  const [gone, setGone] = useState<Set<string>>(new Set())
  const waiting = waitingOn(data)
  // An answered task leaves the list for good once the server's list no
  // longer holds it: forget it then, so `gone` does not grow all day.
  const listed = waiting.map((w) => w.key).join('\n')
  useEffect(() => {
    const keys = new Set(listed.split('\n'))
    setGone((g) => {
      const kept = [...g].filter((k) => keys.has(k))
      return kept.length === g.size ? g : new Set(kept)
    })
  }, [listed])
  const all = waiting.filter((w) => !gone.has(w.key))
  const items = all.filter((w) => w.kind === 'review' || w.tone === 'red')
  const others = all.length - items.length
  const decide = async (w: Waiting, status: 'done' | 'doing') => {
    const id = w.key.slice(2)
    setGone((g) => new Set(g).add(w.key))
    try {
      await postJson(`/api/tasks/${encodeURIComponent(id)}/update`, { status, actor: OPERATOR_ACTOR })
      toast.success(status === 'done' ? t('Accepted: {title}', { title: w.text }) : t('Sent back: {title}', { title: w.text }))
      // The review list is a lens query; the board and the counts follow the server's freshness stamp.
      void qc.invalidateQueries({ queryKey: ['lens'] })
    } catch (err) {
      setGone((g) => { const n = new Set(g); n.delete(w.key); return n })
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }
  return (
    <section aria-label={t('Needs you')} data-testid="needs-you" className="flex flex-col gap-10 min-w-0">
      <Heading label={t('Needs you')} aside={items.length || undefined} to="/kanban" toLabel={t('board')} />
      {items.length === 0 ? (
        <div className="rounded-card border border-dashed border-border-default px-16 py-14 text-13 text-secondary">{t('Nothing waits for you.')}</div>
      ) : (
        <ul className="flex flex-col rounded-card border border-border-subtle bg-surface divide-y divide-[var(--border-subtle)]">
          {items.slice(0, 6).map((w) => (
            <li key={w.key} className="group flex items-center gap-12 px-14 py-10 hover:bg-hover transition-colors">
              <span className={`w-[3px] self-stretch rounded-pill ${w.tone === 'red' ? 'bg-status-red' : w.kind === 'review' ? 'bg-status-info' : 'bg-status-amber'}`} aria-hidden />
              <NavLink to={w.to} className="flex-1 min-w-0 flex flex-col gap-2 no-underline">
                <span className="text-14 text-primary truncate group-hover:text-brand transition-colors" title={w.text}>{w.text}</span>
                <span className="flex items-center gap-6 text-12 text-tertiary">
                  <span className={w.tone === 'red' ? 'text-[var(--status-red-ink)]' : ''}>{w.kind === 'review' ? t('in review') : t('problem · {sev}', { sev: w.why })}</span>
                  {w.project && <><span>·</span><ProjectDot code={w.project} size={6} /><span className="font-mono">{w.project}</span></>}
                </span>
              </NavLink>
              {w.kind === 'review' && (
                <span className="flex items-center gap-6 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
                  <button type="button" onClick={() => void decide(w, 'doing')} className="h-[28px] px-10 rounded-[7px] border border-border-default text-12 text-secondary hover:text-primary hover:border-border-strong">{t('Send back')}</button>
                  <button type="button" onClick={() => void decide(w, 'done')} className="h-[28px] px-10 rounded-[7px] bg-brand text-on-brand text-12 font-medium hover:bg-brand-hover">{t('Accept')}</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <span className="flex gap-16 text-12 text-tertiary">
        {items.length > 6 && <Link to="/kanban" className="hover:text-brand no-underline">{t('{n} more', { n: items.length - 6 })} →</Link>}
        {others > 0 && <Link to="/problems" className="hover:text-brand no-underline">{tn(others, '{n} other open problem', '{n} other open problems')} →</Link>}
      </span>
    </section>
  )
}

/* --------------------------------------------------------------- year */

function YearSection({ year }: { year: Year }) {
  const grid = useMemo(() => yearGrid(year.days), [year.days])
  const run = useMemo(() => streak(year.days), [year.days])
  const cur = useMemo(() => period(year.days, 30), [year.days])
  const prev = useMemo(() => period(year.days, 30, 30), [year.days])
  const total = useMemo(() => grid.reduce((s, c) => s + c.minutes, 0), [grid])
  const nonzero = grid.filter((c) => c.minutes > 0).map((c) => c.minutes).sort((a, b) => a - b)
  const q = (p: number) => nonzero[Math.floor(p * (nonzero.length - 1))] ?? 0
  const cuts = [q(0.25), q(0.5), q(0.8)]
  const level = (m: number) => (m <= 0 ? 0 : m <= cuts[0]! ? 1 : m <= cuts[1]! ? 2 : m <= cuts[2]! ? 3 : 4)
  const fill = ['var(--bg-hover)', 'color-mix(in oklab, var(--brand) 28%, var(--bg-surface))', 'color-mix(in oklab, var(--brand) 52%, var(--bg-surface))', 'color-mix(in oklab, var(--brand) 78%, var(--bg-surface))', 'var(--brand)']
  const weeks = Math.ceil(grid.length / 7)
  const CELL = 14
  const GAP = 3
  const months: Array<{ col: number; name: string }> = []
  for (let w = 0; w < weeks; w += 1) {
    const first = grid[w * 7]!
    if (first.date.getDate() <= 7) months.push({ col: w, name: monthLabel(first.date) })
  }
  const figures: Array<[string, string, number, number]> = [
    [t('agent time'), hMin(cur.minutes, '0m'), cur.minutes, prev.minutes],
    [t('commits'), cur.commits.toLocaleString(locale()), cur.commits, prev.commits],
    [t('lines added'), cur.added.toLocaleString(locale()), cur.added, prev.added],
    [t('tasks worked on'), String(cur.tasks), cur.tasks, prev.tasks],
  ]
  return (
    <section aria-label={t('The year')} className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-20 min-w-0">
      <div className="flex items-baseline gap-12 flex-wrap">
        <h2 className="text-13 font-semibold text-primary">{t('With agents')}</h2>
        <span className="text-12 text-tertiary tabular">{t('{h} of agent time', { h: hMin(total, '0m') })}</span>
        <span className="flex-1" />
        {run > 1 && (
          <span className="inline-flex items-center gap-6 h-24 px-10 rounded-pill bg-brand/10 text-12 text-[var(--brand-ink)] font-medium tabular">
            {tn(run, '{n} day in a row', '{n} days in a row')}
          </span>
        )}
      </div>
      <div className="grid gap-32 xl:grid-cols-[minmax(0,1fr)_auto] items-start">
      <div className="grid grid-cols-2 gap-20">
        {figures.map(([label, text, v, p]) => (
          <div key={label} className="flex flex-col gap-2">
            <span className="text-12 text-tertiary">{label} · {t('30 days')}</span>
            <span className="text-24 font-semibold text-primary tabular">{text}</span>
            <DeltaChip value={v} usual={p} against={t('against the 30 days before')} />
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-8 min-w-0">
      <div className="overflow-x-auto -mx-4 px-4">
        <svg width={weeks * (CELL + GAP) + 28} height={7 * (CELL + GAP) + 18} role="img" aria-label={t('Agent time per day, the last year')} className="block">
          {months.map((m) => (
            <text key={m.col} x={28 + m.col * (CELL + GAP)} y={10} fontSize={10} fill="var(--text-tertiary)">{m.name}</text>
          ))}
          {[1, 3, 5].map((r) => (
            <text key={r} x={0} y={18 + r * (CELL + GAP) + CELL - 2} fontSize={10} fill="var(--text-tertiary)">
              {new Date(2024, 0, r).toLocaleDateString(locale(), { weekday: 'short' })}
            </text>
          ))}
          {grid.map((c, i) => c.future ? null : (
            <rect key={c.day} x={28 + Math.floor(i / 7) * (CELL + GAP)} y={18 + (i % 7) * (CELL + GAP)} width={CELL} height={CELL} rx={3}
              fill={fill[level(c.minutes)]} className="home-cell" style={{ animationDelay: `${Math.floor(i / 7) * 12}ms` }}>
              <title>{`${dayHeading(c.day)} · ${c.minutes ? hMin(c.minutes) : t('no agent time')}`}</title>
            </rect>
          ))}
        </svg>
      </div>
      <div className="flex items-center gap-6 text-11 text-tertiary">
        <span>{t('less')}</span>
        {fill.map((f, i) => <span key={i} className="w-12 h-12 rounded-[3px]" style={{ background: f }} />)}
        <span>{t('more')}</span>
      </div>
      {year.truncated && (
        <p className="text-11 text-tertiary">{t('The year shows the latest {n} chats.', { n: YEAR_LIMIT.toLocaleString(locale()) })}</p>
      )}
      </div>
      </div>
    </section>
  )
}

/* ----------------------------------------------------------- projects */

function Projects({ data, year }: { data: OverviewData; year: Year }) {
  const days = data.days
  // Agent minutes per project per day, in one pass over the days shown.
  const perProject = useMemo(() => {
    const out = new Map<string, number[]>()
    days.forEach((d, i) => {
      for (const s of year.days.get(d) ?? []) {
        const per = out.get(s.project) ?? new Array<number>(days.length).fill(0)
        per[i]! += Number(s.agent_min) || 0
        out.set(s.project, per)
      }
    })
    return out
  }, [days, year.days])
  const rows = (data.snapshot?.projects ?? []).map((p) => {
    const per = perProject.get(p.code) ?? days.map(() => 0)
    return { p, per, total: per.reduce((a, b) => a + b, 0) }
  }).sort((a, b) => b.total - a.total || String(b.p.last_activity).localeCompare(String(a.p.last_activity)))
  const max = Math.max(1, ...rows.flatMap((r) => r.per))
  return (
    <section aria-label={t('Projects')} className="flex flex-col gap-10 min-w-0">
      <Heading label={t('Projects')} aside={rows.length} />
      <ul data-testid="fleet-cards" className="flex flex-col rounded-card border border-border-subtle bg-surface divide-y divide-[var(--border-subtle)]">
        {rows.map(({ p, per, total }) => {
          const standup = data.latestStandup.get(p.code)
          return (
            <li key={p.code}>
              <NavLink to={`/project/${encodeURIComponent(p.code)}`} className="group grid items-center gap-16 px-14 py-12 no-underline hover:bg-hover transition-colors md:grid-cols-[160px_minmax(0,1fr)_150px_120px]">
                <span className="flex items-center gap-8 min-w-0"><ProjectDot code={p.code} /><span className="font-mono text-13 text-primary truncate group-hover:text-brand">{p.code}</span></span>
                <span className="text-13 text-secondary truncate" title={standup?.l1 || p.l1_headline}>{standup?.l1 || p.l1_headline || '—'}</span>
                <span className="flex items-end gap-2 h-24" aria-label={t('agent time per day, last {n} days', { n: days.length })}>
                  {per.map((v, i) => <span key={i} className="flex-1 rounded-[1px]" style={{ height: v ? `${Math.max(3, (v / max) * 24)}px` : '1px', background: v ? 'var(--brand)' : 'var(--border-default)', opacity: v ? 0.45 + 0.55 * (v / max) : 1 }} />)}
                </span>
                <span className="flex flex-col items-end text-12 tabular">
                  <span className="text-primary">{total ? hMin(total) : '—'}</span>
                  <span className="text-tertiary">{t('{n} open', { n: p.open_tasks })}</span>
                </span>
              </NavLink>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* --------------------------------------------------------------- page */

const MOTION = `
@keyframes home-draw { from { stroke-dashoffset: 1 } to { stroke-dashoffset: 0 } }
@keyframes home-fade { from { opacity: 0 } to { opacity: 1 } }
@keyframes home-ping { 0% { transform: scale(.6); opacity: .5 } 100% { transform: scale(2.2); opacity: 0 } }
@keyframes home-cell { from { opacity: 0 } to { opacity: 1 } }
.home-draw { stroke-dasharray: 1; animation: home-draw 1.1s cubic-bezier(.2,.7,.2,1) both }
.home-fade { animation: home-fade .9s .3s ease-out both }
.home-ping { transform-box: fill-box; transform-origin: center; animation: home-ping 1.8s ease-out infinite }
.home-cell { animation: home-cell .4s ease-out both }
@media (prefers-reduced-motion: reduce) { .home-draw, .home-fade, .home-ping, .home-cell { animation: none } }
`

export function Home({ data }: { data: OverviewData }) {
  const year = useYear()
  const now = useLive(data, year)
  return (
    <div className="flex flex-col gap-24 max-w-[1180px] w-full">
      <style>{MOTION}</style>
      <Greeting data={data} live={now.live.length} />
      <Composer data={data} year={year} />
      <div className="grid gap-24 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] items-start">
        {year.ready ? <TodayCard year={year} /> : <div className="rounded-card border border-border-subtle bg-surface h-[420px] animate-pulse" />}
        <div className="flex flex-col gap-32 min-w-0">
          <NowSection {...now} />
          <YesterdayColumn data={data} />
        </div>
      </div>
      <NeedsYou data={data} />
      {year.ready && <YearSection year={year} />}
      {year.ready && <Projects data={data} year={year} />}
      <PageGuide id="overview" guide={OVERVIEW_GUIDE} examples={0} />
    </div>
  )
}
