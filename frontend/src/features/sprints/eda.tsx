import { useState } from 'react'

import { t, tn } from '../../i18n/scope/views'
/**
 * Small plots for the block statistics — an EDA panel, not a dashboard.
 *
 * Every chart here is single-series on purpose. The product's tokens fail a
 * categorical check (its green and its brand sit ΔE 5.9 apart under protan,
 * and the green reads near-gray), so identity is never carried by hue in
 * these plots: one hue does magnitude, direction does sign, texture marks
 * weekends, and values are labelled directly. The table beside them is the
 * accessible twin — the contrast of brand against this surface is below 3:1,
 * which obliges labels or a table, and there are both.
 */

const AXIS = 'color-mix(in srgb, var(--text-tertiary) 45%, transparent)'
const INK = 'var(--text-tertiary)'

function useHover<T>() {
  const [hover, setHover] = useState<{ x: number; y: number; datum: T } | null>(null)
  return { hover, setHover }
}

function Tip({ x, y, lines }: { x: number; y: number; lines: string[] }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 rounded-input border border-border-default bg-surface px-6 py-3 shadow-lg"
      style={{ left: x, top: y, transform: 'translate(-50%, -115%)' }}
    >
      {lines.map((l, i) => (
        <div key={i} className={`text-10 font-mono whitespace-nowrap ${i === 0 ? 'text-primary' : 'text-tertiary'}`}>{l}</div>
      ))}
    </div>
  )
}

/**
 * A plot without a stated finding makes the reader do the work twice. The
 * headline is the answer; the chart is the evidence for it.
 */
function Frame({
  title, finding, note, children, empty,
}: {
  title: string
  /** The reading, in words — what this chart says. */
  finding?: string
  note?: string
  children: React.ReactNode
  empty?: string
}) {
  return (
    <figure className="flex flex-col gap-4 m-0">
      <figcaption className="flex flex-col gap-1">
        <span className="flex items-baseline gap-6">
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{title}</span>
          {note && <span className="text-10 font-mono text-tertiary/70" style={{ fontSize: 9 }}>{note}</span>}
        </span>
        {finding && <span className="text-12 text-primary leading-snug">{finding}</span>}
      </figcaption>
      {empty ? <span className="text-10 font-mono text-tertiary italic py-8">{empty}</span> : children}
    </figure>
  )
}

/** Distribution of a small integer sample — the classic first EDA look. */
export function Histogram({ values, unit, title, finding }: { values: number[]; unit: string; title: string; finding?: string }) {
  const { hover, setHover } = useHover<{ label: string; n: number }>()
  if (values.length === 0) return <Frame title={title} empty={t('no samples yet')}>{null}</Frame>
  const max = Math.max(...values)
  const cap = Math.min(max, 5)
  const bins: Array<{ label: string; n: number }> = []
  for (let i = 0; i <= cap; i++) {
    bins.push({ label: i === cap && max > cap ? `${i}+` : String(i), n: values.filter((v) => (i === cap && max > cap ? v >= i : v === i)).length })
  }
  const peak = Math.max(1, ...bins.map((b) => b.n))
  const H = 104
  return (
    <Frame title={title} finding={finding} note={tn(values.length, '{n} sample', '{n} samples')}>
      <div className="relative">
        <div className="flex items-end gap-2" style={{ height: H }}>
          {bins.map((b) => (
            <div
              key={b.label}
              className="flex-1 flex flex-col items-center justify-end gap-2"
              onMouseEnter={(e) => setHover({ x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2, y: H - 4, datum: b })}
              onMouseLeave={() => setHover(null)}
            >
              {b.n > 0 && <span className="text-10 font-mono" style={{ fontSize: 9, color: INK }}>{b.n}</span>}
              <span
                className="w-full"
                style={{
                  height: Math.max(b.n > 0 ? 3 : 1, (b.n / peak) * (H - 18)),
                  backgroundColor: b.n > 0 ? 'var(--brand)' : AXIS,
                  opacity: b.n > 0 ? 0.85 : 0.4,
                  borderRadius: '4px 4px 0 0',
                }}
              />
            </div>
          ))}
        </div>
        <div className="flex gap-2 border-t pt-2" style={{ borderColor: AXIS }}>
          {bins.map((b) => (
            <span key={b.label} className="flex-1 text-center text-10 font-mono" style={{ fontSize: 9, color: INK }}>{b.label}</span>
          ))}
        </div>
        <span className="text-10 font-mono" style={{ fontSize: 9, color: INK }}>{unit}</span>
        {hover && <Tip x={hover.x} y={hover.y} lines={[tn(hover.datum.n, '{n} task', '{n} tasks'), `${hover.datum.label} ${unit}`]} />}
      </div>
    </Frame>
  )
}

/** Magnitude by a fixed category — weekends hatched, never a second hue. */
export function WeekdayBars({ minutes, title, finding }: { minutes: number[]; title: string; finding?: string }) {
  const { hover, setHover } = useHover<{ day: string; m: number }>()
  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const peak = Math.max(1, ...minutes)
  const H = 104
  const fmt = (m: number) => (m >= 60 ? `${Math.round(m / 6) / 10}h` : `${Math.round(m)}m`)
  if (minutes.every((m) => m === 0)) return <Frame title={title} empty={t('no hours booked in this range')}>{null}</Frame>
  return (
    <Frame title={title} finding={finding} note={t('hatched = weekend')}>
      <div className="relative">
        <div className="flex items-end gap-2" style={{ height: H }}>
          {DAYS.map((d, i) => {
            const weekend = i >= 5
            return (
              <div
                key={d}
                className="flex-1 flex flex-col items-center justify-end gap-2"
                onMouseEnter={(e) => setHover({ x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2, y: H - 4, datum: { day: d, m: minutes[i]! } })}
                onMouseLeave={() => setHover(null)}
              >
                {minutes[i]! > 0 && <span className="text-10 font-mono" style={{ fontSize: 9, color: INK }}>{fmt(minutes[i]!)}</span>}
                <span
                  className="w-full"
                  style={{
                    height: Math.max(minutes[i]! > 0 ? 3 : 1, (minutes[i]! / peak) * (H - 18)),
                    backgroundColor: minutes[i]! > 0 ? 'var(--brand)' : AXIS,
                    opacity: minutes[i]! > 0 ? 0.85 : 0.4,
                    borderRadius: '4px 4px 0 0',
                    backgroundImage: weekend && minutes[i]! > 0
                      ? 'repeating-linear-gradient(45deg, var(--hatch) 0 3px, transparent 3px 6px)'
                      : undefined,
                  }}
                />
              </div>
            )
          })}
        </div>
        <div className="flex gap-2 border-t pt-2" style={{ borderColor: AXIS }}>
          {DAYS.map((d) => <span key={d} className="flex-1 text-center text-10 font-mono" style={{ fontSize: 9, color: INK }}>{d[0]}</span>)}
        </div>
        {hover && <Tip x={hover.x} y={hover.y} lines={[t('{fmt} of your hours', { fmt: fmt(hover.datum.m) }), hover.datum.day]} />}
      </div>
    </Frame>
  )
}

/** Sign by direction, magnitude by length — no colour needed for polarity. */
export function NetBars({ days, title, finding }: { days: Array<{ date: string; net: number }>; title: string; finding?: string }) {
  const { hover, setHover } = useHover<{ date: string; net: number }>()
  const peak = Math.max(1, ...days.map((d) => Math.abs(d.net)))
  const H = 104, mid = H / 2
  if (days.every((d) => d.net === 0)) return <Frame title={title} empty={t('Cards created and cards done were equal every day')}>{null}</Frame>
  return (
    <Frame title={title} finding={finding} note={t('Each day: cards created above the line, cards done below')}>
      <div className="relative" style={{ height: H }}>
        <div className="absolute left-0 right-0 border-t" style={{ top: mid, borderColor: AXIS }} aria-hidden />
        <div className="absolute inset-0 flex items-stretch gap-2">
          {days.map((d) => {
            const h = (Math.abs(d.net) / peak) * (mid - 8)
            return (
              <div
                key={d.date}
                className="flex-1 relative"
                onMouseEnter={(e) => setHover({ x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2, y: mid, datum: d })}
                onMouseLeave={() => setHover(null)}
              >
                {d.net !== 0 && (
                  <span
                    className="absolute left-0 right-0"
                    style={{
                      height: Math.max(4, h),
                      top: d.net > 0 ? mid - Math.max(3, h) : mid,
                      backgroundColor: 'var(--brand)',
                      opacity: d.net > 0 ? 0.85 : 0.45,
                      borderRadius: d.net > 0 ? '4px 4px 0 0' : '0 0 4px 4px',
                      backgroundImage: d.net < 0 ? 'repeating-linear-gradient(45deg, var(--hatch) 0 3px, transparent 3px 6px)' : undefined,
                    }}
                  />
                )}
              </div>
            )
          })}
        </div>
        {hover && (
          <Tip x={hover.x} y={hover.y} lines={[
            hover.datum.net === 0 ? 'level' : hover.datum.net > 0 ? t('{net} more created than done', { net: hover.datum.net }) : t('{v} more done than created', { v: -hover.datum.net }),
            hover.datum.date.slice(5),
          ]} />
        )}
      </div>
    </Frame>
  )
}
