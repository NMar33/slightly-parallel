/**
 * The Statistics page (data.ts): the numbers first, then every finished
 * task as a row — what it took in the chat, in the repository, and on the
 * calendar. It cuts by project and period, says how many rows are
 * estimated (stretch guessed from the mentions, not closed with #done),
 * and opens a task's window on a click.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { BarChart3 } from 'lucide-react'

import { PageHeader } from '../../components/PageHeader'
import { ProjectPills } from '../../components/ProjectPills'
import { Segmented } from '../../components/Segmented'
import { StatTile } from '../../components/StatTile'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { TH, TH_BUTTON } from '../../components/ui'
import { STATS_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import { useTaskOpener } from '../agents/parts'
import {
  CLOSED_COLOR, cut, hours, mins, summary, useTaskStats,
  type Cut, type Period, type TaskStat,
} from './data'


import { t } from '../../i18n/scope/views'
/* ---------------------------------------------------------------- frame */

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <StatTile label={label} value={value} sub={sub} wrapSub title={sub} />
}

function Frame({ children }: { children: (rows: TaskStat[], open: (id: string) => void) => ReactNode }) {
  useEffect(() => { document.title = t('Statistics — Slightly Parallel') }, [])
  const q = useTaskStats()
  const all = useMemo(() => q.data?.tasks ?? [], [q.data])
  const projects = useMemo(() => [...new Set(all.map((r) => r.project))].sort(
    (a, b) => all.filter((r) => r.project === b).length - all.filter((r) => r.project === a).length), [all])
  const [c, setC] = useState<Cut>({ project: '', period: 'all' })
  const project = c.project || projects[0] || ''
  const rows = useMemo(() => cut(all, { ...c, project }), [all, c, project])
  const s = summary(rows)
  const { open, modal } = useTaskOpener(project)
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader
        variant="lens" icon={BarChart3} title={t('Statistics')} count={q.data ? t('{length} finished tasks', { length: rows.length }) : ''}
        actions={(
          <Segmented label={t('Period')} shape="pill" height={20} value={c.period} onChange={(v) => setC({ ...c, period: v as Period })}
            options={[['30', t('30 days')], ['90', t('90 days')], ['all', t('all')]] as const} />
        )}
        below={projects.length > 1 ? (
          <ProjectPills projects={projects.map((p) => ({ code: p, count: cut(all, { ...c, project: p }).length }))}
            value={project} onPick={(v) => setC({ ...c, project: v })} />
        ) : undefined}
      />
      <PageGuide id="stats" guide={STATS_GUIDE} examples={0} />
      {q.isLoading && <LoadingSkeleton variant="row" count={6} />}
      {q.isError && <ErrorBanner title={t('The statistics could not be read')} onRetry={() => void q.refetch()} hideDismiss />}
      {q.data && rows.length === 0 && (
        <EmptyState icon={<BarChart3 size={24} aria-hidden />} title={t('There are no finished tasks here.')}
          subtitle={t('A task appears here once it is closed, with #done in a chat or on the board.')} />
      )}
      {rows.length > 0 && (
        <>
          <div className="grid gap-10 grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
            <Tile label={t('Finished')} value={String(s.done)} sub={t('{byDone} with #done · {v} on the board', { byDone: s.byDone, v: s.done - s.byDone })} />
            <Tile label={t('Messages a task')} value={s.messages == null ? '—' : String(Math.round(s.messages))} sub={t('median of the {inChat} worked in a chat', { inChat: s.inChat })} />
            <Tile label={t('Time in the chat')} value={mins(s.minutes)} sub={t('median active time a task')} />
            <Tile label={t('Commits a task')} value={s.commits == null ? '—' : String(Math.round(s.commits))} sub={t('median')} />
            <Tile label={t('Created → done')} value={hours(s.lead)} sub={t('median · first message → done {hours}', { hours: hours(s.work) })} />
            <Tile label={t('Reopened')} value={String(s.reopened)} sub={t('moved back out of done')} />
          </div>
          <p className="text-11 font-mono text-tertiary">
            {t('{exact} of {total} tasks worked in a chat have an exact stretch, closed with #done; the rest are estimated from where the task was named to where the next one was, and stop at the end of the chat.', { exact: s.exact, total: s.inChat })}
          </p>
          {children(rows, open)}
        </>
      )}
      {modal}
    </div>
  )
}

function Estimated({ r }: { r: TaskStat }) {
  if (r.stretch === 'done') return <span className="text-10 font-mono" style={{ color: 'var(--s-done)' }} title={t('exact: closed with #done')}>{t('exact')}</span>
  if (r.stretch === 'estimated') return <span className="text-10 font-mono text-tertiary" title={t('estimated from where the task was named')}>≈</span>
  return <span className="text-10 font-mono text-tertiary" title={t('not named in any chat')}>—</span>
}

function Closed({ r }: { r: TaskStat }) {
  if (!r.closed) return null
  return (
    <span className="inline-flex items-center gap-4 text-11 text-secondary whitespace-nowrap">
      <span className="w-8 h-8 rounded-pill" style={{ background: CLOSED_COLOR[r.closed] }} aria-hidden />
      {r.closed === '#done' ? '#done' : 'board'}
    </span>
  )
}

/* ============================================================ A · Ledger */

type Key = 'done_at' | 'messages' | 'minutes' | 'commits' | 'files' | 'lead_hours' | 'work_hours'
const COLS: Array<[Key, string]> = [
  ['done_at', t('Done')], ['messages', t('Messages')], ['minutes', t('Chat time')], ['commits', t('Commits')],
  ['files', t('Files')], ['work_hours', t('First message → done')], ['lead_hours', t('Created → done')],
]

function Ledger({ rows, open }: { rows: TaskStat[]; open: (id: string) => void }) {
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: 'done_at', desc: true })
  const sorted = useMemo(() => rows.slice().sort((a, b) => {
    const x = a[sort.key] ?? -1, y = b[sort.key] ?? -1
    return (x < y ? -1 : x > y ? 1 : 0) * (sort.desc ? -1 : 1)
  }), [rows, sort])
  const top = (k: Key) => Math.max(1, ...rows.map((r) => Number(r[k] ?? 0)))
  const bar = (r: TaskStat, k: Key) => {
    const v = Number(r[k] ?? 0)
    return <span className="absolute bottom-[4px] right-10 h-2 rounded-pill" style={{ width: `${(v / top(k)) * 70}%`, background: 'var(--border-strong)' }} aria-hidden />
  }
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12 tabular-nums">
        <thead className={`bg-surface ${TH}`}>
          <tr>
            <th className="text-left px-10 py-6 font-normal">{t('Task')}</th>
            {COLS.map(([k, w]) => (
              <th key={k} className="text-right px-10 py-6 font-normal">
                <button type="button" onClick={() => setSort({ key: k, desc: sort.key === k ? !sort.desc : true })}
                  className={`${TH_BUTTON} ${sort.key === k ? 'text-primary' : ''}`}>
                  {w}{sort.key === k ? (sort.desc ? ' ↓' : ' ↑') : ''}
                </button>
              </th>
            ))}
            <th className="text-left px-10 py-6 font-normal" title={t('How the task was closed, and whether its stretch of the chat is exact (#done) or estimated')}>{t('Closed')}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} className="border-t border-border-subtle hover:bg-hover cursor-pointer" onClick={() => open(r.id)}>
              <td className="px-10 py-6 max-w-[320px]">
                <button type="button" onClick={(e) => { e.stopPropagation(); open(r.id) }}
                  className="block w-full truncate text-left text-primary" title={r.title}>
                  {r.title || r.id}
                </button>
                <div className="text-10 font-mono text-tertiary">{r.id}{r.reopened ? ` · ${t('reopened {n}×', { n: r.reopened })}` : ''}</div>
              </td>
              <td className="px-10 py-6 text-right text-secondary whitespace-nowrap">{r.done_at.slice(5, 10).replace('-', '/')}</td>
              <td className="relative px-10 py-6 text-right">{bar(r, 'messages')}<span className="relative">{r.stretch === 'none' ? '—' : r.messages}</span></td>
              <td className="relative px-10 py-6 text-right">{bar(r, 'minutes')}<span className="relative">{r.stretch === 'none' ? '—' : mins(r.minutes)}</span></td>
              <td className="relative px-10 py-6 text-right">{bar(r, 'commits')}<span className="relative">{r.commits || '—'}</span></td>
              <td className="px-10 py-6 text-right text-secondary whitespace-nowrap" title={`+${r.add} −${r.del}`}>{r.files ? `${r.files} · +${r.add}` : '—'}</td>
              <td className="px-10 py-6 text-right text-secondary">{hours(r.work_hours)}</td>
              <td className="px-10 py-6 text-right text-secondary">{hours(r.lead_hours)}</td>
              <td className="px-10 py-6 whitespace-nowrap"><Closed r={r} />{r.closed !== '#done' && <> <Estimated r={r} /></>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The Statistics page: the ledger, chosen from three looks. */
export function StatsPage() {
  return (
    <Frame>
      {(rows, open) => <Ledger rows={rows} open={open} />}
    </Frame>
  )
}
