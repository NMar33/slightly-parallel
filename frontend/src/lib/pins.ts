/**
 * Marks on one message — pins, carried messages, forks for later.
 *
 * Beside the ★ and none of them a star: #pin (come back to it), #carry /
 * #carry-brief (given back to the agent after a context compaction, whole
 * or as the brief it wrote) and #fork-later (work another agent could take,
 * with the command that starts it). One list per kind for the whole app
 * (GET /api/pins, /api/carries, /api/forks), read once and shared, like
 * `useMarks()`. A message is `<agent_id>#<turn>`; the agent's reply in that
 * turn is `<agent_id>#<turn>/reply`.
 */

import { useCallback, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { getJson, postJson } from './getJson'
import type { MentionAgent } from '../features/project/mentions'
import { t } from '../i18n/scope/shell'

export type PinList = 'pin' | 'carry' | 'fork'
export type MsgSide = '' | 'reply'
export type ForkState = '' | 'started' | 'dropped'

export interface MsgMark {
  id: string
  kind: 'pin' | 'carry' | 'carry-brief' | 'fork'
  target: string
  project: string
  agent_id: string
  session_id: string
  turn: number
  side: MsgSide
  excerpt: string
  marked_at: string
  source: string
  /** When the message was written. */
  at: string
  /** The message (its first 800 characters), and its whole length. */
  text: string
  chars: number
  agent?: MentionAgent | null
  /** Carried: the reply after a #carry message, the brief of a #carry-brief one. */
  reply?: string
  brief?: string
  brief_at?: string
  brief_by?: string
  /** Carried: the last time it was given back after a compaction, or left out. */
  given_at?: string
  left_out_at?: string
  /** Fork later: started, dropped, or '' (waiting), and the command that starts it. */
  state?: ForkState
  state_at?: string
  command?: string
  tool?: string
}

export interface CarryDelivery {
  at: string
  agent_id: string
  via: string
  given: string[]
  left_out: string[]
  chars: number
}

const PATH: Record<PinList, string> = { pin: '/api/pins', carry: '/api/carries', fork: '/api/forks' }
const key = (list: PinList) => ['msgmarks', list] as const

export const msgTarget = (agentId: string, turn: number, side: MsgSide = '') =>
  `${agentId}#${turn}${side ? `/${side}` : ''}`

/** One list, every project: the pages filter in the browser. */
export function usePinList(list: PinList) {
  return useQuery({
    queryKey: key(list),
    queryFn: ({ signal }) => getJson<{ items: MsgMark[]; deliveries?: CarryDelivery[] }>(PATH[list], signal),
    staleTime: 30_000,
  })
}

/** Every mark on a message, for the buttons: which kind each target has. */
export function useMsgMarks() {
  const pins = usePinList('pin')
  const carries = usePinList('carry')
  const forks = usePinList('fork')
  const all = useMemo(
    () => [...(pins.data?.items ?? []), ...(carries.data?.items ?? []), ...(forks.data?.items ?? [])],
    [pins.data, carries.data, forks.data],
  )
  const index = useMemo(() => new Map(all.map((m) => [`${m.kind}:${m.target}`, m])), [all])
  const of = useCallback((kind: MsgMark['kind'], target: string) => index.get(`${kind}:${target}`), [index])
  return { all, of, deliveries: carries.data?.deliveries ?? [] }
}

/** What the buttons send with a mark: the chat, the turn and a line of the message. */
export interface MsgRef {
  agent_id: string
  turn: number
  side: MsgSide
  project?: string
  session_id?: string
  excerpt?: string
}

export function useMsgMarkActions() {
  const qc = useQueryClient()
  const done = (list: PinList) => void qc.invalidateQueries({ queryKey: key(list) })
  const m = useMutation({
    mutationFn: async (v: { list: PinList; on: boolean; ref: MsgRef; level?: 'carry' | 'brief' }) => {
      const target = msgTarget(v.ref.agent_id, v.ref.turn, v.ref.side)
      if (!v.on) return postJson(`${PATH[v.list]}/remove`, { target, actor: 'operator' })
      // The chat's agent goes as `chat_agent`: an `agent_id` reads as that agent writing.
      const { agent_id, ...rest } = v.ref
      return postJson(PATH[v.list], { ...rest, chat_agent: agent_id, level: v.level, actor: 'operator' })
    },
    onSuccess: (_d, v) => done(v.list),
    onError: (e: Error) => toast.error(t('Could not change the mark: {error}', { error: e.message })),
  })
  const state = useMutation({
    mutationFn: (v: { target: string; state: ForkState }) =>
      postJson('/api/forks/state', { ...v, actor: 'operator' }),
    onSuccess: () => done('fork'),
    onError: (e: Error) => toast.error(t('Could not change the mark: {error}', { error: e.message })),
  })
  return {
    set: (list: PinList, on: boolean, ref: MsgRef, level?: 'carry' | 'brief') => m.mutate({ list, on, ref, level }),
    remove: (list: PinList, target: string) => {
      const [agent_id = '', rest = ''] = target.split('#')
      const [turn = '0', side = ''] = rest.split('/')
      m.mutate({ list, on: false, ref: { agent_id, turn: Number(turn), side: side as MsgSide } })
    },
    setState: (target: string, s: ForkState) => state.mutate({ target, state: s }),
  }
}
