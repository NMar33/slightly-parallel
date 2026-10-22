/**
 * The monitor's two drawings: a sparkline for small places, and a strip
 * chart — one measure over time, the unusual spans shaded behind it, holes
 * in the record left blank, and a shared cursor so every strip on a page
 * points at the same moment.
 */

import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { SEVERITY_COLOR, clock, type MonitorEvent } from '../../lib/monitor'
import { dayMonth } from '../../lib/months'

export function Spark({ values, color, width = 48, height = 14, max, fill = true, label }: {
  values: Array<number | null | undefined>
  color: string
  width?: number
  height?: number
  /** A fixed top (100 for a percentage); else the highest value. */
  max?: number
  fill?: boolean
  label?: string
}) {
  const pts = values.map((v) => (v == null || !Number.isFinite(v) ? null : v))
  const top = max ?? Math.max(1e-9, ...pts.filter((v): v is number => v != null))
  const n = Math.max(1, pts.length - 1)
  const xy = pts.map((v, i) => (v == null ? null : [(i / n) * width, height - 1 - (Math.min(v, top) / top) * (height - 2)] as const))
  let d = ''
  let area = ''
  let run: Array<readonly [number, number]> = []
  const flush = () => {
    if (run.length > 1) {
      d += `M${run.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join('L')}`
      area += `M${run[0]![0].toFixed(1)},${height}L${run.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join('L')}L${run[run.length - 1]![0].toFixed(1)},${height}Z`
    }
    run = []
  }
  for (const p of xy) { if (p) run.push(p); else flush() }
  flush()
  const last = [...xy].reverse().find(Boolean)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true} className="shrink-0 overflow-visible">
      {fill && <path d={area} fill={color} opacity={0.14} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.25} strokeLinejoin="round" strokeLinecap="round" />
      {last && <circle cx={last[0]} cy={last[1]} r={1.6} fill={color} />}
    </svg>
  )
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(600)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/** A fixed empty list, so a strip without gaps keeps its memoized paths. */
const NO_GAPS: Array<[number, number]> = []

export interface Line {
  values: Array<number | null>
  color: string
  /** Peaks drawn as a faint band above the average line. */
  peaks?: Array<number | null>
  name: string
}

/**
 * One measure over [from, to]. `format` words a value; `max` fixes the top
 * (100 for percentages). Hovering moves the shared cursor (`cursor`,
 * `onCursor`); clicking an unusual span calls `onEvent`.
 */
export function Strip({
  t, lines, from, to, format, max, height = 64, events = [], gaps = NO_GAPS, cursor, onCursor, onEvent, title, now, dense = false, bare = false,
}: {
  t: number[]
  lines: Line[]
  from: number
  to: number
  format: (v: number | null | undefined) => string
  max?: number
  height?: number
  events?: MonitorEvent[]
  gaps?: Array<[number, number]>
  cursor?: number | null
  onCursor?: (t: number | null) => void
  onEvent?: (e: MonitorEvent) => void
  title: ReactNode
  /** The live value beside the title. */
  now?: ReactNode
  dense?: boolean
  /** Leave out the title row (the value under the cursor moves into a tooltip). */
  bare?: boolean
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const span = Math.max(1, to - from)
  const x = useCallback((ts: number) => ((ts - from) / span) * width, [from, span, width])
  const top = useMemo(() => {
    if (max != null) return max
    let m = 0
    for (const l of lines) for (const v of [...l.values, ...(l.peaks ?? [])]) if (v != null && v > m) m = v
    return m > 0 ? m * 1.1 : 1
  }, [lines, max])
  const y = useCallback((v: number) => height - 2 - (Math.min(v, top) / top) * (height - 6), [height, top])

  const paths = useMemo(() => lines.map((l) => {
    let band = ''
    let seg: number[] = []
    const out: string[] = []
    const inGap = (a: number, b: number) => gaps.some(([g0, g1]) => a <= g0 && b >= g1)
    for (let i = 0; i < t.length; i++) {
      const v = l.values[i]
      if (v == null || (i > 0 && inGap(t[i - 1]!, t[i]!))) {
        if (seg.length > 1) out.push(seg.map((k) => `${x(t[k]!).toFixed(1)},${y(l.values[k]!).toFixed(1)}`).join('L'))
        seg = v == null ? [] : [i]
        continue
      }
      seg.push(i)
    }
    if (seg.length > 1) out.push(seg.map((k) => `${x(t[k]!).toFixed(1)},${y(l.values[k]!).toFixed(1)}`).join('L'))
    const d = out.map((s) => `M${s}`).join('')
    if (l.peaks) {
      const up: string[] = [], down: string[] = []
      for (let i = 0; i < t.length; i++) {
        const a = l.values[i], p = l.peaks[i]
        if (a == null || p == null) continue
        up.push(`${x(t[i]!).toFixed(1)},${y(p).toFixed(1)}`)
        down.unshift(`${x(t[i]!).toFixed(1)},${y(a).toFixed(1)}`)
      }
      if (up.length > 1) band = `M${up.join('L')}L${down.join('L')}Z`
    }
    return { d, band }
  }), [lines, t, x, y, gaps])

  const at = cursor != null && cursor >= from && cursor <= to ? cursor : null
  let idx = -1
  if (at != null && t.length) {
    let best = Infinity
    for (let i = 0; i < t.length; i++) { const dd = Math.abs(t[i]! - at); if (dd < best) { best = dd; idx = i } }
  }
  const shown = events.filter((e) => e.kind !== 'gap')

  return (
    <div className="flex flex-col gap-2 min-w-0">
      {!bare && <div className="flex items-baseline gap-8 min-w-0">
        <span className="text-11 font-mono uppercase tracking-wide text-tertiary">{title}</span>
        {idx >= 0 ? (
          <span className="text-11 font-mono tabular-nums text-secondary">
            {clock(t[idx]!, true)} · {lines.map((l) => `${lines.length > 1 ? `${l.name} ` : ''}${format(l.values[idx])}`).join(' · ')}
          </span>
        ) : now}
        <span className="ml-auto text-10 font-mono text-tertiary tabular-nums">{format(max ?? top / 1.1)}</span>
      </div>}
      <div ref={ref} className="relative" style={{ height }}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          onCursor?.(from + ((e.clientX - r.left) / r.width) * span)
        }}
        onMouseLeave={() => onCursor?.(null)}>
        <svg width={width} height={height} className="absolute inset-0 overflow-visible" aria-hidden>
          <line x1={0} x2={width} y1={height - 1.5} y2={height - 1.5} stroke="var(--border-default)" />
          <line x1={0} x2={width} y1={y(top / 2)} y2={y(top / 2)} stroke="var(--border-subtle)" strokeDasharray="2 4" />
          {gaps.map(([a, b]) => (
            <rect key={a} x={x(a)} width={Math.max(1, x(b) - x(a))} y={0} height={height}
              fill="var(--bg-elevated)" opacity={0.6} />
          ))}
          {shown.map((e) => (
            <rect key={e.id} x={x(Math.max(from, e.started))} y={0}
              width={Math.max(3, x(Math.min(to, e.ended ?? to)) - x(Math.max(from, e.started)))} height={height}
              fill={SEVERITY_COLOR[e.severity]} opacity={dense ? 0.1 : 0.14}
              style={{ cursor: onEvent ? 'pointer' : undefined }}
              onClick={() => onEvent?.(e)}>
              <title>{e.title}</title>
            </rect>
          ))}
          {paths.map((p, i) => (
            <g key={i}>
              {p.band && <path d={p.band} fill={lines[i]!.color} opacity={0.12} />}
              <path d={p.d} fill="none" stroke={lines[i]!.color} strokeWidth={1.5} strokeLinejoin="round" />
            </g>
          ))}
          {bare && idx >= 0 && (
            <text x={Math.min(x(t[idx]!) + 6, width - 150)} y={10} className="text-10 font-mono" fill="var(--text-secondary)">
              {clock(t[idx]!, true)} · {lines.map((l) => `${lines.length > 1 ? `${l.name} ` : ''}${format(l.values[idx])}`).join(' · ')}
            </text>
          )}
          {bare && idx < 0 && <text x={2} y={10} className="text-10 font-mono" fill="var(--text-tertiary)">{format(max ?? top / 1.1)}</text>}
          {idx >= 0 && (
            <g>
              <line x1={x(t[idx]!)} x2={x(t[idx]!)} y1={0} y2={height} stroke="var(--text-tertiary)" strokeWidth={1} />
              {lines.map((l, i) => l.values[idx] != null && (
                <circle key={i} cx={x(t[idx]!)} cy={y(l.values[idx]!)} r={3} fill={l.color} stroke="var(--bg-base)" strokeWidth={1.5} />
              ))}
            </g>
          )}
        </svg>
      </div>
    </div>
  )
}

/** Time ticks for the bottom of a stack of strips. */
export function TimeAxis({ from, to }: { from: number; to: number }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const span = to - from
  const steps = [60, 300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400, 7 * 86400, 30 * 86400]
  const step = steps.find((s) => span / s <= Math.max(3, width / 110)) ?? 30 * 86400
  const offset = new Date().getTimezoneOffset() * 60
  const ticks: number[] = []
  for (let v = Math.ceil((from - offset) / step) * step + offset; v <= to; v += step) ticks.push(v)
  const long = span > 2 * 86400
  return (
    <div ref={ref} className="relative h-16 text-10 font-mono text-tertiary tabular-nums">
      {ticks.map((v) => (
        <span key={v} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: ((v - from) / span) * width }}>
          {long ? dayMonth(new Date(v * 1000)) : clock(v)}
        </span>
      ))}
    </div>
  )
}
