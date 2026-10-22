/**
 * The expanded agent — everything under one id, arranged for reading.
 *
 * `AgentDossier` renders seven sections as a rail: a vertical nav on the
 * left, one section at a time on the right.
 *
 * The chats section is a real reader: the captured turns of a chat,
 * user and agent, full text, with find-in-chat — not a link to elsewhere.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { persistPref } from '../../lib/uiPrefs'

import {
  DaySpark,
  DidChips,
  EntryRows,
  HourStrip,
  LinkRows,
  OriginLine,
  Stat,
  TaskRows,
  fmtDay,
} from './parts'
import { approx, fmtLines, fmtMinutes, profileHeadline, sessionLine, type AgentProfile } from './profile'
import { ChatReader } from './chatReader'
import { readPrefOr } from './chatReaderHooks'

import { t } from '../../i18n/scope/views'
import { isTypingTarget } from '../../lib/typing'
// The reader's parts live in their own files; the rest of the app reads
// them from here.
export { ChatReader } from './chatReader'
export { TaskChips, type PromptMark } from './chatMessage'
export { useSessionTurns, type SessionTurn } from './sessionTurns'
export { WorkLine } from './workLine'

export type SectionId = 'overview' | 'chats' | 'files' | 'decisions' | 'tasks' | 'work' | 'links'

interface Section {
  id: SectionId
  label: string
  count?: number
  render: () => ReactNode
}

export const SECTION_IDS: SectionId[] = ['overview', 'chats', 'files', 'decisions', 'tasks', 'work', 'links']

export function AgentDossier({
  p, range, peak, byId, onOpenLens, onOpenTask, initial = 'overview', header, section, onSectionChange, hotkeys = false,
}: {
  p: AgentProfile
  range: [number, number]
  peak: number
  byId?: Map<string, AgentProfile>
  onOpenLens: (lens: string, id: string) => void
  onOpenTask: (id: string) => void
  initial?: SectionId
  /** Slot above the sections (identity goes here). */
  header?: ReactNode
  /** Controlled section (the host keeps it, e.g. in the URL). */
  section?: SectionId
  onSectionChange?: (s: SectionId) => void
  /** Digits 1–7 switch sections (when the host is focused). */
  hotkeys?: boolean
}) {
  const tot = p.totals
  const [own, setOwn] = useState<SectionId>(initial)
  // The section survives walking the roster — only an explicit `initial`
  // change resets it.
  useEffect(() => { setOwn(initial) }, [initial])
  const active = section ?? own
  const setActive = (s: SectionId) => { setOwn(s); onSectionChange?.(s) }
  useEffect(() => {
    if (!hotkeys) return
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e) || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= SECTION_IDS.length) {
        e.preventDefault()
        const s = SECTION_IDS[n - 1]!
        setOwn(s)
        onSectionChange?.(s)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [hotkeys, onSectionChange])

  const sections: Section[] = [
    { id: 'overview', label: t('overview'), render: () => <Overview p={p} range={range} peak={peak} byId={byId} /> },
    { id: 'chats', label: t('chats'), count: tot.sessions_n, render: () => <Chats p={p} range={range} onOpenLens={onOpenLens} onOpenTask={onOpenTask} /> },
    { id: 'files', label: t('files'), count: tot.scans_n + tot.file_entries_n, render: () => <Files p={p} onOpenLens={onOpenLens} /> },
    { id: 'decisions', label: t('decisions'), count: tot.decisions_n, render: () => <Decisions p={p} onOpenLens={onOpenLens} /> },
    { id: 'tasks', label: t('tasks'), count: tot.tasks_n, render: () => <TaskRows tasks={p.tasks} onOpen={onOpenTask} /> },
    { id: 'work', label: t('features & fixes'), count: tot.architecture_n + tot.problems_n + tot.rules_n, render: () => <Work p={p} onOpenLens={onOpenLens} /> },
    { id: 'links', label: t('links and subagents'), count: tot.links_n + p.children.length + (p.parent ? 1 : 0) + p.group.members.length, render: () => <LinkRows p={p} byId={byId} /> },
  ]

  const nav = (
    <div role="tablist" aria-label={t('Sections')} className="flex flex-col gap-2 min-w-[176px]">
      {sections.map((s, i) => {
        const on = s.id === active
        return (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => setActive(s.id)}
            className={`text-12 rounded-input px-10 py-4 text-left flex items-center gap-6 ${on ? 'bg-brand-glow text-primary font-medium' : 'text-secondary hover:text-primary hover:bg-hover'}`}
          >
            {hotkeys && <kbd className={`text-10 font-mono w-12 shrink-0 ${on ? 'text-brand' : 'text-tertiary'}`}>{i + 1}</kbd>}
            <span className="truncate">{s.label}</span>
            {s.count != null && <span className={`ml-auto text-10 font-mono ${on ? 'text-brand' : 'text-tertiary'}`}>{s.count}</span>}
          </button>
        )
      })}
    </div>
  )
  const body = <div className="min-w-0 flex-1 h-full">{sections.find((s) => s.id === active)?.render()}</div>

  return (
    <div className="flex flex-col gap-12 min-w-0 h-full min-h-0">
      {header}
      <div className="flex gap-16 min-w-0 flex-1 min-h-0">
        {nav}
        <div className="min-w-0 flex-1 min-h-0 overflow-y-auto pr-4">{body}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function Overview({ p, range, peak, byId }: { p: AgentProfile; range: [number, number]; peak: number; byId?: Map<string, AgentProfile> }) {
  const tot = p.totals
  const headline = profileHeadline(p)
  const busiest = p.by_hour.indexOf(Math.max(...p.by_hour))
  return (
    <div className="flex flex-col gap-12">
      {headline && <p className="text-13 text-secondary leading-relaxed max-w-[860px]">{headline}</p>}
      <OriginLine p={p} full />
      <div className="grid grid-cols-3 md:grid-cols-6 gap-10 rounded-card border border-border-subtle bg-base/40 p-12">
        <Stat label={t('agent time')} value={`${approx(tot.minutes_approx)}${fmtMinutes(tot.minutes)}`}
          sub={sessionLine(tot.session_minutes, tot.waiting_minutes, tot.helper_minutes) || t('{chats} chats · {days} days', { chats: tot.sessions_n, days: tot.days_active })} />
        <Stat label={t('turns')} value={tot.turns} sub={t('{message_count} msgs', { message_count: p.agent.message_count })} />
        <Stat label={t('lines')} value={fmtLines(tot.lines_add, tot.lines_del)} sub={t('{files_n} files · {scans_n} scans', { files_n: tot.files_n, scans_n: tot.scans_n })} />
        <Stat label={t('features · fixes')} value={`${tot.features_n} · ${tot.bugs_resolved_n}`} sub={t('{architecture_n} arch · {problems_n} problems', { architecture_n: tot.architecture_n, problems_n: tot.problems_n })} />
        <Stat label={t('tasks')} value={tot.tasks_handed_n ? `${tot.tasks_done_n} / ${tot.tasks_handed_n}` : '—'} sub={t('done / handed')} />
        <Stat label={t('decisions')} value={tot.decisions_n} sub={t('{rules_n} rules', { rules_n: tot.rules_n })} />
      </div>
      <div className="flex items-end gap-24 flex-wrap">
        <div>
          <div className="text-10 uppercase tracking-wide font-mono text-tertiary mb-4">{t('days ·')}{' '}{fmtDay(p.agent.created_date)} → {fmtDay(p.agent.last_active)}</div>
          <DaySpark byDay={p.by_day} range={range} max={peak} width={420} height={40} />
        </div>
        <div>
          <div className="text-10 uppercase tracking-wide font-mono text-tertiary mb-4">{t('hours')}{p.by_hour.some(Boolean) ? ` · busiest ${String(busiest).padStart(2, '0')}:00` : ''}</div>
          <HourStrip byHour={p.by_hour} width={240} height={14} />
        </div>
      </div>
      <div className="flex flex-col gap-4">
        <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('posted')}</div>
        <DidChips p={p} />
      </div>
      <div className="flex flex-col gap-4">
        <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('links and subagents')}</div>
        <LinkRows p={p} byId={byId} />
      </div>
    </div>
  )
}

function Files({ p, onOpenLens }: { p: AgentProfile; onOpenLens: (lens: string, id: string) => void }) {
  return (
    <div className="grid gap-16" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
      <Block title={t('scans · {length}', { length: p.scans.length })} sub={t('what each scan reported')}>
        <EntryRows rows={p.scans} lens="scans" onOpen={onOpenLens} right={(r) => `${r.files_n}f +${r.lines_add}/−${r.lines_del}`} empty={t('No scans yet. #scan posts one.')} />
      </Block>
      <Block title={t('file entries · {length}', { length: p.files.length })} sub={t('files each scan changed, and how much each matters')}>
        <EntryRows rows={p.files} lens="files" onOpen={onOpenLens} right={(r) => `${r.files_important_n ?? 0} important`} empty={t('No file entries yet. One is written as the second part of every #scan.')} />
      </Block>
      {p.agent.files_touched.length > 0 && (
        <Block title={t('touched · {length}', { length: p.agent.files_touched.length })} sub={t('files this agent changed')}>
          <ul className="flex flex-col gap-1 max-h-[240px] overflow-y-auto">
            {p.agent.files_touched.map((f) => <li key={f} className="text-11 font-mono text-secondary truncate" title={f}>{f}</li>)}
          </ul>
        </Block>
      )}
    </div>
  )
}

function Decisions({ p, onOpenLens }: { p: AgentProfile; onOpenLens: (lens: string, id: string) => void }) {
  return (
    <div className="flex flex-col gap-12">
      {p.decisions.length === 0 ? <div className="text-12 text-tertiary italic">{t('No decisions yet. #decision logs one.')}</div> : (
        <ol className="flex flex-col gap-6">
          {p.decisions.map((d) => (
            <li key={d.id}>
              <button type="button" onClick={() => onOpenLens('decisions', d.id)} className="w-full text-left rounded-input px-8 py-6 hover:bg-hover">
                <div className="text-10 font-mono text-tertiary">{fmtDay(d.created_date)} {d.created_time ?? ''}{d.source ? ` · ${d.source}` : ''}</div>
                <div className="text-13 text-primary leading-snug">{d.decision_text}</div>
                {d.rationale && <div className="text-12 text-secondary leading-snug mt-2">{d.rationale}</div>}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function Work({ p, onOpenLens }: { p: AgentProfile; onOpenLens: (lens: string, id: string) => void }) {
  return (
    <div className="grid gap-16" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
      <Block title={t('architecture · {length}', { length: p.architecture.filter((a) => a.kind !== 'none').length })} sub={t('features and changes to how the system is built')}>
        <EntryRows rows={p.architecture.filter((a) => a.kind !== 'none')} lens="architecture" onOpen={onOpenLens} right={(r) => `${r.kind}${r.op ? ` · ${r.op}` : ''}${r.area ? ` · ${r.area}` : ''}`} empty={t('No architecture entries yet. #architecture writes one after a scan.')} />
      </Block>
      <Block title={t('problems · {length}', { length: p.problems.length })} sub={t('logged problems; solved ones count as fixes')}>
        <EntryRows rows={p.problems} lens="problems" onOpen={onOpenLens} right={(r) => `${r.severity ?? ''} · ${r.status}`} empty={t('No problems yet. #problem logs one.')} />
      </Block>
      {p.rules.length > 0 && (
        <Block title={t('rules · {length}', { length: p.rules.length })} sub={t('rules this agent wrote after a correction')}>
          <EntryRows rows={p.rules} lens="rules" onOpen={onOpenLens} right={(r) => `${r.kind ?? ''} · ${r.status ?? ''}`} />
        </Block>
      )}
    </div>
  )
}

function Block({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div>
        <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{title}</div>
        {sub && <div className="text-11 text-tertiary">{sub}</div>}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chats — the list + a reader for the captured turns
// ---------------------------------------------------------------------------

function Chats({ p, range, onOpenLens, onOpenTask }: { p: AgentProfile; range: [number, number]; onOpenLens: (lens: string, id: string) => void; onOpenTask: (id: string) => void }) {
  const sessions = useMemo(() => p.sessions.slice().reverse(), [p.sessions])
  const [picked, setPicked] = useState<string>(sessions[0]?.id ?? '')
  const [scope, setScope] = useState<'one' | 'all'>(() => (readPrefOr('sp-chat-scope', 'one') === 'all' ? 'all' : 'one'))
  const pickScope = (v: 'one' | 'all') => { setScope(v); persistPref('sp-chat-scope', v) }
  // A refreshed list keeps the chat being read; another agent's list, or a
  // chat that is gone, opens on the newest.
  useEffect(() => {
    setPicked((cur) => (sessions.some((s) => s.id === cur) ? cur : sessions[0]?.id ?? ''))
  }, [sessions])
  if (sessions.length === 0) return <div className="text-12 text-tertiary italic">{t('No messages yet')}</div>
  const idx = Math.max(0, sessions.findIndex((s) => s.id === picked))
  const cur = sessions[idx]!
  const all = scope === 'all'
  const pickDay = (date: string) => {
    const s = sessions.find((x) => x.created_date === date)
    if (s) { setPicked(s.id); if (all) pickScope('one') }
  }
  return (
    <div className="grid gap-12 min-w-0 h-full min-h-0" style={{ gridTemplateColumns: all ? 'minmax(0, 1fr)' : 'minmax(200px, 260px) minmax(0, 1fr)', gridTemplateRows: 'auto minmax(0, 1fr)' }}>
      <div className="flex items-end gap-10 min-w-0" style={{ gridColumn: '1 / -1' }}>
        <div className="min-w-0">
          <div className="text-10 uppercase tracking-wide font-mono text-tertiary mb-2">{t('days · click one to jump to its chat')}</div>
          {/* Scaled to this agent, not the fleet — inside one agent's stage
              the question is which of its days were the big ones. */}
          <DaySpark byDay={p.by_day} range={range} width={520} height={28} onPick={pickDay} picked={all ? undefined : cur.created_date} />
        </div>
        <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden shrink-0" role="tablist" aria-label={t('Chat scope')}>
          <button type="button" role="tab" aria-selected={!all} onClick={() => pickScope('one')} className={`px-8 h-20 text-10 font-mono ${!all ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>{t('per chat')}</button>
          <button type="button" role="tab" aria-selected={all} onClick={() => pickScope('all')} className={`px-8 h-20 text-10 font-mono border-l border-border-subtle ${all ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>{t('all')}</button>
        </span>
        <div className="ml-auto text-11 font-mono text-tertiary tabular whitespace-nowrap">{sessions.length} {t('sessions ·')}{' '}{fmtMinutes(p.totals.minutes)} · {p.totals.turns} {t('turns')}</div>
      </div>
      {!all && (
        <ol className="flex flex-col gap-1 overflow-y-auto pr-2 min-h-0" aria-label={t('Sessions')}>
          {sessions.map((s) => {
            const on = s.id === cur.id
            return (
              <li key={s.id}>
                <button type="button" onClick={() => setPicked(s.id)} aria-pressed={on}
                  className={`w-full text-left rounded-input px-8 py-6 flex flex-col gap-2 ${on ? 'bg-brand-glow' : 'hover:bg-hover'}`}>
                  <div className="flex items-center gap-6 text-10 font-mono text-tertiary tabular">
                    <span>{fmtDay(s.created_date)} {s.start_time}</span>
                    <span className="ml-auto" title={s.agent_min != null ? (s.helper_min ? t('Working {worked} of {total}; {waiting} waiting for you; its helpers worked {helpers} between them', { worked: fmtMinutes(s.agent_min), total: fmtMinutes(s.duration_min), waiting: fmtMinutes(s.waiting_min ?? 0), helpers: fmtMinutes(s.helper_min) }) : t('Working {worked} of {total}; {waiting} waiting for you', { worked: fmtMinutes(s.agent_min), total: fmtMinutes(s.duration_min), waiting: fmtMinutes(s.waiting_min ?? 0) })) : undefined}>
                      {s.turns_n}{t('t ·')}{' '}{s.agent_min != null ? `${approx(s.timed === 'approx')}${fmtMinutes(s.agent_min)} / ${fmtMinutes(s.duration_min)}` : fmtMinutes(s.duration_min)}
                    </span>
                  </div>
                  <div className={`text-12 leading-snug ${on ? 'text-primary' : 'text-secondary'}`} style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.l1}</div>
                </button>
              </li>
            )
          })}
        </ol>
      )}
      <ChatReader
        sessions={all ? sessions.slice().reverse() : [cur]}
        onOpenLens={onOpenLens}
        onOpenTask={onOpenTask}
        fill
        position={all ? undefined : { index: idx, total: sessions.length }}
        onPrev={!all && idx < sessions.length - 1 ? () => setPicked(sessions[idx + 1]!.id) : undefined}
        onNext={!all && idx > 0 ? () => setPicked(sessions[idx - 1]!.id) : undefined}
      />
    </div>
  )
}
