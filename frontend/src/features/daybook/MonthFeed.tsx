import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

import { LoadingSkeleton } from '../../components/states'
import { daysOfMonth, monthKey, monthLabel, useMonth, ZERO, type DayNumbers } from './data'

import { t } from '../../i18n/scope/views'
/** Months from `m` (YYYY-MM) up to this one; 0 for this month or a later one. */
function monthsTo(m: string): number {
  const [ay, am] = monthKey().split('-').map(Number), [by, bm] = m.split('-').map(Number)
  return Math.max(0, (ay! - by!) * 12 + (am! - bm!))
}

/**
 * A day book's days, newest first, with no end but the project's start.
 *
 * It opens on this month and, as the reader nears the bottom, adds the
 * month before — one small request per month for the day's numbers; the
 * entries themselves are already in memory. It stops at the first month
 * older than the oldest entry in which nothing happened, and says so.
 *
 * The month grid above stays the way to jump: `anchor` is the month it
 * shows, and the feed loads down to it and scrolls there; `active` is a
 * picked day, scrolled to once it is drawn.
 */
export function MonthFeed({ project, earliest, anchor, active, keep, renderDay, onReach, zoom = 1 }: {
  project: string
  /** How large the entries read (ReadingSizeControl); 1 is as designed. */
  zoom?: number
  /** The oldest month with an entry of this page's kind, YYYY-MM ('' for none). */
  earliest: string
  /** The month the grid shows; the feed reaches it and scrolls to it. */
  anchor: string
  /** The picked day, YYMM-DD. */
  active: string
  /** Whether a day gets a line: an entry, or work that day. */
  keep: (day: string, n: DayNumbers | undefined) => boolean
  renderDay: (day: string, n: DayNumbers) => ReactNode
  /** Told the oldest month the feed draws, each time it grows (see `useReach`). */
  onReach?: (oldest: string) => void
}) {
  const newest = monthKey()
  const [count, setCount] = useState(() => monthsTo(anchor) + 1)
  // Months whose numbers came back empty: where the feed may stop. Both
  // sets hold `project|month`: a month already in the cache reports in
  // before the parent's effects run, so a set emptied on a project switch
  // would lose that report and the feed would never grow.
  const [quiet, setQuiet] = useState<Set<string>>(() => new Set())
  const [loaded, setLoaded] = useState<Set<string>>(() => new Set())
  // Another project: start again from the anchor. Only on a change.
  const shownFor = useRef(project)
  useEffect(() => {
    if (shownFor.current === project) return
    shownFor.current = project
    setCount(monthsTo(anchor) + 1)
    // The anchor moving alone is the effect below: it grows, never shrinks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project])

  const months = Array.from({ length: count }, (_, i) => monthKey(new Date(), -i))
  const last = months[months.length - 1]!
  const done = last < (earliest || newest) && quiet.has(`${project}|${last}`)
  // Told when the oldest month changes, not when the host draws a new callback.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onReach?.(last) }, [last])

  // The grid moved to an older month: reach it.
  useEffect(() => { setCount((c) => Math.max(c, monthsTo(anchor) + 1)) }, [anchor])

  // Near the bottom and the last month is in: add the one before it.
  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el || done) return
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting) && loaded.has(`${project}|${last}`)) setCount((c) => c + 1)
    }, { rootMargin: '800px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [done, last, loaded, project])

  // Scroll to the picked day, or to the month the grid moved to, once it
  // is drawn — not on the first draw, which starts at the top.
  const pending = useRef<string | null>(null)
  const seen = useRef({ anchor, active })
  if (seen.current.anchor !== anchor || seen.current.active !== active) {
    pending.current = active ? `day-${active}` : `month-${anchor}`
    seen.current = { anchor, active }
  }
  useEffect(() => {
    if (!pending.current) return
    const el = document.getElementById(pending.current)
    // A month still loading is too short to land on: wait for its days.
    if (el && el.dataset.ready !== '0') { el.scrollIntoView({ block: 'start' }); pending.current = null }
  })

  const onMonth = useCallback((key: string, empty: boolean) => {
    setLoaded((s) => (s.has(key) ? s : new Set(s).add(key)))
    if (empty) setQuiet((s) => (s.has(key) ? s : new Set(s).add(key)))
  }, [])

  return (
    <div className="flex flex-col" style={zoom !== 1 ? { zoom } : undefined}>
      {months.map((m) => (
        <FeedMonth key={m} project={project} month={m} keep={keep} renderDay={renderDay} onLoaded={onMonth} />
      ))}
      <div ref={sentinel} className="py-12 text-11 font-mono text-tertiary">
        {done ? t('Nothing older. The first entry is from {monthLabel}.', { monthLabel: monthLabel(earliest || last) }) : t('Loading older days…')}
      </div>
    </div>
  )
}

function FeedMonth({ project, month, keep, renderDay, onLoaded }: {
  project: string
  month: string
  keep: (day: string, n: DayNumbers | undefined) => boolean
  renderDay: (day: string, n: DayNumbers) => ReactNode
  /** Told `project|month` once the month's numbers are in. */
  onLoaded: (key: string, empty: boolean) => void
}) {
  const cal = useMonth(project, month)
  const days = cal.data?.month === month ? cal.data.days : undefined
  const shown = days ? daysOfMonth(month).reverse().filter((d) => keep(d, days[d])) : []
  const empty = !!days && Object.values(days).every((n) => !n.messages_n && !n.commits_n) && shown.length === 0
  // The previous project's month, shown while this one's loads, is not this
  // project's answer: it must not mark the month loaded or quiet.
  const placeholder = cal.isPlaceholderData
  useEffect(() => { if (days && !placeholder) onLoaded(`${project}|${month}`, empty) }, [days, empty, placeholder, project, month, onLoaded])
  return (
    <section id={`month-${month}`} aria-label={monthLabel(month)} data-ready={days ? '1' : '0'} className="scroll-mt-16">
      <h2 className="sticky top-0 z-10 bg-base py-6 text-11 uppercase tracking-wide font-mono text-tertiary border-b border-border-subtle">
        {monthLabel(month)}
      </h2>
      {!days && <LoadingSkeleton variant="text" count={2} label={t('Loading {monthLabel}', { monthLabel: monthLabel(month) })} className="py-8" />}
      {days && shown.length === 0 && <div className="py-8 text-11 font-mono text-tertiary">{t('Nothing this month.')}</div>}
      {shown.map((d) => <div key={d}>{renderDay(d, days?.[d] ?? ZERO)}</div>)}
    </section>
  )
}
