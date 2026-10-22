import { useState } from 'react'
import { Segmented } from '../../components/Segmented'
import { Info } from 'lucide-react'

import { COUNTS, DEFAULTS, type Row, SORTS, type SortKey, WEIGHT_BLIND } from './rows'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { t, tn } from '../../i18n/scope/system'

const SORT_KEY = 'sp-files-sort'
const COUNT_KEY = 'sp-files-count'
const WEIGHT_KEY = 'sp-files-weight'

/** A stored number, or null when there is none: `Number(null)` is 0, which is a real count and weight. */
function storedNumber(key: string): number | null {
  const raw = readPref(key)
  if (raw === null || raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function useControls() {
  const [sort, setSortRaw] = useState<SortKey>(() => {
    const saved = readPref(SORT_KEY) as SortKey | null
    return saved && (saved === 'original' || SORTS.some(([k]) => k === saved)) ? saved : DEFAULTS.sort
  })
  const [count, setCountRaw] = useState<number>(() => {
    const n = storedNumber(COUNT_KEY)
    return n !== null && COUNTS.includes(n as 10) ? n : DEFAULTS.count
  })
  const [weight, setWeightRaw] = useState<number>(() => {
    const n = storedNumber(WEIGHT_KEY)
    return n !== null && n >= 0 && n <= 10 ? n : DEFAULTS.weight
  })
  const setSort = (v: SortKey) => { setSortRaw(v); persistPref(SORT_KEY, v) }
  const setCount = (v: number) => { setCountRaw(v); persistPref(COUNT_KEY, String(v)) }
  const setWeight = (v: number) => { setWeightRaw(v); persistPref(WEIGHT_KEY, String(v)) }
  return {
    sort, count, weight, setSort, setCount, setWeight,
  }
}

/** The control bar: how they are ordered, how many, and how much now counts. */
export function Controls({
  sort, weight, onSort, onWeight, total, shown,
}: {
  sort: SortKey
  weight: number
  onSort: (v: SortKey) => void
  onWeight: (v: number) => void
  total: number
  shown: number
}) {
  const [info, setInfo] = useState(false)
  const blind = WEIGHT_BLIND[sort]
  const hint = SORTS.find(([k]) => k === sort)?.[2]
    ?? 'Sorted by most changes. Click a button above to sort another way, and click it again to return to this order.'
  return (
    <div className="rounded-card border border-border-subtle bg-surface px-12 py-10 flex flex-col gap-8">
      {/* The orderings wrap inside their own column, so "show" keeps its
          corner however many of them there are. */}
      <div className="flex items-start gap-10">
        <div className="flex-1 min-w-0 flex items-center gap-4 flex-wrap">
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary inline-flex items-center gap-2">
            {t('order by')}
            <button
              type="button"
              onClick={() => setInfo((v) => !v)}
              aria-expanded={info}
              aria-label={t('How to read this')}
              title={t('How to read this')}
              className="inline-flex items-center text-tertiary hover:text-brand"
            >
              <Info size={12} aria-hidden />
            </button>
          </span>
          {SORTS.map(([k, label, why]) => (
            <button
              key={k}
              type="button"
              // Pressing the ordering you are already in puts the list back
              // the way it came — a click has an undo, in the same place.
              onClick={() => onSort(sort === k ? 'original' : k)}
              aria-pressed={sort === k}
              title={sort === k ? `${why}\n\n${t('Click again to return to the default order')}` : why}
              className={`h-20 px-8 rounded-pill text-10 font-mono whitespace-nowrap ${
                sort === k ? 'bg-brand text-on-brand' : 'border border-border-subtle text-tertiary hover:text-primary hover:border-brand'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

      </div>

      <div className="flex items-center gap-8 flex-wrap">
        <label
          className={`flex items-center gap-8 text-10 font-mono text-tertiary ${blind ? 'opacity-45' : ''}`}
          title={blind ? t('The slider does not change this ordering: {why}', { why: blind }) : undefined}
        >
          <span className="uppercase tracking-wide">{t('now counts')}</span>
          <input
            type="range"
            min={0}
            max={10}
            step={1}
            value={weight}
            onChange={(e) => onWeight(Number(e.target.value))}
            className="w-[180px] accent-[var(--brand)]"
            aria-label={t('How much recent work counts')}
          />
          <span className="text-secondary w-[130px]">
            {weight === 0 ? t('all history equally') : weight >= 9 ? t('only the last scan') : t('weight {n}', { n: weight })}
          </span>
        </label>
        {blind && (
          <span className="text-10 font-mono text-status-amber" title={blind}>
            {t('The slider does not affect importance or gone cold')}
          </span>
        )}
        <span className="text-10 font-mono text-tertiary">
          {t('{shown} of {total} files', { shown, total })} · {hint}
        </span>
      </div>

      {info && (
        <div className="rounded-input border border-border-subtle bg-elevated px-10 py-8 flex flex-col gap-3">
          <p className="text-11 text-secondary">
            {t('Every number here comes from the file entries agents posted: the counts, the lines, and the importance they gave each change.')}
          </p>
          <dl className="grid gap-x-10 gap-y-1" style={{ gridTemplateColumns: 'auto 1fr' }}>
            {SORTS.map(([k, label, why]) => (
              <div key={k} className="contents">
                <dt className="text-10 font-mono text-tertiary whitespace-nowrap">{label}</dt>
                <dd className="text-11 text-secondary">{why}</dd>
              </div>
            ))}
          </dl>
          <p className="text-11 text-secondary">
            <strong className="text-primary">{t('now counts')}</strong> {t('sets how much recent work weighs in the order. At the top, recent work comes first; at zero, a month-old change counts as much as one from today. It only reorders files and hides none. It applies to every ordering except importance and gone cold.')}
          </p>
        </div>
      )}
    </div>
  )
}

/** The bar that says what a file gained and lost, in one line. */
export function ChurnBar({ add, del, scale }: { add: number; del: number; scale: number }) {
  const w = (n: number) => `${Math.min(50, (n / Math.max(1, scale)) * 50)}%`
  return (
    <span className="flex items-center h-8 w-full" title={t('+{add} / −{del} lines', { add, del })}>
      <span className="flex-1 flex justify-end">
        <span className="h-6 rounded-l-bar" style={{ width: w(del), backgroundColor: 'var(--status-red)', opacity: 0.65 }} />
      </span>
      <span className="w-px h-8 bg-border-default" aria-hidden />
      <span className="flex-1">
        <span className="h-6 rounded-r-bar block" style={{ width: w(add), backgroundColor: 'var(--status-green)', opacity: 0.65 }} />
      </span>
    </span>
  )
}

/** Touches across the window, oldest to newest. */
export function Spark({ row, entries }: { row: Row; entries: string[] }) {
  const byId = new Map(row.story.map((s) => [s.entry.id, s.cell]))
  const peak = Math.max(1, ...row.story.map((s) => s.cell.count))
  return (
    <span className="inline-flex items-end gap-2 h-12" aria-hidden>
      {entries.map((id) => {
        const c = byId.get(id)
        return (
          <span
            key={id}
            className="w-3 rounded-bar"
            style={{
              height: c ? Math.max(2, (c.count / peak) * 12) : 1,
              backgroundColor: c ? 'var(--brand)' : 'var(--border-default)',
              opacity: c ? 0.85 : 0.6,
            }}
          />
        )
      })}
    </span>
  )
}

/** What the agent wrote, which is the part worth reading. */
export function Why({ row, limit = 3 }: { row: Row; limit?: number }) {
  const told = row.story.filter((s) => s.cell.why)
  if (told.length === 0) return <span className="text-11 text-tertiary italic">{t('No note for this file.')}</span>
  return (
    <div className="flex flex-col gap-3">
      {told.slice(0, limit).map(({ entry, cell }) => (
        <div key={entry.id} className="flex gap-8">
          <span className="text-10 font-mono text-tertiary shrink-0 w-[52px]" style={{ fontSize: 9 }}>{entry.date}</span>
          <span className="text-11 text-secondary leading-snug">{cell.why}</span>
        </div>
      ))}
      {told.length > limit && (
        <span className="text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>
          {tn(told.length - limit, '{n} earlier note', '{n} earlier notes')}
        </span>
      )}
    </div>
  )
}

/**
 * Importance as a bar, not just a number. The score is the agent's own
 * judgment of the change, so it is worth as much room as the line counts.
 */
export function Importance({ score, width = 42 }: { score?: number; width?: number }) {
  const n = Math.max(0, Math.min(100, score ?? 0))
  return (
    <span
      className="inline-flex items-center gap-4"
      title={t('Importance {n}, as the agent rated this change', { n })}
    >
      <span className="rounded-pill bg-elevated overflow-hidden" style={{ width, height: 4 }}>
        <span
          className="block h-full rounded-pill"
          style={{ width: `${n}%`, backgroundColor: n >= 60 ? 'var(--status-amber)' : 'var(--brand)', opacity: 0.85 }}
        />
      </span>
      <span className="text-10 font-mono text-tertiary tabular">{n}</span>
    </span>
  )
}

/** How many files to draw. Lives beside whatever row has the room. */
export function CountSwitch({ count, onCount }: { count: number; onCount: (v: number) => void }) {
  return (
    <span className="inline-flex items-center gap-6">
      <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('show')}</span>
      <Segmented label={t('Show')} shape="pill" value={String(count)} onChange={(v) => onCount(Number(v))}
        options={COUNTS.map((n) => [String(n), n === 0 ? t('all') : String(n), n === 0 ? t('Every file') : t('The first {n} in this order', { n })] as const)} />
    </span>
  )
}
