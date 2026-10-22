/**
 * The week workbench's own arithmetic: the strip's range, the order items
 * take inside a day column, and the tally line. Pure, so it is testable
 * without a browser; the page is layout.
 */
import { addDays, daysBetween, eachDay, startOfWeek, type CalendarPayload, type DayItem, type DayFacts, EMPTY_FACTS } from '../model'

import { t } from '../../../i18n/scope/views'
/** Eight Monday-first weeks: six before the shown week, the week, the next. */
const STRIP_WEEKS = 8

export function stripRange(week: string): { from: string; to: string; weeks: string[] } {
  const from = addDays(week, -(STRIP_WEEKS - 2) * 7)
  const to = addDays(week, 13)
  const weeks = Array.from({ length: STRIP_WEEKS }, (_, i) => addDays(from, i * 7))
  return { from, to, weeks }
}

/** Milestones first, then entries with a time by the clock, entries without,
 *  then tasks in the shared order (due · planned · done · comebacks · created). */
export function orderDayItems(items: DayItem[]): DayItem[] {
  const rank = (it: DayItem): [number, string] => {
    if (it.kind === 'milestone') return [0, '']
    if (it.kind === 'entry') return it.entry.time ? [1, it.entry.time] : [2, it.entry.title]
    return [3, '']
  }
  return items
    .map((it, i) => ({ it, i, r: rank(it) }))
    .sort((a, b) => a.r[0] - b.r[0] || (a.r[0] < 3 ? a.r[1].localeCompare(b.r[1]) : 0) || a.i - b.i)
    .map((x) => x.it)
}

/** "this week · 5 due · 2 entries · 3 chats/day" from the week's days. */
export function weekTally(p: Pick<CalendarPayload, 'days' | 'tasks' | 'entries'> | undefined, week: string, today: string): string {
  if (!p) return ''
  const days = eachDay(week, addDays(week, 6))
  const set = new Set(days)
  const due = p.tasks.filter((it) => set.has(it.due) && it.status !== 'done' && it.status !== 'done-archived').length
  const entries = p.entries.filter((e) => days.some((d) => e.date <= d && d <= (e.end_date || e.date))).length
  const sessions = days.reduce((n, d) => n + (p.days[d]?.sessions ?? 0), 0)
  const label = set.has(today) ? t('this week') : today < week ? t('a week ahead') : t('a past week')
  const parts = [label, `${due} due`, `${entries} ${entries === 1 ? 'entry' : 'entries'}`]
  if (sessions) parts.push(`${Math.round((sessions / 7) * 10) / 10} chats/day`)
  return parts.join(' · ')
}

/** The day's numbers as rows, only the ones with a value. */
export function factRows(f: DayFacts = EMPTY_FACTS): Array<[string, string]> {
  const rows: Array<[string, number | string]> = [
    ['chats', f.sessions], ['turns', f.turns], ['minutes', f.minutes], ['commits', f.commits],
    ['lines', f.add || f.del ? `+${f.add} −${f.del}` : 0], [t('hours logged'), f.hours_min ? `${Math.round(f.hours_min / 6) / 10}h` : 0],
    ['done', f.tasks_done], ['written', f.tasks_created], ['checkpoints', f.standups + f.decisions + f.scans],
    ['problems', f.problems],
  ]
  return rows.filter(([, v]) => v !== 0 && v !== '').map(([k, v]) => [k, String(v)])
}

/**
 * The picked day after the week moves to `monday`: the same weekday in the
 * new week. The pane beside the week reads the loaded range, so a pick
 * left behind in a week the range no longer holds would read as empty.
 */
export function pickInWeek(sel: string, monday: string): string {
  return addDays(monday, daysBetween(startOfWeek(sel), sel))
}
