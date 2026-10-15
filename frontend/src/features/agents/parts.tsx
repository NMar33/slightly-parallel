/**
 * Shared parts for the agent pages — the roster variants and the personal
 * page draw from the same profile and the same pieces, so a number means
 * the same thing wherever it is printed.
 */

import { StatTile } from '../../components/StatTile'
import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil } from 'lucide-react'

import { CopyButton } from '../../components/CopyButton'
import { Badge, Button, Card } from '../../components/primitives'
import { EmptyState, LoadingSkeleton } from '../../components/states'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { safeParseMs } from '../../utils/dateUtils'
import { TaskAddModal } from '../project/kanban/TaskWindow'
import type { TaskRow } from '../project/kanban/model'
import { fetchTask } from '../tasks/data'
import { fail } from '../../lib/getJson'
import { toast } from '../../components/primitives'
import { resumeCommand } from '../project/AgentDrill'
import { AgentEditDialog } from './AgentEditDialog'
import { LINK_DASH, LINK_KIND_LABEL, type AgentLink } from './links'
import {
  fmtLines,
  fmtMinutes,
  profileLabel,
  sumTotals,
  approx,
  sessionLine,
  taskTone,
  toolOfProfile,
  TOOL_LABEL,
  type AgentProfile,
  type ProfileTask,
} from './profile'

import { t, tn } from '../../i18n/scope/views'
import { rich } from '../../i18n/rich'
import { dayMonth } from '../../lib/months'
export function RosterLoading() {
  return (
    <div className="flex flex-col gap-16">
      <LoadingSkeleton variant="text" count={2} label={t('Loading agents')} />
      <LoadingSkeleton variant="kpi" label={t('Loading numbers')} />
      <LoadingSkeleton variant="row" count={6} label={t('Loading the roster')} />
    </div>
  )
}

export function RosterError({ error, retry }: { error: Error | null; retry: () => void }) {
  return (
    <div>
      <Card padding="lg" className="border-status-red">
        <div className="text-14 text-primary mb-8">{t('Could not load the agents.')}</div>
        <div className="text-13 text-secondary mb-16">{error?.message ?? t('Unknown error.')}</div>
        <Button onClick={retry}>{t('Retry')}</Button>
      </Card>
    </div>
  )
}

export function RosterEmpty() {
  return (
    <EmptyState
      title={t('No agents yet')}
      subtitle={t('Start a chat in this project\'s folder. The agent appears here after its first message.')}
    />
  )
}

// ---------------------------------------------------------------------------
// Fleet strip — the sums over every agent, same numbers everywhere
// ---------------------------------------------------------------------------

export function FleetStrip({ profiles }: { profiles: AgentProfile[] }) {
  const tot = sumTotals(profiles)
  const cells: Array<[string, ReactNode, string]> = [
    ['agents', profiles.length, `${new Set(profiles.map((p) => p.agent.agent_group).filter(Boolean)).size} groups`],
    [t('agent time'), `${approx(tot.minutes_approx)}${fmtMinutes(tot.minutes)}`, sessionLine(tot.session_minutes, tot.waiting_minutes, tot.helper_minutes) || t('{sessions_n} chats · {turns} turns', { sessions_n: tot.sessions_n, turns: tot.turns })],
    ['lines', fmtLines(tot.lines_add, tot.lines_del), t('{files_n} files across {scans_n} scans', { files_n: tot.files_n, scans_n: tot.scans_n })],
    ['features · bugs', `${tot.features_n} · ${tot.bugs_resolved_n}`, t('{architecture_n} architecture entries, {problems_n} problems', { architecture_n: tot.architecture_n, problems_n: tot.problems_n })],
    ['tasks', t('{tasks_done_n} of {tasks_handed_n}', { tasks_done_n: tot.tasks_done_n, tasks_handed_n: tot.tasks_handed_n }), t('handed over → done')],
    ['decisions · rules', `${tot.decisions_n} · ${tot.rules_n}`, `${tot.standups_n} standups`],
  ]
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-10">
      {cells.map(([label, value, sub]) => <StatTile key={label} label={label} value={value} sub={sub} wrapSub title={sub} />)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function ToolBadge({ tool }: { tool: string }) {
  if (!tool) return null
  return (
    <span className="text-10 font-mono uppercase tracking-wide rounded-pill border border-border-subtle px-6 py-1 text-tertiary whitespace-nowrap">
      {TOOL_LABEL[tool] ?? tool}
    </span>
  )
}

function GroupChip({ name }: { name?: string }) {
  if (!name) return null
  return (
    <span className="text-10 font-mono rounded-pill bg-elevated border border-border-subtle px-6 py-1 text-secondary whitespace-nowrap" title={t('group')}>
      ⌂ {name}
    </span>
  )
}

/** Name, tool, group, id — the identity line used everywhere. */
export function AgentIdentity({ p, size = 'md', linkTo = true }: { p: AgentProfile; size?: 'sm' | 'md' | 'lg'; linkTo?: boolean }) {
  const label = profileLabel(p)
  const cls = size === 'lg' ? 'text-20 font-semibold' : size === 'md' ? 'text-14 font-medium' : 'text-13 font-medium'
  const name = linkTo ? (
    <Link to={`/agent/${encodeURIComponent(p.agent.agent_id)}`} className={`${cls} text-primary hover:text-brand no-underline truncate`}>
      {label}
    </Link>
  ) : (
    <span className={`${cls} text-primary truncate`}>{label}</span>
  )
  return (
    <div className="min-w-0 flex flex-col gap-2">
      <div className="flex items-center gap-6 min-w-0 flex-wrap">
        {name}
        <ToolBadge tool={toolOfProfile(p)} />
        <GroupChip name={p.agent.agent_group} />
      </div>
      <div className="text-10 font-mono text-tertiary truncate">
        {p.agent.agent_id}
        {p.parent && <> {t('· child of')}{' '}{p.parent.agent_name || p.parent.agent_id}</>}
      </div>
    </div>
  )
}

/** YYMM-DD or ISO → epoch ms; null when neither. Agents carry both. */
export function anyMs(s: unknown): number | null {
  const a = safeParseMs(s)
  if (a != null) return a
  if (typeof s !== 'string' || !s) return null
  const b = Date.parse(s)
  return Number.isFinite(b) ? b : null
}

export function fmtDay(yymmdd: string): string {
  const ms = anyMs(yymmdd)
  return ms ? dayMonth(new Date(ms)) : yymmdd
}

/** The project's day range, from every agent's by-day — so sparks share an axis. */
export function projectRange(profiles: AgentProfile[]): [number, number] {
  let lo = Infinity, hi = -Infinity
  for (const p of profiles) {
    for (const d of p.by_day) {
      const ms = safeParseMs(d.date)
      if (ms == null) continue
      lo = Math.min(lo, ms); hi = Math.max(hi, ms)
    }
    const c = anyMs(p.agent.created_date)
    const l = anyMs(p.agent.last_active)
    if (c != null) { lo = Math.min(lo, c); hi = Math.max(hi, c) }
    if (l != null) { lo = Math.min(lo, l); hi = Math.max(hi, l) }
  }
  if (!Number.isFinite(lo)) { const now = Date.now(); return [now - 7 * 864e5, now] }
  return [lo, Math.max(hi, lo + 864e5)]
}

/**
 * DaySpark — one bar per day of activity, on the project's shared axis.
 * Height = turns that day; a hover title says the day, turns, minutes.
 */
export function DaySpark({
  byDay,
  range,
  width = 160,
  height = 22,
  color = 'var(--brand)',
  max,
  onPick,
  picked,
}: {
  byDay: AgentProfile['by_day']
  range: [number, number]
  width?: number
  height?: number
  color?: string
  /** Shared maximum so bars compare across agents; defaults to this agent's. */
  max?: number
  /** When set, bars are buttons — click a day. */
  onPick?: (date: string) => void
  /** The day drawn in full colour when others dim. */
  picked?: string
}) {
  const days = Math.max(1, Math.round((range[1] - range[0]) / 864e5) + 1)
  const slot = width / days
  const bw = Math.max(1.5, slot - 1)
  const peak = Math.max(1, max ?? Math.max(0, ...byDay.map((d) => d.turns)))
  return (
    <svg width={width} height={height} aria-label={t('{length} active days', { length: byDay.length })} role="img" className="shrink-0">
      <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} stroke="var(--border-subtle)" />
      {byDay.map((d) => {
        const ms = safeParseMs(d.date)
        if (ms == null) return null
        const i = Math.round((ms - range[0]) / 864e5)
        const h = Math.max(2, (d.turns / peak) * (height - 3))
        const dim = picked && picked !== d.date
        return (
          <rect
            key={d.date} x={i * slot} y={height - 1 - h} width={bw} height={h} rx={1} fill={color}
            opacity={dim ? 0.3 : 0.85}
            style={onPick ? { cursor: 'pointer' } : undefined}
            onClick={onPick ? () => onPick(d.date) : undefined}
            role={onPick ? 'button' : undefined}
            aria-label={onPick ? `${fmtDay(d.date)}: ${d.turns} turns` : undefined}
          >
            <title>{`${fmtDay(d.date)} · ${tn(d.turns, '{n} turn', '{n} turns')} · ${fmtMinutes(d.minutes)} · ${tn(d.sessions, '{n} chat', '{n} chats')}`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

/** HourStrip — 24 cells, darker where the agent's turns fell. */
export function HourStrip({ byHour, width = 168, height = 10 }: { byHour: number[]; width?: number; height?: number }) {
  const peak = Math.max(1, ...byHour)
  const cw = width / 24
  const busiest = byHour.indexOf(Math.max(...byHour))
  return (
    <svg width={width} height={height} role="img" aria-label={byHour.some(Boolean) ? t('busiest hour {busiest}:00', { busiest }) : t('no turns')} className="shrink-0">
      {byHour.map((n, h) => (
        <rect key={h} x={h * cw + 0.5} y={0} width={Math.max(1, cw - 1)} height={height} rx={1.5}
          fill={n ? 'var(--brand)' : 'var(--border-subtle)'} opacity={n ? 0.25 + 0.75 * (n / peak) : 0.6}>
          <title>{`${String(h).padStart(2, '0')}:00 — ${tn(n, '{n} turn', '{n} turns')}`}</title>
        </rect>
      ))}
    </svg>
  )
}

export function Stat({ label, value, sub, size = 'md' }: { label: string; value: ReactNode; sub?: ReactNode; size?: 'sm' | 'md' | 'lg' }) {
  const v = size === 'lg' ? 'text-32' : size === 'md' ? 'text-20' : 'text-14'
  return (
    <div className="min-w-0">
      <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{label}</div>
      <div className={`${v} font-semibold text-primary tabular leading-tight mt-2 break-words`}>{value}</div>
      {sub && <div className="text-11 text-tertiary mt-2 truncate">{sub}</div>}
    </div>
  )
}

/** What the agent did, as counted chips — zeros are left out. */
export function DidChips({ p, onOpen }: { p: AgentProfile; onOpen?: (lens: string) => void }) {
  const tot = p.totals
  const items: Array<[string, number, string, string, [string, string]]> = [
    ['feature', tot.features_n, 'architecture', 'text-status-green', ['feature', 'features']],
    ['bug fixed', tot.bugs_resolved_n, 'problems', 'text-status-amber', ['bug fixed', 'bugs fixed']],
    ['decision', tot.decisions_n, 'decisions', 'text-brand', ['decision', 'decisions']],
    ['scan', tot.scans_n, 'scans', 'text-secondary', ['scan', 'scans']],
    ['rule', tot.rules_n, 'rules', 'text-status-purple', ['rule', 'rules']],
  ]
  const shown = items.filter(([, n]) => n > 0)
  if (shown.length === 0) return <EmptyState compact title={t('No entries posted.')} />
  return (
    <div className="flex flex-wrap gap-4">
      {shown.map(([word, n, lens, tone, [one, many]]) => (
        <button
          key={word}
          type="button"
          onClick={onOpen ? () => onOpen(lens) : undefined}
          className={`text-11 font-mono rounded-pill border border-border-subtle bg-surface px-6 py-1 ${onOpen ? 'hover:bg-hover' : 'cursor-default'}`}
          title={tn(n, `{n} ${one}`, `{n} ${many}`)}
        >
          <span className={`${tone} font-semibold`}>{n}</span> <span className="text-secondary">{tn(n, `{n} ${one}`, `{n} ${many}`).replace(String(n), '').trim()}</span>
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tasks — the ones named in this agent's turns
// ---------------------------------------------------------------------------

function TaskDot({ status }: { status: string }) {
  const tone = taskTone(status)
  const cls = tone === 'done' ? 'bg-status-green' : tone === 'doing' ? 'bg-status-amber' : 'bg-status-neutral'
  return <span aria-hidden className={`inline-block h-6 w-6 rounded-pill shrink-0 ${cls}`} title={status} />
}

/** A hook that opens a task in the board's editor from its id. */
export function useTaskOpener(projectCode: string) {
  const [task, setTask] = useState<TaskRow | null>(null)
  // The last click wins: an earlier task answering later does not open over it.
  const asked = useRef(0)
  const open = (id: string) => {
    const n = ++asked.current
    fetchTask(id).then(
      (it) => {
        if (n !== asked.current) return
        if (it) setTask(it)
        else toast.error(t('The task {id} was not found.', { id }))
      },
      (e) => { if (n === asked.current) fail(e) },
    )
  }
  const modal = task ? (
    <TaskAddModal
      projectCode={projectCode}
      initialStatus={task.status || 'unclassified'}
      existingTask={task}
      onClose={() => setTask(null)}
      onSaved={() => setTask(null)}
    />
  ) : null
  return { open, modal }
}

export function TaskRows({ tasks, limit, onOpen, dense = false }: { tasks: ProfileTask[]; limit?: number; onOpen?: (id: string) => void; dense?: boolean }) {
  const rows = limit ? tasks.slice(0, limit) : tasks
  if (tasks.length === 0) return <EmptyState compact title={t('No task is named in its turns.')} />
  return (
    <ul className={`flex flex-col ${dense ? 'gap-1' : 'gap-3'}`}>
      {rows.map((it) => (
        <li key={it.id} className="min-w-0">
          <button
            type="button"
            onClick={onOpen ? () => onOpen(it.id) : undefined}
            className={`w-full text-left flex items-center gap-6 min-w-0 rounded-input px-4 py-1 ${onOpen ? 'hover:bg-hover' : 'cursor-default'}`}
            title={t('{id} · {status} · handed {handed_n}× · replied {replied_n}×', { id: it.id, status: it.status, handed_n: it.handed_n, replied_n: it.replied_n })}
          >
            <TaskDot status={it.status} />
            <span className={`${dense ? 'text-11' : 'text-12'} text-primary truncate`}>{it.title || it.id}</span>
            <span className="ml-auto text-10 font-mono text-tertiary shrink-0">
              {it.turn_max > 1 ? `.${it.turn_max} · ` : ''}{it.status}
            </span>
          </button>
        </li>
      ))}
      {limit && tasks.length > limit && (
        <li className="text-10 font-mono text-tertiary px-4">+{tasks.length - limit} {t('more')}</li>
      )}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Entries — rows that open in the lens drawer
// ---------------------------------------------------------------------------

export function useDrawer() {
  const [open, setOpen] = useState<{ lens: string; id: string } | null>(null)
  const drawer = open && LENSES[open.lens] ? (
    <LensDrawer lens={LENSES[open.lens]!} id={open.id} presentation="reading" onClose={() => setOpen(null)} />
  ) : null
  return { open: (lens: string, id: string) => setOpen({ lens, id }), drawer }
}

/** What a row needs to be listed: its id, its day, and a line to show. */
interface EntryRowLike { id: string; created_date: string; created_time?: string; start_time?: string; l1?: string; decision_text?: string; goal_text?: string }

export function EntryRows<R extends EntryRowLike>({
  rows,
  lens,
  onOpen,
  limit,
  right,
  empty = t('nothing yet'),
}: {
  rows: R[]
  lens: string
  onOpen: (lens: string, id: string) => void
  limit?: number
  right?: (row: R) => ReactNode
  empty?: string
}) {
  const shown = limit ? rows.slice(0, limit) : rows
  if (rows.length === 0) return <EmptyState compact title={empty} />
  return (
    <ol className="flex flex-col gap-1">
      {shown.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onOpen(lens, r.id)}
            className="w-full text-left text-12 flex items-baseline gap-8 px-6 py-3 rounded-input hover:bg-hover min-w-0"
          >
            <span className="text-10 font-mono text-tertiary tabular shrink-0">
              {fmtDay(r.created_date)} {r.created_time || r.start_time || ''}
            </span>
            <span className="text-secondary truncate">{r.l1 || r.decision_text || r.goal_text || r.id}</span>
            {right && <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{right(r)}</span>}
          </button>
        </li>
      ))}
      {limit && rows.length > limit && <li className="text-10 font-mono text-tertiary px-6">+{rows.length - limit} {t('more')}</li>}
    </ol>
  )
}

// ---------------------------------------------------------------------------
// Origin + edit
// ---------------------------------------------------------------------------

export function OriginLine({ p, full = false }: { p: AgentProfile; full?: boolean }) {
  const tool = toolOfProfile(p)
  const cmd = resumeCommand(tool, p.origin.cwd, p.origin.session_ref)
  const folder = p.origin.cwd
  const short = folder ? folder.split('/').filter(Boolean).slice(-2).join('/') : ''
  return (
    <div className={`flex ${full ? 'flex-col gap-6' : 'items-center gap-8 flex-wrap'} text-11 font-mono text-tertiary min-w-0`}>
      <span className="inline-flex items-center gap-6 min-w-0">
        <span className="text-secondary">{t('ran in')}</span>
        <span className="truncate" title={folder || t('folder not recorded')}>{full ? (folder || '—') : (short || '—')}</span>
      </span>
      {full && (
        <span><span className="text-secondary">{t('chat')}</span> {p.origin.session_ref || '—'}</span>
      )}
      {cmd && (
        <span className="inline-flex items-center gap-6 min-w-0">
          <code className="text-11 text-primary truncate max-w-[420px]" title={cmd}>{cmd}</code>
          <CopyButton
            text={cmd}
            title={t('Copy resume command')}
            className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"
          />
        </span>
      )}
    </div>
  )
}

export function EditAgentButton({ p, code, label = false }: { p: AgentProfile; code: string; label?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t('Edit {profileLabel}', { profileLabel: profileLabel(p) })}
        title={t('rename · group')}
        className={`inline-flex items-center gap-4 rounded-input text-tertiary hover:text-primary hover:bg-hover ${label ? 'px-8 h-24 text-11' : 'h-24 w-24 justify-center'}`}
      >
        <Pencil size={11} aria-hidden />
        {label && 'edit'}
      </button>
      {open && (
        <AgentEditDialog
          agent={{ ...p.agent, project: code }}
          project={code}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

export function OpenAgentButton({ p, label = false }: { p: AgentProfile; label?: boolean }) {
  return (
    <Link
      to={`/agent/${encodeURIComponent(p.agent.agent_id)}`}
      aria-label={t('Open {profileLabel}', { profileLabel: profileLabel(p) })}
      title={t('Open the agent\'s page: chats, files, folder')}
      className={`inline-flex items-center gap-4 rounded-input text-tertiary hover:text-primary hover:bg-hover no-underline ${label ? 'px-8 h-24 text-11' : 'h-24 w-24 justify-center'}`}
    >
      <Eye size={12} aria-hidden />
      {label && 'open'}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Links + family
// ---------------------------------------------------------------------------

export function LinkRows({ p, byId }: { p: AgentProfile; byId?: Map<string, AgentProfile> }) {
  const me = p.agent.agent_id
  const nameOf = (b: AgentLink['from']) => {
    const q = byId?.get(b.agent_id)
    return q ? profileLabel(q) : b.agent_name || b.agent_id
  }
  const fam: ReactNode[] = []
  if (p.parent) fam.push(<li key="parent" className="text-12 text-secondary">{t('started by')}{' '}<Link to={`/agent/${encodeURIComponent(p.parent.agent_id)}`} className="text-primary hover:text-brand">{nameOf(p.parent)}</Link></li>)
  for (const c of p.children) fam.push(<li key={c.agent_id} className="text-12 text-secondary">{t('started')}{' '}<Link to={`/agent/${encodeURIComponent(c.agent_id)}`} className="text-primary hover:text-brand">{nameOf(c)}</Link></li>)
  for (const m of p.group.members) fam.push(<li key={`g-${m.agent_id}`} className="text-12 text-secondary">{rich(t('in group {group} with {agent}'), { group: <span className="font-mono text-11">{p.group.name}</span>, agent: <Link to={`/agent/${encodeURIComponent(m.agent_id)}`} className="text-primary hover:text-brand">{nameOf(m)}</Link> })}</li>)
  for (const l of p.links) {
    const other = l.from_id === me ? l.to : l.from
    const outgoing = l.from_id === me
    fam.push(
      <li key={l.id} className="text-12 text-secondary flex items-center gap-6 min-w-0">
        <svg width="22" height="8" aria-hidden className="shrink-0"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--text-secondary)" strokeWidth="1.5" strokeDasharray={LINK_DASH[l.style]} strokeLinecap="round" /></svg>
        <span className="truncate">
          {l.kind === 'branch'
            ? (outgoing ? <>{nameOf(other)} {t('branched from this one')}</> : <>{t('branched from')}{' '}<Link to={`/agent/${encodeURIComponent(other.agent_id)}`} className="text-primary hover:text-brand">{nameOf(other)}</Link></>)
            : l.kind === 'subagent'
              ? (outgoing ? <>{t('started')}{' '}<Link to={`/agent/${encodeURIComponent(other.agent_id)}`} className="text-primary hover:text-brand">{nameOf(other)}</Link> {t('as a subagent')}</> : <>{t('subagent of')}{' '}<Link to={`/agent/${encodeURIComponent(other.agent_id)}`} className="text-primary hover:text-brand">{nameOf(other)}</Link></>)
              : <>{outgoing ? LINK_KIND_LABEL[l.kind] : LINK_KIND_LABEL[l.kind].replace(t('handed over to'), t('took over from'))} <Link to={`/agent/${encodeURIComponent(other.agent_id)}`} className="text-primary hover:text-brand">{nameOf(other)}</Link></>}
          {l.note && <span className="text-tertiary"> — {l.note}</span>}
        </span>
      </li>,
    )
  }
  if (fam.length === 0) return <EmptyState compact title={t('No links.')} subtitle={t('Use Connect on the timeline to add one.')} />
  return <ul className="flex flex-col gap-3">{fam}</ul>
}

/** Status badge for a profile: active today / this week / idle. */
export function ActivityBadge({ p }: { p: AgentProfile }) {
  const ms = anyMs(p.agent.last_active)
  if (ms == null) return <Badge tone="idle">{t('no activity')}</Badge>
  const age = Date.now() - ms
  if (age < 864e5) return <Badge tone="active" dot>{t('today')}</Badge>
  if (age < 7 * 864e5) return <Badge tone="info">{t('this week')}</Badge>
  return <Badge tone="idle">{t('idle')}{' '}{Math.floor(age / 864e5)}{t('d')}</Badge>
}
