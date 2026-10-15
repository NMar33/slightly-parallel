/**
 * The task table itself: every column the Ledger and the statistics had,
 * each one switchable, sortable and totalled; the title column frozen; a
 * row opens its task.
 */

import { TH, TH_BUTTON } from '../../components/ui'
import { memo, useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, Settings2, Star } from 'lucide-react'
import { usePopover } from '../../hooks/usePopover'

import { persistPref, readPref } from '../../lib/uiPrefs'
import { COLOR, norm } from '../project/taskViz'
import { CLOSED_COLOR, hours, median, mins } from '../stats/data'
import { isDone, type Row } from './model'

import { t, tc, tn, locale } from '../../i18n/scope/views'
import { dayMonth } from '../../lib/months'
/* ------------------------------------------------------------- columns */

type Group = 'Task' | 'Time' | 'Chat' | 'Repository' | 'Board'

interface Column {
  id: string
  label: string
  group: Group
  hint: string
  align?: 'left' | 'right' | 'center'
  width?: number
  /** For sorting; null sorts last. */
  value: (r: Row) => number | string | null
  cell: (r: Row, ctx: Ctx) => ReactNode
  /** The footer: a sum or a median of the rows shown. */
  total?: 'sum' | 'median'
  fmt?: (v: number) => string
}

interface Ctx { sprints: Record<string, string>; maxOf: (id: string) => number }

const n = (v: number | null | undefined) => (v == null ? '—' : String(Math.round(v)))
const day = (ts: string) => (ts ? dayMonth(new Date(ts.slice(0, 16))) : '—')
const days = (d: number | null) => (d == null ? '—' : d < 1 ? '<1 d' : `${Math.round(d)} d`)

function Bar({ children }: { v: number; max: number; children: ReactNode }) {
  return <>{children}</>
}

/**
 * GitHub-style activity: a column per week, Monday at the top, each day a
 * square shaded by how much happened — board changes and chat mentions.
 * `counts` ends today; the grid ends on this week's column.
 */
const Weeks = memo(function Weeks({ counts }: { counts: number[] }) {
  const C = 5, G = 1, S = C + G
  const today = new Date()
  const dow = (today.getDay() + 6) % 7                       // Monday 0 … Sunday 6
  const cells = counts.map((n, i) => {
    const back = counts.length - 1 - i
    const slot = dow - back                                 // days from this week's Monday
    const col = Math.floor(slot / 7)
    const row = ((slot % 7) + 7) % 7
    return { n, back, col, row }
  })
  const minCol = Math.min(...cells.map((c) => c.col))
  const cols = -minCol + 1
  // Fixed steps, the same in every row, so two tasks compare at a glance.
  const level = (n: number) => (n === 0 ? 0 : n === 1 ? 1 : n <= 3 ? 2 : n <= 6 ? 3 : 4)
  const fill = ['var(--bg-elevated)', 'color-mix(in srgb, var(--brand) 30%, transparent)', 'color-mix(in srgb, var(--brand) 55%, transparent)',
    'color-mix(in srgb, var(--brand) 80%, transparent)', 'var(--brand)']
  const day = (back: number) => {
    const d = new Date(today)
    d.setDate(d.getDate() - back)
    return d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
  }
  const total = counts.reduce((a, b) => a + b, 0)
  // One path per shade, not a node per day: 120 rows of 91 squares were
  // 11 000 nodes and two seconds to draw. The hover label comes from the pointer.
  const paths = ['', '', '', '', '']
  const at = new Map<string, (typeof cells)[number]>()
  for (const c of cells) {
    const x = (c.col - minCol) * S, y = c.row * S
    paths[level(c.n)] += `M${x} ${y}h${C}v${C}h-${C}Z`
    at.set(`${c.col - minCol},${c.row}`, c)
  }
  const hover = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const c = at.get(`${Math.floor((e.clientX - r.left) / S)},${Math.floor((e.clientY - r.top) / S)}`)
    const tv = e.currentTarget.querySelector('title')
    if (tv) tv.textContent = c ? `${day(c.back)}: ${c.n ? tn(c.n, '{n} change or mention', '{n} changes or mentions') : t('nothing')}` : ''
  }
  return (
    <svg width={cols * S - G} height={7 * S - G} role="img" onMouseMove={hover}
      aria-label={t('{total} changes and mentions in the last {length} days', { total, length: counts.length })}>
      <title />
      {paths.map((d, i) => d && <path key={i} d={d} fill={fill[i]} />)}
    </svg>
  )
})

function StatusChip({ s }: { s: string }) {
  const k = norm(s === 'done-archived' ? 'done' : s)
  return (
    <span className="inline-flex items-center gap-4 text-11 font-mono text-secondary whitespace-nowrap">
      <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: COLOR[k] ?? 'var(--border-default)' }} aria-hidden />
      {s || 'unclassified'}
    </span>
  )
}

const COLUMNS: Column[] = [
  // ---------------------------------------------------------------- task
  { id: 'status', label: t('Status'), group: 'Task', hint: t('where it is on the board'), value: (r) => r.status, cell: (r) => <StatusChip s={r.status} /> },
  // Beside the status, where the eye starts: when the task was alive.
  { id: 'activity', label: t('Activity'), group: 'Board', hint: t('board changes and chat mentions a day, the last 13 weeks, a column per week'), value: (r) => r.activity.reduce((a, b) => a + b, 0), cell: (r) => <Weeks counts={r.activity} /> },
  { id: 'priority', label: t('Priority'), group: 'Task', hint: t('the board’s priority'), value: (r) => r.priority || null, cell: (r) => <span className="text-secondary">{r.priority || '—'}</span> },
  { id: 'assignee', label: t('Assignee'), group: 'Task', hint: t('who it is for'), value: (r) => r.assignee || null, cell: (r) => <span className="text-secondary truncate block max-w-[120px]">{r.assignee || '—'}</span> },
  { id: 'sprint', label: t('Sprint'), group: 'Task', hint: t('its sprint'), value: (r) => r.sprint_id || null, cell: (r, c) => <span className="text-secondary truncate block max-w-[120px]">{c.sprints[r.sprint_id] ?? (r.sprint_id || '—')}</span> },
  { id: 'tags', label: t('Tags'), group: 'Task', hint: t('its tags'), value: (r) => r.tags.join(',') || null, cell: (r) => <span className="text-tertiary truncate block max-w-[140px]">{r.tags.join(', ') || '—'}</span> },
  { id: 'impact', label: t('Impact'), group: 'Task', hint: t('impact, as set'), value: (r) => r.impact || null, cell: (r) => <span className="text-secondary">{r.impact || '—'}</span> },
  { id: 'effort', label: t('Effort'), group: 'Task', hint: t('effort, as set'), value: (r) => r.effort || null, cell: (r) => <span className="text-secondary">{r.effort || '—'}</span> },
  // ---------------------------------------------------------------- time
  { id: 'created', label: t('Created'), group: 'Time', hint: t('the day it was created'), align: 'right', value: (r) => r.created || null, cell: (r) => <span className="text-secondary">{day(r.created)}</span> },
  { id: 'done_at', label: t('Done'), group: 'Time', hint: t('the day it was finished'), align: 'right', value: (r) => r.done_at || null, cell: (r) => <span className="text-secondary">{day(r.done_at)}</span> },
  { id: 'age', label: t('Age'), group: 'Time', hint: t('days since it was created'), align: 'right', value: (r) => r.age_days, cell: (r) => days(r.age_days), total: 'median', fmt: (v) => days(v) },
  { id: 'instatus', label: t('In status'), group: 'Time', hint: t('days since its last move; amber: open and five days or more'), align: 'right', value: (r) => r.in_status_days,
    cell: (r) => <span className={!isDone(r.status) && (r.in_status_days ?? 0) >= 5 ? 'text-status-amber' : ''}>{days(r.in_status_days)}</span>, total: 'median', fmt: (v) => days(v) },
  { id: 'work', label: t('1st message → done'), group: 'Time', hint: t('from its first message in a chat to done'), align: 'right', value: (r) => r.work_hours, cell: (r) => hours(r.work_hours), total: 'median', fmt: (v) => hours(v) },
  { id: 'lead', label: t('Created → done'), group: 'Time', hint: t('from its creation to done'), align: 'right', value: (r) => r.lead_hours, cell: (r) => hours(r.lead_hours), total: 'median', fmt: (v) => hours(v) },
  // ---------------------------------------------------------------- chat
  { id: 'messages', label: t('Messages'), group: 'Chat', hint: t('messages in its stretch of the chat'), align: 'right', value: (r) => (r.stretch === 'none' ? null : r.messages),
    cell: (r, c) => (r.stretch === 'none' ? '—' : <Bar v={r.messages} max={c.maxOf('messages')}>{r.messages}{r.stretch === 'estimated' && <span className="text-tertiary" title={t('estimated')}>≈</span>}</Bar>), total: 'sum', fmt: (v) => n(v) },
  { id: 'minutes', label: t('Chat time'), group: 'Chat', hint: t('active time in the chat'), align: 'right', value: (r) => (r.stretch === 'none' ? null : r.minutes),
    cell: (r, c) => (r.stretch === 'none' ? '—' : <Bar v={r.minutes} max={c.maxOf('minutes')}>{mins(r.minutes)}</Bar>), total: 'sum', fmt: (v) => mins(v) },
  { id: 'chats', label: t('Chats'), group: 'Chat', hint: t('chats that named it'), align: 'right', value: (r) => r.named_in, cell: (r) => r.named_in || '—', total: 'sum', fmt: (v) => n(v) },
  { id: 'agents', label: t('Agents'), group: 'Chat', hint: t('agents whose chats worked on it'), value: (r) => r.agents.join(',') || null, cell: (r) => <span className="text-tertiary font-mono text-11 truncate block max-w-[140px]">{r.agents.join(', ') || '—'}</span> },
  { id: 'stretch', label: t('Stretch'), group: 'Chat', hint: t('exact (closed with #done) or estimated from where it was named'), align: 'center', value: (r) => r.stretch,
    cell: (r) => (r.stretch === 'done' ? <span style={{ color: 'var(--s-done)' }}>{t('exact')}</span> : r.stretch === 'estimated' ? <span className="text-tertiary">≈</span> : <span className="text-tertiary">—</span>) },
  { id: 'closed', label: t('Closed'), group: 'Chat', hint: t('with #done in the chat, or on the board'), value: (r) => r.closed || null,
    cell: (r) => (r.closed ? <span className="inline-flex items-center gap-4 whitespace-nowrap"><span className="w-8 h-8 rounded-pill" style={{ background: CLOSED_COLOR[r.closed] }} />{r.closed}</span> : '—') },
  // ---------------------------------------------------------- repository
  { id: 'commits', label: t('Commits'), group: 'Repository', hint: t('commits made in its stretch'), align: 'right', value: (r) => r.commits, cell: (r, c) => (r.commits ? <Bar v={r.commits} max={c.maxOf('commits')}>{r.commits}</Bar> : '—'), total: 'sum', fmt: (v) => n(v) },
  { id: 'files', label: t('Files'), group: 'Repository', hint: t('files it touched'), align: 'right', value: (r) => r.files, cell: (r) => r.files || '—', total: 'sum', fmt: (v) => n(v) },
  { id: 'lines', label: t('Lines'), group: 'Repository', hint: t('lines added and removed'), align: 'right', value: (r) => r.add + r.del,
    cell: (r) => (r.add + r.del ? <span className="whitespace-nowrap"><span className="text-status-green">+{r.add}</span> <span className="text-status-red">−{r.del}</span></span> : '—'), total: 'sum', fmt: (v) => n(v) },
  // --------------------------------------------------------------- board
  { id: 'moves', label: t('Moves'), group: 'Board', hint: t('status changes'), align: 'right', value: (r) => r.moves, cell: (r) => r.moves || '—', total: 'sum', fmt: (v) => n(v) },
  { id: 'edits', label: t('Edits'), group: 'Board', hint: t('other changes to the card'), align: 'right', value: (r) => r.edits, cell: (r) => r.edits || '—', total: 'sum', fmt: (v) => n(v) },
  { id: 'reopened', label: t('Reopened'), group: 'Board', hint: t('times moved back out of done'), align: 'right', value: (r) => r.reopened, cell: (r) => (r.reopened ? <span className="text-status-amber">{r.reopened}</span> : '—'), total: 'sum', fmt: (v) => n(v) },
  { id: 'reports', label: t('Reports'), group: 'Board', hint: t('times an agent said it was done'), align: 'right', value: (r) => r.reports, cell: (r) => r.reports || '—', total: 'sum', fmt: (v) => n(v) },
]

const GROUPS: Group[] = ['Task', 'Time', 'Chat', 'Repository', 'Board']

/** Column sets one click away. */
const COLUMN_SETS: Record<string, { name: string; ids: string[] }> = {
  default: { name: t('Everyday'), ids: ['status', 'activity', 'age', 'instatus', 'messages', 'minutes', 'commits', 'lines', 'lead', 'closed'] },
  board: { name: t('Board'), ids: ['status', 'activity', 'age', 'instatus', 'moves', 'edits', 'chats'] },
  effort: { name: t('Effort (the statistics)'), ids: ['done_at', 'messages', 'minutes', 'commits', 'files', 'lines', 'work', 'lead', 'closed', 'stretch'] },
  all: { name: t('Everything'), ids: COLUMNS.map((c) => c.id) },
}

/* -------------------------------------------------------------- prefs */

interface TablePrefs { columns: string[]; dense: boolean; totals: boolean; sort: { id: string; desc: boolean } }
const KEY = 'sp-task-table'

function readTablePrefs(): TablePrefs {
  try {
    const p = JSON.parse(readPref(KEY) ?? 'null') ?? {}
    const cols = Array.isArray(p.columns) ? p.columns.filter((c: string) => COLUMNS.some((x) => x.id === c)) : null
    return {
      columns: cols?.length ? cols : COLUMN_SETS.default!.ids,
      dense: p.dense === true, totals: p.totals !== false,
      sort: p.sort && typeof p.sort.id === 'string' ? p.sort : { id: 'instatus', desc: true },
    }
  } catch {
    return { columns: COLUMN_SETS.default!.ids, dense: false, totals: true, sort: { id: 'instatus', desc: true } }
  }
}

export function useTablePrefs() {
  const [prefs, setPrefs] = useState(readTablePrefs)
  const set = (p: Partial<TablePrefs>) => {
    const next = { ...prefs, ...p }
    setPrefs(next)
    persistPref(KEY, JSON.stringify(next))
  }
  return [prefs, set] as const
}

/* ---------------------------------------------------------- settings UI */

export function ColumnsButton({ prefs, set }: { prefs: TablePrefs; set: (p: Partial<TablePrefs>) => void }) {
  const { open, setOpen, rootRef } = usePopover()
  const toggle = (id: string) => set({ columns: prefs.columns.includes(id) ? prefs.columns.filter((c) => c !== id) : COLUMNS.filter((c) => prefs.columns.includes(c.id) || c.id === id).map((c) => c.id) })
  return (
    <span ref={rootRef} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className={`h-20 px-8 inline-flex items-center gap-4 rounded-pill border text-11 font-mono ${open ? 'border-border-strong text-primary bg-hover' : 'border-border-default text-tertiary hover:text-primary'}`}>
        <Settings2 size={11} aria-hidden /> {t('columns')}{' '}{prefs.columns.length}
      </button>
      {open && (
        <>
          <div className="absolute right-0 top-full mt-4 z-50 w-[560px] max-w-[92vw] p-12 rounded-card border border-border-default bg-base shadow-lg flex flex-col gap-10">
            <div className="flex items-center gap-6 flex-wrap">
              <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Sets')}</span>
              {Object.entries(COLUMN_SETS).map(([k, v]) => (
                <button key={k} type="button" onClick={() => set({ columns: v.ids })}
                  className="h-20 px-8 rounded-pill border border-border-subtle text-11 text-secondary hover:text-primary hover:border-brand">{v.name}</button>
              ))}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-16 gap-y-8">
              {GROUPS.map((g) => (
                <div key={g} className="flex flex-col gap-2">
                  <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{tc('column group', g)}</span>
                  {COLUMNS.filter((c) => c.group === g).map((c) => (
                    <label key={c.id} className="flex items-center gap-6 text-12 text-primary cursor-pointer" title={c.hint}>
                      <input type="checkbox" checked={prefs.columns.includes(c.id)} onChange={() => toggle(c.id)} className="accent-[var(--brand)]" />
                      {c.label}
                    </label>
                  ))}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-16 pt-6 border-t border-border-subtle text-12 text-secondary">
              <label className="inline-flex items-center gap-6"><input type="checkbox" checked={prefs.dense} onChange={(e) => set({ dense: e.target.checked })} className="accent-[var(--brand)]" /> {t('compact rows')}</label>
              <label className="inline-flex items-center gap-6"><input type="checkbox" checked={prefs.totals} onChange={(e) => set({ totals: e.target.checked })} className="accent-[var(--brand)]" /> {t('totals row')}</label>
            </div>
          </div>
        </>
      )}
    </span>
  )
}

/* -------------------------------------------------------------- table */

const TaskRow = memo(function TaskRow({ r, colKey, dense, ctx, onOpen }: {
  r: Row; colKey: string; dense: boolean; ctx: Ctx; onOpen: (id: string) => void
}) {
  const ids = colKey.split(',')
  const cols = COLUMNS.filter((c) => ids.includes(c.id))
  const py = dense ? 'py-2' : 'py-4'
  return (
    <tr className="group cursor-pointer" onClick={() => onOpen(r.id)}>
      <td className={`sticky left-0 z-[2] bg-base group-hover:bg-hover px-10 ${py} border-b border-border-subtle max-w-[360px]`}>
        <div className="flex items-center gap-6 min-w-0">
          {r.starred && <Star size={11} className="shrink-0" style={{ color: 'var(--star)', fill: 'var(--star)' }} aria-label={t('starred')} />}
          <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(r.id) }}
            className={`truncate min-w-0 text-left text-12 ${isDone(r.status) ? 'text-secondary' : 'text-primary'}`} title={r.title}>
            {r.title || r.id}
          </button>
        </div>
        {!dense && <div className="text-10 font-mono text-tertiary">{r.id}</div>}
      </td>
      {cols.map((c) => (
        <td key={c.id} className={`px-10 ${py} border-b border-border-subtle bg-base group-hover:bg-hover ${c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : ''}`}>
          {c.cell(r, ctx)}
        </td>
      ))}
    </tr>
  )
})

/**
 * A column's heading: a click sorts by it. At module level — defined inside
 * the table it was a new component on every draw, so the heading was thrown
 * away and built again and the button just pressed lost the keyboard.
 */
function Head({ id, label, hint, align, sort, onSort }: {
  id: string; label: string; hint: string; align?: string
  sort: TablePrefs['sort']; onSort: (id: string) => void
}) {
  return (
    <th className={`px-10 py-6 font-normal whitespace-nowrap border-b border-border-subtle ${align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'}`} title={hint}>
      <button type="button" onClick={() => onSort(id)} className={`inline-flex items-center gap-2 ${TH_BUTTON} ${sort.id === id ? 'text-primary' : ''}`}>
        {label}{sort.id === id && (sort.desc ? <ArrowDown size={10} /> : <ArrowUp size={10} />)}
      </button>
    </th>
  )
}

export function TaskTable({ rows, prefs, set, onOpen, sprints, bare = false }: {
  rows: Row[]
  /** Inside a panel: no frame of its own. */
  bare?: boolean
  prefs: TablePrefs
  set: (p: Partial<TablePrefs>) => void
  onOpen: (id: string) => void
  sprints: Record<string, string>
}) {
  const cols = COLUMNS.filter((c) => prefs.columns.includes(c.id))
  const sortCol = COLUMNS.find((c) => c.id === prefs.sort.id)
  const sorted = useMemo(() => {
    if (!sortCol && prefs.sort.id !== 'title') return rows
    const get = prefs.sort.id === 'title' ? (r: Row) => r.title.toLowerCase() : sortCol!.value
    return rows.slice().sort((a, b) => {
      const x = get(a), y = get(b)
      if (x == null && y == null) return 0
      if (x == null) return 1
      if (y == null) return -1
      return (x < y ? -1 : x > y ? 1 : 0) * (prefs.sort.desc ? -1 : 1)
    })
  }, [rows, sortCol, prefs.sort])
  const ctx = useMemo<Ctx>(() => ({ sprints, maxOf: () => 1 }), [sprints])
  // The latest opener, through a ref: a row redraws only when its own task,
  // the columns or the density change — typing a query redrew 11 000 squares.
  const openRef = useRef(onOpen)
  openRef.current = onOpen
  const openRow = useCallback((id: string) => openRef.current(id), [])
  const colKey = cols.map((c) => c.id).join(',')
  const sortBy = (id: string) => set({ sort: { id, desc: prefs.sort.id === id ? !prefs.sort.desc : id !== 'title' } })
  const total = (c: Column) => {
    const vals = rows.map((r) => c.value(r)).filter((v): v is number => typeof v === 'number')
    if (!c.total || !vals.length) return ''
    const v = c.total === 'sum' ? vals.reduce((a, b) => a + b, 0) : median(vals)
    return v == null ? '' : `${c.total === 'median' ? 'median ' : ''}${c.fmt ? c.fmt(v) : v}`
  }
  return (
    <div className={`overflow-auto max-h-[calc(100vh-220px)] ${bare ? 'border-t border-border-subtle' : 'rounded-card border border-border-subtle'}`}>
      <table className="w-full text-12 tabular-nums border-separate border-spacing-0">
        <thead className={`sticky top-0 z-[3] bg-base ${TH}`}>
          <tr>
            <th className="sticky left-0 z-[4] bg-base text-left px-10 py-6 font-normal border-b border-border-subtle min-w-[280px]">
              <button type="button" onClick={() => sortBy('title')} className={`${TH_BUTTON} ${prefs.sort.id === 'title' ? 'text-primary' : ''}`}>
                {t('Task ·')}{' '}{rows.length}
              </button>
            </th>
            {cols.map((c) => <Head key={c.id} id={c.id} label={c.label} hint={c.hint} align={c.align} sort={prefs.sort} onSort={sortBy} />)}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => <TaskRow key={r.id} r={r} colKey={colKey} dense={prefs.dense} ctx={ctx} onOpen={openRow} />)}
          {sorted.length === 0 && (
            <tr><td colSpan={cols.length + 1} className="px-10 py-24 text-center text-12 text-tertiary">{t('No task matches. Remove a filter above.')}</td></tr>
          )}
        </tbody>
        {prefs.totals && sorted.length > 0 && (
          <tfoot className="sticky bottom-0 z-[3] bg-base text-10 font-mono text-tertiary">
            <tr>
              <td className="sticky left-0 z-[4] bg-base px-10 py-6 border-t border-border-default">{rows.length} {t('tasks')}</td>
              {cols.map((c) => <td key={c.id} className={`px-10 py-6 border-t border-border-default whitespace-nowrap ${c.align === 'right' ? 'text-right' : ''}`}>{total(c)}</td>)}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}
