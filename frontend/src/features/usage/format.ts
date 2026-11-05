/**
 * Token counts as the page, the chat viewer and the terminal show them.
 * One rule in Python (backend usagelib.format_tokens) and here, identical:
 *
 *   0–999            → 512
 *   1 000–9 999      → 2.4k   one decimal, ".0" dropped (3k)
 *   10 000–999 999   → 108k   whole k
 *   1M–9.99M         → 4.1M   one decimal
 *   ≥ 10M            → 41M    whole M
 *
 * Each band rounds to the nearest step, a tie goes down, and a value never
 * rounds up into the next band's form: 999 950 is 999k, not 1000k; 9 960 is
 * 9.9k. Integer arithmetic only, so no float lands differently in two languages.
 */

function step(n: number, unit: number, cap: number): number {
  const q = Math.floor(n / unit)
  const r = n - q * unit
  return Math.min(r * 2 > unit ? q + 1 : q, cap)
}

function tenths(q: number): string {
  return q % 10 === 0 ? String(q / 10) : `${Math.floor(q / 10)}.${q % 10}`
}

/** Python's round(): to the nearest integer, a tie to the even one. */
export function roundHalfEven(x: number): number {
  const f = Math.floor(x)
  const d = x - f
  if (d > 0.5) return f + 1
  if (d < 0.5) return f
  return f % 2 === 0 ? f : f + 1
}

export function formatTokens(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value < 0 ? '-' : ''
  const n = Number.isInteger(value) ? Math.abs(value) : roundHalfEven(Math.abs(value))
  if (n < 1_000) return `${sign}${n}`
  if (n < 10_000) return `${sign}${tenths(step(n, 100, 99))}k`
  if (n < 1_000_000) return `${sign}${step(n, 1_000, 999)}k`
  if (n < 10_000_000) return `${sign}${tenths(step(n, 100_000, 99))}M`
  return `${sign}${step(n, 1_000_000, Number.MAX_SAFE_INTEGER)}M`
}

/** The exact count, for tooltips and the detail table: 108,233. */
export function exactTokens(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return Math.round(value).toLocaleString('en-US')
}

/**
 * A fraction 0–1 as a whole percent, the server's rule (usagelib._pct):
 * the nearest whole percent, a tie down, after the float noise is rounded
 * off at six places (0.699 × 100 is 69.9). 0.625 → 62, 0.6251 → 63.
 * 0 or below is 0.
 */
export function pctValue(value: number | null | undefined): number | null {
  if (value == null || typeof value !== 'number' || !Number.isFinite(value)) return null
  if (value <= 0) return 0
  const v = roundHalfEven(value * 100 * 1e6) / 1e6
  const whole = Math.floor(v)
  return v - whole > 0.5 ? whole + 1 : whole
}

/** The same as text: 0.976 → "98%", no value → "—". */
export function pct(value: number | null | undefined): string {
  const v = pctValue(value)
  return v == null ? '—' : `${v}%`
}

/** A share 0–1 as a whole percent (the one percent rule). */
export const sharePct = pct

/**
 * The day against the usual day in whole tenths, the server's rule
 * (usagelib.ratio_tenths): both as whole tokens, value × 10 ÷ usual to the
 * nearest integer, a tie down. null without a usual day. 4.1M against
 * 2.6M → 16 (shown "1.6").
 */
export function ratioTenths(value: number, usual: number | null | undefined): number | null {
  const whole = (x: number | null | undefined) => (typeof x === 'number' && Number.isFinite(x) ? Math.max(0, Math.trunc(x)) : 0)
  const v = whole(value), u = whole(usual)
  if (u <= 0) return null
  const n = v * 10
  const q = Math.floor(n / u)
  return (n - q * u) * 2 > u ? q + 1 : q
}

/** Tenths as text: 16 → "1.6", 20 → "2.0". */
export function tenthsText(q: number): string {
  return `${Math.floor(q / 10)}.${q % 10}`
}

/** cache ÷ (cache + new), rounded as the server rounds it (4 places); null when both are 0. */
export function cacheShare(cache: number, fresh: number): number | null {
  const all = cache + fresh
  return all > 0 ? roundHalfEven((cache / all) * 10_000) / 10_000 : null
}
