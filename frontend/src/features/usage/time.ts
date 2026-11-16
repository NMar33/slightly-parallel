import { t } from '../../i18n/scope/system'

/**
 * The clock words of the limits: when a window resets, how long until
 * then, and where an even pace would put the bar. Times on the wire are
 * local ISO seconds ("2026-11-01T16:40:00").
 */

function parse(iso: string): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

const pad = (n: number) => String(n).padStart(2, '0')

/** "16:40" — the time of day of a stamp. */
export function clock(iso: string): string {
  const d = parse(iso)
  return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : '—'
}

export function isPast(iso: string, now: Date): boolean {
  const d = parse(iso)
  return !!d && d.getTime() <= now.getTime()
}

/** The time of a stamp, with the weekday when it is another day than now or
 *  when `weekday` asks for it: "16:40", "Thu 09:00" (the server's _clock rule). */
export function whenText(iso: string, now: Date, lang = 'en-GB', weekday = false): string {
  const d = parse(iso)
  if (!d) return '—'
  return !weekday && d.toDateString() === now.toDateString() ? clock(iso) : `${d.toLocaleDateString(lang, { weekday: 'short' })} ${clock(iso)}`
}

/** "resets 16:40 · in 1 h 52 min"; "resets Thu 09:00" when there is no "in".
 *  `left` and `when` are the server's words, shown as given. */
export function resetText(iso: string, now: Date, lang = 'en-GB', left?: string, when?: string): string {
  if (!parse(iso)) return '—'
  const at = when || whenText(iso, now, lang)
  return left ? t('resets {when} · in {left}', { when: at, left }) : t('resets {when}', { when: at })
}

/** Where the bar would be if the plan were used evenly: time passed ÷ window, 0–1. */
export function evenPace(resetsAt: string, spanSeconds: number, now: Date): number | null {
  const d = parse(resetsAt)
  if (!d || spanSeconds <= 0) return null
  const start = d.getTime() - spanSeconds * 1000
  const f = (now.getTime() - start) / (spanSeconds * 1000)
  return Math.max(0, Math.min(1, f))
}

/** "Sun 1 Nov". */
export function dayWord(d: Date, lang = 'en-GB'): string {
  return d.toLocaleDateString(lang, { weekday: 'short', day: 'numeric', month: 'short' })
}

/** "31 Oct" from a stamp. */
export function shortDate(iso: string, lang = 'en-GB'): string {
  const d = parse(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return d ? d.toLocaleDateString(lang, { day: 'numeric', month: 'short' }) : iso
}
