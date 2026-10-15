import { useMemo } from 'react'

import { hm } from './deck'
import { Segmented } from '../../components/Segmented'

import { locale, t } from '../../i18n/scope/views'
/**
 * Timeline bands — six ways to draw a block's rhythm over a week or a month.
 *
 * Every one of them takes the same per-day series and answers the same three
 * demands: show how hard the work was going, let a day be clicked for what
 * actually happened in it, and open up when there is room. They differ only
 * in what they make intensity *look* like — height, heat, shape, direction,
 * mass or flow — which is the thing worth choosing between.
 */

export type Day = {
  date: string
  done: number
  human_min: number
  agent_min: number
  events: number
  /** Tasks by status on that day, when the deck was asked for a range. */
  bands?: Record<string, number>
}

export type BandKind = 'bars' | 'heat' | 'ridge' | 'split' | 'dots' | 'stream'

export const BAND_LABELS: Record<BandKind, string> = {
  bars: 'bars', heat: 'heat', ridge: 'ridge', split: 'split', dots: 'dots', stream: 'stream',
}

/** Everything a day is worth, in one number: minutes plus a nudge per event. */
export const weightOf = (d: Day): number => d.human_min + d.agent_min + d.events * 2

export function dayLabel(iso: string): string {
  const dt = new Date(`${iso}T00:00:00`)
  return dt.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
}

const isToday = (iso: string, today: string) => iso === today
const isWeekend = (iso: string) => {
  const d = new Date(`${iso}T00:00:00`).getDay()
  return d === 0 || d === 6
}

export function Band({
  kind, days, today, height = 26, onPick, picked,
}: {
  kind: BandKind
  days: Day[]
  today: string
  height?: number
  onPick?: (d: Day) => void
  picked?: string | null
}) {
  const max = useMemo(() => Math.max(1, ...days.map(weightOf)), [days])
  const common = { days, today, height, onPick, picked, max }
  switch (kind) {
    case 'heat': return <HeatBand {...common} />
    case 'ridge': return <RidgeBand {...common} />
    case 'split': return <SplitBand {...common} />
    case 'dots': return <DotsBand {...common} />
    case 'stream': return <StreamBand {...common} />
    default: return <BarsBand {...common} />
  }
}

type Inner = {
  days: Day[]
  today: string
  height: number
  max: number
  onPick?: (d: Day) => void
  picked?: string | null
}

/** The hit area every band shares: one button per day, same title everywhere. */
function DayCell({
  d, today, picked, onPick, children, className = '',
}: {
  d: Day
  today: string
  picked?: string | null
  onPick?: (d: Day) => void
  children: React.ReactNode
  className?: string
}) {
  const title = `${dayLabel(d.date)} · ${d.done} done · ${hm(d.human_min)} you · ${hm(d.agent_min)} agents · ${d.events} events`
  return (
    <button
      type="button"
      onClick={() => onPick?.(d)}
      title={title}
      aria-label={title}
      aria-pressed={picked === d.date}
      className={`relative flex-1 min-w-0 flex items-end justify-center ${onPick ? 'cursor-pointer' : 'cursor-default'} ${picked === d.date ? 'outline outline-1 outline-brand rounded-bar' : ''} ${className}`}
    >
      {children}
      {isToday(d.date, today) && <span className="absolute -bottom-2 left-1/2 -translate-x-1/2 h-2 w-2 rounded-pill bg-brand" aria-hidden />}
    </button>
  )
}

function BarsBand({ days, today, height, max, onPick, picked }: Inner) {
  return (
    <div className="flex items-end gap-2 w-full" style={{ height }}>
      {days.map((d) => {
        const h = Math.max(1, (weightOf(d) / max) * (height - 4))
        return (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick}>
            <span className="w-full rounded-t-bar" style={{
              height: h,
              backgroundColor: isWeekend(d.date) ? 'color-mix(in srgb, var(--brand) 35%, transparent)' : 'var(--brand)',
              opacity: weightOf(d) === 0 ? 0.15 : 0.85,
            }} />
            {d.done > 0 && (
              <span className="absolute left-1/2 -translate-x-1/2 h-3 w-3 rounded-pill bg-status-green" style={{ bottom: h + 1 }} aria-hidden />
            )}
          </DayCell>
        )
      })}
    </div>
  )
}

function HeatBand({ days, today, height, max, onPick, picked }: Inner) {
  return (
    <div className="flex items-stretch gap-2 w-full" style={{ height }}>
      {days.map((d) => {
        const f = weightOf(d) / max
        return (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick} className="items-stretch">
            <span className="w-full rounded-bar flex items-center justify-center" style={{
              backgroundColor: f === 0
                ? 'color-mix(in srgb, var(--status-red) 8%, var(--bg-elevated))'
                : `color-mix(in oklab, var(--brand) ${Math.round(18 + f * 70)}%, var(--bg-elevated))`,
            }}>
              {d.done > 0 && <span className="text-10 font-mono font-semibold" style={{ color: 'var(--bg-base)', fontSize: 9 }}>{d.done}</span>}
            </span>
          </DayCell>
        )
      })}
    </div>
  )
}

function RidgeBand({ days, today, height, max, onPick, picked }: Inner) {
  const pts = days.map((d, i) => {
    const x = (i + 0.5) / days.length * 100
    const y = height - 3 - (weightOf(d) / max) * (height - 8)
    return `${x},${y}`
  })
  const area = `0,${height} ${pts.join(' ')} 100,${height}`
  return (
    <div className="relative w-full" style={{ height }}>
      <svg className="absolute inset-0 w-full h-full" viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" aria-hidden>
        <polygon points={area} fill="color-mix(in srgb, var(--brand) 22%, transparent)" />
        <polyline points={pts.join(' ')} fill="none" stroke="var(--brand)" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="absolute inset-0 flex items-end gap-2">
        {days.map((d) => (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick}>
            {d.done > 0 && <span className="h-4 w-4 rounded-pill bg-status-green mb-[1px]" aria-hidden />}
          </DayCell>
        ))}
      </div>
    </div>
  )
}

function SplitBand({ days, today, height, onPick, picked }: Inner) {
  const mid = height / 2
  const scale = Math.max(1, ...days.map((d) => Math.max(d.human_min, d.agent_min)))
  return (
    <div className="relative w-full" style={{ height }}>
      <div className="absolute left-0 right-0 h-px bg-border-default" style={{ top: mid }} aria-hidden />
      <div className="absolute inset-0 flex gap-2">
        {days.map((d) => (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick} className="items-center">
            <span className="relative w-full h-full block">
              <span className="absolute left-0 right-0 rounded-t-bar" style={{
                bottom: mid, height: Math.max(0, (d.human_min / scale) * (mid - 2)),
                backgroundColor: 'var(--brand)', opacity: 0.85,
              }} />
              <span className="absolute left-0 right-0 rounded-b-bar" style={{
                top: mid, height: Math.max(0, (d.agent_min / scale) * (mid - 2)),
                backgroundColor: 'var(--status-purple)', opacity: 0.7,
              }} />
              {d.done > 0 && (
                <span className="absolute left-1/2 -translate-x-1/2 h-3 w-3 rounded-pill bg-status-green" style={{ top: mid - 1.5 }} aria-hidden />
              )}
            </span>
          </DayCell>
        ))}
      </div>
    </div>
  )
}

function DotsBand({ days, today, height, max, onPick, picked }: Inner) {
  return (
    <div className="flex items-center gap-2 w-full" style={{ height }}>
      {days.map((d) => {
        const f = weightOf(d) / max
        const size = f === 0 ? 3 : 4 + f * (height - 10)
        return (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick} className="items-center">
            <span
              className="rounded-pill"
              style={{
                width: size, height: size,
                backgroundColor: f === 0 ? 'var(--border-default)' : 'var(--brand)',
                opacity: f === 0 ? 0.6 : 0.5 + f * 0.5,
                boxShadow: d.done > 0 ? '0 0 0 2px var(--status-green)' : undefined,
              }}
            />
          </DayCell>
        )
      })}
    </div>
  )
}

function StreamBand({ days, today, height, onPick, picked }: Inner) {
  const scale = Math.max(1, ...days.map((d) => d.human_min + d.agent_min))
  return (
    <div className="flex items-end gap-2 w-full" style={{ height }}>
      {days.map((d) => {
        const h1 = (d.human_min / scale) * (height - 4)
        const h2 = (d.agent_min / scale) * (height - 4)
        return (
          <DayCell key={d.date} d={d} today={today} picked={picked} onPick={onPick}>
            <span className="w-full flex flex-col justify-end" style={{ height: height - 2 }}>
              <span className="w-full" style={{ height: h2, backgroundColor: 'var(--status-purple)', opacity: 0.55 }} />
              <span className="w-full rounded-t-bar" style={{ height: h1, backgroundColor: 'var(--brand)', opacity: 0.85 }} />
              {h1 + h2 === 0 && <span className="w-full" style={{ height: 1, backgroundColor: 'var(--border-default)' }} />}
            </span>
            {d.done > 0 && (
              <span className="absolute left-1/2 -translate-x-1/2 h-3 w-3 rounded-pill bg-status-green" style={{ bottom: h1 + h2 + 1 }} aria-hidden />
            )}
          </DayCell>
        )
      })}
    </div>
  )
}

/** What a clicked day actually contained. */
export function DayDetail({ day, tasksLanded, onClose }: { day: Day; tasksLanded: string[]; onClose: () => void }) {
  return (
    <div className="rounded-input border border-brand/50 bg-elevated px-10 py-8 flex flex-col gap-4">
      <div className="flex items-baseline gap-8">
        <span className="text-12 font-semibold text-primary">{dayLabel(day.date)}</span>
        <span className="text-10 font-mono text-tertiary">
          {hm(day.human_min)} {t('yours ·')}{' '}{hm(day.agent_min)} {t('fleet ·')}{' '}{day.events} {t('events')}
        </span>
        <button type="button" onClick={onClose} className="ml-auto text-10 font-mono text-tertiary hover:text-primary" aria-label={t('Close the day')}>×</button>
      </div>
      {tasksLanded.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {tasksLanded.map((it) => (
            <li key={it} className="text-11 text-secondary flex items-center gap-4">
              <span className="h-4 w-4 rounded-pill bg-status-green shrink-0" aria-hidden />{it}
            </li>
          ))}
        </ul>
      ) : (
        <span className="text-11 text-tertiary italic">
          {day.events > 0 ? t('activity, but no task done') : t('no activity')}
        </span>
      )}
    </div>
  )
}

/** The week / month switch every band shares. */
export function RangeSwitch({ value, onChange }: { value: 7 | 30; onChange: (v: 7 | 30) => void }) {
  return (
    <Segmented
      label={t('Range')}
      shape="pill"
      value={String(value)}
      onChange={(v) => onChange(v === '30' ? 30 : 7)}
      options={[['7', 'week', t('The last seven days')], ['30', 'month', t('The last thirty days')]] as const}
    />
  )
}
