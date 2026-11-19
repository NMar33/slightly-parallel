/**
 * What the message menu reads and does, through the routes the right
 * sidebar's «Сообщения» tab and the board already use — never an agent's:
 *
 * - the chat's recorded turns: GET /api/sessions?agent_id= and
 *   /api/sessions/turns (useSessionTurns), the record a click is matched in;
 * - pin, carry (word for word / as a summary), hand over later: the marks
 *   API (lib/pins: POST /api/pins, /api/carries, /api/forks, …/remove);
 * - a branch: the message marked to fork, the command the server gives for
 *   it (GET /api/forks: `claude -r <session> --fork-session <message>`), run
 *   in a new terminal opened in a window of its own, the fork set started;
 * - a task: POST /api/tasks as the operator (todo), the message its text,
 *   `title_from: "message"` with the message as `title_source`: the server
 *   titles it from the message for now, and the chat's agent gives the title
 *   on its next turn (backend titlelib.py);
 * - a task's card and column: GET /api/tasks/{id}, POST …/update {status};
 * - a note: the Notes page's feed (or /api/notes/{id}/full).
 *
 * The task and the branch made from a message are kept in this browser
 * (they have no mark on the server), so their mark stays on the block.
 */

import { useMemo, useSyncExternalStore } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../../lib/getJson'
import { msgTarget, useMsgMarkActions, useMsgMarks, type MsgMark, type MsgRef } from '../../../lib/pins'
import { useSessionTurns } from '../../agents/sessionTurns'
import { nowStamp, OPERATOR_ACTOR } from '../../project/types'
import { Record, type CapturedTurn, type Found } from './match'

/* ------------------------------------------------------------ the record */

interface ChatSession { id: string; agent_id: string; turns_n?: number; end_time?: string; chat_end_line?: number }

/** How many of the chat's latest sessions are searched (the sidebar shows 3). */
const SESSIONS = 6

/** The chat's recorded turns, newest sessions only, as a Record to match clicks in. */
export function useChatRecord(agentId: string) {
  const q = useQuery({
    queryKey: ['msgmenu', 'sessions', agentId],
    queryFn: ({ signal }) => getJson<{ sessions: ChatSession[] }>(`/api/sessions?agent_id=${encodeURIComponent(agentId)}`, signal),
    enabled: !!agentId,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 10_000,
  })
  const sessions = useMemo(() => [...(q.data?.sessions ?? [])].reverse().slice(-SESSIONS), [q.data])
  const turns = useSessionTurns(sessions)
  return useMemo(() => {
    const seen = new Map<number, CapturedTurn>()
    for (const s of sessions) for (const x of turns.data?.[s.id] ?? []) seen.set(x.n, { n: x.n, sid: s.id, user: x.user ?? '', agent: x.agent ?? '' })
    return { record: seen.size ? new Record([...seen.values()].sort((a, b) => a.n - b.n)) : null, loading: q.isLoading || turns.isLoading }
  }, [sessions, turns.data, q.isLoading, turns.isLoading])
}

/** The message a Found names, as the marks API takes it. */
export function refOf(agentId: string, project: string, f: Found, text: string): MsgRef {
  return { agent_id: agentId, turn: f.n, side: f.side, project, session_id: f.sid, excerpt: firstLine(text).slice(0, 160) }
}

export const firstLine = (s: string) => s.split('\n').find((l) => l.trim())?.trim() ?? ''

/* ------------------------------------------------------------ kept in this browser */

export interface Kept { tasked: { [target: string]: string }; branched: { [target: string]: true } }
const KEY = 'sp-msgmenu'
const empty = (): Kept => ({ tasked: {}, branched: {} })

function load(): Kept {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '') as Partial<Kept>
    return { tasked: { ...(v.tasked ?? {}) }, branched: { ...(v.branched ?? {}) } }
  } catch { return empty() }
}
let kept: Kept = load()
const subs = new Set<() => void>()
function keep(next: Kept) {
  kept = next
  try { localStorage.setItem(KEY, JSON.stringify(kept)) } catch { /* private window: kept for this page only */ }
  for (const l of subs) l()
}
export const useKept = () => useSyncExternalStore((l) => { subs.add(l); return () => { subs.delete(l) } }, () => kept, () => kept)
/** For tests: forget what was kept. */
export function resetKept() { keep(empty()) }

/* ------------------------------------------------------------ the marks on a message */

export type CarryLevel = 'carry' | 'brief'

export interface MessageMarks {
  pinned: boolean
  carry: CarryLevel | ''
  /** Marked to hand over later and not started yet. */
  later: boolean
  /** A branch was opened from it. */
  branched: boolean
  task: string
}

export function marksOf(of: (kind: MsgMark['kind'], target: string) => MsgMark | undefined, k: Kept, target: string): MessageMarks {
  const fork = of('fork', target)
  return {
    pinned: !!of('pin', target),
    carry: of('carry', target) ? 'carry' : of('carry-brief', target) ? 'brief' : '',
    later: !!fork && (fork.state ?? '') === '',
    branched: !!k.branched[target] || (fork?.state ?? '') === 'started',
    task: k.tasked[target] ?? '',
  }
}

/* ------------------------------------------------------------ the actions */

export interface TaskRow { id: string; title: string; status: string; project: string }

export const taskKey = (id: string) => ['msgmenu', 'task', id] as const

export function useTask(id: string, on: boolean) {
  return useQuery({
    queryKey: taskKey(id),
    queryFn: ({ signal }) => getJson<{ metadata: TaskRow; description?: string }>(`/api/tasks/${encodeURIComponent(id)}`, signal),
    enabled: on && !!id,
    staleTime: 5_000,
    retry: false,
  })
}

/** A terminal opened for a branch, and the window it shows in. */
export interface BranchOpener { open: (command: string, label: string) => Promise<boolean> }

export function useMessageActions(agentId: string, project: string) {
  const qc = useQueryClient()
  const marks = useMsgMarks()
  const act = useMsgMarkActions()
  return {
    marks,
    pin: (ref: MsgRef, on: boolean) => act.set('pin', on, ref),
    /** The same level again takes the carry off. */
    carry: (ref: MsgRef, now: CarryLevel | '', level: CarryLevel) => (now === level ? act.set('carry', false, ref) : act.set('carry', true, ref, level)),
    later: (ref: MsgRef, on: boolean) => act.set('fork', on, ref),

    /** A copy of the chat from this message, in a new terminal in its own window. Why not, or ''. */
    branch: async (ref: MsgRef, opener: BranchOpener): Promise<string> => {
      const target = msgTarget(ref.agent_id, ref.turn, ref.side)
      const had = !!marks.of('fork', target)
      if (!had) {
        const { agent_id, ...rest } = ref
        await postJson('/api/forks', { ...rest, chat_agent: agent_id, actor: OPERATOR_ACTOR })
      }
      const d = await getJson<{ items: MsgMark[] }>(`/api/forks?agent_id=${encodeURIComponent(agentId)}`)
      const item = d.items.find((m) => m.target === target)
      const undo = async () => { if (!had) await postJson('/api/forks/remove', { target, actor: OPERATOR_ACTOR }).catch(() => undefined) }
      if (!item?.command) { await undo(); void qc.invalidateQueries({ queryKey: ['msgmarks'] }); return 'no-command' }
      const ok = await opener.open(item.command, firstLine(ref.excerpt ?? ''))
      if (!ok) { await undo(); void qc.invalidateQueries({ queryKey: ['msgmarks'] }); return 'no-terminal' }
      await postJson('/api/forks/state', { target, state: 'started', actor: OPERATOR_ACTOR }).catch(() => undefined)
      keep({ ...kept, branched: { ...kept.branched, [target]: true } })
      void qc.invalidateQueries({ queryKey: ['msgmarks'] })
      return ''
    },

    /** A task in todo with the message as its text; the same message again names the task already made. */
    makeTask: async (ref: MsgRef, text: string, source: string): Promise<{ id: string; existing: boolean; title: string }> => {
      const target = msgTarget(ref.agent_id, ref.turn, ref.side)
      const was = kept.tasked[target]
      if (was) return { id: was, existing: true, title: '' }
      const { dateStr, timeStr } = nowStamp()
      const title = firstLine(text).replace(/\s+/g, ' ').slice(0, 120) || target
      const description = `${text.trim()}\n\n${source}`
      const d = await postJson<{ metadata?: { id?: string; title?: string } }>('/api/tasks', {
        project, projects: project, agent_id: OPERATOR_ACTOR, actor: OPERATOR_ACTOR, created_date: dateStr, created_time: timeStr,
        title, description, status: 'todo', priority: 'med', assignee: '', lane: 'unassigned',
        // The server's title for now, from the message; the chat's agent gives the real one.
        title_from: 'message', title_source: target,
      })
      const id = d.metadata?.id ?? ''
      if (!id) throw new Error('the task was not created')
      keep({ ...kept, tasked: { ...kept.tasked, [target]: id } })
      void qc.invalidateQueries({ queryKey: ['tasks'] })
      return { id, existing: false, title: d.metadata?.title ?? '' }
    },

    /** The operator's own column change, the board's route. */
    moveTask: async (id: string, status: string) => {
      await postJson(`/api/tasks/${encodeURIComponent(id)}/update`, { status, actor: OPERATOR_ACTOR })
      await qc.invalidateQueries({ queryKey: taskKey(id) })
      void qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  }
}
