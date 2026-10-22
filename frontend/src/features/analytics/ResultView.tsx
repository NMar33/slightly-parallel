/**
 * A query's answer, drawn the way its shape asks:
 *
 * - one row, one number → a big number;
 * - a time first, numbers after → a line over time (bars when few points);
 * - a category first, numbers after → horizontal bars, in the order given;
 * - anything else → the table.
 *
 * The table is always one click away, and a chart with several number
 * columns lets you pick which one it draws. One series, one colour.
 */

import { useLayoutEffect, useMemo, useRef, useState } from 'react'

import { Segmented } from '../../components/Segmented'
import { isNumeric, isTime, type Result } from './data'

import { locale, t, tn } from '../../i18n/scope/views'
import { dayMonth } from '../../lib/months'
type Kind = 'number' | 'time' | 'bars' | 'table' | 'grid'

const distinct = (r: Result, i: number) => new Set(r.rows.map((row) => String(row[i]))).size

export function kindOf(r: Result): Kind {
  const cols = r.columns
  if (r.rows.length === 1 && cols.length === 1 && isNumeric(cols[0]!.type)) return 'number'
  // Two splits and a number: a grid, when both splits are short lists.
  // The second column must be a split, not a total: totals come back as BIGINT,
  // HUGEINT or DOUBLE; a split is text or a small whole number (hour, INTEGER).
  if (cols.length === 3 && isNumeric(cols[2]!.type) && !isTime(cols[0]!.type) && r.rows.length >= 4
      && !/BIGINT|HUGEINT|DOUBLE|DECIMAL|FLOAT/i.test(cols[1]!.type)
      && distinct(r, 0) <= 31 && distinct(r, 1) <= 31) return 'grid'
  if (cols.length >= 2 && cols.slice(1).some((c) => isNumeric(c.type))) {
    if (isTime(cols[0]!.type)) return 'time'
    if (!isNumeric(cols[0]!.type) || r.rows.length <= 60) return 'bars'
  }
  return 'table'
}

const fmt = (v: unknown): string => {
  if (v == null) return '—'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString(locale()) : v.toLocaleString(locale(), { maximumFractionDigits: 2 })
  const s = String(v)
  return /^\d{4}-\d{2}-\d{2}T00:00$/.test(s) ? s.slice(0, 10) : s.replace('T', ' ')
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(640)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const order = (vals: string[]) => (vals.every((v) => WEEK.includes(v))
  ? WEEK.filter((w) => vals.includes(w))
  : vals.every((v) => v !== '' && Number.isFinite(Number(v))) ? vals.sort((a, b) => Number(a) - Number(b)) : vals.sort())

/** Two splits as rows and columns, the number as the shade of each cell — one hue. */
function Heatmap({ r }: { r: Result }) {
  const [hover, setHover] = useState<string | null>(null)
  const rows = order([...new Set(r.rows.map((x) => String(x[0])))])
  const cols = order([...new Set(r.rows.map((x) => String(x[1])))])
  const val = new Map(r.rows.map((x) => [`${x[0]}|${x[1]}`, Number(x[2] ?? 0)]))
  const top = Math.max(1, ...val.values())
  const tip = hover ? `${hover.replace('|', ' · ')}: ${fmt(val.get(hover) ?? 0)} ${r.columns[2]!.name}` : t('{name} × {name2} · darker is more', { name: r.columns[0]!.name, name2: r.columns[1]!.name })
  return (
    <div className="flex flex-col gap-6 overflow-x-auto">
      <span className="text-11 font-mono text-secondary h-16">{tip}</span>
      <div className="inline-grid gap-2 items-center" style={{ gridTemplateColumns: `auto repeat(${cols.length}, minmax(18px, 1fr))` }}>
        <span />
        {cols.map((c) => <span key={c} className="text-10 font-mono text-tertiary text-center">{c}</span>)}
        {rows.map((rw) => (
          <FragmentRow key={rw} label={rw}>
            {cols.map((c) => {
              const v = val.get(`${rw}|${c}`) ?? 0
              return (
                <span key={c} onMouseEnter={() => setHover(`${rw}|${c}`)} onMouseLeave={() => setHover(null)}
                  className="h-20 rounded-[3px] border border-transparent hover:border-[var(--text-primary)]"
                  style={{ background: v ? `color-mix(in srgb, var(--brand) ${Math.round(12 + (v / top) * 88)}%, transparent)` : 'var(--bg-elevated)' }} />
              )
            })}
          </FragmentRow>
        ))}
      </div>
    </div>
  )
}

function FragmentRow({ label, children }: { label: string; children: React.ReactNode }) {
  return <><span className="text-11 font-mono text-secondary pr-8 text-right whitespace-nowrap">{label}</span>{children}</>
}

function TimeChart({ r, y, line: forceLine }: { r: Result; y: number; line?: boolean }) {
  const [ref, W] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const H = 200, L = 44, B = 22, T = 8
  const pts = r.rows.map((row) => ({ t: Date.parse(String(row[0])), v: Number(row[y] ?? 0), row })).filter((p) => Number.isFinite(p.t)).sort((a, b) => a.t - b.t)
  if (!pts.length) return <p className="text-12 text-tertiary">{t('Nothing to draw.')}</p>
  const t0 = pts[0]!.t, t1 = pts[pts.length - 1]!.t || t0 + 1
  const top = Math.max(1, ...pts.map((p) => p.v)) * 1.1
  const bars = forceLine == null ? pts.length <= 40 : !forceLine
  const bw = Math.max(2, ((W - L - 8) / Math.max(1, pts.length)) * 0.7)
  // Bars are centred on their time: half a bar of room keeps the first off the axis labels.
  const pad = bars ? bw / 2 + 4 : 0
  const x = (it: number) => L + pad + ((it - t0) / Math.max(1, t1 - t0)) * (W - L - 8 - 2 * pad)
  const yy = (v: number) => T + (1 - v / top) * (H - T - B)
  const ticks = [0, 0.5, 1].map((f) => top / 1.1 * f)
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${yy(p.v).toFixed(1)}`).join('')
  const labelEvery = Math.max(1, Math.ceil(pts.length / Math.max(2, W / 90)))
  return (
    <div ref={ref} className="relative">
      <svg width={W} height={H} className="block" onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const px = e.clientX - e.currentTarget.getBoundingClientRect().left
          let best = 0
          pts.forEach((p, i) => { if (Math.abs(x(p.t) - px) < Math.abs(x(pts[best]!.t) - px)) best = i })
          setHover(best)
        }}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - 8} y1={yy(v)} y2={yy(v)} stroke="var(--border-subtle)" strokeDasharray={v ? '2 4' : undefined} />
            <text x={L - 6} y={yy(v) + 3} textAnchor="end" fontSize={10} fill="var(--text-tertiary)" fontFamily="var(--font-mono)">{fmt(Math.round(v))}</text>
          </g>
        ))}
        {bars
          ? pts.map((p, i) => <rect key={i} x={x(p.t) - bw / 2} y={yy(p.v)} width={bw} height={Math.max(0, yy(0) - yy(p.v))} rx={2} fill="var(--brand)" opacity={hover == null || hover === i ? 1 : 0.55} />)
          : <><path d={`${line}L${x(t1)},${yy(0)}L${x(t0)},${yy(0)}Z`} fill="var(--brand)" opacity={0.12} /><path d={line} fill="none" stroke="var(--brand)" strokeWidth={2} strokeLinejoin="round" /></>}
        {pts.map((p, i) => i % labelEvery === 0 && (
          <text key={`l${i}`} x={x(p.t)} y={H - 6} textAnchor="middle" fontSize={10} fill="var(--text-tertiary)" fontFamily="var(--font-mono)">
            {dayMonth(new Date(p.t))}
          </text>
        ))}
        {hover != null && (
          <g>
            <line x1={x(pts[hover]!.t)} x2={x(pts[hover]!.t)} y1={T} y2={yy(0)} stroke="var(--text-tertiary)" />
            {!bars && <circle cx={x(pts[hover]!.t)} cy={yy(pts[hover]!.v)} r={4} fill="var(--brand)" stroke="var(--bg-base)" strokeWidth={2} />}
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="absolute top-0 pointer-events-none px-8 py-4 rounded-input border border-border-subtle bg-base shadow-md text-11 font-mono"
          style={{ left: Math.min(W - 180, Math.max(0, x(pts[hover]!.t) + 8)) }}>
          <div className="text-tertiary">{fmt(pts[hover]!.row[0])}</div>
          <div className="text-primary">{r.columns[y]!.name}: {fmt(pts[hover]!.v)}</div>
        </div>
      )}
    </div>
  )
}

function BarChart({ r, y }: { r: Result; y: number }) {
  const rows = r.rows.slice(0, 60)
  const top = Math.max(1, ...rows.map((row) => Number(row[y] ?? 0)))
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => {
        const v = Number(row[y] ?? 0)
        return (
          <div key={i} className="group grid grid-cols-[minmax(80px,200px)_minmax(0,1fr)_72px] items-center gap-8 text-12" title={`${fmt(row[0])}: ${fmt(v)}`}>
            <span className="truncate text-secondary text-right">{fmt(row[0])}</span>
            <span className="h-14 flex items-center">
              <span className="h-full rounded-r-[4px] group-hover:opacity-80" style={{ width: `${Math.max(0.5, (v / top) * 100)}%`, background: 'var(--brand)' }} />
            </span>
            <span className="font-mono tabular-nums text-primary text-right">{fmt(v)}</span>
          </div>
        )
      })}
      {r.rows.length > 60 && <p className="text-11 text-tertiary">{t('The first 60 of')}{' '}{r.rows.length} {t('— the table has them all.')}</p>}
    </div>
  )
}

function ResultTable({ r }: { r: Result }) {
  return (
    <div className="overflow-auto max-h-[420px] border-t border-border-subtle">
      <table className="w-full text-12 tabular-nums border-separate border-spacing-0">
        <thead className="sticky top-0 bg-base text-10 uppercase tracking-wide font-mono text-tertiary">
          <tr>{r.columns.map((c) => <th key={c.name} className={`px-10 py-6 font-normal border-b border-border-subtle whitespace-nowrap ${isNumeric(c.type) ? 'text-right' : 'text-left'}`}>{c.name}</th>)}</tr>
        </thead>
        <tbody>
          {r.rows.map((row, i) => (
            <tr key={i} className="hover:bg-hover">
              {row.map((v, j) => (
                <td key={j} className={`px-10 py-3 border-b border-border-subtle max-w-[360px] truncate ${isNumeric(r.columns[j]!.type) ? 'text-right font-mono' : 'text-secondary'}`} title={String(v ?? '')}>{fmt(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ResultView({ r, error, loading, force }: {
  r?: Result; error?: Error | null; loading?: boolean
  /** From the pipeline's `as` step. */
  force?: 'line' | 'bars' | 'table' | 'number' | 'grid' | null
}) {
  const auto = r ? kindOf(r) : 'table'
  const natural: Kind = !r || !force ? auto
    : force === 'table' ? 'table'
    : force === 'number' ? 'number'
    : force === 'grid' ? (r.columns.length >= 3 ? 'grid' : auto)
    : force === 'line' ? (isTime(r.columns[0]?.type ?? '') ? 'time' : auto)
    : isTime(r.columns[0]?.type ?? '') ? 'time' : 'bars'
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const numbers = useMemo(() => (r ? r.columns.map((c, i) => [i, c] as const).filter(([i, c]) => i > 0 && isNumeric(c.type)) : []), [r])
  const [pick, setPick] = useState<number | null>(null)
  const y = pick != null && numbers.some(([i]) => i === pick) ? pick : numbers[0]?.[0] ?? 1
  if (error) return <p className="text-12 font-mono px-10 py-8 rounded-input" style={{ color: 'var(--status-red)', background: 'color-mix(in srgb, var(--status-red) 8%, transparent)' }}>{error.message}</p>
  if (!r) return loading ? <p className="text-12 font-mono text-tertiary">{t('Running…')}</p> : null
  const chart = natural !== 'table' && view === 'chart'
  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center gap-8 text-10 font-mono text-tertiary flex-wrap">
        <span>{tn(r.rows.length, '{n} row', '{n} rows', { n: r.rows.length.toLocaleString(locale()) })}{r.truncated ? t(' (the first 5000)') : ''} · {r.ms} {t('ms')}{loading ? t(' · running…') : ''}</span>
        {natural !== 'table' && natural !== 'number' && numbers.length > 1 && view === 'chart' && (
          <select value={y} onChange={(e) => setPick(Number(e.target.value))} aria-label={t('Column to draw')}
            className="h-20 px-4 rounded-input border border-border-subtle bg-surface text-10 font-mono text-secondary">
            {numbers.map(([i, c]) => <option key={i} value={i}>{c.name}</option>)}
          </select>
        )}
        {natural !== 'table' && (
          <span className="ml-auto"><Segmented label={t('View')} shape="pill" height={20} value={view} onChange={setView} options={[['chart', 'chart'], ['table', 'table']] as const} /></span>
        )}
      </div>
      {chart && natural === 'number' && (
        <div className="flex gap-32 flex-wrap">
          {r.columns.map((c, i) => (
            <div key={c.name} className="flex flex-col"><span className="text-10 uppercase tracking-wide font-mono text-tertiary">{c.name}</span>
              <span className="text-32 font-semibold text-primary tabular-nums leading-none">{fmt(r.rows[0]?.[i])}</span></div>
          ))}
        </div>
      )}
      {chart && natural === 'grid' && <Heatmap r={r} />}
      {chart && natural === 'time' && <TimeChart r={r} y={y} line={force === 'line' ? true : force === 'bars' ? false : undefined} />}
      {chart && natural === 'bars' && <BarChart r={r} y={y} />}
      {!chart && <ResultTable r={r} />}
    </div>
  )
}
