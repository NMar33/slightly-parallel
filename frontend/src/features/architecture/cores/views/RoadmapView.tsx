import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Segmented } from '../../../../components/Segmented'
import { ErrorBanner, LoadingSkeleton } from '../../../../components/states'
import { coreColor, useTimeline, type Lane, type LaneDay, type Timeline } from '../data'
import { TypeDot, typeWord } from '../parts'
import type { CoreViewProps } from './types'
import { t, tn } from '../../../../i18n/scope/system'

type Range = '14' | '30' | '90'

/**
 * The roadmap of the cores: one lane per core, the days across — how each
 * one changed. A lane shows, day by
 * day, your notes and the agents' notes, the linked tasks made and done,
 * the commits those tasks made, and the commits in the core's files that no
 * linked task made (paler). Tracking shows as a tint behind the days it was
 * on. Above the lanes: the day's standup and the release tags. A click on a
 * day shows what happened to every core that day; a click on a name opens
 * the core.
 */
export function RoadmapView({ projectCode, cores, show, onOpen }: CoreViewProps) {
  const [range, setRange] = useState<Range>('30')
  const [picked, setPicked] = useState('')
  const { data, isLoading, isError, error, refetch } = useTimeline(projectCode, Number(range))

  if (isError) return <ErrorBanner title={t('Could not load the lanes.')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss />
  if (isLoading || !data) return <LoadingSkeleton variant="row" count={6} />
  return <Lanes data={data} cores={cores} show={show} range={range} setRange={setRange} picked={picked} setPicked={setPicked} onOpen={onOpen} projectCode={projectCode} />
}

function Lanes({ data, cores, show, range, setRange, picked, setPicked, onOpen, projectCode }: {
  data: Timeline; cores: CoreViewProps['cores']; show: CoreViewProps['show']
  range: Range; setRange: (r: Range) => void
  picked: string; setPicked: (d: string) => void; onOpen: (id: string) => void; projectCode: string
}) {
  const wanted = useMemo(() => new Set(cores.filter((c) => c.status === 'view').map((c) => c.id)), [cores])
  const lanes = useMemo(() => data.lanes.filter((l) => wanted.has(l.id)), [data.lanes, wanted])
  const dense = data.days.length > 45
  const releases = useMemo(() => new Map(data.releases.map((r) => [r.day, r.name])), [data.releases])
  // The day shown under the lanes: the one clicked, else the latest with anything on it.
  const day = picked && data.days.includes(picked) ? picked
    : [...data.days].reverse().find((d) => lanes.some((l) => weight(l.days[d]) > 0)) ?? data.last
  const cols = `220px repeat(${data.days.length}, minmax(0, 1fr))`

  return (
    <div className="flex flex-col gap-14 min-w-0">
      <div className="flex items-center gap-14 flex-wrap text-11 font-mono text-tertiary">
        <Segmented label={t('Days')} shape="pill" value={range} onChange={setRange}
          options={[['14', t('2 weeks')], ['30', t('30 days')], ['90', t('90 days')]]} />
        <Legend />
      </div>

      <div className="rounded-card border border-border-subtle overflow-x-auto">
        <div className="relative min-w-[880px]">
          <div className="grid items-end h-[26px] border-b border-border-subtle bg-surface" style={{ gridTemplateColumns: cols }}>
            <span className="px-12 pb-4 text-10 font-mono uppercase tracking-wider text-tertiary">{monthLabel(data.first, data.last)}</span>
            {data.days.map((d) => (
              <button key={d} type="button" onClick={() => setPicked(d)} title={d} aria-label={d}
                className={`h-full flex items-end justify-center pb-4 text-10 font-mono ${d === day ? 'text-primary bg-elevated' : weekend(d) ? 'text-tertiary opacity-60' : 'text-tertiary'}`}>
                {dayLabel(d, dense)}
              </button>
            ))}
          </div>
          <div className="grid items-center h-[22px] border-b border-border-subtle" style={{ gridTemplateColumns: cols }}>
            <span className="px-12 text-10 font-mono uppercase tracking-wider text-tertiary">{t('standup')}</span>
            {data.days.map((d) => {
              const st = data.standups[d]
              return (
                <button key={d} type="button" onClick={() => setPicked(d)} title={st ? `${d} · ${st.summary}` : d}
                  aria-label={st ? t('Standup for {day}', { day: d }) : t('No standup for {day}', { day: d })}
                  className="h-full flex items-center justify-center">
                  <i className={`block h-[6px] rounded-[2px] ${dense ? 'w-[70%]' : 'w-[14px]'} ${st ? 'bg-border-strong' : 'border border-border-subtle'}`} />
                </button>
              )
            })}
          </div>

          {lanes.map((lane) => (
            <LaneRow key={lane.id} lane={lane} days={data.days} cols={cols} dense={dense} day={day} show={show}
              onPick={setPicked} onOpen={() => onOpen(lane.id)} />
          ))}

          {/* A release: a line down every lane, its tag at the top. */}
          {data.days.map((d, i) => releases.has(d) && (
            <div key={d} aria-hidden="true" className="absolute top-[26px] bottom-0 pointer-events-none"
              style={{ left: `calc(220px + (100% - 220px) * ${(i + 0.5) / data.days.length})` }}>
              <div className="absolute top-0 bottom-0 border-l-2 border-primary" />
              <span className="absolute top-[2px] left-[4px] whitespace-nowrap rounded-[3px] bg-primary px-4 text-10 font-mono text-base">{releases.get(d)}</span>
            </div>
          ))}
        </div>
      </div>

      <DayPanel day={day} data={data} lanes={lanes} show={show} projectCode={projectCode} onOpen={onOpen} />
    </div>
  )
}

function LaneRow({ lane, days, cols, dense, day, show, onPick, onOpen }: {
  lane: Lane; days: string[]; cols: string; dense: boolean; day: string; show: CoreViewProps['show']
  onPick: (d: string) => void; onOpen: () => void
}) {
  const color = coreColor(lane.type)
  const tracked = (d: string) => lane.tracking_spans.some((s) => s.from <= d && d <= s.to)
  return (
    <div className="grid border-b border-border-subtle last:border-b-0 h-[58px]" style={{ gridTemplateColumns: cols }}>
      <button type="button" onClick={onOpen} className="flex flex-col justify-center gap-2 px-12 text-left hover:bg-surface min-w-0">
        <span className="flex items-center gap-8 text-13 font-semibold text-primary min-w-0">
          <TypeDot type={lane.type} /><span className="truncate">{lane.name}</span>
        </span>
        <span className="text-10 font-mono text-tertiary truncate pl-[18px]">
          {lane.tracking.on
            ? <span className="text-brand">{t('tracking')} · {lane.tracking.days_left == null ? t('no expiry') : tn(lane.tracking.days_left, '{n} day left', '{n} days left')}</span>
            : `${typeWord(lane.type)} · ${tn(lane.totals.commits, '{n} commit', '{n} commits')}`}
        </span>
      </button>
      {days.map((d) => {
        const cell = lane.days[d]
        return (
          <button key={d} type="button" onClick={() => onPick(d)} title={cellTitle(d, cell)} aria-label={`${lane.name} · ${cellTitle(d, cell)}`}
            className={`flex flex-col items-center justify-center gap-4 border-l border-border-subtle ${d === day ? 'bg-elevated' : ''}`}
            style={tracked(d) ? { background: 'var(--brand-glow)' } : d < lane.created ? { opacity: 0.35 } : undefined}>
            {dense ? <Density cell={cell} color={color} /> : <Marks cell={cell} color={color} show={show} />}
          </button>
        )
      })}
    </div>
  )
}

/** A day at 90 days: one square, stronger with more on it. */
function Density({ cell, color }: { cell?: LaneDay; color: string }) {
  const n = weight(cell)
  if (!n) return null
  return <i className="block w-[70%] max-w-[12px] aspect-square rounded-[2px]" style={{ background: color, opacity: n >= 6 ? 1 : n >= 3 ? 0.7 : 0.42 }} />
}

function Marks({ cell, color, show }: { cell?: LaneDay; color: string; show: CoreViewProps['show'] }) {
  if (!cell) return null
  const notes = (cell.notes ?? []).filter((n) => show === 'everyone' || n.approved)
  const mine = notes.some((n) => n.operator)
  const theirs = notes.filter((n) => !n.operator)
  const done = cell.done?.length ?? 0
  const made = cell.made?.length ?? 0
  const commits = cell.commits?.length ?? 0
  const nearby = cell.nearby?.length ?? 0
  return (
    <>
      <span className="flex items-center gap-[3px] h-[10px]">
        {mine && <i className="block w-[9px] h-[9px] rounded-full" style={{ background: color }} />}
        {theirs.length > 0 && (
          <i className="block w-[9px] h-[9px] rounded-full"
            style={{ border: `1.5px ${theirs.some((n) => !n.approved) ? 'dashed' : 'solid'} ${color}` }} />
        )}
        {done > 0 && <i className="block w-[9px] h-[9px] rounded-[2px] bg-status-green" />}
        {made > 0 && done === 0 && <i className="block w-[9px] h-[9px] rounded-[2px] border border-border-strong" />}
      </span>
      <span className="flex items-end gap-[2px] h-[10px]">
        {Array.from({ length: Math.min(commits, 4) }, (_, i) => <i key={i} className="block w-[2px] h-[10px] bg-secondary" />)}
        {commits > 4 && <span className="text-[9px] leading-none font-mono text-secondary">+{commits - 4}</span>}
        {commits === 0 && nearby > 0 && <i className="block w-[2px] h-[6px] bg-border-strong" />}
      </span>
    </>
  )
}

function Legend() {
  return (
    <span className="flex items-center gap-14 flex-wrap">
      <span className="flex items-center gap-6"><i className="block w-[9px] h-[9px] rounded-full bg-secondary" />{t('your note')}</span>
      <span className="flex items-center gap-6"><i className="block w-[9px] h-[9px] rounded-full" style={{ boxShadow: 'inset 0 0 0 1.5px var(--text-secondary)' }} />{t('agent note')}</span>
      <span className="flex items-center gap-6"><i className="block w-[9px] h-[9px] rounded-[2px] bg-status-green" />{t('task done')}</span>
      <span className="flex items-center gap-6"><i className="block w-[9px] h-[9px] rounded-[2px] border border-border-strong" />{t('new task')}</span>
      <span className="flex items-center gap-6"><i className="block w-[2px] h-[10px] bg-secondary" />{t('commit of a linked task')}</span>
      <span className="flex items-center gap-6"><i className="block w-[2px] h-[6px] bg-border-strong" />{t('commit in its files only')}</span>
      <span className="flex items-center gap-6"><i className="block w-[16px] h-[9px]" style={{ background: 'var(--brand-glow)' }} />{t('tracking on')}</span>
    </span>
  )
}

/** What happened on one day, to every core. */
function DayPanel({ day, data, lanes, show, projectCode, onOpen }: {
  day: string; data: Timeline; lanes: Lane[]; show: CoreViewProps['show']; projectCode: string; onOpen: (id: string) => void
}) {
  const standup = data.standups[day]
  const release = data.releases.find((r) => r.day === day)
  const busy = lanes.filter((l) => weight(l.days[day]) > 0 || (l.days[day]?.nearby?.length ?? 0) > 0)
  const task = (id: string) => `/project/${encodeURIComponent(projectCode)}#task=${encodeURIComponent(id)}`
  return (
    <section aria-label={t('The selected day')} className="flex flex-col gap-12 rounded-card border border-border-subtle bg-surface p-16">
      <div className="flex items-baseline gap-12 flex-wrap">
        <h3 className="m-0 text-16 font-semibold text-primary">{longDay(day)}</h3>
        {release && <span className="rounded-[3px] bg-primary px-6 text-11 font-mono text-base">{release.name}</span>}
        <span className="text-12 text-secondary min-w-0">{standup ? standup.summary : t('No standup for this day.')}</span>
      </div>
      {busy.length === 0 ? (
        <p className="m-0 text-12 text-tertiary">{t('Nothing happened to the cores on this day.')}</p>
      ) : (
        <div className="grid gap-14" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {busy.map((l) => {
            const c = l.days[day] ?? {}
            const notes = (c.notes ?? []).filter((n) => show === 'everyone' || n.approved)
            return (
              <div key={l.id} className="flex flex-col gap-6 min-w-0">
                <button type="button" onClick={() => onOpen(l.id)} className="flex items-center gap-6 text-left text-10 font-mono uppercase tracking-wider" style={{ color: coreColor(l.type) }}>
                  <TypeDot type={l.type} size={8} />{l.name}
                </button>
                {notes.map((n) => (
                  <p key={n.id} className={`m-0 text-12 text-primary break-words ${n.operator ? '' : 'rounded-input px-6 py-4'}`}
                    style={n.operator ? undefined : { background: 'var(--brand-glow)' }}>
                    {n.text}
                    <span className="ml-6 text-10 font-mono text-tertiary">{n.operator ? t('you') : n.approved ? t('agent · approved') : t('agent · to approve')}</span>
                  </p>
                ))}
                {(c.done ?? []).map((tk) => (
                  <Link key={`d${tk.id}`} to={task(tk.id)} className="text-12 text-primary no-underline hover:text-brand">
                    <span className="text-10 font-mono mr-6" style={{ color: 'var(--status-green-ink)' }}>{t('done')}</span>{tk.title}
                  </Link>
                ))}
                {(c.made ?? []).map((tk) => (
                  <Link key={`m${tk.id}`} to={task(tk.id)} className="text-12 text-secondary no-underline hover:text-brand">
                    <span className="text-10 font-mono text-tertiary mr-6">{t('new task')}</span>{tk.title}
                  </Link>
                ))}
                {(c.commits ?? []).slice(0, 4).map((cm) => (
                  <span key={cm.sha} className="text-11 font-mono text-secondary truncate" title={cm.subject}>{cm.sha} · {cm.subject}</span>
                ))}
                {(c.commits?.length ?? 0) > 4 && <span className="text-10 font-mono text-tertiary">{tn((c.commits?.length ?? 0) - 4, '{n} more commit', '{n} more commits')}</span>}
                {(c.nearby?.length ?? 0) > 0 && (
                  <span className="text-10 font-mono text-tertiary">{tn(c.nearby?.length ?? 0, '{n} commit in its files, not linked to a task', '{n} commits in its files, not linked to a task')}</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function weight(cell?: LaneDay): number {
  if (!cell) return 0
  return (cell.notes?.length ?? 0) * 2 + (cell.done?.length ?? 0) * 2 + (cell.made?.length ?? 0) + (cell.commits?.length ?? 0)
}

function cellTitle(day: string, cell?: LaneDay): string {
  if (!cell) return day
  const parts = [day]
  if (cell.notes?.length) parts.push(tn(cell.notes.length, '{n} note', '{n} notes'))
  if (cell.done?.length) parts.push(tn(cell.done.length, '{n} task done', '{n} tasks done'))
  if (cell.made?.length) parts.push(tn(cell.made.length, '{n} new task', '{n} new tasks'))
  if (cell.commits?.length) parts.push(tn(cell.commits.length, '{n} commit', '{n} commits'))
  if (cell.nearby?.length) parts.push(tn(cell.nearby.length, '{n} commit in its files', '{n} commits in its files'))
  return parts.join(' · ')
}

function weekend(iso: string): boolean {
  const d = new Date(`${iso}T00:00:00`).getDay()
  return d === 0 || d === 6
}

function dayLabel(iso: string, dense: boolean): string {
  const n = Number(iso.slice(8, 10))
  if (!dense) return String(n)
  return new Date(`${iso}T00:00:00`).getDay() === 1 ? String(n) : ''
}

function monthLabel(first: string, last: string): string {
  return first.slice(0, 7) === last.slice(0, 7) ? first.slice(0, 7) : `${first.slice(0, 7)} – ${last.slice(5, 7)}`
}

function longDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return `${d.toLocaleDateString(undefined, { weekday: 'long' })}, ${iso}`
}
