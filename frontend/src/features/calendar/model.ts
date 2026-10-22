import { hm } from '../../utils/format'
import { t, tn } from '../../i18n/scope/views'
import { monthLong, monthShort, weekdayShort } from '../../lib/months'
/**
 * The calendar's model — shared by every variant.
 *
 * Variants differ in how they lay the axis out (a month, a week, a line),
 * never in what a day holds. So the types, the date arithmetic, the layers
 * a page can switch, the lenses that narrow the tasks, and the quick-add
 * parser live here once. Dates are ISO strings (YYYY-MM-DD) in local time
 * everywhere on the client; the server already normalised the ledgers.
 */

// ---------------------------------------------------------------------------
// Payload
// ---------------------------------------------------------------------------

export interface DayFacts {
  tasks_created: number
  tasks_done: number
  sessions: number
  turns: number
  minutes: number
  commits: number
  files: number
  add: number
  del: number
  hours_min: number
  standups: number
  decisions: number
  scans: number
  problems: number
  entries: number
}

export interface CalTask {
  id: string
  title: string
  project: string
  status: string
  priority: string
  assignee: string
  created: string
  due: string
  planned: string
  resurface: string
  done: string
  archived: boolean
  sprint_id: string
  milestone_id: string
  tags: string
}

export type EntryKind = 'meeting' | 'deadline' | 'reminder' | 'note' | 'event'
type EntryStatus = 'open' | 'done' | 'cancelled'
export const ENTRY_KINDS: EntryKind[] = ['meeting', 'deadline', 'reminder', 'note', 'event']

export interface CalEntry {
  id: string
  project: string
  kind: EntryKind
  date: string
  time: string
  end_date: string
  end_time: string
  title: string
  body: string
  task_id: string
  milestone_id: string
  people: string
  link: string
  status: EntryStatus
  created_at: string
  updated_at: string
  actor: string
  source: 'calendar'
}

type MilestoneStatus = 'planned' | 'active' | 'reached' | 'dropped'
export const MILESTONE_STATUSES: MilestoneStatus[] = ['planned', 'active', 'reached', 'dropped']

export interface Milestone {
  id: string
  project: string
  title: string
  outcome: string
  check: string
  target_date: string
  reached_date: string
  status: MilestoneStatus
  position: number
  /** What shows a reached milestone is true: a link, a number, a line. */
  proof: string
  tasks: string[]
  tasks_n: number
  done_n: number
  first_task: string
  last_done: string
}

export interface CalSprint {
  id: string
  name: string
  status: string
  started: string
  ended: string
  bet_days: number | null
}

export interface CalSession {
  id: string
  project: string
  agent_id: string
  date: string
  start: string
  end: string
  minutes: number
  turns: number
  l1: string
  git: { commits: number; files: number; add: number; del: number }
}

export interface CalendarPayload {
  project: string
  /** The codes that were read: one, a board's members, or every project. */
  projects: string[]
  from: string
  to: string
  today: string
  days: Record<string, DayFacts>
  tasks: CalTask[]
  entries: CalEntry[]
  milestones: Milestone[]
  sprints: CalSprint[]
  sessions: CalSession[]
}

export const EMPTY_FACTS: DayFacts = {
  tasks_created: 0, tasks_done: 0, sessions: 0, turns: 0, minutes: 0, commits: 0, files: 0,
  add: 0, del: 0, hours_min: 0, standups: 0, decisions: 0, scans: 0, problems: 0, entries: 0,
}

// ---------------------------------------------------------------------------
// Dates — ISO strings, local time, Monday weeks
// ---------------------------------------------------------------------------

const DAY_MS = 86_400_000

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function isoToday(now: Date = new Date()): string {
  return isoOf(now)
}
export function dateOf(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y!, (m ?? 1) - 1, d ?? 1)
}
export function addDays(iso: string, n: number): string {
  const d = dateOf(iso)
  d.setDate(d.getDate() + n)
  return isoOf(d)
}
export function daysBetween(a: string, b: string): number {
  return Math.round((dateOf(b).getTime() - dateOf(a).getTime()) / DAY_MS)
}
/** Monday of the week the day is in. */
export function startOfWeek(iso: string): string {
  const d = dateOf(iso)
  const shift = (d.getDay() + 6) % 7
  return addDays(iso, -shift)
}
export function monthOf(iso: string): string {
  return iso.slice(0, 7)
}
export function firstOfMonth(month: string): string {
  return `${month}-01`
}
export function lastOfMonth(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return isoOf(new Date(y!, m!, 0))
}
export function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y!, m! - 1 + n, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
/** Six Monday-first weeks that cover the month, every cell an ISO day. */
export function monthGrid(month: string): string[][] {
  const start = startOfWeek(firstOfMonth(month))
  const weeks: string[][] = []
  for (let w = 0; w < 6; w++) {
    weeks.push(Array.from({ length: 7 }, (_, i) => addDays(start, w * 7 + i)))
  }
  // Drop trailing weeks that lie wholly in the next month (a February
  // starting on a Monday needs four).
  while (weeks.length > 4 && monthOf(weeks[weeks.length - 1]![0]!) !== month) weeks.pop()
  return weeks
}
export function eachDay(from: string, to: string): string[] {
  const n = Math.max(0, daysBetween(from, to))
  return Array.from({ length: n + 1 }, (_, i) => addDays(from, i))
}

/** ISO → Slightly Parallel's YYMM-DD (the task window's due-date form). Anything
 *  already in that form, or empty, passes through. */
export function toSpDate(iso: string): string {
  const s = (iso || '').trim()
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s.slice(2, 4)}${s.slice(5, 7)}-${s.slice(8, 10)}` : s
}

const MONTHS = Array.from({ length: 12 }, (_, i) => monthLong(i))
const MONTHS_SHORT = Array.from({ length: 12 }, (_, i) => monthShort(i))
export const WEEKDAYS = Array.from({ length: 7 }, (_, i) => weekdayShort(i))

export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTHS[m! - 1]} ${y}`
}
/** "Wed 10 Sep" — the day as a person says it. */
export function dayLabel(iso: string, withMonth = true): string {
  const d = dateOf(iso)
  const wd = WEEKDAYS[(d.getDay() + 6) % 7]
  return withMonth ? `${wd} ${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}` : `${wd} ${d.getDate()}`
}
export function shortDate(iso: string): string {
  if (!iso) return ''
  const d = dateOf(iso)
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`
}
/** "today", "tomorrow", "in 3 days", "yesterday", "12 days ago", or the date. */
export function relativeDay(iso: string, today: string): string {
  const n = daysBetween(today, iso)
  if (n === 0) return t('today')
  if (n === 1) return t('tomorrow')
  if (n === -1) return t('yesterday')
  if (n > 1 && n <= 14) return t('in {n} days', { n })
  if (n < -1 && n >= -14) return t('{v} days ago', { v: -n })
  return shortDate(iso)
}

// ---------------------------------------------------------------------------
// Layers — what a page draws; every variant offers the same set
// ---------------------------------------------------------------------------

export type Layer = 'due' | 'planned' | 'done' | 'created' | 'resurface' | 'entries' | 'milestones' | 'sprints' | 'facts'

export const LAYERS: Array<{ key: Layer; label: string; hint: string; color: string }> = [
  { key: 'due', label: t('due'), hint: t('tasks on the day they are due'), color: 'var(--status-amber)' },
  { key: 'planned', label: t('planned'), hint: t('tasks on the day they were planned for'), color: 'var(--brand)' },
  { key: 'done', label: t('done'), hint: t('tasks on the day they became done'), color: 'var(--status-green)' },
  { key: 'created', label: t('created'), hint: t('tasks on the day they were created'), color: 'var(--status-neutral)' },
  { key: 'resurface', label: t('returns'), hint: t('tasks on the day they return to the board'), color: 'var(--status-purple)' },
  { key: 'entries', label: t('entries'), hint: t('meetings, deadlines, reminders, notes, events'), color: 'var(--status-info)' },
  { key: 'milestones', label: t('milestones'), hint: t('outcomes on their target day'), color: 'var(--status-red)' },
  { key: 'sprints', label: t('sprints'), hint: t('sprints as bands across their days'), color: 'var(--brand-glow)' },
  { key: 'facts', label: t('work'), hint: t('chats, commits, lines and hours for each day'), color: 'var(--text-tertiary)' },
]
const DEFAULT_LAYERS: Layer[] = ['due', 'planned', 'done', 'entries', 'milestones', 'sprints', 'facts']
export const LAYER_COLOR: Record<Layer, string> = Object.fromEntries(LAYERS.map((l) => [l.key, l.color])) as Record<Layer, string>

export const KIND_COLOR: Record<EntryKind, string> = {
  meeting: 'var(--status-info)',
  deadline: 'var(--status-red)',
  reminder: 'var(--status-amber)',
  note: 'var(--status-neutral)',
  event: 'var(--status-purple)',
}
export const KIND_GLYPH: Record<EntryKind, string> = {
  meeting: '◉', deadline: '▲', reminder: '◔', note: '▪', event: '◆',
}

export function parseLayers(raw: string | undefined): Layer[] {
  if (raw === undefined) return DEFAULT_LAYERS
  const known = new Set(LAYERS.map((l) => l.key))
  return raw.split(',').map((s) => s.trim()).filter((s): s is Layer => known.has(s as Layer))
}
export function serializeLayers(layers: Layer[]): string {
  const same = layers.length === DEFAULT_LAYERS.length && DEFAULT_LAYERS.every((l) => layers.includes(l))
  return same ? '' : layers.join(',')
}

// ---------------------------------------------------------------------------
// Lenses — named narrowings of the task set
// ---------------------------------------------------------------------------

export type Lens = 'all' | 'open' | 'done' | 'overdue' | 'slipped' | 'old' | 'agent' | 'mine' | 'undated'

export const isDone = (it: CalTask): boolean => it.status === 'done' || it.status === 'done-archived'

export const LENSES: Array<{ key: Lens; label: string; hint: string; test: (it: CalTask, today: string) => boolean }> = [
  { key: 'all', label: t('all'), hint: t('every task of the project'), test: () => true },
  { key: 'open', label: t('open'), hint: t('not done'), test: (it) => !isDone(it) && !it.archived },
  { key: 'done', label: t('done'), hint: t('done, on the day it happened'), test: (it) => isDone(it) },
  { key: 'overdue', label: t('overdue'), hint: t('due before today and still open'), test: (it, today) => !isDone(it) && !!it.due && it.due < today },
  { key: 'slipped', label: t('slipped'), hint: t('planned for a day that passed, still open'), test: (it, today) => !isDone(it) && !!it.planned && it.planned < today },
  { key: 'old', label: t('old'), hint: t('open and written more than 30 days ago'), test: (it, today) => !isDone(it) && !it.archived && !!it.created && daysBetween(it.created, today) > 30 },
  { key: 'agent', label: t('agent\'s'), hint: t('in the agent column'), test: (it) => it.status === 'agent' },
  { key: 'undated', label: t('undated'), hint: t('Open tasks with no due date.'), test: (it) => !isDone(it) && !it.archived && !it.due },
  { key: 'mine', label: t('todo'), hint: t('todo · doing · review'), test: (it) => ['todo', 'doing', 'review', 'next'].includes(it.status) },
]

export function applyLens(tasks: CalTask[], lens: Lens, today: string, q = ''): CalTask[] {
  const test = LENSES.find((l) => l.key === lens)?.test ?? (() => true)
  const needle = q.trim().toLowerCase()
  return tasks.filter((it) => test(it, today) && (!needle || `${it.title} ${it.tags} ${it.assignee} ${it.id}`.toLowerCase().includes(needle)))
}

// ---------------------------------------------------------------------------
// What a day holds
// ---------------------------------------------------------------------------

export type Why = 'due' | 'planned' | 'done' | 'created' | 'resurface'

export type DayItem =
  | { kind: 'task'; why: Why; task: CalTask; id: string; title: string }
  | { kind: 'entry'; entry: CalEntry; id: string; title: string }
  | { kind: 'milestone'; milestone: Milestone; id: string; title: string }

const WHY_FIELD: Record<Why, keyof CalTask> = { due: 'due', planned: 'planned', done: 'done', created: 'created', resurface: 'resurface' }
const WHY_ORDER: Why[] = ['due', 'planned', 'done', 'resurface', 'created']

/** Everything drawn on one day, foreground only, in reading order:
 *  milestones, timed entries, then tasks by why. A task on a day for two
 *  reasons shows once, under the first reason that applies. */
export function itemsOn(p: Pick<CalendarPayload, 'tasks' | 'entries' | 'milestones'>, iso: string, layers: Layer[], tasks: CalTask[] = p.tasks): DayItem[] {
  const out: DayItem[] = []
  if (layers.includes('milestones')) {
    for (const m of p.milestones) {
      if (m.target_date === iso || (m.reached_date === iso && m.status === 'reached')) out.push({ kind: 'milestone', milestone: m, id: m.id, title: m.title })
    }
  }
  if (layers.includes('entries')) {
    for (const e of p.entries) {
      const end = e.end_date || e.date
      if (e.date <= iso && iso <= end) out.push({ kind: 'entry', entry: e, id: e.id, title: e.title })
    }
  }
  const seen = new Set<string>()
  for (const why of WHY_ORDER) {
    if (!layers.includes(why)) continue
    const field = WHY_FIELD[why]
    for (const tv of tasks) {
      if (tv[field] === iso && !seen.has(tv.id)) {
        seen.add(tv.id)
        out.push({ kind: 'task', why, task: tv, id: tv.id, title: tv.title })
      }
    }
  }
  return out
}

/** The whole range at once, keyed by day — cheaper than itemsOn per cell. */
export function itemsByDay(p: Pick<CalendarPayload, 'tasks' | 'entries' | 'milestones'>, from: string, to: string, layers: Layer[], tasks: CalTask[] = p.tasks): Map<string, DayItem[]> {
  const out = new Map<string, DayItem[]>()
  for (const d of eachDay(from, to)) out.set(d, itemsOn(p, d, layers, tasks))
  return out
}

/** Sprints as spans clipped to the range; an open sprint runs to `to`. */
export function sprintSpans(sprints: CalSprint[], from: string, to: string): Array<{ sprint: CalSprint; from: string; to: string; open: boolean }> {
  const out: Array<{ sprint: CalSprint; from: string; to: string; open: boolean }> = []
  for (const s of sprints) {
    if (!s.started) continue
    const end = s.ended || to
    if (end < from || s.started > to) continue
    out.push({ sprint: s, from: s.started < from ? from : s.started, to: end > to ? to : end, open: !s.ended })
  }
  return out
}


/** "3 chats · 41 turns · 12 commits · +812 −40 · 2.5h" — only what is there. */
export function factLine(f: DayFacts): string {
  const parts: string[] = []
  if (f.sessions) parts.push(tn(f.sessions, '{n} chat', '{n} chats'))
  if (f.turns) parts.push(tn(f.turns, '{n} turn', '{n} turns'))
  if (f.commits) parts.push(tn(f.commits, '{n} commit', '{n} commits'))
  if (f.add || f.del) parts.push(`+${f.add} −${f.del}`)
  if (f.hours_min) parts.push(t('{time} logged', { time: hm(f.hours_min) }))
  if (f.tasks_done) parts.push(t('{n} done', { n: f.tasks_done }))
  if (f.tasks_created) parts.push(t('{n} written', { n: f.tasks_created }))
  const checks = f.standups + f.decisions + f.scans
  if (checks) parts.push(tn(checks, '{n} checkpoint', '{n} checkpoints'))
  return parts.join(' · ')
}

// ---------------------------------------------------------------------------
// Quick add — one line becomes an entry, or a task
// ---------------------------------------------------------------------------

export interface Quick {
  kind: EntryKind | 'task'
  title: string
  date: string
  time: string
  end_time: string
}

const WEEKDAY_WORDS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const KIND_WORDS: Array<[RegExp, EntryKind]> = [
  [/\b(meet(ing)?|call|sync|standup|stand-up|1:1|interview|demo|review with|catch-?up)\b/i, 'meeting'],
  [/\b(deadline|due|submit|ship by|release by|hand in|by end of)\b/i, 'deadline'],
  [/\b(remind(er)?|remember|follow[- ]?up|ping|check on)\b/i, 'reminder'],
  [/\b(conference|talk|trip|launch|event|birthday|holiday|offsite)\b/i, 'event'],
]

/**
 * Reads a line the way a person types it: "call with Anna tomorrow 14:00",
 * "deadline: grant form fri", "/task fix the login", "note 2026-09-20 the
 * client renamed the product". The date falls back to the day the line was
 * typed on. What is left after the dates, times and the leading kind word
 * is the title.
 */
export function parseQuick(input: string, base: string): Quick {
  let text = input.trim()
  let kind: Quick['kind'] | null = null
  let date = base
  let time = ''
  let end_time = ''

  // A leading command word sets the kind. It leaves the title when it is
  // part of the sentence ("call with Anna") and goes when it is a label
  // ("deadline: grant form", "/task fix the login", "note …").
  const lead = text.match(/^(\/?)(task|todo|meeting|meet|call|deadline|reminder|remind|note|event)\b(:?)[\s-]*/i)
  if (lead) {
    const w = lead[2]!.toLowerCase()
    kind = w === 'task' || w === 'todo' ? 'task' : w === 'meet' || w === 'call' ? 'meeting' : w === 'remind' ? 'reminder' : (w as EntryKind)
    const label = !!lead[1] || !!lead[3] || ['task', 'todo', 'note', 'reminder', 'remind', 'deadline', 'event'].includes(w)
    if (label) text = text.slice(lead[0].length)
  }

  const times = [...text.matchAll(/\b([01]?\d|2[0-3]):([0-5]\d)\b/g)]
  if (times[0]) {
    time = `${times[0][1]!.padStart(2, '0')}:${times[0][2]}`
    if (times[1]) end_time = `${times[1][1]!.padStart(2, '0')}:${times[1][2]}`
    text = text.replace(/\s*[-–]?\s*\b([01]?\d|2[0-3]):([0-5]\d)\b/g, ' ')
  }

  const isoM = text.match(/\b(\d{4}-\d{2}-\d{2})\b/)
  // A day.month token stands alone and writes the month in two digits
  // (24.09): "release 1.2" and "v2.3.1" are not dates.
  const dotM = text.match(/(?<![\w.])(\d{1,2})\.(\d{2})(?:\.(\d{2,4}))?(?![\w.])/)
  const inM = text.match(/\bin (\d{1,2}) days?\b/i)
  // Full weekday names anywhere; the three-letter forms only lowercase, as
  // a token of their own at the end or after "on" / "next" — "sat with the
  // team" is a sentence, "to Sun" is a name, "grant form fri" is a date.
  const wdM = text.match(new RegExp(`\\b(next |on )?(${WEEKDAY_WORDS.join('|')})\\b`, 'i'))
    ?? text.match(/\b(next |on )(mon|tue|wed|thu|fri|sat|sun)\b/)
    ?? text.match(/\b()(mon|tue|wed|thu|fri|sat|sun)\s*$/)
  let dotDate = ''
  if (dotM) {
    const dd = Number(dotM[1]); const mm = Number(dotM[2])
    const yRaw = dotM[3]; const y = yRaw ? (yRaw.length === 2 ? 2000 + Number(yRaw) : Number(yRaw)) : Number(base.slice(0, 4))
    const built = new Date(y, mm - 1, dd)
    // A real day only: 31.02 rolls over in JS and is not a date here.
    if (built.getDate() === dd && built.getMonth() === mm - 1) dotDate = isoOf(built)
  }
  if (isoM) {
    date = isoM[1]!
    text = text.replace(isoM[0], ' ')
  } else if (dotM && dotDate) {
    date = dotDate
    text = text.replace(dotM[0], ' ')
  } else if (/\btomorrow\b/i.test(text)) {
    date = addDays(base, 1)
    text = text.replace(/\btomorrow\b/i, ' ')
  } else if (/\btoday\b/i.test(text)) {
    text = text.replace(/\btoday\b/i, ' ')
  } else if (inM) {
    date = addDays(base, Number(inM[1]))
    text = text.replace(inM[0], ' ')
  } else if (wdM) {
    const want = WEEKDAY_WORDS.findIndex((w) => w.startsWith(wdM[2]!.toLowerCase().slice(0, 3)))
    const cur = (dateOf(base).getDay() + 6) % 7
    let ahead = (want - cur + 7) % 7
    if (ahead === 0) ahead = 7
    if ((wdM[1] ?? '').trim().toLowerCase() === 'next') ahead += 7
    date = addDays(base, ahead)
    text = text.replace(wdM[0], ' ')
  }

  if (!kind) {
    kind = 'note'
    for (const [re, k] of KIND_WORDS) {
      if (re.test(text)) { kind = k; break }
    }
  }
  const title = text.replace(/\s+/g, ' ').replace(/^[\s:,-]+|[\s:,-]+$/g, '').trim()
  return { kind, title, date, time, end_time }
}
