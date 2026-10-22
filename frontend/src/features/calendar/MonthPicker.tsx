/*
 * The month label as a button that opens a year of months: a far month is
 * two clicks away instead of twelve arrow presses.
 */
import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { FIELD } from '../promptlib/taskstyle'
import { isoToday, monthOf } from './model'

import { t } from '../../i18n/scope/views'
const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * The month label is a button: it opens a small window with the year and
 * its twelve months, so a far month is two clicks away instead of twelve
 * arrow presses. `month` is YYYY-MM; the label is whatever the page shows
 * (a month name, a week's range).
 */
export function MonthPicker({ month, label, onPick, className = '', today }: {
  month: string
  label: string
  onPick: (month: string) => void
  className?: string
  /** Today's month, marked in the grid; defaults to the clock. */
  today?: string
}) {
  const [open, setOpen] = useState(false)
  const [year, setYear] = useState(() => Number(month.slice(0, 4)))
  // The field is typed as text: "20" on the way to "2031" is not a year
  // yet, so the grid follows only a whole four-digit year, and a field
  // left half-typed goes back to the year it shows.
  const [yearText, setYearText] = useState(() => String(year))
  const rootRef = useRef<HTMLDivElement>(null)
  const thisMonth = today ?? monthOf(isoToday())
  useEffect(() => { if (open) setYear(Number(month.slice(0, 4))) }, [open, month])
  useEffect(() => { setYearText(String(year)) }, [year])
  const typeYear = (raw: string) => {
    const v = raw.replace(/\D/g, '').slice(0, 4)
    setYearText(v)
    if (v.length === 4) { const n = Number(v); if (n > 1970 && n < 2200) setYear(n) }
  }
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => {
      // While the picker is open its keys are its own: the page's ← → t
      // must not move the month underneath it.
      if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); return }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 't') e.stopPropagation()
      if (e.key === 'ArrowLeft' && e.shiftKey) setYear((y) => y - 1)
      if (e.key === 'ArrowRight' && e.shiftKey) setYear((y) => y + 1)
    }
    document.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey, true)
    return () => { document.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey, true) }
  }, [open])
  const pick = (m: string) => { onPick(m); setOpen(false) }
  return (
    <div ref={rootRef} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={t('Pick a month or a year')}
        className="inline-flex items-center gap-4 rounded-input px-4 -mx-4 hover:bg-hover text-left"
      >
        {label}
      </button>
      {open && (
        <div role="dialog" aria-label={t('Pick a month')} className="absolute left-0 top-full mt-4 z-40 w-[248px] rounded-card border border-border-default bg-surface shadow-lg p-8 flex flex-col gap-6"
          onKeyDown={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-4">
            <button type="button" onClick={() => setYear((y) => y - 1)} aria-label={t('Previous year')} title={t('Previous year (Shift+←)')} className="h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"><ChevronLeft size={14} aria-hidden /></button>
            <input
              value={yearText}
              onChange={(e) => typeYear(e.target.value)}
              onBlur={() => setYearText(String(year))}
              aria-label={t('Year')}
              inputMode="numeric"
              className={`${FIELD} h-24 py-0 w-[72px] text-center font-semibold text-primary text-13`}
            />
            <button type="button" onClick={() => setYear((y) => y + 1)} aria-label={t('Next year')} title={t('Next year (Shift+→)')} className="h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"><ChevronRight size={14} aria-hidden /></button>
            <button type="button" onClick={() => pick(thisMonth)} className="ml-auto h-24 px-8 rounded-input text-11 font-mono text-tertiary hover:text-primary hover:bg-hover" title={t('This month')}>{t('today')}</button>
          </div>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            {MONTH_SHORT.map((name, i) => {
              const key = `${year}-${String(i + 1).padStart(2, '0')}`
              const on = key === month
              const now = key === thisMonth
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => pick(key)}
                  aria-pressed={on}
                  aria-label={`${name} ${year}`}
                  className={`h-32 rounded-input text-12 font-mono transition-colors ${on ? 'bg-brand text-on-brand' : 'text-secondary hover:text-primary hover:bg-hover'} ${now && !on ? 'ring-1 ring-brand' : ''}`}
                >
                  {name}
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-4 text-10 font-mono text-tertiary px-2">
            {[-1, 0, 1].map((d) => {
              const y = Number(thisMonth.slice(0, 4)) + d
              return <button key={y} type="button" onClick={() => setYear(y)} className={`px-4 h-20 rounded-input hover:bg-hover ${y === year ? 'text-primary' : ''}`}>{y}</button>
            })}
          </div>
        </div>
      )}
    </div>
  )
}
