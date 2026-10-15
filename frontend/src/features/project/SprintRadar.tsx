/*
 * The sprint numbers in two readings: the radar (each running block as a
 * shape on five axes) and the collapsed table of how every number is made.
 */
import { useState } from 'react'

import { LoadingSkeleton } from '../../components/states'
import { Button } from '../../components/primitives'
import { useSprintSeries, useSprintsSeries, type SeriesDay, type SprintRow } from './sprintsModel'
import { t } from '../../i18n/scope/project'

import { rich } from '../../i18n/rich'
// ---------------------------------------------------------------------------
// Radar — the blocks as shapes, on live data
// ---------------------------------------------------------------------------

const RADAR_AXES = [
  { label: t('progress'), hint: t('Share of tasks done. The outer ring means all done.') },
  { label: t('pace'), hint: t('The middle ring means on pace. Outside means ahead of plan, inside means behind.') },
  { label: t('budget left'), hint: t('Shows how much of the block\'s hour budget is unspent: outer means untouched, the centre means spent or overspent. It counts only timer entries linked to this block, so it reads full when you never start the timer, and sits in the middle when the block has no budget.') },
  { label: t('agent lift'), hint: t('Share of the work done by agents, from the chats that mention the block\'s tasks.') },
  { label: t('fresh'), hint: t('Task changes and human and agent minutes in the last two days. The centre means no activity.') },
]
const RADAR_TONES = ['var(--brand)', 'var(--status-amber)', 'var(--status-green)']

function radarPt(C: number, R: number, axis: number, v: number): [number, number] {
  const ang = (-90 + axis * (360 / RADAR_AXES.length)) * (Math.PI / 180)
  return [C + R * v * Math.cos(ang), C + R * v * Math.sin(ang)]
}

function radarHealth(vs: number[]): number {
  let area = 0
  for (let i = 0; i < vs.length; i++) area += vs[i]! * vs[(i + 1) % vs.length]!
  return Math.round((area / vs.length) * 100)
}

/** The five axis values at day index `at` of the series (default: last). */
function axesFromSeries(sp: SprintRow, days: SeriesDay[], at?: number): number[] {
  const i = Math.max(0, Math.min(at ?? days.length - 1, days.length - 1))
  const d = days[i]
  if (!d) return [0, 0.5, 0.5, 0, 0]
  const bet = Number(sp.bet_days) || 0
  const progress = d.scope > 0 ? d.done / d.scope : 0
  const timeF = bet > 0 ? (i + 1) / bet : 0
  const humanCum = days.slice(0, i + 1).reduce((a, x) => a + x.human_min, 0)
  const agentCum = days.slice(0, i + 1).reduce((a, x) => a + x.agent_min, 0)
  const w = days.slice(Math.max(0, i - 1), i + 1)
  const fresh = w.reduce((a, x) => a + x.events, 0) / 8 * 0.5 +
    w.reduce((a, x) => a + x.human_min + x.agent_min, 0) / 360 * 0.5
  return [
    progress,
    Math.max(0, Math.min(1, 0.5 + (progress - timeF))),
    Number(sp.budget_h) > 0 ? Math.max(0, Math.min(1, 1 - humanCum / 60 / Number(sp.budget_h))) : 0.5,
    humanCum + agentCum > 0 ? agentCum / (humanCum + agentCum) : 0,
    Math.max(0, Math.min(1, fresh)),
  ]
}

export function RadarPanel({ sprints }: { sprints: SprintRow[] }) {
  // A block whose series failed draws from no days, as before.
  const series = useSprintsSeries(sprints.map((s) => s.id))
  const SZ = 210, C = SZ / 2, R = C - 40
  return (
    <div className="rounded-card border border-border-subtle bg-surface p-16">
      <div className="flex gap-16 flex-wrap justify-center">
        {sprints.map((sp, bi) => {
          const days = series[sp.id]
          if (!days) return <LoadingSkeleton key={sp.id} variant="text" count={3} label={`Loading ${sp.name}`} className="py-24" />
          const now = axesFromSeries(sp, days)
          const past = days.length > 2 ? axesFromSeries(sp, days, days.length - 3) : null
          const health = radarHealth(now)
          const dh = past ? health - radarHealth(past) : 0
          const tone = RADAR_TONES[bi % RADAR_TONES.length]!
          return (
            <div key={sp.id} className="flex flex-col items-center">
              <svg viewBox={`0 0 ${SZ} ${SZ}`} width={SZ} height={SZ} role="img" aria-label={`${sp.name} radar`}>
                {[0.5, 1].map((ring) => (
                  <polygon key={ring} points={RADAR_AXES.map((_, i) => radarPt(C, R, i, ring).join(',')).join(' ')} fill="none" stroke="var(--border-subtle)" />
                ))}
                {RADAR_AXES.map((a, i) => {
                  const [x2, y2] = radarPt(C, R, i, 1)
                  const [lx, ly] = radarPt(C, R, i, 1.26)
                  return (
                    <g key={a.label}>
                      <line x1={C} y1={C} x2={x2} y2={y2} stroke="var(--border-subtle)" />
                      <text x={lx} y={ly + 3} fontSize={8.5} fill="var(--text-tertiary)" textAnchor="middle" fontFamily="monospace" style={{ cursor: 'help' }}>
                        {a.label.split(' ')[0]}
                        <title>{a.hint}</title>
                      </text>
                    </g>
                  )
                })}
                {past && (
                  <polygon points={past.map((v, ax) => radarPt(C, R, ax, Math.max(v, 0.04)).join(',')).join(' ')} fill="none" stroke="var(--text-tertiary)" strokeWidth={1} strokeDasharray="3 3" />
                )}
                <polygon points={now.map((v, ax) => radarPt(C, R, ax, Math.max(v, 0.04)).join(',')).join(' ')} fill={`color-mix(in srgb, ${tone} 22%, transparent)`} stroke={tone} strokeWidth={1.5} />
                <text x={C} y={C + 4} fontSize={15} fontWeight={700} fill="var(--text-primary)" textAnchor="middle">{health}</text>
              </svg>
              <span className="text-12 font-medium text-primary">{sp.name}</span>
              <span className={`text-10 font-mono ${dh > 0 ? 'text-status-green' : dh < 0 ? 'text-status-red' : 'text-tertiary'}`}>
                {t('health')} {health}/100{past ? ` · ${dh > 0 ? t('growing +{n}', { n: dh }) : dh < 0 ? t('shrinking {n}', { n: dh }) : t('holding')}` : ''}
              </span>
            </div>
          )
        })}
      </div>
      <p className="text-10 font-mono text-tertiary mt-6 text-center">
        {t('Outer is better. The number is the area. The dashed line shows two days ago.')}
      </p>
      <dl className="grid gap-x-16 gap-y-3 mt-8 text-11 max-w-[640px] mx-auto" style={{ gridTemplateColumns: 'auto 1fr' }}>
        {RADAR_AXES.map((a) => (
          <div key={a.label} className="contents">
            <dt className="font-mono text-secondary whitespace-nowrap">{a.label}</dt>
            <dd className="text-tertiary leading-relaxed">{a.hint}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

// ---------------------------------------------------------------------------
// How the numbers are made — the collapsed truth table
// ---------------------------------------------------------------------------

/**
 * Every number the sprint views show, with its exact formula — substituted
 * with the first running block's real data, or a worked example when the
 * project has none. Collapsed by default; honesty on demand.
 */
/** One line of the explainer: the term, its formula, the numbers put in. At module level, so a redraw keeps it. */
function CalcRow({ term, formula, sub, note }: { term: string; formula: string; sub: string; note?: string }) {
  return (
    <div className="grid gap-x-12 gap-y-1 py-6 border-b border-border-subtle last:border-0" style={{ gridTemplateColumns: '110px 1fr' }}>
      <span className="text-11 uppercase tracking-wide font-mono text-secondary">{term}</span>
      <div className="min-w-0">
        <code className="block text-11 font-mono text-primary">{formula}</code>
        <div className="text-11 font-mono text-brand mt-1">{sub}</div>
        {note && <div className="text-11 text-tertiary mt-1 leading-relaxed">{note}</div>}
      </div>
    </div>
  )
}

export function CalcExplainer({ sprints }: { sprints: SprintRow[] }) {
  const [open, setOpen] = useState(false)
  const sp = sprints[0] ?? null
  // Read once opened; a failed read leaves the formulas without numbers.
  const seriesRead = useSprintSeries(sp?.id, open)
  const series: SeriesDay[] | null = open ? seriesRead.data ?? null : null

  const ex = sp === null
  const name = sp?.name ?? t('Login (example)')
  const bet = Number(sp?.bet_days) || 7
  const daysLeft = sp?.days_left ?? 4
  const age = bet - (daysLeft ?? 0)
  const humanMin = sp?.human_min ?? 340
  const budget = Number(sp?.budget_h) || (ex ? 12 : 0)
  const agentMin = sp?.agent_min ?? 510
  const done = sp?.tasks_done ?? 2
  const total = sp?.tasks_total ?? 6
  const last2 = series ? series.slice(-2) : null
  const fresh = last2
    ? { events: last2.reduce((a, d) => a + d.events, 0), human: last2.reduce((a, d) => a + d.human_min, 0), agent: last2.reduce((a, d) => a + d.agent_min, 0) }
    : ex ? { events: 5, human: 130, agent: 190 } : null
  const scopeLine = series
    ? series.map((d) => d.scope).join(' → ')
    : ex ? '2 → 4 → 5 → 6' : null

  const h = (min: number) => (min >= 60 ? t('{n}h', { n: Math.round(min / 6) / 10 }) : t('{n}m', { n: min }))
  return (
    <div>
      <Button
        variant="text"
        size="bare"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="uppercase tracking-wide"
      >
        {open ? '▾' : '▸'} {t('how these numbers are counted')}
      </Button>
      {open && (
        <div className="mt-6 rounded-card border border-border-subtle bg-surface px-14 py-8">
          <p className="text-11 text-tertiary leading-relaxed py-4">
            {ex
              ? t('No block is running, so the numbers below are an example. Start a block to see its own.')
              : <>{rich(t('Numbers of {name}, counted again each time this opens.'), { name: <strong className="text-secondary">{name}</strong> })}</>}
          </p>
          <CalcRow
            term={t('days left')}
            formula={t('planned days − days since the start')}
            sub={`${bet} − ${age} = ${daysLeft}d ${Number(daysLeft) < 0 ? 'overdue' : 'left'}`}
            note={t('Calendar days. They count down whether or not anyone works.')}
          />
          <CalcRow
            term={t('human hours')}
            formula={t('Σ timer entry × its share')}
            sub={(budget ? t('{used} of the {n}h budget ({pct}%)', { used: h(humanMin), n: budget, pct: Math.round((humanMin / 60 / budget) * 100) }) : t('{used} — no budget set', { used: h(humanMin) }))}
            note={t('Your own time on the block: the timer entries linked to it, each at the share you set. With no timer entries it is zero.')}
          />
          <CalcRow
            term={t('agent hours')}
            formula={t('Σ length of chats that mention a task of the block')}
            sub={t('{time} across the block\'s tasks', { time: h(agentMin) })}
            note={t('Each chat counts once and whole. A chat that mentions tasks of two blocks counts fully in both.')}
          />
          <CalcRow
            term={t('progress')}
            formula={t('tasks done / tasks in the block now')}
            sub={`${done} / ${total} = ${total ? Math.round((done / total) * 100) : 0}%`}
            note={t('Counted against today\'s tasks, so adding tasks lowers progress.')}
          />
          <CalcRow
            term={t('scope by day')}
            formula={t('tasks in the block on each day')}
            sub={scopeLine ? `scope: ${scopeLine}` : t('loading…')}
            note={t('Read from each task\'s history of joining and leaving the block.')}
          />
          <CalcRow
            term={t('fresh')}
            formula={t('task events + human minutes + agent minutes, last 2 days')}
            sub={fresh ? t('{events} events · {human} human · {agent} agent in the last 2 days', { events: fresh.events, human: h(fresh.human), agent: h(fresh.agent) }) : t('loading…')}
            note={t('Task changes (moves, edits, status) count even when no timer runs.')}
          />
          <CalcRow
            term={t('pace')}
            formula={t('progress − share of planned days spent')}
            sub={t('{done}% done vs {spent}% of the planned days spent → {pace}', { done: total ? Math.round((done / total) * 100) : 0, spent: Math.round((age / bet) * 100), pace: total && done / total - age / bet > 0.15 ? t('ahead') : total && age / bet - done / total > 0.15 ? t('behind') : t('on pace') })}
            note={t('Ahead or behind means a gap of more than 15 points between work done and time spent.')}
          />
        </div>
      )}
    </div>
  )
}
