import { persistPref } from '../../../lib/uiPrefs'
import { normalizeStatus, todayISO, type TaskRow } from './model'
import { t } from '../../../i18n/scope/project'
import { currentLang } from '../../../i18n'

/**
 * Carry-over — what yesterday's plan leaves behind.
 *
 * A card planned for a day carries that date. The Today lane shows only the
 * cards with today's date, so at midnight the plan empties itself and the
 * unfinished cards go quiet in their columns. Nothing is lost — the date is
 * still on them — but nothing tells the operator either. This module finds
 * those cards and remembers, per day, that the operator has been asked.
 */

const SEEN_PREF = 'sp-today-carry-seen'

/** Planned for an earlier day and still open: the cards worth asking about. */
export function leftovers(tasks: TaskRow[], today: string = todayISO()): TaskRow[] {
  return tasks
    .filter((t) => {
      const on = String(t.today_on || '')
      if (!on || on >= today || t.archived_at) return false
      const s = normalizeStatus(t.status)
      return s !== 'done' && s !== 'done-archived'
    })
    .sort((a, b) => (a.today_on! < b.today_on! ? 1 : a.today_on! > b.today_on! ? -1 : 0))
}

const WEEKDAYS = [t('Sunday'), t('Monday'), t('Tuesday'), t('Wednesday'), t('Thursday'), t('Friday'), t('Saturday')]
const MONTHS = [t('Jan'), t('Feb'), t('Mar'), t('Apr'), t('May'), t('Jun'), t('Jul'), t('Aug'), t('Sep'), t('Oct'), t('Nov'), t('Dec')]

function dateOf(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y!, (m ?? 1) - 1, d ?? 1)
}

/** The day a person would name it: "yesterday", "Wednesday", "28 Aug".
 *  A week back the weekday would be today's own name, so it becomes a date. */
export function dayWord(on: string, today: string = todayISO()): string {
  const days = Math.round((dateOf(today).getTime() - dateOf(on).getTime()) / 86_400_000)
  if (days <= 1) return t('yesterday')
  const d = dateOf(on)
  if (currentLang() === 'ru') {
    return days <= 6
      ? d.toLocaleDateString('ru-RU', { weekday: 'long' })
      : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  }
  if (days <= 6) return WEEKDAYS[d.getDay()]!
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`
}

/** The days the leftovers come from, for the window's title. */
export function fromWhen(rows: TaskRow[], today: string = todayISO()): string {
  const days = Array.from(new Set(rows.map((t) => String(t.today_on)))).sort().reverse()
  if (days.length === 0) return ''
  if (days.length === 1) return dayWord(days[0]!, today)
  return t('{day} and earlier', { day: dayWord(days[0]!, today) })
}

export function carrySeenToday(today: string = todayISO()): boolean {
  try { return localStorage.getItem(SEEN_PREF) === today } catch { return false }
}
export function markCarrySeen(today: string = todayISO()): void {
  persistPref(SEEN_PREF, today)
}
