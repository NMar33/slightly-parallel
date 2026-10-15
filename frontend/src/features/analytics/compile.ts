/**
 * Two ways to write a query without SQL, both compiled to SQL.
 *
 * The pipeline — one line, steps joined by `|`, read left to right:
 *
 *   messages | last 30d | where commands like '%vision%' | by agent_name | count | top 10
 *
 *   <table>                   messages · chats · tasks · task_events
 *   last 7d · last 12w        the table's own clock (sent_at, started, created, changed_at)
 *   where <condition>         any SQL condition on the table's columns
 *   by <col>[, <col>]         group; `by day` · `by week` · `by month` bucket the clock
 *   count · sum <col> · avg <col> · median <col> · min <col> · max <col>
 *                             measures, comma-separated; `count distinct <col>` too
 *   top <n> · sort <col> [asc] · limit <n>
 *
 * The builder — the same query as a form (Spec), compiled the same way.
 */

import { TIME_COLUMN } from './data'

import { t } from '../../i18n/scope/views'
interface Spec {
  table: string
  period: number | null          // days back on the table's clock
  where: string[]                // SQL conditions, ANDed
  by: string[]                   // columns, or day/week/month
  measures: string[]             // count · sum:col · avg:col · median:col · min:col · max:col · distinct:col
  sort: { by: string; desc: boolean } | null
  limit: number | null
  /** `as line · bars · table · number · grid`: how to draw it, when the shape alone would not say. */
  view?: View | null
}

type View = 'line' | 'bars' | 'table' | 'number' | 'grid'
export const VIEWS: View[] = ['line', 'bars', 'table', 'number', 'grid']

export const BUCKETS = ['hour', 'day', 'week', 'month'] as const
const AGG = ['sum', 'avg', 'median', 'min', 'max'] as const

const ident = (s: string) => /^[a-z_][a-z0-9_]*$/i.test(s)

/** Buckets a table already has as columns: used as they are, so an alias never shadows one. */
const OWN: Record<string, string[]> = { messages: ['day', 'hour'], chats: ['day'] }

function groupExpr(table: string, col: string): [string, string] {
  const tv = TIME_COLUMN[table] ?? 'day'
  if (OWN[table]?.includes(col)) return [col, col]
  if (col === 'hour') return [`hour(${tv})`, 'hour']
  if (col === 'day' || col === 'week' || col === 'month') return [`date_trunc('${col}', ${tv})`, col]
  return [col, col]
}

function measureExpr(m: string): [string, string] {
  if (m === 'count') return ['count(*)', 'count']
  const [fn, col] = m.split(':')
  if (fn === 'distinct') return [`count(DISTINCT ${col})`, `distinct_${col}`]
  if (fn === 'avg' || fn === 'median') return [`round(${fn}(${col}), 2)`, `${fn}_${col}`]
  return [`${fn}(${col})`, `${fn}_${col}`]
}

/** Only one project's rows: the table read through a filter, under its own name. */
function scoped(table: string, project: string): string {
  const p = project.replace(/'/g, "''")
  if (table === 'task_events') return `(SELECT * FROM task_events WHERE task_id IN (SELECT id FROM tasks WHERE project = '${p}')) AS task_events`
  return `(SELECT * FROM ${table} WHERE project = '${p}') AS ${table}`
}

export function toSql(s: Spec, project = ''): string {
  const where = [...s.where.filter((w) => w.trim())]
  if (s.period != null) where.unshift(`${TIME_COLUMN[s.table] ?? 'day'} >= current_date - ${Math.round(s.period)}`)
  const groups = s.by.map((b) => groupExpr(s.table, b))
  const measures = (s.measures.length ? s.measures : groups.length ? ['count'] : []).map(measureExpr)
  const select = groups.length || measures.length
    ? [...groups.map(([e, a]) => (e === a ? e : `${e} AS ${a}`)), ...measures.map(([e, a]) => `${e} AS ${a}`)]
    : ['*']
  let sql = `SELECT ${select.join(', ')}\nFROM ${project ? scoped(s.table, project) : s.table}`
  if (where.length) sql += `\nWHERE ${where.join('\n  AND ')}`
  if (groups.length && measures.length) sql += `\nGROUP BY ${groups.map((_, i) => i + 1).join(', ')}`
  // A weekday reads Monday to Sunday, not by its count.
  if (!s.sort && groups[0]?.[1] === 'weekday') {
    sql += "\nORDER BY list_position(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], weekday)"
    return s.limit != null ? `${sql}\nLIMIT ${Math.round(s.limit)}` : sql
  }
  const sortBy = s.sort?.by ?? (groups.length && groups.some(([e]) => e.startsWith('date_trunc') || e.startsWith('hour')) ? groups[0]![1] : measures[0]?.[1])
  if (sortBy) {
    const timeGroup = groups.some(([e, a]) => a === sortBy && (e.startsWith('date_trunc') || e.startsWith('hour'))) || sortBy === 'hour'
    const desc = s.sort ? s.sort.desc : !timeGroup
    sql += `\nORDER BY ${sortBy}${desc ? ' DESC' : ''}`
  }
  if (s.limit != null) sql += `\nLIMIT ${Math.round(s.limit)}`
  else if (!groups.length && !measures.length) sql += '\nLIMIT 200'
  return sql
}

export function parsePipeline(text: string, tables: string[]): { spec: Spec | null; error: string } {
  const steps = text.split('|').map((x) => x.trim()).filter(Boolean)
  if (!steps.length) return { spec: null, error: '' }
  const table = steps[0]!.toLowerCase()
  if (!tables.includes(table)) return { spec: null, error: t('Start with a table: {v}.', { v: tables.join(', ') }) }
  const spec: Spec = { table, period: null, where: [], by: [], measures: [], sort: null, limit: null }
  for (const step of steps.slice(1)) {
    const [head, ...rest] = step.split(/\s+/)
    const arg = rest.join(' ').trim()
    const h = head!.toLowerCase().replace(/,$/, '')
    if (h === 'last') {
      const m = /^(\d+)\s*([dwm]?)$/i.exec(arg)
      if (!m) return { spec, error: t('"last" needs a span, like 30d, 12w or 6m.') }
      spec.period = Number(m[1]) * ({ d: 1, w: 7, m: 30 }[(m[2] || 'd').toLowerCase() as 'd' | 'w' | 'm'])
    } else if (h === 'where') {
      if (!arg) return { spec, error: t('"where" needs a condition, like words > 50.') }
      spec.where.push(arg)
    } else if (h === 'by') {
      const cols = arg.split(',').map((x) => x.trim()).filter(Boolean)
      if (!cols.length || !cols.every(ident)) return { spec, error: t('"by" needs column names, or day / week / month.') }
      spec.by.push(...cols)
    } else if (h === 'count' || AGG.includes(h as (typeof AGG)[number])) {
      for (const part of step.split(',').map((x) => x.trim()).filter(Boolean)) {
        const [f, ...c] = part.split(/\s+/)
        const fn = f!.toLowerCase()
        if (fn === 'count' && !c.length) spec.measures.push('count')
        else if (fn === 'count' && c[0]?.toLowerCase() === 'distinct' && c[1] && ident(c[1])) spec.measures.push(`distinct:${c[1]}`)
        else if (AGG.includes(fn as (typeof AGG)[number]) && c[0] && ident(c[0])) spec.measures.push(`${fn}:${c[0]}`)
        else return { spec, error: t('Measures are count, count distinct <col>, sum / avg / median / min / max <col>.') }
      }
    } else if (h === 'top') {
      const n = Number(arg || 10)
      if (!Number.isFinite(n)) return { spec, error: t('"top" needs a number.') }
      spec.limit = n
      spec.sort = null
    } else if (h === 'sort') {
      const [c, dir] = arg.split(/\s+/)
      if (!c || !ident(c)) return { spec, error: t('"sort" needs a column: sort messages, sort day asc.') }
      spec.sort = { by: c, desc: (dir ?? 'desc').toLowerCase() !== 'asc' }
    } else if (h === 'as') {
      if (!VIEWS.includes(arg as View)) return { spec, error: t('"as" takes one of: {v}.', { v: VIEWS.join(', ') }) }
      spec.view = arg as View
    } else if (h === 'limit') {
      const n = Number(arg)
      if (!Number.isFinite(n)) return { spec, error: t('"limit" needs a number.') }
      spec.limit = n
    } else {
      return { spec, error: t('"{head}" is not a step. Steps: last, where, by, count / sum / avg …, top, sort, limit, as.', { head }) }
    }
  }
  return { spec, error: '' }
}

/** The examples, by the question they answer. */
export const EXAMPLE_GROUPS: Array<{ group: string; items: Array<{ q: string; line: string }> }> = [
  { group: t('Your activity'), items: [
    { q: t('Messages a day, this month'), line: 'messages | last 30d | by day | count' },
    { q: t('Messages by hour of the day'), line: 'messages | by hour | count' },
    { q: t('Messages by day of the week'), line: 'messages | by weekday | count' },
    { q: t('The week as a heatmap'), line: 'messages | last 90d | by weekday, hour | count | as grid' },
    { q: t('How much I write, a week'), line: 'messages | by week | sum words, sum pasted_words' },
    { q: t('Long messages (over 150 words)'), line: 'messages | where words > 150 | by week | count' },
    { q: t('The busiest days ever'), line: "messages | by day | count | top 10" },
    { q: t('Messages a month'), line: "messages | by month | count" },
    { q: t('Late nights (22:00–05:00)'), line: "messages | where hour >= 22 or hour < 5 | by week | count" },
    { q: 'Weekends', line: "messages | where weekday in ('Sat', 'Sun') | by week | count" },
  ] },
  { group: 'Agents', items: [
    { q: t('The busiest agents'), line: 'messages | last 90d | by agent_name | count, sum answer_words | top 10' },
    { q: t('Who answers at length'), line: 'messages | by agent_name | avg answer_words | top 10' },
    { q: t('Agents at work, a week'), line: 'messages | by week | count distinct agent_id' },
    { q: t('Chats per agent'), line: 'chats | by agent_name | count, sum minutes | top 12' },
    { q: t('Agents this week'), line: "messages | last 7d | by agent_name | count" },
    { q: t('How long the answers are, by agent'), line: "messages | by agent_name | median answer_words | top 10" },
    { q: t('Agents per project'), line: "chats | by project | count distinct agent_id" },
    { q: t('Agents across the week'), line: "messages | last 14d | by agent_name, weekday | count | as grid" },
  ] },
  { group: t('Commands and tasks in chats'), items: [
    { q: t('The commands I use'), line: "messages | where commands <> '' | by commands | count | top 12" },
    { q: t('Messages that name a task, a week'), line: 'messages | where has_task | by week | count' },
    { q: t('Chats, a week, and how long'), line: 'chats | last 90d | by week | count, avg minutes' },
    { q: t('The longest chats'), line: 'chats | sort minutes | limit 15 | as table' },
    { q: t('Visions kept, a week'), line: "messages | where commands like '%vision%' | by week | count" },
    { q: t('#done in the chats'), line: "messages | where commands like '%done%' | by day | count" },
    { q: t('Long chats (an hour or more), a week'), line: "chats | where minutes >= 60 | by week | count" },
    { q: t('Messages in a chat, a week'), line: "chats | by week | median messages, max messages" },
    { q: t('Chats a day, this month'), line: "chats | last 30d | by day | count" },
  ] },
  { group: t('Words and pasting'), items: [
    { q: t('Words I type, a week'), line: 'messages | by week | sum words' },
    { q: t('Pasted text, a week'), line: 'messages | where pasted_words > 0 | by week | count, sum pasted_words' },
    { q: t('Words back for each word I type'), line: 'messages | by week | sum answer_words, sum words' },
    { q: t('The longest answers'), line: 'messages | sort answer_words | limit 15 | as table' },
    { q: t('Short messages (under 5 words)'), line: 'messages | where words < 5 | by week | count' },
  ] },
  { group: 'Tasks', items: [
    { q: t('Tasks finished a week'), line: 'tasks | where done_at is not null | by week | count, median lead_hours' },
    { q: t('Where the tasks are'), line: 'tasks | by status | count' },
    { q: t('What a finished task takes'), line: "tasks | where status = 'done' | median messages, median minutes, median commits | as table" },
    { q: t('The heaviest tasks'), line: 'tasks | sort messages | limit 15 | as table' },
    { q: t('Closed with #done, or on the board'), line: "tasks | where done_at is not null | by closed | count" },
    { q: t('Tasks created a week'), line: "tasks | by week | count" },
    { q: t('Open tasks, by priority'), line: "tasks | where status not in ('done', 'done-archived') | by priority | count" },
    { q: t('Tasks by assignee'), line: "tasks | by assignee | count | top 10" },
    { q: t('Reopened tasks'), line: "tasks | where reopened > 0 | sort reopened | as table" },
    { q: t('Commits a finished task, a week'), line: "tasks | where done_at is not null | by week | median commits" },
    { q: t('Tasks never worked in a chat'), line: "tasks | where stretch = 'none' | by status | count" },
    { q: t('Waiting longest (open)'), line: "tasks | where done_at is null | sort created asc | limit 15 | as table" },
  ] },
  { group: t('The board'), items: [
    { q: t('Moves this month, by new status'), line: "task_events | last 30d | where field = 'status' | by new_value | count" },
    { q: t('Who changes the board'), line: 'task_events | by actor | count | top 10' },
    { q: t('Board activity, a day'), line: 'task_events | last 30d | by day | count' },
    { q: t('What changes most on a card'), line: "task_events | by field | count | top 10" },
    { q: t('Board changes by hour'), line: "task_events | by hour | count" },
    { q: t('Agents saying done, a week'), line: "task_events | where field = 'agent_report' | by week | count" },
    { q: t('Moves to done, a week'), line: "task_events | where field = 'status' and new_value = 'done' | by week | count" },
  ] },
]
