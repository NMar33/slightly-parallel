import { useState } from 'react'

import { persistPref, readPref } from '../../lib/uiPrefs'

import { t } from '../../i18n/scope/views'

/**
 * How large a day book's entries read. Standups and scans are read, not
 * scanned, so the size sits in the title row where it is seen, not behind a
 * gear. Five steps from a little smaller to half again as large; each page
 * keeps its own. The size is a zoom on the entries only — the month grid and
 * the title row keep theirs — so type, spacing and charts grow as one piece,
 * the way the interface scale in Appearance grows the whole app.
 */
export const READING_SIZES = [0.9, 1, 1.15, 1.3, 1.5] as const
type ReadingSize = (typeof READING_SIZES)[number]

const DEFAULT: ReadingSize = 1.15

function parse(raw: string | null): ReadingSize {
  const n = Number(raw)
  return (READING_SIZES as readonly number[]).includes(n) ? (n as ReadingSize) : DEFAULT
}

/** The page's reading size and its setter; `page` names the page's own key. */
export function useReadingSize(page: string): [ReadingSize, (n: ReadingSize) => void] {
  const key = `sp-reading-${page}`
  const [size, setSize] = useState<ReadingSize>(() => parse(readPref(key)))
  return [size, (n) => { setSize(n); persistPref(key, String(n)) }]
}

/** Five A's, each a size larger: click one to read the entries at that size. */
export function ReadingSizeControl({ value, onChange }: { value: ReadingSize; onChange: (n: ReadingSize) => void }) {
  const glyph = [10, 11.5, 13, 14.5, 16.5]
  return (
    <div role="radiogroup" aria-label={t('Text size')} title={t('Text size')}
      className="inline-flex items-end h-24 rounded-input border border-border-subtle bg-surface px-2">
      {READING_SIZES.map((s, i) => {
        const on = s === value
        return (
          <button key={s} type="button" role="radio" aria-checked={on}
            aria-label={t('Text size {p}%', { p: Math.round(s * 100) })}
            title={t('Text size {p}%', { p: Math.round(s * 100) })}
            onClick={() => onChange(s)}
            className={`w-20 h-20 mb-1 inline-flex items-center justify-center rounded-input leading-none font-semibold transition-colors ${
              on ? 'text-brand bg-brand/12' : 'text-tertiary hover:text-primary hover:bg-hover'
            }`}
            style={{ fontSize: glyph[i] }}>
            A
          </button>
        )
      })}
    </div>
  )
}
