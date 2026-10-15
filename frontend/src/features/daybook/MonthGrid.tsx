import { dayHeading } from '../../utils/dateUtils'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { daysOfMonth, intensity, monthLabel, todayKey, weekday, type DayNumbers, ZERO } from './data'

import { t, tn } from '../../i18n/scope/views'
import { weekdayShort } from '../../lib/months'
/**
 * A month as a grid of days, one cell per day, seven columns Monday to
 * Sunday. The shade is the messages of the day against the busiest day of
 * the month, so the same month looks the same on every page that draws it.
 * `marked` are the days that have an entry of this page's kind: they get a
 * ring and a dot. Today is underlined. Every cell is a button that names
 * its numbers.
 */
const WEEKDAYS = Array.from({ length: 7 }, (_, i) => weekdayShort(i))

/** The five shades, mixed from the brand token so both themes hold. */
function shade(level: 0 | 1 | 2 | 3 | 4): string {
  const pct = [0, 22, 42, 65, 100][level]
  return level === 0 ? 'var(--bg-elevated)' : `color-mix(in srgb, var(--brand) ${pct}%, var(--bg-elevated))`
}

function cellLabel(day: string, n: DayNumbers, mark = ''): string {
  const parts = [dayHeading(day)]
  if (n.messages_n) parts.push(tn(n.messages_n, '{n} message', '{n} messages'))
  if (n.commits_n) parts.push(tn(n.commits_n, '{n} commit', '{n} commits'))
  if (n.tasks_done_n) parts.push(t('{tasks_done_n} tasks done', { tasks_done_n: n.tasks_done_n }))
  if (mark) parts.push(mark)
  if (!n.messages_n && !n.commits_n) parts.push(t('no work'))
  return parts.join(' · ')
}

export function MonthGrid({ month, days, marked, markWord = 'standup', active, onPick, onMonth, size = 'small' }: {
  month: string
  days: Record<string, DayNumbers>
  /** The days that have an entry of this page's kind. */
  marked?: Set<string>
  /** What that entry is called, for the cell's label. */
  markWord?: string
  active?: string
  onPick: (day: string) => void
  onMonth: (delta: 1 | -1) => void
  size?: 'small' | 'large'
}) {
  const keys = daysOfMonth(month)
  const max = Math.max(0, ...keys.map((k) => days[k]?.messages_n ?? 0))
  const lead = keys.length ? weekday(keys[0]!) : 0
  const today = todayKey()
  const big = size === 'large'
  const cell = big ? 'h-64' : 'h-20'
  return (
    <div className="flex flex-col gap-8" data-month={month}>
      <div className="flex items-center gap-8">
        <button type="button" onClick={() => onMonth(-1)} aria-label={t('Previous month')}
          className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover">
          <ChevronLeft size={14} aria-hidden />
        </button>
        <span className="text-12 font-medium text-primary min-w-[140px] text-center">{monthLabel(month)}</span>
        <button type="button" onClick={() => onMonth(1)} aria-label={t('Next month')}
          className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover">
          <ChevronRight size={14} aria-hidden />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-3" role="grid" aria-label={monthLabel(month)}>
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-10 font-mono text-tertiary text-center">{w}</div>
        ))}
        {Array.from({ length: lead }).map((_, i) => <div key={`lead-${i}`} aria-hidden />)}
        {keys.map((day) => {
          const n = days[day] ?? ZERO
          const has = marked ? marked.has(day) : !!n.standup_id
          const level = intensity(n.messages_n, max)
          const isActive = active === day
          const isToday = today === day
          return (
            <button key={day} type="button" role="gridcell" data-day={day} data-level={level}
              onClick={() => onPick(day)} aria-label={cellLabel(day, n, has ? markWord : '')} title={cellLabel(day, n, has ? markWord : '')}
              aria-current={isToday ? 'date' : undefined}
              style={{ background: shade(level) }}
              className={`relative ${cell} rounded-input border text-left transition-colors ${
                isActive ? 'border-brand outline outline-1 outline-brand' : has ? 'border-brand' : 'border-border-subtle'
              } ${level >= 3 ? 'text-on-brand' : 'text-secondary'} hover:border-brand focus:outline-none focus:border-brand`}>
              {big ? (
                <span className="absolute inset-0 p-4 flex flex-col text-10 font-mono leading-tight">
                  <span className={`${isToday ? 'underline' : ''}`}>{Number(day.slice(-2))}</span>
                  {n.messages_n > 0 && <span className="mt-auto tabular">{n.messages_n} {t('msg')}</span>}
                  {n.commits_n > 0 && <span className="tabular">{n.commits_n} {t('commits')}</span>}
                  {n.tasks_done_n > 0 && <span className="tabular">{n.tasks_done_n} {t('done')}</span>}
                </span>
              ) : (
                <span className={`absolute left-4 top-2 text-10 font-mono leading-none ${isToday ? 'underline' : ''}`}>
                  {Number(day.slice(-2))}
                </span>
              )}
              {has && (
                <span aria-hidden className={`absolute ${big ? 'right-4 top-4 h-6 w-6' : 'right-3 bottom-3 h-4 w-4'} rounded-pill bg-brand`} />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
