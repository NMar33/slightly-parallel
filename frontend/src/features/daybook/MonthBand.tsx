import { dayHeading } from '../../utils/dateUtils'
import type { ReactNode } from 'react'

import { MonthGrid } from './MonthGrid'
import { monthKey, type DayNumbers } from './data'

import { t } from '../../i18n/scope/views'
/**
 * The band every day book opens with: the month as a grid, the month's
 * totals, and a strip of the days that have an entry. Scans, standups and
 * decisions draw the same band, so a month looks like the same month
 * wherever it is read; only the marks and the totals change.
 */
export function MonthBand({ month, days, marked, markWord, totals, active, onPick, onMonth, emptyWord, beside, showDays = true }: {
  month: string
  days: Record<string, DayNumbers>
  /** The days that have an entry of this page's kind. */
  marked: Set<string>
  /** What one entry is called: standup, scan, decision. */
  markWord: string
  /** The month in numbers, already worded by the page. */
  totals: ReactNode
  active?: string
  onPick: (day: string) => void
  onMonth: (month: string) => void
  /** Said when the month has no entry of this kind. */
  emptyWord: string
  /** What stands in the room the day strip would take. */
  beside?: ReactNode
  /** The strip of days that have an entry. Off where the grid is the way in. */
  showDays?: boolean
}) {
  const withEntry = Object.keys(days).filter((d) => marked.has(d)).sort().reverse()
  return (
    <div className="grid gap-16 md:grid-cols-[260px_minmax(0,1fr)] items-start">
      <MonthGrid
        month={month} days={days} marked={marked} markWord={markWord} active={active} onPick={onPick}
        onMonth={(d) => onMonth(monthKey(new Date(`${month}-01T12:00:00`), d))}
      />
      <div className="flex flex-col gap-8 pt-24 min-w-0">
        <div className="text-11 font-mono text-tertiary tabular flex gap-12 flex-wrap">{totals}</div>
        {showDays ? (
          <nav aria-label={t('Days with a {markWord}', { markWord })} className="flex gap-4 flex-wrap">
            {withEntry.length === 0 && <span className="text-11 font-mono text-tertiary">{emptyWord}</span>}
            {withEntry.map((k) => (
              <button key={k} type="button" onClick={() => onPick(k)}
                className={`h-20 px-8 rounded-pill border text-10 font-mono ${active === k ? 'border-brand text-brand' : 'border-border-subtle text-secondary hover:text-primary'}`}>
                {dayHeading(k)}
              </button>
            ))}
          </nav>
        ) : (
          withEntry.length === 0 && <span className="text-11 font-mono text-tertiary">{emptyWord}</span>
        )}
        {beside}
      </div>
    </div>
  )
}

/** One day of the book: the date, the day's numbers, and what was written. */
export function DaySection({ day, active, heading, children }: {
  day: string
  active?: boolean
  heading: ReactNode
  children: ReactNode
}) {
  return (
    <section id={`day-${day}`} aria-label={dayHeading(day)}
      className={`scroll-mt-16 flex flex-col gap-8 py-12 border-b border-border-subtle ${active ? 'bg-brand-glow -mx-8 px-8 rounded-card' : ''}`}>
      <div className="flex items-baseline gap-10 flex-wrap">
        <h2 className="text-16 font-semibold text-primary">{dayHeading(day)}</h2>
        {heading}
      </div>
      {children}
    </section>
  )
}

/** A day that had work and nothing of this kind written. */
export function NothingDay({ day, word, numbers }: { day: string; word: string; numbers?: ReactNode }) {
  return (
    <section id={`day-${day}`} aria-label={dayHeading(day)} className="scroll-mt-16 flex items-baseline gap-10 py-6 border-b border-border-subtle">
      <span className="text-12 font-mono text-tertiary w-[120px] shrink-0">{dayHeading(day)}</span>
      {/* One width on every row, so the numbers after it line up. */}
      <span className="text-11 font-mono text-tertiary w-[80px] shrink-0 whitespace-nowrap">{word}</span>
      {numbers}
    </section>
  )
}
