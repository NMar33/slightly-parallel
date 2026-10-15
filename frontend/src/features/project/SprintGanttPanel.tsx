import { hm } from '../../utils/format'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Button, Card, IconButton } from '../../components/primitives'
import { Modal } from '../../components/Modal'
import { getJson, refused } from '../../lib/getJson'
import { isoDay } from '../../utils/dateUtils'
import type { AgentDetailAnswer } from './types'
import { sprintsTimelineQuery, type SpanTask, type TimelineSprint } from './sprintsModel'
import { agentLabel } from '../../utils/agentLabel'
import { AgentDrillById } from './AgentDrill'
import { EmptyState, LoadingSkeleton } from '../../components/states'
import { LABEL } from '../promptlib/taskstyle'
import { t, tn } from '../../i18n/scope/project'

/**
 * SprintGanttPanel — the project's life through its sprints, on real data.
 *
 * The winning timeline concept: one row per sprint (active and settled),
 * the bet solid, the overrun hatched, the verdict at the end of the bar;
 * a row unfolds into its tasks as join → done spans. Clicking a sprint's
 * name opens the dossier — the block's full story: how long it ran, both
 * clocks, the agents that worked it, and the commits and lines written in
 * its window when the project folder is a git repo. Everything is derived
 * on read; whatever cannot be known says so.
 */

const DAY = 86400e3

function days(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / DAY)
}

export function SprintGanttPanel({ projectCode }: { projectCode: string }) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [dossier, setDossier] = useState<string | null>(null)
  const read = useQuery(sprintsTimelineQuery(projectCode))
  // A timeline that could not be read shows as none, as before.
  const rows = useMemo((): TimelineSprint[] | null => (read.data
    ? (Array.isArray(read.data.sprints) ? read.data.sprints : [])
    : read.isError ? [] : null), [read.data, read.isError])

  const geom = useMemo(() => {
    if (!rows || rows.length === 0) return null
    // Today on this computer: the server's dates are its local days, and the
    // UTC day is yesterday's for half the morning east of Greenwich.
    const today = isoDay(new Date())
    const t0 = rows.reduce((a, s) => (s.started < a ? s.started : a), today)
    const spanDays = Math.max(days(t0, today) + 4, 10)
    const frac = (iso: string) => Math.max(0, Math.min(days(t0, iso), spanDays)) / spanDays
    const x = (iso: string) => `${frac(iso) * 100}%`
    const w = (a: string, b: string) => `${(Math.max(0, Math.min(days(a, b), spanDays)) / spanDays) * 100}%`
    return { t0, spanDays, today, frac, x, w }
  }, [rows])

  if (rows === null) return <LoadingSkeleton variant="row" count={3} />

  return (
    <section aria-labelledby="sprint-gantt">
      <div className="flex items-center gap-8 mb-16 flex-wrap">
        <h2 id="sprint-gantt" className="text-20 font-semibold text-primary" style={{ letterSpacing: '-0.022em' }}>
          {t('Sprint timeline')}
        </h2>
        <span className="text-11 font-mono text-tertiary">{t('Every sprint of the project. Click a name for its details.')}</span>
      </div>
      <Card padding="md">
        {rows.length === 0 || !geom ? (
          <EmptyState title={t('No sprints yet')} subtitle={t('Start one on the Sprints tab.')} />
        ) : (
          <div>
            {/* axis: week ticks */}
            <div className="relative h-14 mb-6" style={{ marginLeft: 170 }}>
              {Array.from({ length: Math.floor(geom.spanDays / 7) + 1 }, (_, i) => i * 7).map((d) => {
                const iso = new Date(Date.parse(geom.t0) + d * DAY).toISOString().slice(0, 10)
                return (
                  <span key={d} className="absolute top-0 -translate-x-1/2 text-10 font-mono text-tertiary whitespace-nowrap" style={{ left: geom.x(iso) }}>
                    {iso.slice(5)}
                  </span>
                )
              })}
              <span className="absolute top-0 -translate-x-1/2 text-10 font-mono text-status-amber" style={{ left: geom.x(geom.today) }}>{t('now')}</span>
            </div>
            <div className="relative flex flex-col gap-3">
              <div className="absolute top-0 bottom-0 w-px bg-status-amber/50 pointer-events-none" style={{ left: `calc(170px + (100% - 170px) * ${Math.min(days(geom.t0, geom.today), geom.spanDays) / geom.spanDays})` }} aria-hidden />
              {rows.map((s) => {
                const isOpen = open.has(s.id)
                const end = s.ended ?? geom.today
                const betEnd = new Date(Date.parse(s.started) + (Number(s.bet_days) || 0) * DAY).toISOString().slice(0, 10)
                const over = Number(s.bet_days) > 0 && end > betEnd
                const tone = s.status !== 'ended' ? 'var(--brand)' : over ? 'var(--status-red)' : 'var(--status-green)'
                const doneN = s.tasks.filter((t) => t.done !== null).length
                return (
                  <div key={s.id}>
                    <div className="flex items-center">
                      <div className="w-[170px] shrink-0 pr-8 flex items-baseline gap-4 min-w-0">
                        <Button
                          variant="text"
                          size="bare"
                          onClick={() => setOpen((cur) => { const n = new Set(cur); if (n.has(s.id)) n.delete(s.id); else n.add(s.id); return n })}
                          aria-expanded={isOpen}
                          aria-label={`Unfold ${s.name}`}
                          className="shrink-0"
                        >
                          {isOpen ? '▾' : '▸'}
                        </Button>
                        <button
                          type="button"
                          onClick={() => setDossier(s.id)}
                          title={t('Open the sprint\'s details')}
                          className="text-12 text-primary truncate text-left hover:text-brand hover:underline decoration-dotted"
                        >
                          {s.name}
                        </button>
                      </div>
                      <div className="relative flex-1" style={{ height: 20 }}>
                        {Number(s.bet_days) > 0 && (
                          <div
                            className="absolute rounded-pill"
                            style={{ top: 5, bottom: 5, left: geom.x(s.started), width: geom.w(s.started, betEnd < end && s.status !== 'ended' ? betEnd : (s.status === 'ended' && !over ? end : betEnd)), backgroundColor: `color-mix(in srgb, ${tone} 30%, var(--bg-elevated))`, border: `1px solid ${tone}` }}
                            title={t('{name} · planned {days}d from {start}', { name: s.name, days: s.bet_days ?? '—', start: s.started }) + (s.ended ? t(' · ended {date}', { date: s.ended }) : t(' · running'))}
                          />
                        )}
                        {over && (
                          <div className="absolute" style={{ top: 5, bottom: 5, left: geom.x(betEnd), width: geom.w(betEnd, end), background: 'repeating-linear-gradient(45deg, color-mix(in srgb, var(--status-red) 50%, transparent) 0 4px, transparent 4px 8px)', borderRadius: '0 999px 999px 0' }} aria-hidden />
                        )}
                        <span className="absolute text-10 font-mono text-tertiary whitespace-nowrap"
                          // Beside the bar's end; when that runs off the row, before the bar's start instead.
                          style={1 - geom.frac(end) < 0.25 && geom.frac(s.started) > 1 - geom.frac(end)
                            ? { right: `calc(${(1 - geom.frac(s.started)) * 100}% + 6px)`, top: 3 }
                            : { left: `calc(${geom.x(end)} + 6px)`, top: 3 }}>
                          {doneN}/{s.tasks.length}
                          {s.status === 'ended' ? (over ? ` +${days(betEnd, end)}d` : ' ✓') : ''}
                          {' · '}{hm(s.human_min)} {t('· agent')} {hm(s.agent_min)}
                        </span>
                      </div>
                    </div>
                    {isOpen && (
                      <div className="flex flex-col gap-2 mt-2 mb-4">
                        {s.tasks.length === 0 && (
                          <div className="pl-16 text-11 text-tertiary italic" style={{ marginLeft: 170 }}>{t('no tasks')}</div>
                        )}
                        {s.tasks.map((task) => (
                          <div key={task.id} className="flex items-center">
                            <div className="w-[170px] shrink-0 pr-8 pl-16 text-11 text-tertiary truncate" title={task.title}>{task.title}</div>
                            <div className="relative flex-1" style={{ height: 12 }}>
                              <div
                                className="absolute rounded-pill"
                                style={{ top: 3, bottom: 3, left: geom.x(task.joined), width: geom.w(task.joined, task.done ?? geom.today), minWidth: 4, backgroundColor: task.done !== null ? 'color-mix(in srgb, var(--status-green) 55%, transparent)' : 'color-mix(in srgb, var(--brand) 45%, transparent)' }}
                                title={`${task.title} · ${t('joined {date}', { date: task.joined })} · ${task.done !== null ? t('done {date}', { date: task.done }) : t('still open')}`}
                              />
                              {task.done !== null && (
                                <span className="absolute h-6 w-6 rounded-pill bg-status-green" style={{ left: `calc(${geom.x(task.done)} - 3px)`, top: 3 }} aria-hidden />
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <p className="text-10 font-mono text-tertiary mt-8">{t('solid: planned days · hatched: overrun · ▸ shows the tasks, from joining to done · click a name for details')}</p>
          </div>
        )}
      </Card>
      {dossier && <SprintDossier sprintId={dossier} onClose={() => setDossier(null)} />}
    </section>
  )
}

/* ---------------------------------------------------------------------------
 * The dossier — one block's full story, everything derived
 * ------------------------------------------------------------------------- */

type Dossier = {
  sprint: { id: string; name: string; status: string; started: string; ended: string | null; bet_days: number; budget_h?: number | null; ran_days: number; over_days: number }
  tasks: SpanTask[]
  human_min: number
  agent_min: number
  agents: Array<{ agent_id: string; sessions_n: number; minutes: number; turns: number }>
  events_n: number
  scans_n: number
  decisions_n: number
  git: { available: boolean; commits?: number; lines_add?: number; lines_del?: number; files_touched?: number }
  l2: string
  l3: string[]
  l4: string
}

function SprintDossier({ sprintId, onClose }: { sprintId: string; onClose: () => void }) {
  const read = useQuery({
    queryKey: ['sprints', 'dossier', sprintId],
    queryFn: ({ signal }) => getJson<Dossier>(`/api/sprints/${encodeURIComponent(sprintId)}/dossier`, signal),
  })
  const d = read.data ?? null
  const err = read.isError

  const sp = d?.sprint
  const doneN = d ? d.tasks.filter((t) => t.done !== null).length : 0
  const overBudget = !!sp?.budget_h && d !== null && d.human_min / 60 > Number(sp.budget_h)
  return (
    <Modal label={t('Sprint details')} onClose={onClose} width="w-[600px]" padding="p-20">
      <div className="flex flex-col gap-14">
        {err && <p className="text-12 text-error">{t('Could not load the sprint\'s details.')}</p>}
        {!d && !err && <LoadingSkeleton variant="row" count={4} />}
        {d && sp && (
          <>
            <div className="flex items-baseline gap-10">
              <h3 className="text-20 font-semibold text-primary">{sp.name}</h3>
              <span className={`text-11 font-mono ${sp.status === 'ended' ? (sp.over_days > 0 ? 'text-status-red' : 'text-status-green') : 'text-brand'}`}>
                {sp.status === 'ended' ? (sp.over_days > 0 ? t('ended · {n}d over plan', { n: sp.over_days }) : t('ended · on plan ✓')) : t('running')}
              </span>
              <IconButton label={t('Close')} onClick={onClose} className="ml-auto">×</IconButton>
            </div>

            {/* The plan, in numbers */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
              <Stat label={t('planned')} value={t('{n}d', { n: sp.bet_days || '—' })} sub={t('from {date}', { date: sp.started })} />
              <Stat label={t('ran')} value={t('{n}d', { n: sp.ran_days })} sub={sp.ended ? t('to {date}', { date: sp.ended }) : t('so far')} warn={sp.over_days > 0} />
              <Stat label={t('your hours')} value={hm(d.human_min)} sub={sp.budget_h ? t('of {n}h budget', { n: sp.budget_h }) : t('no budget set')} warn={overBudget} />
              <Stat label={t('agent hours')} value={hm(d.agent_min)} sub={tn(d.agents.length, '{n} agent', '{n} agents')} />
            </div>

            {/* Code, honestly */}
            <div className="rounded-input border border-border-subtle bg-elevated/50 p-10">
              <div className={`${LABEL} mb-4`}>{t('code in this period')}</div>
              {d.git.available ? (
                <div className="flex items-baseline gap-14 flex-wrap text-13 font-mono">
                  <span className="text-primary font-semibold">{d.git.commits} {t('commits')}</span>
                  <span className="text-status-green">+{d.git.lines_add}</span>
                  <span className="text-status-red">−{d.git.lines_del}</span>
                  <span className="text-secondary">{d.git.files_touched} {t('files')}</span>
                  <span className="text-10 text-tertiary">{t('Commits made during the block, across the whole repository')}</span>
                </div>
              ) : (
                <p className="text-12 text-tertiary">{t('Not available: the project folder is not a git repository.')}</p>
              )}
            </div>

            {/* The fleet */}
            <div>
              <div className={`${LABEL} mb-4`}>{t('agents on this block')}</div>
              {d.agents.length === 0 ? (
                <p className="text-12 text-tertiary">{t('No chats mention this block\'s tasks.')}</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {d.agents.map((a) => <FleetRow key={a.agent_id} row={a} />)}
                  <p className="text-10 font-mono text-tertiary">{t('Chats that mention the block\'s tasks, counted whole. Click a name for the agent\'s chat, scans and resume command.')}</p>
                </div>
              )}
            </div>

            {/* Ship */}
            <div>
              <div className={`${LABEL} mb-4`}>{t('shipped {done} of {total}', { done: doneN, total: d.tasks.length })}</div>
              <div className="flex flex-col gap-2 max-h-[180px] overflow-y-auto pr-4">
                {d.tasks.map((t) => (
                  <div key={t.id} className="flex items-center gap-8 text-12">
                    <span className={`h-8 w-8 rounded-pill shrink-0 ${t.done !== null ? 'bg-status-green' : 'border border-border-strong'}`} aria-hidden />
                    <span className={t.done !== null ? 'text-tertiary line-through' : 'text-secondary'}>{t.title}</span>
                    <span className="text-10 font-mono text-tertiary ml-auto shrink-0">{t.done !== null ? t.done.slice(5) : `open since ${t.joined.slice(5)}`}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Trail */}
            <div className="flex items-center gap-14 text-11 font-mono text-tertiary">
              <span>{tn(d.events_n, '{n} task event', '{n} task events')}</span>
              <span>{d.scans_n} {t('scans')}</span>
              <span>{d.decisions_n} {t('decisions')}</span>
              <span className="text-10">{t('in this period')}</span>
            </div>

            {(d.l3.length > 0 || d.l2) && (
              <div className="border-t border-border-subtle pt-10 flex flex-col gap-6">
                {d.l3.length > 0 && (
                  <div>
                    <div className={`${LABEL} mb-2`}>{sp.status === 'ended' ? 'goals' : 'goals'}</div>
                    {d.l3.map((g, i) => <div key={i} className="text-12 text-secondary">· {g}</div>)}
                  </div>
                )}
                {d.l2 && (
                  <p className="text-12 text-secondary leading-relaxed whitespace-pre-line">{d.l2}</p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}

/**
 * FleetRow — an agent on the block: its human name, the load it carried,
 * and (unfolded) the same drill the Agents tab has — scans, files, the
 * captured chats, and the copyable resume command.
 */
function FleetRow({ row }: { row: { agent_id: string; sessions_n: number; minutes: number; turns: number } }) {
  const [open, setOpen] = useState(false)
  // A refused read (the agent is gone) names it by id; a failed one too.
  const read = useQuery({
    queryKey: ['agent', row.agent_id],
    queryFn: ({ signal }) => getJson<AgentDetailAnswer>(`/api/agent/${encodeURIComponent(row.agent_id)}`, signal).catch(refused(null)),
  })
  const a = read.data?.agent
  const meta = read.isLoading ? null : {
    label: a ? agentLabel({
      agent_id: row.agent_id,
      agent_name: a.agent_name === row.agent_id ? '' : a.agent_name,
      chat_title: a.chat_title, created_date: a.created_date,
    }) : row.agent_id,
  }
  return (
    <div className={open ? 'rounded-input border border-border-subtle bg-elevated/40 px-8 py-4' : ''}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-baseline gap-8 text-12 text-left group"
      >
        <span className="text-10 font-mono text-tertiary shrink-0">{open ? '▾' : '▸'}</span>
        <span className="text-primary font-medium truncate group-hover:text-brand">{meta?.label ?? '…'}</span>
        <span className="font-mono text-11 text-brand shrink-0">{row.agent_id}</span>
        <span className="text-tertiary font-mono text-11 ml-auto shrink-0">{tn(row.sessions_n, '{n} chat', '{n} chats')} · {tn(row.turns, '{n} turn', '{n} turns')} · {hm(row.minutes)}</span>
      </button>
      {open && (
        <div className="pl-16 pb-4">
          <AgentDrillById agentId={row.agent_id} />
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className="rounded-input bg-elevated px-10 py-8">
      <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{label}</div>
      <div className={`text-20 font-semibold tabular leading-tight ${warn ? 'text-status-red' : 'text-primary'}`}>{value}</div>
      {sub && <div className="text-10 font-mono text-tertiary mt-1">{sub}</div>}
    </div>
  )
}
