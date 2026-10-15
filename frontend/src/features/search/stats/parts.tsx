/**
 * The parts the numbers are set in.
 *
 * A statistics page is a table first: one accent, one rule weight, figures
 * aligned on the right in tabular numerals, and a bar that is a div wide
 * enough to read. Nothing here animates, and nothing here holds state.
 */

import { StatTile } from '../../../components/StatTile'
import type { ReactNode } from 'react'
import type { Bucket, DayBar, NearWord, Ranked } from './rollups'
import { num, pct } from './rollups'
import { t } from '../../../i18n/scope/system'

/* ----------------------------------------------------------- the frame */

/** A block of the sheet: a rule, a name, a note, and the figures. */
export function Block({
  title,
  note,
  children,
  className = '',
}: {
  title: string
  note?: ReactNode
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <section className={`flex flex-col gap-8 min-w-0 break-inside-avoid ${className}`}>
      <div className="flex items-baseline justify-between gap-8 border-t border-border-strong pt-6">
        <h2 className="text-11 uppercase tracking-wide text-primary">{title}</h2>
        {note != null && note !== '' && (
          <span className="text-10 font-mono tabular text-tertiary">{note}</span>
        )}
      </div>
      {children}
    </section>
  )
}

/** One figure of the headline row: the shared number tile. */
export function Stat({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}): JSX.Element {
  return <StatTile label={label} value={value} sub={note} />
}

/* ------------------------------------------------------------ the days */

/**
 * One bar per day of the index.
 *
 * With a word, every day keeps its full height in the border colour and
 * the word's share of that day is filled in the accent, so a tall pale bar
 * is a busy day the word was not said on.
 */
export function DayBand({
  bars,
  word,
}: {
  bars: DayBar[]
  word: string
}): JSX.Element {
  const top = bars.reduce<DayBar | null>((best, b) => (best && best.n >= b.n ? best : b), null)
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <div className="flex items-end gap-2 h-64 min-w-0">
        {bars.map((b) => (
          <div
            key={b.day}
            className="relative flex-1 h-64 min-w-0"
            title={
              word
                ? `${b.day} · ${t('{a} of {b} rows', { a: num(b.n), b: num(b.base) })} · ${pct(b.n, b.base)}`
                : `${b.day} · ${t('{n} rows', { n: num(b.n) })}`
            }
          >
            <div
              className="absolute bottom-0 left-0 right-0 bg-border-default"
              style={{ height: `${Math.max(b.baseScale * 100, 1)}%` }}
            />
            <div
              className="absolute bottom-0 left-0 right-0 bg-brand"
              style={{ height: `${b.n > 0 ? Math.max(b.scale * 100, 2) : 0}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex items-baseline justify-between gap-8 text-10 font-mono tabular text-tertiary">
        <span>{bars[0]?.day}</span>
        {top && top.n > 0 && (
          <span className="text-secondary">
            {t('busiest {day}', { day: top.day })} · {num(top.n)}
            {word ? ` ${t('of {n}', { n: num(top.base) })}` : ''}
          </span>
        )}
        <span>{bars[bars.length - 1]?.day}</span>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------- the tables */

const ROW = 'grid grid-cols-[18px_minmax(0,1fr)_64px_52px] items-center gap-8 min-w-0'

/** The header of a ranked table. */
function Head({
  what,
  unit = 'rows',
  right = 'share',
}: {
  what: string
  unit?: string
  right?: string
}): JSX.Element {
  return (
    <div className={`${ROW} border-b border-border-subtle pb-4 text-10 uppercase tracking-wide text-tertiary`}>
      <span className="text-right">#</span>
      <span>{t(what)}</span>
      <span className="text-right">{t(unit)}</span>
      <span className="text-right">{t(right)}</span>
    </div>
  )
}

/** The bar a table row carries under its name. */
function Bar({ scale }: { scale: number }): JSX.Element {
  return (
    <div className="h-3 w-full bg-border-subtle" aria-hidden>
      <div className="h-3 bg-brand" style={{ width: `${Math.max(scale * 100, 1)}%` }} />
    </div>
  )
}

/**
 * A ranked table: rank, name, count, share, and a bar per row.
 *
 * A table beats a cloud here. The rows are sorted, the figures line up,
 * and the eye can stop on any one of them.
 */
export function RankTable({
  rows,
  what,
  unit = 'rows',
  onPick,
  format,
}: {
  rows: Ranked[]
  what: string
  unit?: string
  /** When given, every name is a button that searches it. */
  onPick?: (label: string) => void
  /** How a name reads. */
  format?: (label: string) => string
}): JSX.Element {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <Head what={what} unit={unit} />
      <ul role="list" className="flex flex-col gap-4 min-w-0">
        {rows.map((r) => (
          <li key={r.label} className="flex flex-col gap-2 min-w-0">
            <div className={ROW}>
              <span className="text-right text-10 font-mono tabular text-tertiary">{r.rank}</span>
              {onPick ? (
                <button
                  type="button"
                  onClick={() => onPick(r.label)}
                  className="truncate text-left font-mono text-12 text-primary hover:text-brand focus:text-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  title={t('Search {what}', { what: r.label })}
                >
                  {format ? format(r.label) : r.label}
                </button>
              ) : (
                <span className="truncate font-mono text-12 text-primary" title={r.label}>
                  {format ? format(r.label) : r.label}
                </span>
              )}
              <span className="text-right font-mono tabular text-12 text-secondary">{num(r.n)}</span>
              <span className="text-right font-mono tabular text-11 text-tertiary">
                {pct(r.share, 1)}
              </span>
            </div>
            <div className={ROW}>
              <span />
              <Bar scale={r.scale} />
              <span />
              <span />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The words that sit around the searched word, strongest lift first. */
export function NearTable({
  rows,
  onPick,
}: {
  rows: NearWord[]
  onPick: (word: string) => void
}): JSX.Element {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <Head what="word nearby" right="lift" />
      <ul role="list" className="flex flex-col gap-4 min-w-0">
        {rows.map((r) => (
          <li key={r.word} className="flex flex-col gap-2 min-w-0">
            <div className={ROW}>
              <span className="text-right text-10 font-mono tabular text-tertiary">{r.rank}</span>
              <button
                type="button"
                onClick={() => onPick(r.word)}
                className="truncate text-left font-mono text-12 text-primary hover:text-brand focus:text-brand focus:outline-none focus:ring-1 focus:ring-brand"
                title={t('Search {what}', { what: r.word })}
              >
                {r.word}
              </button>
              <span className="text-right font-mono tabular text-12 text-secondary">{num(r.n)}</span>
              <span className="text-right font-mono tabular text-11 text-tertiary">
                {r.lift.toFixed(1)}×
              </span>
            </div>
            <div className={ROW}>
              <span />
              <Bar scale={r.scale} />
              <span />
              <span />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ---------------------------------------------------- turn length, roles */

/** The turn lengths, with the bucket the middle turn falls in marked. */
export function Distribution({ buckets }: { buckets: Bucket[] }): JSX.Element {
  return (
    <ul role="list" className="flex flex-col gap-4 min-w-0">
      {buckets.map((b) => (
        <li
          key={b.bucket}
          className="grid grid-cols-[72px_minmax(0,1fr)_52px_48px] items-center gap-8 min-w-0"
        >
          <span className="font-mono tabular text-11 text-secondary">{b.bucket}</span>
          <div className="h-8 w-full bg-border-subtle" aria-hidden>
            <div className="h-8 bg-brand" style={{ width: `${Math.max(b.scale * 100, 1)}%` }} />
          </div>
          <span className="text-right font-mono tabular text-12 text-secondary">{num(b.n)}</span>
          <span className="text-right font-mono tabular text-10 text-tertiary">
            {b.median ? t('median') : pct(b.share, 1)}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Who said more: one bar in two parts, and the two counts under it. */
export function RoleSplit({
  user,
  agent,
}: {
  user: number
  agent: number
}): JSX.Element {
  const total = user + agent
  const share = total ? (user / total) * 100 : 0
  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex h-10 w-full bg-border-subtle" aria-hidden>
        <div className="h-10 bg-brand" style={{ width: `${share}%` }} />
        <div className="h-10 flex-1 bg-border-default" />
      </div>
      <div className="flex items-baseline justify-between gap-8 font-mono tabular text-11">
        <span className="text-primary">
          {t('Operator')} {num(user)} <span className="text-tertiary">{pct(user, total)}</span>
        </span>
        <span className="text-primary">
          <span className="text-tertiary">{pct(agent, total)}</span> {num(agent)} {t('agents')}
        </span>
      </div>
    </div>
  )
}
