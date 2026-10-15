import { usePopover } from '../../hooks/usePopover'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Info, Link2, X } from 'lucide-react'
import { toast } from 'sonner'
import { useQuery } from '@tanstack/react-query'
import { getJson } from '../../lib/getJson'

import {
  AgentTimeline,
  LINK_DASH,
  type AgentMeta,
  type LaneMark,
  type LaneMarkCluster,
  type TimelineLink,
} from '../../components/AgentTimeline/AgentTimeline'
import { Modal } from '../../components/Modal'
import { Button, IconButton } from '../../components/primitives'
import { Confirm } from '../../components/Confirm'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { agentLabel } from '../../utils/agentLabel'
import { formatStamp, safeParseMs } from '../../utils/dateUtils'
import { AgentEditDialog } from '../agents/AgentEditDialog'
import {
  LINK_DEFAULT_STYLE,
  LINK_KINDS,
  LINK_KIND_HINT,
  LINK_KIND_LABEL,
  LINK_STYLES,
  useAgentLinks,
  useLinkMutations,
  type AgentLink,
  type AgentLinkKind,
  type AgentLinkStyle,
} from '../agents/links'
import { SectionHeading } from '../../components/SectionHeading'
import { TaskAddModal } from './kanban/TaskWindow'
import type { TaskRow } from './kanban/model'
import { fetchTask, useProjectTasks, type TaskLinksAnswer } from '../tasks/data'
import { foldGroups, foldLinks, foldMarks } from './timelineFold'
import { persistPref } from '../../lib/uiPrefs'
import { isGroupKey } from '../../lib/groups'
import { useMarks } from '../../lib/marks'
import { MarkLegend, markTasks, renderMarkWith, swatchWith, type MarkTask } from './agentMarks'
import { LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'

/**
 * AgentTimelinePanel — the timeline plus its operator affordances:
 * an ⓘ popover explaining where this data comes from, ✎ rename / group
 * on every lane, 👁 to the agent's page, and connect mode — click one
 * lane, click another, say why: the line is drawn in the style you pick
 * and the dot on it holds the note.
 */
const NO_MARKS: Record<string, LaneMark[]> = {}
/** No task is known yet: every mark is drawn grey. */
const NO_MARK_TASKS = new Map<string, MarkTask>()

export function AgentTimelinePanel({
  agents,
  projectCode,
}: {
  agents: AgentMeta[]
  /** When given, task mentions are drawn on the lanes, as a 3 × 3 grid
   *  coloured by each task's state. */
  projectCode?: string
}) {
  const navigate = useNavigate()
  const [editing, setEditing] = useState<AgentMeta | null>(null)
  const [openTask, setOpenTask] = useState<TaskRow | null>(null)
  const [openSession, setOpenSession] = useState<string | null>(null)

  // Connect mode — two picks make a draft, the composer makes it a link.
  const [connecting, setConnecting] = useState(false)
  const [pick, setPick] = useState<{ agent: AgentMeta; at: Date } | null>(null)
  const [draft, setDraft] = useState<{ from: AgentMeta; to: AgentMeta; fromAt: Date; toAt: Date } | null>(null)
  const [editingLink, setEditingLink] = useState<AgentLink | null>(null)

  const linksQuery = useAgentLinks(projectCode)
  const links = useMemo(() => linksQuery.data ?? [], [linksQuery.data])

  // The task mentions drawn on the lanes. Through the query cache, so a
  // new mention in a chat shows without a reload; optional — none on a failure.
  const marksQuery = useQuery({
    queryKey: ['tasks', 'mentions-by-agent', projectCode],
    queryFn: ({ signal }) =>
      getJson<{ agents?: Record<string, LaneMark[]> }>(`/api/tasks/mentions/by-agent?project=${encodeURIComponent(projectCode ?? '')}`, signal)
        .then((d) => (d?.agents && typeof d.agents === 'object' ? d.agents : NO_MARKS)),
    enabled: !!projectCode,
  })
  const marks = marksQuery.data ?? NO_MARKS

  // The marks colour each task by its state now: read the project's
  // tasks and links once.
  const markTaskRows = useProjectTasks(projectCode ?? '', !!projectCode)
  const markLinks = useQuery({
    queryKey: ['tasks', 'links', projectCode],
    queryFn: ({ signal }) =>
      getJson<TaskLinksAnswer>(`/api/tasks/links?project=${encodeURIComponent(projectCode ?? '')}`, signal)
        .then((d) => (Array.isArray(d?.links) ? d.links : [])),
    enabled: !!projectCode,
  })
  // Until both are in (or one could not be read) the marks stay grey.
  const taskInfo = useMemo<Map<string, MarkTask>>(
    () => (markTaskRows.data && markLinks.data ? markTasks(markTaskRows.data, markLinks.data) : NO_MARK_TASKS),
    [markTaskRows.data, markLinks.data],
  )
  const renderMark = useMemo(() => (projectCode ? renderMarkWith(taskInfo) : undefined), [projectCode, taskInfo])
  const markSwatch = useMemo(() => (projectCode ? swatchWith(taskInfo) : undefined), [projectCode, taskInfo])

  // Escape leaves connect mode.
  useEffect(() => {
    if (!connecting) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setConnecting(false); setPick(null) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [connecting])

  // One task → open it; a cluster → the chat turn they came from.
  const onMarkClick = (c: LaneMarkCluster) => {
    const ids = new Set(c.marks.map((m) => m.task_id))
    if (ids.size === 1) {
      // The editor needs the row as it is now (status, lane…), not the
      // mark's snapshot — fetch it, fall back to the chat when it is gone.
      const m = c.marks[0]!
      fetchTask(m.task_id)
        .then(setOpenTask)
        .catch(() => { if (m.session_id) setOpenSession(m.session_id) })
    } else if (c.marks[0]?.session_id) {
      setOpenSession(c.marks[0].session_id)
    }
  }

  // Folded groups, remembered per project: each shows as one lane.
  const foldKey = `sp-timeline-folded:${projectCode ?? ''}`
  const [folded, setFolded] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem(foldKey) || '[]') as string[]) } catch { return new Set() }
  })
  const toggleGroup = (name: string) => setFolded((cur) => {
    const next = new Set(cur)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    persistPref(foldKey, JSON.stringify([...next]))
    return next
  })

  const onConnectPick = (agent: AgentMeta, at: Date) => {
    if (isGroupKey(agent.agent_id)) { toast(t('Unfold the group to connect one of its lanes')); return }
    if (!pick) { setPick({ agent, at }); return }
    if (pick.agent.agent_id === agent.agent_id) { setPick(null); return }
    // The earlier lane is "from" whatever order the clicks came in.
    const a = pick.agent, b = agent
    const aFirst = safeParseMs(a.created_date)
    const bFirst = safeParseMs(b.created_date)
    const swap = aFirst != null && bFirst != null && bFirst < aFirst
    setDraft(swap
      ? { from: b, to: a, fromAt: at, toAt: pick.at }
      : { from: a, to: b, fromAt: pick.at, toAt: at })
    setPick(null)
    setConnecting(false)
  }

  // Lanes that named a task, the most recently active first; the list
  // shows five until it is opened.
  const touched = useMemo(() => {
    const out: Array<{ agent: AgentMeta; titles: string[]; last: string }> = []
    for (const a of agents) {
      const list = marks[a.agent_id] ?? []
      if (list.length === 0) continue
      const newest = [...list].sort((x, y) => (x.at < y.at ? 1 : x.at > y.at ? -1 : 0))
      const titles = [...new Set(newest.map((m) => m.title || m.task_id))]
      out.push({ agent: a, titles, last: newest[0]!.at })
    }
    return out.sort((x, y) => (x.last < y.last ? 1 : x.last > y.last ? -1 : 0))
  }, [agents, marks])
  const [allTouched, setAllTouched] = useState(false)
  const TOUCHED_SHOWN = 5
  // An important agent's lane says so before its name.
  const starred = useMarks().has
  const labeled = useMemo(
    () =>
      agents.map((a) => ({
        ...a,
        agent_name: `${starred('agent', a.agent_id) ? '★ ' : ''}${agentLabel(a)}`,
      })),
    [agents, starred],
  )
  const fold = useMemo(() => foldGroups(labeled, folded), [labeled, folded])
  const timelineLinks: TimelineLink[] = useMemo(
    () => foldLinks(links.map((l) => ({
      id: l.id, from_id: l.from_id, to_id: l.to_id, kind: l.kind, style: l.style,
      note: l.note, from_at: l.from_at, to_at: l.to_at,
    })), fold.laneOf),
    [links, fold],
  )
  const laneMarks = useMemo(() => foldMarks(marks, fold.laneOf), [marks, fold])

  return (
    <section aria-labelledby="overview-timeline">
      <SectionHeading>
        <span className="flex items-center gap-8 flex-wrap">
        <span id="overview-timeline" className="inline-flex items-center gap-6">
          {t('Agent timeline')}
          <TimelineInfo />
        </span>
        {projectCode && (
          <span className="ml-auto inline-flex items-center gap-8 normal-case tracking-normal font-normal">
            {connecting && (
              <span className="text-11 text-brand" role="status">
                {pick ? `From ${agentLabel(pick.agent)}. Now click the other lane` : t('Click the first lane, on its name or its bar')}
                <span className="text-tertiary"> {t('· Esc to stop')}</span>
              </span>
            )}
            <Button
              variant={connecting ? 'primary' : 'ghost'}
              size="sm"
              type="button"
              aria-pressed={connecting}
              onClick={() => { setConnecting((v) => !v); setPick(null) }}
              title={t('Link two lanes, with a note on why')}
            >
              <Link2 size={12} aria-hidden className="mr-4" />
              {connecting ? 'connecting…' : 'connect'}
            </Button>
          </span>
        )}
        </span>
      </SectionHeading>
      {/* No frame here: the timeline draws its own. */}
      <div>
        <AgentTimeline
          agents={fold.agents}
          marks={projectCode ? laneMarks : undefined}
          onMarkClick={projectCode ? onMarkClick : undefined}
          renderMark={renderMark}
          markSwatch={markSwatch}
          links={timelineLinks}
          onLinkClick={(lk) => setEditingLink(links.find((l) => l.id === lk.id) ?? null)}
          onRenameRequest={(a) => setEditing(a)}
          onOpenRequest={(a) => navigate(`/agent/${encodeURIComponent(a.agent_id)}`)}
          onGroupToggle={toggleGroup}
          folded={folded}
          connect={{ active: connecting, from: pick?.agent.agent_id ?? null }}
          onConnectPick={onConnectPick}
        />
        <p className="mt-6 text-11 text-tertiary flex flex-wrap gap-x-10 gap-y-2 items-center">
          <span>{t('One lane per chat')}</span>
          <span>{t('✎ rename / group (id stays)')}</span>
          <span>{t('click a group\'s bracket to fold it into one lane')}</span>
          <span>{t('👁 the agent\'s page')}</span>
          {links.length > 0 && <span>{t('click a line or its dot to edit the link')}</span>}
          {links.length > 0 && <LinkLegend links={links} />}
        </p>
        {projectCode && (
          <p className="mt-4 text-11 text-tertiary"><MarkLegend /></p>
        )}
        {touched.length > 0 && (
          <ul className="mt-8 flex flex-col gap-2 border-t border-border-subtle pt-8">
            {(allTouched ? touched : touched.slice(0, TOUCHED_SHOWN)).map(({ agent, titles }) => (
              <li key={agent.agent_id} className="text-11 font-mono text-tertiary truncate">
                <span className="text-secondary">{agentLabel(agent)}</span> {t('— worked on:')}{' '}
                {titles.slice(0, 5).join(' · ')}
                {titles.length > 5 ? ` +${titles.length - 5}` : ''}
              </li>
            ))}
            {touched.length > TOUCHED_SHOWN && (
              <li>
                <button type="button" onClick={() => setAllTouched((v) => !v)} className="text-11 font-mono text-brand hover:underline">
                  {allTouched ? t('show the last five') : t('show all {n}', { n: touched.length })}
                </button>
              </li>
            )}
          </ul>
        )}
      </div>
      {openTask && projectCode && (
        <TaskAddModal
          projectCode={projectCode}
          initialStatus={openTask.status || 'unclassified'}
          existingTask={openTask}
          onClose={() => setOpenTask(null)}
          onSaved={() => setOpenTask(null)}
        />
      )}
      {openSession && (
        <LensDrawer lens={LENSES['sessions']!} id={openSession} presentation="reading" onClose={() => setOpenSession(null)} />
      )}
      {editing && (
        <AgentEditDialog
          agent={agents.find((a) => a.agent_id === editing.agent_id) ?? editing}
          project={projectCode}
          onClose={() => setEditing(null)}
        />
      )}
      {draft && projectCode && (
        <LinkComposer
          project={projectCode}
          draft={draft}
          onClose={() => setDraft(null)}
        />
      )}
      {editingLink && projectCode && (
        <LinkEditor
          project={projectCode}
          link={editingLink}
          onClose={() => setEditingLink(null)}
        />
      )}
    </section>
  )
}

/* ---------------------------------------------------------------------------
 * Legend for the drawn links — every style in use, drawn as it is drawn.
 * ------------------------------------------------------------------------- */

function LinkLegend({ links }: { links: AgentLink[] }) {
  const styles = [...new Set(links.map((l) => l.style))]
  const kindsByStyle = new Map<string, Set<string>>()
  for (const l of links) {
    const s = kindsByStyle.get(l.style) ?? new Set()
    s.add(l.kind)
    kindsByStyle.set(l.style, s)
  }
  return (
    <span className="inline-flex items-center gap-8">
      {styles.map((s) => (
        <span key={s} className="inline-flex items-center gap-4">
          <svg width="26" height="8" aria-hidden>
            <line x1="1" y1="4" x2="25" y2="4" stroke="var(--text-secondary)" strokeWidth="1.5" strokeDasharray={LINK_DASH[s]} strokeLinecap="round" />
          </svg>
          <span>{[...(kindsByStyle.get(s) ?? [])].join(' / ')}</span>
        </span>
      ))}
      <span>{t('● note on the dot')}</span>
    </span>
  )
}

/* ---------------------------------------------------------------------------
 * Link composer — two lanes picked; kind, style, note; one POST.
 * ------------------------------------------------------------------------- */

function isoLocal(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`
}

function LinkComposer({
  project,
  draft,
  onClose,
}: {
  project: string
  draft: { from: AgentMeta; to: AgentMeta; fromAt: Date; toAt: Date }
  onClose: () => void
}) {
  const { create } = useLinkMutations(project)
  const [from, setFrom] = useState(draft.from)
  const [to, setTo] = useState(draft.to)
  const [kind, setKind] = useState<AgentLinkKind>('branch')
  const [style, setStyle] = useState<AgentLinkStyle>(LINK_DEFAULT_STYLE.branch)
  const [styleTouched, setStyleTouched] = useState(false)
  const [note, setNote] = useState('')
  const [anchor, setAnchor] = useState(true)

  const pickKind = (k: AgentLinkKind) => {
    setKind(k)
    if (!styleTouched) setStyle(LINK_DEFAULT_STYLE[k])
  }
  const swap = () => { setFrom(to); setTo(from) }

  const save = () => {
    create.mutate(
      {
        from: from.agent_id, to: to.agent_id, kind, style, note: note.trim(),
        from_at: anchor ? isoLocal(from === draft.from ? draft.fromAt : draft.toAt) : '',
        to_at: anchor ? isoLocal(to === draft.to ? draft.toAt : draft.fromAt) : '',
      },
      {
        onSuccess: (r) => {
          toast.success(r.created ? t('Linked') : t('This link exists. Click its dot to edit it.'))
          onClose()
        },
        onError: (e: Error) => toast.error(e.message),
      },
    )
  }

  return (
    <Modal label={t('Connect two agents')} onClose={onClose} width="w-[520px]">
      <div className="flex flex-col gap-12">
        <div className="flex items-start justify-between gap-8">
          <div>
            <h2 className="text-14 font-semibold text-primary">{t('Connect two agents')}</h2>
            <p className="text-11 text-tertiary mt-2">{t('A line between two lanes, with a note on why')}</p>
          </div>
          <IconButton label={t('Close')} size={20} onClick={onClose}>
            <X size={12} aria-hidden />
          </IconButton>
        </div>

        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-8 rounded-input border border-border-subtle bg-base px-10 py-8">
          <div className="min-w-0">
            <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('from')}</div>
            <div className="text-13 text-primary truncate">{agentLabel(from)}</div>
            <div className="text-10 font-mono text-tertiary truncate">{from.agent_id}</div>
          </div>
          <button type="button" onClick={swap} className="text-11 text-brand hover:underline px-6" title={t('Swap direction')}>⇄</button>
          <div className="min-w-0 text-right">
            <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('to')}</div>
            <div className="text-13 text-primary truncate">{agentLabel(to)}</div>
            <div className="text-10 font-mono text-tertiary truncate">{to.agent_id}</div>
          </div>
        </div>

        <fieldset className="flex flex-col gap-6">
          <legend className={`${LABEL} mb-4`}>{t('kind')}</legend>
          <div className="flex flex-wrap gap-6">
            {LINK_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => pickKind(k)}
                aria-pressed={kind === k}
                className={`rounded-pill border px-10 py-3 text-12 transition-colors ${kind === k ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary hover:bg-hover'}`}
              >
                {k}
              </button>
            ))}
          </div>
          <p className="text-11 text-tertiary">
            <span className="text-secondary">{agentLabel(kind === 'branch' ? to : from)}</span>{' '}
            {LINK_KIND_LABEL[kind]}{' '}
            <span className="text-secondary">{agentLabel(kind === 'branch' ? from : to)}</span>
            {' — '}{LINK_KIND_HINT[kind]}
          </p>
        </fieldset>

        <fieldset className="flex flex-col gap-6">
          <legend className={`${LABEL} mb-4`}>{t('line')}</legend>
          <div className="flex flex-wrap gap-6">
            {LINK_STYLES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => { setStyle(s); setStyleTouched(true) }}
                aria-pressed={style === s}
                className={`inline-flex items-center gap-8 rounded-pill border px-10 py-3 text-12 transition-colors ${style === s ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary hover:bg-hover'}`}
              >
                <svg width="34" height="8" aria-hidden>
                  <line x1="1" y1="4" x2="33" y2="4" stroke="currentColor" strokeWidth="1.5" strokeDasharray={LINK_DASH[s]} strokeLinecap="round" />
                </svg>
                {s}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="flex flex-col gap-4">
          <span className={LABEL}>{t('Note shown on the dot')}</span>
          <textarea
            autoFocus
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
            rows={3}
            maxLength={500}
            placeholder={t('e.g. Branched to write the press release')}
            className="w-full rounded-input border border-border-default bg-base px-10 py-8 text-13 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand resize-y"
          />
        </label>

        <label className="flex items-center gap-8 text-12 text-secondary">
          <input type="checkbox" checked={anchor} onChange={(e) => setAnchor(e.currentTarget.checked)} />
          {t('anchor the line where I clicked (otherwise: at the second lane\'s start)')}
        </label>

        <div className="flex items-center gap-8 justify-end">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('Cancel')}</Button>
          <Button variant="primary" size="sm" type="button" onClick={save} disabled={create.isPending}>
            {t('Draw the link')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* ---------------------------------------------------------------------------
 * Link editor — opened from a dot: change kind / style / note, or remove.
 * ------------------------------------------------------------------------- */

function LinkEditor({
  project,
  link,
  onClose,
}: {
  project: string
  link: AgentLink
  onClose: () => void
}) {
  const { update, remove } = useLinkMutations(project)
  const [kind, setKind] = useState<AgentLinkKind>(link.kind)
  const [style, setStyle] = useState<AgentLinkStyle>(link.style)
  const [note, setNote] = useState(link.note ?? '')
  const [confirm, setConfirm] = useState(false)

  const changed = kind !== link.kind || style !== link.style || note.trim() !== (link.note ?? '')
  const fromName = agentLabel(link.from as AgentMeta)
  const toName = agentLabel(link.to as AgentMeta)

  return (
    <Modal label={t('Edit link')} onClose={onClose}>
      <div className="flex flex-col gap-12">
        <div>
          <h2 className="text-14 font-semibold text-primary">
            {fromName} <span className="text-tertiary font-normal">→</span> {toName}
          </h2>
          <p className="text-11 text-tertiary font-mono mt-2">{link.id} {t('· drawn')} {formatStamp(link.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-6">
          {LINK_KINDS.map((k) => (
            <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k}
              className={`rounded-pill border px-10 py-3 text-12 ${kind === k ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary hover:bg-hover'}`}>
              {k}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-6">
          {LINK_STYLES.map((s) => (
            <button key={s} type="button" onClick={() => setStyle(s)} aria-pressed={style === s}
              className={`inline-flex items-center gap-8 rounded-pill border px-10 py-3 text-12 ${style === s ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary hover:bg-hover'}`}>
              <svg width="34" height="8" aria-hidden>
                <line x1="1" y1="4" x2="33" y2="4" stroke="currentColor" strokeWidth="1.5" strokeDasharray={LINK_DASH[s]} strokeLinecap="round" />
              </svg>
              {s}
            </button>
          ))}
        </div>
        <textarea
          autoFocus
          value={note}
          onChange={(e) => setNote(e.currentTarget.value)}
          rows={3}
          maxLength={500}
          aria-label={t('Note')}
          placeholder={t('note shown on the dot')}
          className="w-full rounded-input border border-border-default bg-base px-10 py-8 text-13 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand resize-y"
        />
        <div className="flex items-center gap-8">
          {confirm ? (
            <Confirm
              text={t('Remove this link between the two lanes.')}
              action={t('Remove')}
              onYes={() => remove.mutate(link.id, { onSuccess: () => { toast.success(t('Link removed')); onClose() }, onError: (e: Error) => toast.error(e.message) })}
              onNo={() => setConfirm(false)}
            />
          ) : (
            <Button variant="ghost" size="sm" type="button" className="text-status-red" onClick={() => setConfirm(true)}>{t('remove')}</Button>
          )}
          <span className="ml-auto" />
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('Cancel')}</Button>
          <Button
            variant="primary" size="sm" type="button" disabled={!changed || update.isPending}
            onClick={() => update.mutate(
              { id: link.id, patch: { kind, style, note: note.trim() } },
              { onSuccess: () => { toast.success(t('Link updated')); onClose() }, onError: (e: Error) => toast.error(e.message) },
            )}
          >
            {t('Save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* ---------------------------------------------------------------------------
 * ⓘ popover — what this timeline is, where the data comes from.
 * ------------------------------------------------------------------------- */

function TimelineInfo() {
  const { open, setOpen, rootRef } = usePopover()

  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        aria-label={t('About the agent timeline')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="h-20 w-20 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover transition-colors duration-fast"
      >
        <Info size={13} aria-hidden />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={t('About the agent timeline')}
          className="absolute left-0 top-[calc(100%+6px)] z-dropdown w-[480px] max-w-[90vw] rounded-card border border-border-default bg-surface shadow-lg p-16 flex flex-col gap-12 normal-case tracking-normal font-normal"
        >
          <Pipeline />
          <ul className="flex flex-col gap-4 text-12 text-secondary">
            <ScanBullet>{t('One lane per chat')}</ScanBullet>
            <ScanBullet>
              {t('Rename or group lanes freely. The')} <span className="font-mono text-11">{t('id')}</span>{' '}
              {t('underneath does not change')}
            </ScanBullet>
            <ScanBullet>
              <span className="font-mono text-11">{t('Connect')}</span> {t('draws a line between two lanes, such as a branch or a handoff, with a note on its dot')}
            </ScanBullet>
            <ScanBullet>{t('Everything stays on this computer')}</ScanBullet>
          </ul>
          <Link
            to="/guide#capture"
            className="text-12 text-brand hover:underline self-start"
          >
            {t('More in the Guide')}
          </Link>
        </div>
      )}
    </span>
  )
}

/** The capture pipeline in one glance — stages above, substance below. */
function Pipeline() {
  const stages: Array<[string, string]> = [
    [t('you ⇄ agent'), t('a hook records it')],
    ['chat.md', t('a file on your disk')],
    ['sessions', 'grouped by time'],
    ['lanes', t('this timeline')],
  ]
  return (
    <div className="flex items-start gap-4 overflow-x-auto pb-2">
      {stages.map(([stage, sub], i) => (
        <div key={stage} className="flex items-start gap-4 shrink-0">
          {i > 0 && (
            <span aria-hidden className="text-tertiary text-12 mt-2 px-2">
              →
            </span>
          )}
          <div className="flex flex-col">
            <span className="text-12 font-mono text-primary bg-elevated rounded-input px-8 py-2">
              {stage}
            </span>
            <span className="text-10 text-tertiary mt-2 px-2">{sub}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function ScanBullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-baseline gap-8">
      <span aria-hidden className="text-brand">·</span>
      <span>{children}</span>
    </li>
  )
}
