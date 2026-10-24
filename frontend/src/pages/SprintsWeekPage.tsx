import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Play, Square } from 'lucide-react'

import { EmptyState, LoadingSkeleton } from '../components/states'
import { COLOR, ORDER } from '../features/project/taskViz'
import { dayLabel } from '../features/sprints/bands'
import { Histogram, NetBars, WeekdayBars } from '../features/sprints/eda'
import {
  type Block, VERDICT_TONE, clock, hm, isDone, timerSec, verdictOf,
} from '../features/sprints/deck'
import type { ViewProps } from '../features/sprints/view'
import { FinishDialog } from '../features/sprints/parts'
import { sprintsTimelineQuery, type TimelineSprint } from '../features/project/sprintsModel'
import { Live } from '../lib/clock'
import { betSpan, effectivity, isWeekendMs, isoOf, leadTime, numbers, readings, seriesMap, stuckDays, useWindow, weekdayShort } from '../features/sprints/week'
import { t } from '../i18n/scope/pages'
type Bands = Record<string, number>
type SeriesDay = { date: string; done: number; human_min: number; agent_min: number; events: number; bands?: Bands }
type Spans = Record<string, TimelineSprint['tasks']>

/** A task status as shown: its own entry ("status:doing"), so the bare word
 *  stays free for other uses. */
function statusText(status: string): string {
  const key = `status:${status}`
  const text = t(key)
  return text === key ? status : text
}

/** Each sprint's task spans, from every project's timeline that has come in. */
type ReadState = 'reading' | 'failed' | 'read'
type SpanResult = { data?: { sprints?: TimelineSprint[] }; isPending?: boolean; isError?: boolean }
/** Each sprint's task spans, and how each project's read stands: a sprint
 *  with no tasks, or a read that failed, said "Loading tasks…" for good. */
function spansOf(results: SpanResult[], projects: string[]): { spans: Spans; state: Record<string, ReadState> } {
  const out: Spans = {}
  const state: Record<string, ReadState> = {}
  results.forEach((r, i) => {
    for (const sp of r.data?.sprints ?? []) out[sp.id] = sp.tasks ?? []
    state[projects[i]!] = r.data !== undefined ? 'read' : r.isError ? 'failed' : 'reading'
  })
  return { spans: out, state }
}

export default function SprintsWeekPage({ deck, err, refresh, actions, range }: ViewProps) {
  const [openRow, setOpenRow] = useState<Set<string>>(new Set())
  const [picked, setPicked] = useState<{ block: string; iso: string } | null>(null)
  const [band, setBand] = useState<{ block: string; status: string } | null>(null)
  const [openNumbers, setOpenNumbers] = useState(false)
  const [openEff, setOpenEff] = useState(false)
  const [finishing, setFinishing] = useState<Block | null>(null)
  const win = useWindow(deck?.today ?? isoOf(Date.now()), range)

  // Task spans are only needed when a row opens — one read per project of
  // the open rows, shared with the project's sprint timeline. A read that
  // fails leaves its rows saying the spans are still being read.
  const openProjects = deck ? [...new Set(deck.blocks.filter((b) => openRow.has(b.id)).map((b) => b.project))] : []
  const { spans, state: spanState } = useQueries({
    queries: openProjects.map(sprintsTimelineQuery), combine: (results) => spansOf(results, openProjects),
  })

  const perDay = useMemo(() => {
    if (!deck) return []
    return win.iso.map((iso, i) => {
      const entries = deck.blocks
        .map((b) => ({ block: b, day: seriesMap(b)[iso] as SeriesDay | undefined }))
        .filter((e) => e.day && (e.day.human_min + e.day.agent_min + e.day.events) > 0)
      return {
        iso, ms: win.days[i]!,
        entries,
        minutes: entries.reduce((a, e) => a + (e.day!.human_min + e.day!.agent_min), 0),
        landed: entries.reduce((a, e) => a + e.day!.done, 0),
      }
    })
  }, [deck, win])

  if (err) return <p className="text-12 text-error">{t('The sprints could not be read.')}</p>
  if (!deck) return <LoadingSkeleton variant="row" count={4} />

  const peakDay = Math.max(1, ...perDay.map((d) => d.minutes))
  const shown = range === 7 ? perDay : perDay.slice(-14)

  return (
    <div className="flex flex-col gap-14">

      {deck.blocks.length === 0 ? (
        <EmptyState title={t('No sprints running')} subtitle={t("Start one on a project's Sprints tab.")} />
      ) : (
        <>
          {/* The timeline: a river per block */}
          <section className="rounded-card border border-border-subtle bg-surface p-14 flex flex-col gap-8" aria-label={t('Sprint timeline')}>
            <div className="flex items-baseline gap-10">
              <h2 className="text-13 font-semibold text-primary">{t('Sprint timeline')}</h2>
              <span className="text-10 font-mono text-tertiary">
                {t('tasks by status, per day · faded days had no activity')}
              </span>
              <span className="ml-auto flex items-center gap-6 flex-wrap">
                {ORDER.map((s) => (
                  <span key={s} className="inline-flex items-center gap-3 text-10 font-mono text-tertiary">
                    <span className="h-6 w-6 rounded-bar" style={{ backgroundColor: COLOR[s] }} aria-hidden />{statusText(s)}
                  </span>
                ))}
              </span>
            </div>

            {/* day scale */}
            <div className="flex gap-2" style={{ marginLeft: 190, marginRight: 150 }}>
              {win.days.map((ms, i) => (
                <span key={ms} className={`flex-1 text-center text-10 font-mono ${win.iso[i] === deck.today ? 'text-brand font-semibold' : isWeekendMs(ms) ? 'text-tertiary/50' : 'text-tertiary'}`}>
                  {range === 7 ? weekdayShort(ms) : new Date(ms).getDate()}
                </span>
              ))}
            </div>

            {deck.blocks.map((b) => {
              const map = seriesMap(b) as Record<string, SeriesDay>
              const days: SeriesDay[] = win.iso.map((iso) => map[iso] ?? { date: iso, done: 0, human_min: 0, agent_min: 0, events: 0, bands: {} })
              const scale = Math.max(1, ...days.map((d) => Object.values(d.bands ?? {}).reduce((a, n) => a + n, 0)))
              const span = betSpan(b)
              const tone = VERDICT_TONE[verdictOf(b)]
              const open = openRow.has(b.id)
              const r = readings(b, days)
              const H = 46
              return (
                <div key={b.id} className="flex flex-col gap-2 border-t border-border-subtle pt-6">
                  <div className="flex items-stretch gap-8">
                    <div className="w-[190px] shrink-0 flex flex-col gap-1">
                      <button type="button" onClick={() => setOpenRow((s) => { const n = new Set(s); if (n.has(b.id)) n.delete(b.id); else n.add(b.id); return n })}
                        aria-expanded={open} className="flex items-baseline gap-4 text-left">
                        <span className="text-10 font-mono text-tertiary">{open ? '▾' : '▸'}</span>
                        <span className="text-13 text-primary truncate">{b.name}</span>
                      </button>
                      <span className="text-10 font-mono text-tertiary">
                        {b.project} · {b.tasks_done}/{b.tasks_total}
                        <span style={{ color: (b.days_left ?? 0) < 0 ? 'var(--status-red)' : undefined }}>
                          {' · '}{b.days_left == null ? t('no length set') : b.days_left < 0 ? t('{n}d over', { n: -b.days_left }) : t('{n}d left', { n: b.days_left })}
                        </span>
                      </span>
                      <button type="button" onClick={() => void actions.toggleTimer(b)}
                        className={`self-start h-16 px-6 rounded-pill text-10 font-mono inline-flex items-center gap-2 ${b.timer ? 'bg-brand text-on-brand' : 'border border-border-default text-tertiary hover:text-brand hover:border-brand'}`}>
                        {b.timer ? <><Square size={8} aria-hidden /><Live on={!b.timer.paused_at}>{(now) => clock(timerSec(b.timer!, now))}</Live></> : <><Play size={8} aria-hidden />{t('start')}</>}
                      </button>
                    </div>

                    {/* the river */}
                    <div className="relative flex-1 flex items-end gap-2" style={{ height: H }}>
                      {span && (
                        <div className="absolute pointer-events-none rounded-pill" style={{
                          top: -3, height: 2,
                          left: `${Math.max(0, ((span.start - win.from) / (range * 86400e3)) * 100)}%`,
                          width: `${Math.max(1, ((Math.min(span.end, win.end + 86400e3) - Math.max(span.start, win.from)) / (range * 86400e3)) * 100)}%`,
                          backgroundColor: tone, opacity: 0.7,
                        }} title={t('Length: {n} days', { n: b.bet_days ?? '—' })} />
                      )}
                      {days.map((d) => {
                        const bands = d.bands ?? {}
                        const total = Object.values(bands).reduce((a, n) => a + n, 0)
                        const idle = d.human_min + d.agent_min + d.events === 0
                        const on = picked?.block === b.id && picked.iso === d.date
                        return (
                          <button
                            key={d.date}
                            type="button"
                            onClick={() => setPicked(on ? null : { block: b.id, iso: d.date })}
                            aria-pressed={on}
                            title={`${dayLabel(d.date)} · ${t('{n} tasks open', { n: total })}${d.done ? ` · ${t('{n} done', { n: d.done })}` : ''} · ${t('{time} yours', { time: hm(d.human_min) })}${idle ? ` · ${t('no activity')}` : ''}`}
                            className={`relative flex-1 min-w-0 flex flex-col justify-end rounded-bar ${on ? 'outline outline-1 outline-brand' : ''}`}
                            style={{ height: H, opacity: idle ? 0.32 : 1, filter: idle ? 'saturate(0.25)' : undefined }}
                          >
                            {ORDER.map((st) => {
                              const n = bands[st] ?? 0
                              if (n === 0) return null
                              return (
                                <span key={st} className="w-full" style={{
                                  height: (n / scale) * (H - 4),
                                  backgroundColor: COLOR[st],
                                  opacity: st === 'done' ? 0.55 : 0.9,
                                }} />
                              )
                            })}
                            {total === 0 && <span className="w-full rounded-bar" style={{ height: 2, backgroundColor: 'var(--border-default)' }} />}
                            {d.done > 0 && (
                              <span className="absolute top-0 left-1/2 -translate-x-1/2 text-10 font-mono text-status-green">+{d.done}</span>
                            )}
                          </button>
                        )
                      })}
                    </div>

                    <div className="w-[150px] shrink-0 flex flex-col gap-1 text-10 font-mono">
                      <span className="text-secondary" title={t("Your timer hours plus the agents' chat minutes")}>
                        {hm(r.minutes)} <span className="text-tertiary">{t('effort')}</span>
                      </span>
                      <span className="text-tertiary">{t('{yours} yours · {agents} agents', { yours: hm(r.human), agents: hm(r.agent) })}</span>
                      <span className="text-tertiary" title={t('Days with no time logged and no task changes, of {n} days in this range', { n: r.span })}>
                        {t('{done} done · {idle} of {span} idle', { done: r.landed, idle: r.silent, span: r.span })}
                      </span>
                      {(() => {
                        const lt = leadTime(b, deck.today)
                        return (
                          <>
                            <span className="text-tertiary" title={`${t('Median days from joining this block to done, over {n} done tasks', { n: lt.samples })}${lt.slowest != null ? `; ${t('the slowest took {n}d', { n: lt.slowest })}` : ''}`}>
                              {t('lead {time}', { time: lt.median == null ? '—' : t('{n}d', { n: lt.median }) })}{lt.samples > 0 ? ` (${lt.samples})` : ''}
                            </span>
                            {lt.oldest && (
                              <span
                                title={t('Oldest open task: "{title}", joined {n} days ago', { title: lt.oldest.task.title, n: lt.oldest.age })}
                                style={{ color: lt.oldest.age >= 7 ? 'var(--status-amber)' : undefined }}
                              >
                                {t('oldest open {n}d', { n: lt.oldest.age })}
                              </span>
                            )}
                          </>
                        )
                      })()}
                    </div>
                  </div>

                  {picked?.block === b.id && (() => {
                    const d = days.find((x) => x.date === picked.iso)!
                    const bands = d.bands ?? {}
                    return (
                      <div className="rounded-input border border-brand/50 bg-elevated px-10 py-6 flex items-baseline gap-10 flex-wrap" style={{ marginLeft: 198 }}>
                        <span className="text-12 font-semibold text-primary">{dayLabel(d.date)}</span>
                        <span className="text-10 font-mono text-tertiary">{t('{yours} yours · {agents} agents · {n} task changes', { yours: hm(d.human_min), agents: hm(d.agent_min), n: d.events })}</span>
                        {ORDER.filter((s) => (bands[s] ?? 0) > 0).map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setBand(band?.block === b.id && band.status === s ? null : { block: b.id, status: s })}
                            aria-pressed={band?.block === b.id && band.status === s}
                            title={t('Tasks in {status} now, and for how long', { status: statusText(s) })}
                            className="text-10 font-mono inline-flex items-center gap-3 hover:underline decoration-dotted"
                            style={{ color: COLOR[s] }}
                          >
                            <span className="h-6 w-6 rounded-bar" style={{ backgroundColor: COLOR[s] }} aria-hidden />{bands[s]} {statusText(s)}
                          </button>
                        ))}
                        {d.done > 0 && <span className="text-10 font-mono text-status-green">{t('{n} done that day', { n: d.done })}</span>}
                        {d.human_min + d.agent_min + d.events === 0 && <span className="text-10 font-mono text-tertiary italic">{t('no activity')}</span>}
                        <button type="button" onClick={() => setPicked(null)} className="ml-auto text-10 font-mono text-tertiary hover:text-primary" aria-label={t('Close the day')}>×</button>
                      </div>
                    )
                  })()}

                  {band?.block === b.id && (() => {
                    const inBand = b.tasks
                      .filter((task) => {
                        const st = String(task.status || '').toLowerCase()
                        const norm = ['done', 'done-archived'].includes(st) ? 'done' : (st || 'unclassified')
                        return norm === band.status
                      })
                      .map((task) => ({ task, stuck: stuckDays(task, deck.today) }))
                      .sort((x, y) => (y.stuck ?? 0) - (x.stuck ?? 0))
                    return (
                      <div className="rounded-input border border-border-subtle bg-elevated/60 px-10 py-8 flex flex-col gap-3" style={{ marginLeft: 198 }}>
                        <div className="flex items-baseline gap-8">
                          <span className="text-11 font-mono" style={{ color: COLOR[band.status] }}>{t('in {status} now · {n}', { status: statusText(band.status), n: inBand.length })}</span>
                          <span className="text-10 font-mono text-tertiary">{t('longest first')}</span>
                          <button type="button" onClick={() => setBand(null)} className="ml-auto text-10 font-mono text-tertiary hover:text-primary" aria-label={t('Close')}>×</button>
                        </div>
                        {inBand.length === 0 && <span className="text-11 text-tertiary italic">{t('No tasks in this status today.')}</span>}
                        {inBand.slice(0, 8).map(({ task, stuck }) => (
                          <div key={task.id} className="flex items-center gap-6 group">
                            <button type="button" onClick={() => void actions.setStatus(task, 'done')} aria-label={t('Mark {title} done', { title: task.title })}
                              className="h-12 w-12 shrink-0 rounded-pill border border-border-strong hover:border-status-green" />
                            <span className="text-12 text-secondary truncate">{task.title}</span>
                            <span className="text-10 font-mono shrink-0"
                              style={{ color: (stuck ?? 0) >= 7 ? 'var(--status-red)' : (stuck ?? 0) >= 3 ? 'var(--status-amber)' : 'var(--text-tertiary)' }}
                              title={t('In {status} for {n} days', { status: statusText(band.status), n: stuck ?? '—' })}>
                              {stuck == null ? '—' : t('{n}d here', { n: stuck })}
                            </span>
                            <button type="button" onClick={() => void actions.toggleToday(task, deck.today)} aria-label={t('Plan for today')}
                              className={`text-11 shrink-0 ${String(task.today_on || '') === deck.today ? 'text-brand' : 'text-tertiary opacity-0 group-hover:opacity-100 hover:text-brand'}`}>☀</button>
                          </div>
                        ))}
                      </div>
                    )
                  })()}

                  {open && (
                    <div className="flex flex-col gap-2 pb-4" style={{ marginLeft: 198 }}>
                      {(spans[b.id] ?? []).length === 0 && <span className="text-10 font-mono text-tertiary italic">{
                        spanState[b.project] === 'failed' ? t('Could not read the tasks.')
                          : spanState[b.project] === 'read' ? t('No tasks yet.') : t('Loading tasks…')
                      }</span>}
                      {(spans[b.id] ?? []).slice(0, 14).map((task) => {
                        // Local midnights, as the window's days are.
                        const a = Date.parse(`${task.joined}T00:00:00`), z = task.done ? Date.parse(`${task.done}T00:00:00`) : win.end
                        const total = range * 86400e3
                        return (
                          <div key={task.id} className="flex items-center gap-8">
                            <span className="w-[190px] shrink-0 text-11 text-tertiary truncate pl-12" title={task.title}>{task.title}</span>
                            <span className="relative flex-1 h-8">
                              <span className="absolute rounded-pill" style={{
                                top: 2, bottom: 2,
                                left: `${Math.max(0, ((a - win.from) / total) * 100)}%`,
                                width: `${Math.max(1, ((Math.min(z, win.end + 86400e3) - Math.max(a, win.from)) / total) * 100)}%`,
                                backgroundColor: task.done ? 'color-mix(in srgb, var(--status-green) 55%, transparent)' : 'color-mix(in srgb, var(--brand) 45%, transparent)',
                              }} title={`${task.title} · ${t('joined {date}', { date: task.joined })}${task.done ? ` · ${t('done {date}', { date: task.done })}` : ` · ${t('still open')}`}`} />
                            </span>
                            <span className="w-[150px] shrink-0" />
                          </div>
                        )
                      })}
                      <div className="flex items-center gap-6 pl-12">
                        {[7, 14, 21].map((d) => (
                          <button key={d} type="button" onClick={() => void actions.rebet(b, d)}
                            className="h-16 px-6 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-brand">{t('{n}d', { n: d })}</button>
                        ))}
                        <Link to={`/project/${b.project}#sprints`} className="text-10 font-mono text-tertiary hover:text-brand">{t('open the sprint')} →</Link>
                        <button type="button" onClick={() => setFinishing(b)}
                          className="ml-auto h-16 px-8 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-status-green hover:border-status-green">{t('finish')}</button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </section>

          {/* What the hours bought */}
          <section className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-8" aria-label={t('Effectiveness')}>
            <button
              type="button"
              onClick={() => setOpenEff((v) => !v)}
              aria-expanded={openEff}
              className="flex items-baseline gap-8 text-left flex-wrap"
            >
              <span className="text-10 font-mono text-tertiary">{openEff ? '▾' : '▸'}</span>
              <h2 className="text-13 font-semibold text-primary">{t('Effectiveness')}</h2>
              <span className="text-10 font-mono text-tertiary">
                {t("What each block's hours produced, and the cost of a finished task")}
              </span>
            </button>
            <div className="overflow-x-auto" hidden={!openEff}>
              <table className="w-full text-12 min-w-[780px]">
                <thead>
                  <tr className="border-b border-border-default text-10 uppercase tracking-wide font-mono text-tertiary">
                    <th className="text-left font-normal py-4 pr-8">{t('block')}</th>
                    <th className="text-right font-normal px-6">{t('yours')}</th>
                    <th className="text-right font-normal px-6">{t('agents')}</th>
                    <th className="text-right font-normal px-6">{t('leverage')}</th>
                    <th className="text-right font-normal px-6">{t('done')}</th>
                    <th className="text-right font-normal px-6">{t('your time per task')}</th>
                    <th className="text-right font-normal px-6">{t('all time per task')}</th>
                    <th className="text-right font-normal px-6">{t('tasks per hour')}</th>
                    <th className="text-right font-normal px-6">{t('active days')}</th>
                  </tr>
                </thead>
                <tbody>
                  {deck.blocks.map((b) => {
                    const map = seriesMap(b) as Record<string, SeriesDay>
                    const days = win.iso.map((iso) => map[iso] ?? { date: iso, done: 0, human_min: 0, agent_min: 0, events: 0, bands: {} })
                    const e = effectivity(b, days)
                    return (
                      <tr key={b.id} className="border-b border-border-subtle hover:bg-hover">
                        <td className="py-6 pr-8">
                          <span className="inline-flex items-center gap-6">
                            <span className="h-8 w-8 rounded-pill" style={{ backgroundColor: VERDICT_TONE[verdictOf(b)] }} aria-hidden />
                            <span className="text-13 text-primary">{b.name}</span>
                          </span>
                        </td>
                        <td className="text-right px-6 font-mono tabular text-secondary">{hm(e.human)}</td>
                        <td className="text-right px-6 font-mono tabular text-tertiary">{hm(e.agent)}</td>
                        <td className="text-right px-6 font-mono tabular"
                          title={e.leverage == null ? t('No timer hours yet, so this ratio cannot be computed') : `${t('Agents spent {n} minutes for every minute of yours', { n: Math.round(e.leverage * 10) / 10 })}${e.trend != null ? `; ${e.trend > 0 ? t('rising across this block’s life') : e.trend < 0 ? t('falling across this block’s life') : t('flat across this block’s life')}` : ''}`}>
                          {e.leverage == null ? <span className="text-tertiary">—</span> : (
                            <span style={{ color: e.leverage >= 1 ? 'var(--status-green)' : 'var(--text-secondary)' }}>
                              {Math.round(e.leverage * 10) / 10}×
                              {e.trend != null && Math.abs(e.trend) >= 0.2 && (
                                <span className="text-tertiary"> {e.trend > 0 ? '↑' : '↓'}</span>
                              )}
                            </span>
                          )}
                        </td>
                        <td className="text-right px-6 font-mono tabular text-secondary">{e.landed}</td>
                        <td className="text-right px-6 font-mono tabular"
                          title={t('Your timer minutes divided by tasks done')}>
                          {e.yoursPerLanding == null ? <span className="text-tertiary">—</span> : hm(e.yoursPerLanding)}
                        </td>
                        <td className="text-right px-6 font-mono tabular text-tertiary"
                          title={t("Your minutes plus the agents', divided by tasks done")}>
                          {e.totalPerLanding == null ? '—' : hm(e.totalPerLanding)}
                        </td>
                        <td className="text-right px-6 font-mono tabular text-tertiary"
                          title={t('Tasks done per hour of your time')}>
                          {e.landedPerHour == null ? '—' : Math.round(e.landedPerHour * 10) / 10}
                        </td>
                        <td className="text-right px-6 font-mono tabular"
                          title={t('Active on {n} of {total} days in this range', { n: e.worked, total: e.span })}>
                          <span style={{ color: e.rhythm < 0.34 ? 'var(--status-amber)' : 'var(--text-tertiary)' }}>
                            {e.worked}/{e.span}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  {(() => {
                    const all = deck.blocks.map((b) => {
                      const map = seriesMap(b) as Record<string, SeriesDay>
                      const days = win.iso.map((iso) => map[iso] ?? { date: iso, done: 0, human_min: 0, agent_min: 0, events: 0, bands: {} })
                      return effectivity(b, days)
                    })
                    const human = all.reduce((a, e) => a + e.human, 0)
                    const agent = all.reduce((a, e) => a + e.agent, 0)
                    const landed = all.reduce((a, e) => a + e.landed, 0)
                    return (
                      <tr className="border-t border-border-default">
                        <td className="py-6 pr-8 text-11 font-mono text-tertiary">{t('all running')}</td>
                        <td className="text-right px-6 font-mono tabular text-secondary">{hm(human)}</td>
                        <td className="text-right px-6 font-mono tabular text-tertiary">{hm(agent)}</td>
                        <td className="text-right px-6 font-mono tabular text-secondary"
                          title={t('A chat that touched two blocks counts for both, so this total is high')}>
                          {human > 0 ? `${Math.round((agent / human) * 10) / 10}×` : '—'}
                        </td>
                        <td className="text-right px-6 font-mono tabular text-secondary">{landed}</td>
                        <td className="text-right px-6 font-mono tabular text-secondary">{landed > 0 ? hm(human / landed) : '—'}</td>
                        <td className="text-right px-6 font-mono tabular text-tertiary">{landed > 0 ? hm((human + agent) / landed) : '—'}</td>
                        <td className="text-right px-6 font-mono tabular text-tertiary">{human > 0 ? Math.round((landed / (human / 60)) * 10) / 10 : '—'}</td>
                        <td className="text-right px-6" />
                      </tr>
                    )
                  })()}
                </tfoot>
              </table>
            </div>
          </section>

          {/* The numbers, folded away until asked for */}
          <section className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-8" aria-label={t('Numbers')}>
            <button
              type="button"
              onClick={() => setOpenNumbers((v) => !v)}
              aria-expanded={openNumbers}
              className="flex items-baseline gap-8 text-left"
            >
              <span className="text-10 font-mono text-tertiary">{openNumbers ? '▾' : '▸'}</span>
              <span className="text-13 font-semibold text-primary">{t('Numbers')}</span>
              <span className="text-10 font-mono text-tertiary">
                {t('Median day per block')}
              </span>
            </button>

            {openNumbers && (() => {
              // Three questions about how the work actually goes, asked of
              // everything running at once — the per-block tables below say
              // who is who; these say what the habit is.
              const allDays = win.iso.map((iso) => {
                let human = 0, done = 0, arrivals = 0
                for (const b of deck.blocks) {
                  const d = (seriesMap(b) as Record<string, SeriesDay>)[iso]
                  if (d) { human += d.human_min; done += d.done }
                  for (const t of b.tasks) if (String(t.joined || '').slice(0, 10) === iso) arrivals += 1
                }
                return { iso, human, done, arrivals }
              })
              const lead: number[] = []
              for (const b of deck.blocks) {
                for (const t of b.tasks) {
                  if (!t.joined || !t.done_on) continue
                  const a = Date.parse(`${String(t.joined).slice(0, 10)}T00:00:00`)
                  const z = Date.parse(`${String(t.done_on).slice(0, 10)}T00:00:00`)
                  if (!Number.isNaN(a) && !Number.isNaN(z) && z >= a) lead.push(Math.round((z - a) / 86400e3))
                }
              }
              const byWeekday = [0, 0, 0, 0, 0, 0, 0]
              for (const d of allDays) byWeekday[(new Date(`${d.iso}T00:00:00`).getDay() + 6) % 7]! += d.human
              const DAY_NAMES = [t('on Monday'), t('on Tuesday'), t('on Wednesday'), t('on Thursday'), t('on Friday'), t('on Saturday'), t('on Sunday')]
              const totalMin = byWeekday.reduce((a, n) => a + n, 0)
              const peakDayIdx = byWeekday.indexOf(Math.max(...byWeekday))
              const weekendMin = byWeekday[5]! + byWeekday[6]!
              const sameDay = lead.filter((d) => d === 0).length
              const tail = lead.length ? [...lead].sort((a, z) => a - z)[Math.floor(lead.length * 0.9)]! : null
              const arrived = allDays.reduce((a, d) => a + d.arrivals, 0)
              const landed = allDays.reduce((a, d) => a + d.done, 0)
              return (
              <>
              <div className="grid gap-x-16 gap-y-12 pb-4 border-b border-border-subtle" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
                <WeekdayBars
                  title={t('when you work')}
                  minutes={byWeekday}
                  finding={totalMin === 0 ? t('No timer hours in this range.')
                    : weekendMin / totalMin >= 0.4
                      ? t('{n}% of your hours fall on the weekend.', { n: Math.round((weekendMin / totalMin) * 100) })
                      : t('You log the most hours {day}.', { day: DAY_NAMES[peakDayIdx] ?? '' })}
                />
                <Histogram
                  title={t('time to done')}
                  unit={t('days to done')}
                  values={lead}
                  finding={lead.length === 0 ? t('No tasks done yet.')
                    : `${t('{n}% of tasks are done the day they arrive', { n: Math.round((sameDay / lead.length) * 100) })}${tail && tail > 0 ? `; ${t('the slowest tenth take {n} days', { n: tail })}` : ''}.`}
                />
                <NetBars
                  title={t('arrived and done')}
                  days={allDays.map((d) => ({ date: d.iso, net: d.arrivals - d.done }))}
                  finding={arrived === landed ? t('{arrived} arrived, {done} done. The queue is level.', { arrived, done: landed })
                    : arrived > landed
                      ? t('{arrived} arrived, {done} done. The queue grew by {n}.', { arrived, done: landed, n: arrived - landed })
                      : t('{arrived} arrived, {done} done. The queue shrank by {n}.', { arrived, done: landed, n: landed - arrived })}
                />
              </div>
              <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
                {deck.blocks.map((b) => {
                  const map = seriesMap(b) as Record<string, SeriesDay>
                  const days = win.iso.map((iso) => map[iso] ?? { date: iso, done: 0, human_min: 0, agent_min: 0, events: 0, bands: {} })
                  const n = numbers(b, days)
                  const rate = (m: number | null, max: number, total: number) =>
                    m == null ? '—' : `${t('{n} a day', { n: m })} · ${t('{total} in {span}d', { total, span: n.span })}${max > 0 ? ` · ${t('busiest {n}', { n: max })}` : ''}`
                  const facts: Array<[string, string, string]> = [
                    [t('new tasks'), rate(n.newMedian, n.newMax, n.newTotal), t('Tasks added to this block per day: the median, idle days included')],
                    [t('done'), rate(n.doneMedian, n.doneMax, n.doneTotal), t('Tasks done per day')],
                    [t('net a day'), n.netMedian == null ? '—' : `${n.netMedian > 0 ? '+' : ''}${n.netMedian}`, t('Tasks added minus tasks done on a median day. Above zero, the open list grows.')],
                    [t('open at once'), n.wipMedian == null ? '—' : t('{n} typical · {max} at most', { n: n.wipMedian, max: n.wipMax }), t('Tasks in doing or review on a median day')],
                    [t('effort a day'), n.effortMedian == null ? '—' : t('{time} · {worked} when worked', { time: hm(n.effortMedian), worked: hm(n.effortWorkedMedian ?? 0) }), t("Your time plus the agents' time, on a median day and on a median active day")],
                    [t('lead time'), n.leadMedian == null ? '—' : t('{median}d median · {slow}d slow tail ({n})', { median: n.leadMedian, slow: n.leadP90 ?? '—', n: n.leadSamples }), t('Days from joining the block to done: the median and the 90th percentile')],
                    [t('streaks'), t('{active}d active · {idle}d idle', { active: n.streak, idle: n.silence }), t('Longest run of active days, and of idle days')],
                    [t('weekends'), n.weekendShare == null ? '—' : t('{n}% of your hours', { n: Math.round(n.weekendShare * 100) }), t('Share of your timer hours logged on a Saturday or Sunday')],
                  ]
                  return (
                    <div key={b.id} className="rounded-input border border-border-subtle p-10 flex flex-col gap-4">
                      <div className="flex items-baseline gap-6">
                        <span className="h-8 w-8 rounded-pill" style={{ backgroundColor: VERDICT_TONE[verdictOf(b)] }} aria-hidden />
                        <span className="text-13 text-primary">{b.name}</span>
                        <span className="text-10 font-mono text-tertiary ml-auto">{t('{n} days lived in this range', { n: n.span })}</span>
                      </div>
                      <dl className="grid gap-x-10 gap-y-2" style={{ gridTemplateColumns: 'auto 1fr' }}>
                        {facts.map(([k, v, why]) => (
                          <div key={k} className="contents">
                            <dt className="text-10 uppercase tracking-wide font-mono text-tertiary whitespace-nowrap cursor-help" title={why}>{k}</dt>
                            <dd className="text-11 font-mono text-secondary text-right">{v}</dd>
                          </div>
                        ))}
                      </dl>

                    </div>
                  )
                })}
              </div>
              </>
              )
            })()}
          </section>

          {/* The diary, kept */}
          <div className="grid gap-8" style={{ gridTemplateColumns: `repeat(${Math.min(shown.length, 7)}, minmax(0, 1fr))` }}>
            {shown.map((d) => {
              const today = d.iso === deck.today
              const idle = d.entries.length === 0
              return (
                <section key={d.iso} aria-label={dayLabel(d.iso)}
                  className={`rounded-card border bg-surface flex flex-col min-h-[130px] ${today ? 'border-brand' : 'border-border-subtle'}`}
                  style={idle ? { opacity: 0.55 } : undefined}>
                  <header className={`px-8 py-6 border-b flex items-baseline gap-4 ${today ? 'border-brand/40' : 'border-border-subtle'}`}>
                    <span className={`text-11 font-semibold ${today ? 'text-brand' : isWeekendMs(d.ms) ? 'text-tertiary' : 'text-primary'}`}>{weekdayShort(d.ms)}</span>
                    <span className="text-10 font-mono text-tertiary">{d.iso.slice(5)}</span>
                    {d.minutes > 0 && <span className="ml-auto text-10 font-mono text-secondary">{hm(d.minutes)}</span>}
                  </header>
                  <div className="h-3" style={{ backgroundColor: d.minutes ? `color-mix(in oklab, var(--brand) ${Math.round(20 + (d.minutes / peakDay) * 70)}%, transparent)` : 'transparent' }} aria-hidden />
                  <div className="flex flex-col gap-4 p-8 flex-1">
                    {idle && <span className="text-10 font-mono text-tertiary/60 italic">{t('no activity')}</span>}
                    {d.entries.map(({ block, day }) => (
                      <div key={block.id} className="flex flex-col gap-1">
                        <div className="flex items-baseline gap-4">
                          <span className="h-6 w-6 rounded-pill shrink-0" style={{ backgroundColor: VERDICT_TONE[verdictOf(block)] }} aria-hidden />
                          <span className="text-11 text-secondary truncate">{block.name}</span>
                        </div>
                        <span className="text-10 font-mono text-tertiary pl-10">
                          {day!.human_min > 0 && `${hm(day!.human_min)} `}
                          {day!.agent_min > 0 && `· ${t('agents {time}', { time: hm(day!.agent_min) })} `}
                          {day!.done > 0 && <span className="text-status-green">· {t('{n} done', { n: day!.done })}</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              )
            })}
          </div>

          {/* open work, so the page can still be acted on */}
          <div className="rounded-card border border-border-subtle bg-surface p-12 flex flex-col gap-6">
            <span className="text-11 uppercase tracking-wide font-mono text-tertiary">{t('open tasks · ☀ plans one for today')}</span>
            <div className="grid gap-x-16 gap-y-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
              {deck.blocks.flatMap((b) => b.tasks.filter((task) => !isDone(task.status)).slice(0, 5).map((task) => (
                <div key={task.id} className="flex items-center gap-6 group">
                  <button type="button" onClick={() => void actions.setStatus(task, 'done')} aria-label={t('Mark {title} done', { title: task.title })}
                    className="h-12 w-12 shrink-0 rounded-pill border border-border-strong hover:border-status-green" />
                  <span className="text-12 text-secondary truncate">{task.title}</span>
                  <span className="text-10 font-mono text-tertiary shrink-0">{b.name}</span>
                  <button type="button" onClick={() => void actions.toggleToday(task, deck.today)} aria-label={t('Plan for today')}
                    className={`text-11 shrink-0 ${String(task.today_on || '') === deck.today ? 'text-brand' : 'text-tertiary opacity-0 group-hover:opacity-100 hover:text-brand'}`}>☀</button>
                </div>
              )))}
            </div>
          </div>
        </>
      )}

      {finishing && (
        <FinishDialog block={finishing} onClose={() => setFinishing(null)}
          onFinish={(retro) => { void actions.finish(finishing, retro).then(() => { setFinishing(null); refresh() }) }} />
      )}
    </div>
  )
}
