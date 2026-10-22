/**
 * Important marks — the ★ on agents, tasks and messages.
 *
 * One small list for the whole app (GET /api/marks), read once and shared:
 * every page asks `useMarks()` whether a thing is starred. A message is
 * known by its agent and turn (`<agent_id>#<turn>`); a task's star is the
 * board's own ☆ (its `remember` field). The operator stars in the chat
 * with #important, or by hand here.
 */

import { useCallback, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { getJson, postJson } from './getJson'
import { qk } from './api'
import type { MentionAgent } from '../features/project/mentions'
import { t } from '../i18n/scope/shell'

type MarkKind = 'agent' | 'task' | 'message'

export interface Mark {
  id: string
  kind: MarkKind
  target: string
  project: string
  agent_id: string
  session_id: string
  turn: number
  excerpt: string
  marked_at: string
  source: string
  task?: { id: string; title?: string; status?: string; project?: string }
  agent?: MentionAgent | null
}

/** The colour of a star, wherever it is drawn. */
export const STAR_COLOR = 'var(--star, var(--status-amber))'

const MARKS_KEY = ['marks'] as const

export const messageTarget = (agentId: string, turn: number) => `${agentId}#${turn}`

export function useMarks() {
  const q = useQuery({
    queryKey: MARKS_KEY,
    queryFn: ({ signal }) => getJson<{ marks: Mark[] }>('/api/marks', signal),
    staleTime: 30_000,
  })
  const marks = useMemo(() => q.data?.marks ?? [], [q.data])
  const index = useMemo(() => new Set(marks.map((m) => `${m.kind}:${m.target}`)), [marks])
  // Stable while the marks are: lists memoize on it.
  const has = useCallback((kind: MarkKind, target: string) => index.has(`${kind}:${target}`), [index])
  return { marks, loading: q.isLoading, has }
}

export function useMarkToggle() {
  const qc = useQueryClient()
  const m = useMutation({
    // The chat's agent goes as `chat_agent`: an `agent_id` in a body reads as
    // that agent writing, and the server turns it away (agents use MCP).
    mutationFn: ({ on, agent_id, ...body }: { on: boolean; kind: MarkKind; target: string } & Record<string, unknown>) =>
      postJson(on ? '/api/marks' : '/api/marks/unmark', { ...body, ...(agent_id ? { chat_agent: agent_id } : {}), actor: 'operator' }),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: MARKS_KEY })
      // A task's star is a task field: the board reads it too.
      if (v.kind === 'task') { void qc.invalidateQueries({ queryKey: ['tasks'] }); void qc.invalidateQueries({ queryKey: ['lens', 'tasks'] }) }
      // A message's star counts on its chat's row (the chats' ★ chip).
      if (v.kind === 'message') void qc.invalidateQueries({ queryKey: qk.lensList('sessions', {}).slice(0, 2) })
    },
    onError: (e: Error) => toast.error(t('Could not change the star: {error}', { error: e.message })),
  })
  return (on: boolean, kind: MarkKind, target: string, extra: Record<string, unknown> = {}) =>
    m.mutate({ on, kind, target, ...extra })
}
