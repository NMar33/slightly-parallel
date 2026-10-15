import type { ReactNode } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Clock, ExternalLink, Focus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { ChatReader, type PromptMark } from '../agents/dossier'
import type { ProfileSession } from '../agents/profile'
import { useSendMarks } from '../promptlib/data'
import { fmtDay, useDrawer, useTaskOpener } from '../agents/parts'
import { fmtMinutes } from '../agents/profile'
import { ResumeButton, mentionLabel, mentionWho } from '../project/mentions'
import { useHashState } from '../../hooks/useHashState'
import { PromptScope } from '../../lenses/PromptScope'
import { lensApi, qk } from '../../lib/api'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { DayBookTitle } from '../daybook/DayBookTitle'
import { MonthBand } from '../daybook/MonthBand'
import { useDayBook } from '../daybook/useDayBook'
import { monthOfDay, projectsByNewest } from '../daybook/data'
import { PageGuide } from '../visions/parts'
import { CHATS_GUIDE } from '../visions/guides'
import { AgentPanel, type AgentLine } from './AgentPanel'
import { ChatFocus } from './focus/Focus'
import { ChatSettings, SettingsButton } from './ChatSettings'
import { isGroupKey } from '../../lib/groups'
import { messageTarget, useMarks, useMarkToggle } from '../../lib/marks'
import { StarButton } from '../../components/StarButton'
import { agentLines, gapLabel, ofAgent, producedWords, toSession, type Row } from './data'
import { paneColumns, readChatsPrefs, storeChatsPrefs, type ChatsPrefs } from './prefs'

import { t, tn } from '../../i18n/scope/views'
import { isTypingTarget } from '../../lib/typing'
/**
 * /chats — every captured chat, read as a day book.
 *
 * The page opens the way the scans and the standups open: the title, the
 * guide, then the month as a grid with the month's numbers and the days
 * that have a chat. That header scrolls away with the page; under it the
 * two panes keep their own scrollbars, so the list and the chat never
 * fight the window for height.
 *
 * What the old page kept as loose buttons is now in two places rather than
 * six: the agents are a panel you can find one in, and the reading
 * settings — both text sizes, how the width is split, the order, markdown,
 * the commits on a turn — are under the gear, in the strip the task window
 * opens.
 */

type Scope = 'one' | 'all'
const SCOPE_KEY = 'sp-sessions-scope'

export function ChatsWorkbench({ sift, aside, showDays = true, fixedProject, fixedPrompt }: {
  /** A cut the page applies to the list, from whatever stands beside the calendar. */
  sift?: (s: Row) => boolean
  /** What stands in the room the day strip would take. */
  aside?: (info: { sessions: Row[]; ofProject: Row[]; agents: AgentLine[]; picked: string;
                   onPick: (id: string) => void }) => ReactNode
  showDays?: boolean
  /** The project's own Chats tab: this project only, no switch, no guide. */
  fixedProject?: string
  /** A prompt's page: the chats that prompt was sent in, no guide. */
  fixedPrompt?: string
} = {}) {
  const [hash, setHash] = useHashState()
  const agent = hash.agent ?? ''
  const selected = hash.sel ?? ''
  const promptId = fixedPrompt || (hash.prompt ?? '')
  const q = (hash.q ?? '').trim().toLowerCase()

  const [prefs, setPrefs] = useState<ChatsPrefs>(readChatsPrefs)
  const applyPrefs = (p: ChatsPrefs) => { setPrefs(p); storeChatsPrefs(p) }
  const [settings, setSettings] = useState(false)

  const [scope, setScope] = useState<Scope>(() => {
    return readPref(SCOPE_KEY) === 'all' ? 'all' : 'one'
  })
  const pickScope = (v: Scope) => {
    setScope(v)
    persistPref(SCOPE_KEY, v)
  }

  // Every chat in one request. The project is a day book's own choice, and
  // the agent narrows in the browser, so both switch without a refetch. The
  // find is the server's question — it reads every turn, not the headline —
  // so it stays in the request, and each row says how many turns match.
  const params = useMemo(
    () => ({ prompt: promptId || undefined, q: q || undefined }),
    [promptId, q],
  )
  const list = useQuery({
    queryKey: qk.lensList('sessions', params),
    queryFn: ({ signal }) => lensApi.list('sessions', 'sessions', params, signal),
  })

  const everything = useMemo(() => (list.data?.rows ?? []).map(toSession), [list.data])
  const known = useMemo(
    () => projectsByNewest(everything, (s) => s.project, (s) => s.created_date),
    [everything],
  )
  const { project, month, showMonth, active, days, keys } = useDayBook(fixedProject ? [fixedProject] : known)

  const ofProject = useMemo(() => everything.filter((s) => s.project === project), [everything, project])
  const agents = useMemo(() => agentLines(ofProject), [ofProject])
  const star = useMarks()
  const toggleStar = useMarkToggle()
  // Newest first, like the rail on the agent page.
  const sessions = useMemo(
    () => ofProject.filter((s) => ofAgent(s, agent) && (!sift || sift(s))),
    [ofProject, agent, sift],
  )

  // ------------------------------------------------------------ the month ---
  const byDay = useMemo(() => {
    const m = new Map<string, { chats: number; turns: number; minutes: number }>()
    for (const s of sessions) {
      const d = m.get(s.created_date) ?? { chats: 0, turns: 0, minutes: 0 }
      d.chats += 1
      d.turns += s.turns_n
      d.minutes += s.duration_min
      m.set(s.created_date, d)
    }
    return m
  }, [sessions])
  const marked = useMemo(() => new Set(keys.filter((k) => byDay.has(k))), [keys, byDay])
  const totals = useMemo(() => {
    const who = new Set<string>()
    let chats = 0, turns = 0, minutes = 0, commits = 0
    for (const k of keys) {
      const d = byDay.get(k)
      if (d) { chats += d.chats; turns += d.turns; minutes += d.minutes }
      const n = days[k]
      if (n) {
        commits += n.commits_n
        for (const a of n.agents) who.add(a)
      }
    }
    return { chats, turns, minutes, commits, agents: who.size }
  }, [keys, byDay, days])

  const idx = Math.max(0, sessions.findIndex((s) => s.id === selected))
  // Focus has a filter of its own and can open a chat the page's list leaves
  // out (another agent): that chat is still the open one.
  const cur = sessions.find((s) => s.id === selected) ?? ofProject.find((s) => s.id === selected) ?? sessions[idx]
  const all = scope === 'all'

  // The prompt scope hands each row the turn that carried the prompt; the
  // reader rings it through the same hash the lens uses.
  const turnOf = (id: string) => {
    const r = (list.data?.rows ?? []).find((x) => x.id === id)
    return r && r.prompt_turn != null ? String(r.prompt_turn) : ''
  }
  const pick = (id: string) => setHash({ sel: id, turn: turnOf(id) })
  /** A day in the month, or in the strip: open the first chat of that day. */
  const pickDay = (day: string) => {
    const of = monthOfDay(day)
    const s = sessions.find((x) => x.created_date === day)
    setHash({
      day,
      ...(of && of !== month ? { month: of } : {}),
      ...(s ? { sel: s.id, turn: turnOf(s.id) } : {}),
    })
    if (s && all) pickScope('one')
  }

  // Every send of every prompt, so a turn that was a prompt says so in any
  // chat — the way from a conversation to the prompt, not only back.
  const sendMarks = useSendMarks()
  const promptMarks = useMemo(() => {
    const raw = sendMarks.data?.marks
    if (!raw) return undefined
    const out: Record<string, Record<number, PromptMark>> = {}
    for (const [sid, turns] of Object.entries(raw)) {
      for (const [turn, m] of Object.entries(turns)) {
        ;(out[sid] ??= {})[Number(turn)] = {
          promptId: m.prompt_id, title: m.title, version: m.version, exact: m.exact,
          rating: m.rating ? { task_success: m.rating.task_success, score: m.rating.score } : null,
        }
      }
    }
    return out
  }, [sendMarks.data])

  // Focus: the chat alone, full screen (focus/Focus.tsx). In the address,
  // so a reload or a link keeps it; F opens it, Esc leaves.
  const focus = hash.focus === '1'
  const setFocus = (on: boolean) => setHash({ focus: on ? '1' : '' })
  // Bound to the window once (the useFocusKeys pattern from focus/shared —
  // that hook also locks the page's scroll, so it stays inline here): the
  // listener reads the current chat and state through a ref instead of
  // re-binding on every render.
  const onKeyRef = useRef<(e: KeyboardEvent) => void>(() => {})
  onKeyRef.current = (e: KeyboardEvent) => {
    if (isTypingTarget(e)) return
    if (e.key === 'f' && !e.metaKey && !e.ctrlKey && !e.altKey && cur && !focus) { e.preventDefault(); setFocus(true) }
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => onKeyRef.current(e)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const { open: openDrawer, drawer } = useDrawer()
  const { open: openTask, modal } = useTaskOpener(cur?.project ?? project)

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <DayBookTitle icon={Clock} name={t('Chats')} count={sessions.length}
        projects={fixedProject ? [] : known} project={project}
        onProject={(v) => setHash({ project: v, agent: '', sel: '', turn: '', day: '' })}
        q={hash.q ?? ''} onFind={(v) => setHash({ q: v })}
        right={<SettingsButton open={settings} onToggle={() => setSettings((v) => !v)} />} />

      {!fixedProject && !fixedPrompt && <PageGuide id="chats" guide={CHATS_GUIDE} examples={0} />}
      {settings && <ChatSettings prefs={prefs} onChange={applyPrefs} />}
      {promptId && !fixedPrompt && (
        <PromptScope
          promptId={promptId}
          total={list.data ? list.data.total : null}
          onClear={() => setHash({ prompt: '', sel: '', turn: '' })}
        />
      )}

      <div className={`grid gap-16 min-w-0 items-start ${!aside && agents.length > 1 ? 'xl:grid-cols-[minmax(0,1fr)_300px]' : ''}`}>
        <MonthBand
          month={month} days={days} marked={marked} markWord="chat" active={active}
          onPick={pickDay} onMonth={showMonth} emptyWord={t('No chat this month.')} showDays={showDays}
          beside={aside?.({ sessions, ofProject, agents, picked: agent,
                            onPick: (id) => setHash({ agent: id, sel: '', turn: '' }) })}
          totals={<>
            <span>{totals.chats} {t('chats')}</span>
            <span>{totals.turns} {t('turns')}</span>
            <span>{fmtMinutes(totals.minutes)}</span>
            <span>{totals.agents} {t('agents')}</span>
            <span>{totals.commits} {t('commits')}</span>
          </>}
        />

        {!aside && agents.length > 1 && (
          <div className="h-[176px] min-h-0">
            <AgentPanel agents={agents} picked={agent}
              onPick={(id) => setHash({ agent: id, sel: '', turn: '' })} />
          </div>
        )}
      </div>

      {list.isLoading && !list.data && <LoadingSkeleton variant="row" count={6} />}
      {list.isError && <ErrorBanner title={t('Could not load chats')} onRetry={() => void list.refetch()} hideDismiss />}
      {list.data && sessions.length === 0 && (
        <EmptyState icon={<Clock size={24} aria-hidden />} title={t('No chats match')}
          subtitle={t('Clear the find box, or pick another agent.')} />
      )}

      {cur && (
        <div className="flex items-center gap-10 flex-wrap text-10 font-mono text-tertiary">
          {!all && (
            <>
              <span className="uppercase tracking-wide">{t('List')}</span>
              <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden">
                {(['narrow', 'even', 'wide'] as const).map((it) => (
                  <button key={it} type="button" aria-pressed={prefs.width === it}
                    onClick={() => applyPrefs({ ...prefs, width: it })}
                    className={`px-8 h-20 border-l border-border-subtle first:border-l-0 ${
                      prefs.width === it ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
                    {it}
                  </button>
                ))}
              </span>
              <span className="tabular">{sessions.length} {t('chats')}</span>
              <span className="uppercase tracking-wide ml-6">{t('Text')}</span>
              <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden">
                {([12, 14, 16] as const).map((n) => (
                  <button key={n} type="button" aria-pressed={prefs.list === n}
                    onClick={() => applyPrefs({ ...prefs, list: n })} title={t('{n}px in the list', { n })}
                    className={`px-8 h-20 border-l border-border-subtle first:border-l-0 ${
                      prefs.list === n ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
                    {n === 12 ? 'S' : n === 14 ? 'M' : 'L'}
                  </button>
                ))}
              </span>
            </>
          )}
          <span className="ml-auto uppercase tracking-wide">{t('Chat text')}</span>
          <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden shrink-0">
            {([12, 14, 16] as const).map((n) => (
              <button key={n} type="button" aria-pressed={prefs.chat === n}
                onClick={() => applyPrefs({ ...prefs, chat: n })} title={t('{n}px in the chat', { n })}
                className={`px-8 h-20 border-l border-border-subtle first:border-l-0 ${
                  prefs.chat === n ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
                {n === 12 ? 'S' : n === 14 ? 'M' : 'L'}
              </button>
            ))}
          </span>
          <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden shrink-0" role="tablist" aria-label={t('Chat scope')}>
            <button type="button" role="tab" aria-selected={!all} onClick={() => pickScope('one')}
              className={`px-8 h-20 ${!all ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
              {t('one chat')}
            </button>
            <button type="button" role="tab" aria-selected={all} onClick={() => pickScope('all')}
              className={`px-8 h-20 border-l border-border-subtle ${all ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
              {t('all')}
            </button>
          </span>
        </div>
      )}

      {cur && (
        <div
          className="grid gap-12 min-w-0 h-[72vh] min-h-[420px]"
          style={{ gridTemplateColumns: all ? 'minmax(0, 1fr)' : paneColumns(prefs.width) }}
        >
          {/* --------------------------------------------------------- list --- */}
          {!all && (
            <ol className="flex flex-col gap-1 overflow-y-auto pr-2 min-h-0" aria-label={t('Chats')}>
              {sessions.map((s, i) => {
                const on = s.id === cur.id
                const gap = i > 0 ? gapLabel(sessions[i - 1]!, s) : null
                const made = producedWords(s)
                return (
                  <li key={s.id}>
                    {gap && (
                      <div className="flex items-center gap-6 px-8 py-3 text-10 font-mono text-tertiary/70" aria-label={t('gap of {gap}', { gap })}>
                        <span className="flex-1 border-t border-dashed border-border-subtle" />
                        {gap}
                        <span className="flex-1 border-t border-dashed border-border-subtle" />
                      </div>
                    )}
                    <button type="button" onClick={() => pick(s.id)} aria-pressed={on}
                      className={`w-full text-left rounded-input px-8 py-6 flex flex-col gap-2 ${on ? 'bg-brand-glow' : 'hover:bg-hover'}`}>
                      <div className="flex items-center gap-6 text-10 font-mono text-tertiary tabular">
                        <span>{fmtDay(s.created_date)} {s.start_time}</span>
                        {(!agent || isGroupKey(agent)) && s.agent_id && (
                          <span className="text-tertiary/70 truncate" title={mentionWho(s)}>· {mentionLabel(s)}</span>
                        )}
                        <span className="ml-auto shrink-0">{s.turns_n}{t('t ·')}{' '}{fmtMinutes(s.duration_min)}</span>
                      </div>
                      <div
                        className={`leading-snug ${on ? 'text-primary' : 'text-secondary'}`}
                        style={{ fontSize: prefs.list, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                      >
                        {s.l1}
                      </div>
                      {(made.length > 0 || (q && s.matches > 0)) && (
                        <div className="flex items-center gap-4 flex-wrap text-10 font-mono">
                          {q && s.matches > 0 && (
                            <span className="px-4 py-1 rounded-input bg-brand/16 text-brand">{tn(s.matches, '{n} match', '{n} matches')}</span>
                          )}
                          {made.map((w) => (
                            <span key={w} className="px-4 py-1 rounded-input bg-elevated text-tertiary">{w}</span>
                          ))}
                        </div>
                      )}
                    </button>
                  </li>
                )
              })}
            </ol>
          )}

          {/* ------------------------------------------------------- reader --- */}
          <div className="min-h-0 rounded-card border border-border-subtle bg-surface overflow-hidden flex flex-col">
            <ChatReader
              sessions={all ? sessions.slice().reverse() : [cur]}
              onOpenLens={openDrawer}
              onOpenTask={openTask}
              // A prompt-scoped view opens on the send's turn without being told.
              markTurn={hash.turn ? Number(hash.turn) : (promptId && promptMarks?.[cur.id]
                ? Math.min(...Object.entries(promptMarks[cur.id]!).filter(([, m]) => m.promptId === promptId).map(([n]) => Number(n)))
                : undefined)}
              promptMarks={promptMarks}
              turnExtra={(sess, n, text) => {
                const row = sess as Row
                const target = messageTarget(row.agent_id, n)
                return (
                  <StarButton on={star.has('message', target)} what={t('this message')} quiet={!star.has('message', target)}
                    onToggle={(next) => toggleStar(next, 'message', target, {
                      project: row.project, agent_id: row.agent_id, session_id: row.id, turn: n,
                      excerpt: text.split('\n').find((l) => l.trim())?.trim().slice(0, 160) ?? '',
                    })} />
                )
              }}
              find={hash.q ?? ''}
              onFind={(v) => setHash({ q: v })}
              reading={{ size: prefs.chat, md: prefs.md, reverse: prefs.order === 'newest', work: prefs.work }}
              extra={(v: Row | ProfileSession) => {
                // The chat this header speaks for: the open one, or in the
                // whole history the one in view.
                const s = (sessions.find((x) => x.id === v.id) ?? cur) as Row
                return (
                  <span className="inline-flex items-center gap-6 text-10 font-mono shrink-0">
                    <button type="button" onClick={() => { if (s.id !== cur.id) pick(s.id); setFocus(true) }}
                      title={t('Focus mode: this chat alone, full screen (F)')} aria-label={t('Focus mode')}
                      className="inline-flex items-center justify-center w-20 h-20 rounded-pill border border-border-subtle text-secondary hover:text-brand hover:border-brand">
                      <Focus size={11} aria-hidden />
                    </button>
                    <Link to={`/agent/${encodeURIComponent(s.agent_id)}`} className="inline-flex items-center gap-4 px-6 h-20 rounded-pill border border-border-subtle text-secondary hover:text-primary hover:border-brand" title={mentionWho(s)}>
                      {mentionLabel(s)} <ExternalLink size={9} aria-hidden />
                    </Link>
                    <ResumeButton agent={s.agent} />
                  </span>
                )
              }}
              fill
              position={all ? undefined : { index: idx, total: sessions.length }}
              onPrev={!all && idx < sessions.length - 1 ? () => pick(sessions[idx + 1]!.id) : undefined}
              onNext={!all && idx > 0 ? () => pick(sessions[idx - 1]!.id) : undefined}
            />
          </div>
        </div>
      )}
      {focus && cur && (
        <ChatFocus session={cur} sessions={sessions} pool={ofProject} agent={agent} onPick={pick} onClose={() => setFocus(false)}
          onOpenTask={openTask}
          star={(n, text) => {
            const target = messageTarget(cur.agent_id, n)
            return (
              <StarButton on={star.has('message', target)} what={t('this message')} quiet={!star.has('message', target)}
                onToggle={(next) => toggleStar(next, 'message', target, {
                  project: cur.project, agent_id: cur.agent_id, session_id: cur.id, turn: n,
                  excerpt: text.split('\n').find((l) => l.trim())?.trim().slice(0, 160) ?? '',
                })} />
            )
          }} />
      )}
      {drawer}
      {modal}
    </div>
  )
}
