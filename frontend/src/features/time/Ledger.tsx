/**
 * The ledger of the Timer page: one table with a row a block under its
 * project — the mode, a start pill, today, the last seven days as tinted
 * cells, the totals — then the entries of the last seven days of every
 * project, the way the Timer tab lists them.
 */

import { TH } from '../../components/ui'
import { ProjectDot } from '../../components/ProjectDot'
import { Fragment } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Segmented } from '../../components/Segmented'
import { Live } from '../../lib/clock'
import { dateKey, formatClock, formatDuration, liveElapsed, startDate, weightedSec, type TimeEntry } from '../project/timeEntry'
import { blockOf } from './model'
import { LABEL, MODE_OPTIONS, StartPill, blockRows, hh, projectTab, tint, weekdayOf, type TimeCtx } from './parts'

import { t } from '../../i18n/scope/views'
const hhmm = (d: Date) => `${hh(d.getHours())}:${hh(d.getMinutes())}`

/** The table of blocks by day, then the entries. */
export function Ledger({ c }: { c: TimeCtx }) {
  const { m } = c
  const rows = blockRows(c)
  const days = m.days.slice(-7)
  const todayKey = days[days.length - 1]
  const max = Math.max(1, ...rows.flatMap((r) => days.map((d) => r.t.perDay[d] ?? 0)))
  // The period column repeats the 7-day one when the period is 7 days.
  const long = c.period !== '7'
  const dayTotal = (d: string) => Object.values(m.perDay[d] ?? {}).reduce((a, s) => a + s, 0)
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-12 font-mono border-separate" style={{ borderSpacing: '2px 2px' }}>
          <thead>
            <tr className={TH}>
              <th className="text-left py-4 font-normal">{t('block')}</th>
              <th className="text-left py-4 font-normal w-[1%]">{t('timer')}</th>
              <th className="text-right py-4 pr-12 font-normal">{t('today')}</th>
              {days.map((d) => (
                <th key={d} className={`text-right py-4 px-8 font-normal ${d === todayKey ? 'text-primary' : ''}`}>{weekdayOf(d)} {d.slice(8)}</th>
              ))}
              <th className="text-right py-4 pl-12 font-normal">{t('7 days')}</th>
              {long && <th className="text-right py-4 pl-12 font-normal">{c.period} {t('days')}</th>}
            </tr>
          </thead>
          <tbody>
            {m.projects.map((p) => (
              <Fragment key={p.code}>
                <tr className="bg-elevated/50">
                  <td colSpan={2} className="px-8 py-3">
                    <span className="inline-flex items-center gap-8">
                      <Link to={projectTab(p.code)} title={t('Open the project\'s Timer tab')}
                        className="inline-flex items-center gap-6 text-11 font-semibold text-secondary no-underline hover:underline">
                        <ProjectDot code={p.code} /> {p.code}
                      </Link>
                      <Segmented label={t('Timer mode of {code}', { code: p.code })} value={c.mode(p.code)} onChange={(v) => c.setMode(p.code, v)} options={[...MODE_OPTIONS]} />
                      {p.auto && <span className="text-10 text-brand">{t('● counting')}</span>}
                    </span>
                  </td>
                  <td className="px-8 py-3 pr-12 text-right text-primary tabular">{formatDuration(p.todaySec)}</td>
                  <td colSpan={7} />
                  <td className="px-8 py-3 text-right text-primary tabular">{formatDuration(p.weekSec)}</td>
                  {long && <td className="px-8 py-3 text-right text-primary tabular">{formatDuration(p.periodSec)}</td>}
                </tr>
                {rows.filter((r) => r.project === p.code).map((r) => {
                  const open = r.t.open
                  return (
                    <tr key={r.id || 'other'}>
                      <td className="py-4 pl-8 pr-12 font-sans text-secondary whitespace-nowrap">{r.name}</td>
                      <td className="py-4 pr-12 whitespace-nowrap"><StartPill row={r} c={c} /></td>
                      <td className={`py-4 pr-12 text-right tabular whitespace-nowrap ${open ? (open.paused_at ? 'text-tertiary' : 'text-brand') : r.t.todaySec > 0 ? 'text-primary' : 'text-tertiary'}`}>
                        {open ? <Live on={!open.paused_at}>{(now) => formatClock(liveElapsed(open, now))}</Live> : r.t.todaySec > 0 ? formatDuration(r.t.todaySec) : '·'}
                      </td>
                      {days.map((d) => {
                        const sec = r.t.perDay[d] ?? 0
                        return (
                          <td key={d} className={`py-4 px-8 text-right tabular rounded-bar ${sec > 0 ? 'text-primary' : 'text-tertiary'}`}
                            style={{ backgroundColor: tint(sec / max) }}>
                            {sec > 0 ? formatDuration(sec) : '·'}
                          </td>
                        )
                      })}
                      <td className="py-4 pl-12 text-right tabular text-secondary whitespace-nowrap">{formatDuration(r.t.weekSec)}</td>
                      {long && <td className="py-4 pl-12 text-right tabular text-tertiary whitespace-nowrap">{formatDuration(r.t.periodSec)}</td>}
                    </tr>
                  )
                })}
              </Fragment>
            ))}
            <tr className="text-secondary">
              <td colSpan={2} className="py-5 pl-8 text-10 uppercase tracking-wide font-mono text-tertiary">{t('all')}</td>
              <td className="py-5 pr-12 text-right tabular text-primary font-semibold">{formatDuration(m.todaySec)}</td>
              {days.map((d) => <td key={d} className="py-5 px-8 text-right tabular">{dayTotal(d) > 0 ? formatDuration(dayTotal(d)) : '·'}</td>)}
              <td className="py-5 pl-12 text-right tabular text-primary font-semibold">{formatDuration(m.weekSec)}</td>
              {long && <td className="py-5 pl-12 text-right tabular text-primary font-semibold">{formatDuration(m.periodSec)}</td>}
            </tr>
          </tbody>
        </table>
      </div>
      <Entries c={c} days={days} />
    </>
  )
}

/** The entries of the last seven days, every project, newest day first. A row opens its project's Timer tab. */
function Entries({ c, days }: { c: TimeCtx; days: string[] }) {
  const navigate = useNavigate()
  const byDay = new Map<string, TimeEntry[]>()
  for (const e of c.entries) {
    const d = startDate(e)
    if (!d) continue
    const k = dateKey(d)
    if (days.includes(k)) byDay.set(k, [...(byDay.get(k) ?? []), e])
  }
  const shown = [...days].reverse().filter((d) => byDay.has(d))
  const todayKey = days[days.length - 1]
  return (
    <section className="flex flex-col gap-6 min-w-0" aria-label={t('Entries')}>
      <div className="flex items-center gap-8 border-b border-border-default pb-4">
        <span className={LABEL}>{t('entries')}</span>
        <span className="text-10 font-mono text-tertiary">{t('the last 7 days · click a row to open it on its project\'s Timer tab')}</span>
      </div>
      {shown.length === 0 ? (
        <p className="text-12 text-tertiary italic">{t('No time entries in the last 7 days.')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-12 font-mono">
            <thead>
              <tr className={TH}>
                <th className="text-left py-4 pl-8 font-normal">{t('when')}</th>
                <th className="text-left py-4 font-normal">{t('project')}</th>
                <th className="text-left py-4 font-normal">{t('block')}</th>
                <th className="text-left py-4 font-normal">{t('note')}</th>
                <th className="text-right py-4 font-normal">{t('share')}</th>
                <th className="text-right py-4 pr-8 font-normal">{t('time')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((k) => {
                const es = [...(byDay.get(k) ?? [])].sort((a, b) => Date.parse(a.started_at ?? '') - Date.parse(b.started_at ?? ''))
                return (
                  <Fragment key={k}>
                    <tr className="bg-elevated/50">
                      <td colSpan={5} className="px-8 py-3 text-11 text-secondary font-semibold">{k === todayKey ? t('Today') : `${weekdayOf(k)} ${k}`}</td>
                      <td className="px-8 py-3 text-right text-primary tabular">{formatDuration(weightedSec(es, c.nowMs))}</td>
                    </tr>
                    {es.map((e) => {
                      const d0 = startDate(e)!
                      const d1 = e.ended_at ? new Date(Date.parse(e.ended_at)) : null
                      return (
                        <tr key={e.id} className="border-b border-border-subtle hover:bg-hover cursor-pointer" onClick={() => navigate(projectTab(e.project))}>
                          <td className="py-5 pl-8 text-tertiary tabular whitespace-nowrap">
                            {/* The row is clickable; the button is its keyboard and screen-reader way in. */}
                            <button type="button" onClick={(ev) => { ev.stopPropagation(); navigate(projectTab(e.project)) }}
                              aria-label={t('Open {project}: {time}', { project: e.project, time: `${hhmm(d0)}–${d1 ? hhmm(d1) : t('now')}` })}
                              className="tabular text-left hover:text-primary">
                              {hhmm(d0)}–{d1 ? hhmm(d1) : t('now')}
                            </button>
                          </td>
                          <td className="py-5 whitespace-nowrap"><span className="inline-flex items-center gap-6 text-secondary"><ProjectDot code={e.project} /> {e.project}</span></td>
                          <td className="py-5 text-secondary whitespace-nowrap">{blockOf(e) ? c.sprintName(blockOf(e)) : t('Everything else')}</td>
                          <td className="py-5 text-secondary font-sans truncate max-w-[320px]">
                            {e.source === 'auto' && <span className="mr-6 px-4 rounded-input bg-brand/16 text-brand font-mono text-10" title={t('Counted by the auto-timer while you worked on the project')}>{t('auto')}</span>}
                            {e.note || (e.task_id ? c.taskTitle(e.task_id) : e.source === 'auto' ? null : <span className="text-tertiary italic">—</span>)}
                          </td>
                          <td className={`py-5 text-right tabular ${(e.share_pct ?? 100) < 100 ? 'text-status-amber' : 'text-tertiary'}`}>{e.share_pct ?? 100}%</td>
                          <td className="py-5 pr-8 text-right text-primary tabular whitespace-nowrap">
                            {e.ended_at ? formatDuration(liveElapsed(e, c.nowMs)) : <span className="text-brand"><Live on={!e.paused_at}>{(now) => formatClock(liveElapsed(e, now))}</Live></span>}
                          </td>
                        </tr>
                      )
                    })}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
