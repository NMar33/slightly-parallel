import { t } from '../i18n/scope/shell'
/**
 * Small shared number formatters.
 */

/**
 * Format an hour count for compact display:
 *   NaN/±Infinity → "0"
 *   ≥ 100         → rounded integer ("128")
 *   whole numbers → no decimal ("18")
 *   otherwise     → one decimal ("42.5")
 */
export function formatHours(h: number): string {
  if (!Number.isFinite(h)) return '0'
  // Rounded to the decimal shown first: 18.96 is "19", not "19.0", and
  // 99.96 is "100", not "100.0".
  const r = Math.round(h * 10) / 10
  if (Math.abs(r) >= 100) return String(Math.round(h))
  if (r % 1 === 0) return r.toFixed(0)
  return r.toFixed(1)
}

/**
 * A byte count: `512 B`, `1.2 KB`, `48 KB`, `7.8 GB`, `31 GB` — binary
 * units (1 KB = 1024 B, as the system's own tools count), `digits`
 * decimals under 10, none above. "—" when there is no number.
 */
export function bytes(b: number | null | undefined, digits = 1): string {
  if (b == null || !Number.isFinite(b)) return '—'
  const units = [t('B'), t('KB'), t('MB'), t('GB'), t('TB')]
  let v = b, i = 0
  while (Math.abs(v) >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  // What rounds up to the next unit is said in it: 1023.6 KB is "1.0 MB".
  if (Math.round(Math.abs(v)) >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  const fixed = v.toFixed(digits)
  // 9.97 KB rounds to "10.0": over ten there is no decimal.
  return `${i === 0 || Math.abs(Number(fixed)) >= 10 ? Math.round(v) : fixed} ${units[i]}`
}

/** Minutes, compact: `45m`, `1.2h` — for totals in a tight row. `0h` for none. */
export function hm(min: number): string {
  // 59.6 minutes rounds to an hour: "1h", never "60m".
  return min >= 59.5 ? t('{n}h', { n: Math.round(min / 6) / 10 }) : min > 0 ? t('{n}m', { n: Math.round(min) }) : t('{n}h', { n: 0 })
}

/** Minutes on a clock: `45m`, `1h 05m` — never fractional hours. `empty` for none. */
export function hMin(min: number, empty = '—'): string {
  if (!min || min <= 0) return empty
  // Rounded to a whole minute first: split and then rounded, 59.6 read "60m"
  // and 119.7 read "1h 60m".
  const whole = Math.round(min)
  const h = Math.floor(whole / 60)
  const m = whole % 60
  return h === 0 ? t('{n}m', { n: m }) : t('{h}h {m}m', { h, m: String(m).padStart(2, '0') })
}

/** Seconds as words: `40 s`, `12 min`, `1 h 20 min`, `3 days`. */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return t('{n} s', { n: s })
  const m = Math.round(s / 60)
  if (m < 60) return t('{n} min', { n: m })
  const h = Math.floor(m / 60), rest = m % 60
  if (h < 48) return rest ? t('{h} h {m} min', { h, m: rest }) : t('{n} h', { n: h })
  return t('{n} days', { n: Math.round(h / 24) })
}

/** A count with its noun: `1 task`, `3 tasks`. */
export const plural = (n: number, noun: string): string => `${n} ${noun}${n === 1 ? '' : 's'}`

/**
 * How long ago, from the milliseconds gone by: `just now`, `12m ago`,
 * `5h ago`, `3d ago`. Hours turn to days at `daysFromHours` (a day by
 * default; a list that reads better as "30h ago" passes 48).
 */
export function ago(elapsedMs: number, daysFromHours = 24): string {
  const m = Math.round(elapsedMs / 60000)
  if (m < 1) return t('just now')
  if (m < 60) return t('{n}m ago', { n: m })
  const h = Math.round(m / 60)
  return h < daysFromHours ? t('{n}h ago', { n: h }) : t('{n}d ago', { n: Math.round(h / 24) })
}
