/**
 * The head of the Timer page, from the Timer tab's own parts and counted
 * across every project: the numbers, today as the dial, the 26-week grid.
 */

import { StatTile, StatTiles } from '../../components/StatTile'
import { projectColor } from '../../utils/projectColor'
import { ContributionGrid, DayDial } from '../project/TimeTracker'
import { dateKey, formatDuration, startDate, weightedSec, type BlockDef, type TimeEntry } from '../project/timeEntry'
import { dayTotals } from './model'
import { isOn, type TimeCtx } from './parts'

import { t, tn } from '../../i18n/scope/views'
/** The numbers, and today as the dial beside the 26-week grid. */
export function Head({ c }: { c: TimeCtx }) {
  const { m, nowMs } = c
  const today = new Date(nowMs)
  const todayKey = dateKey(today)
  const todays = c.entries.filter((e) => { const d = startDate(e); return !!d && dateKey(d) === todayKey })
  const opens = c.entries.filter((e) => !e.ended_at)
  const totals = dayTotals(c.entries, nowMs)
  const on = m.projects.filter(isOn)
  const top = [...m.projects].sort((a, b) => b.weekSec - a.weekSec)[0]
  let streak = 0
  for (let i = 0; i < 365; i++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i)
    if ((totals[dateKey(d)] ?? 0) > 0) streak++
    else break
  }
  // The dial has four rings: the projects with time today, the fourth and later together.
  const todayCodes = [...new Set([...todays, ...opens].map((e) => e.project))]
  const rings: BlockDef[] = todayCodes.length <= 4
    ? todayCodes.map((code) => ({ key: code, name: code, tone: projectColor(code) }))
    : [...todayCodes.slice(0, 3).map((code) => ({ key: code, name: code, tone: projectColor(code) })), { key: 'other', name: t('other projects') }]
  const ringOf = (e: TimeEntry) => (rings.some((r) => r.key === e.project) ? e.project : 'other')

  return (
    <>
      <StatTiles>
        {[
          [t('today'), formatDuration(m.todaySec), on.length ? t('● {codes} running', { codes: on.map((p) => p.code).join(' + ') }) : t('idle')],
          [t('this week'), formatDuration(m.weekSec), t('{formatDuration} a day', { formatDuration: formatDuration(m.weekSec / 7) })],
          [t('top project'), top && top.weekSec > 0 ? top.code : '—', top && top.weekSec > 0 ? t('{formatDuration} this week', { formatDuration: formatDuration(top.weekSec) }) : t('nothing logged this week')],
          [t('streak'), tn(streak, '{n} day', '{n} days'), t('with logged time')],
        ].map(([k, v, sub]) => <StatTile key={k} label={k} value={v} sub={sub} />)}
      </StatTiles>

      <div className="grid gap-16 items-center" style={{ gridTemplateColumns: '220px 1fr' }}>
        <DayDial blocks={rings.length ? rings : [{ key: 'other', name: t('no time today') }]} todays={todays} opens={opens}
          nowMs={nowMs} weightedSec={weightedSec(todays, nowMs)} nameOf={(k) => rings.find((r) => r.key === k)?.name ?? k} ringOf={ringOf} />
        <ContributionGrid minutesOn={(k) => (totals[k] ?? 0) / 60} today={today} />
      </div>

    </>
  )
}
