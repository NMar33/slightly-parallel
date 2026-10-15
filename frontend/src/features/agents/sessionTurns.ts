/**
 * The captured turns of chats, fetched once per version of each chat —
 * what the dossier's reader and the chats page's focus mode read.
 */

import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import type { TurnWork } from '../../lib/api'

export interface SessionTurn { n: number; at: string; user: string; agent: string; work?: TurnWork }

async function fetchTurns(ids: string[], signal?: AbortSignal): Promise<Record<string, SessionTurn[]>> {
  const out: Record<string, SessionTurn[]> = {}
  // 500 ids per request is the server's cap; the reader rarely nears it.
  for (let i = 0; i < ids.length; i += 400) {
    const chunk = ids.slice(i, i + 400)
    const d = await getJson<{ turns: Record<string, SessionTurn[]> }>(`/api/sessions/turns?ids=${encodeURIComponent(chunk.join(','))}`, signal)
    Object.assign(out, d.turns)
  }
  return out
}

/**
 * The turns of several chats, each fetched once per version of it.
 *
 * A chat's version is its turn count, its last minute and its last line:
 * a new message moves them, and only that chat is asked for again. The whole history of
 * 270 chats was 3.7 MB, fetched again on every message of a live chat.
 */
const turnCache = new Map<string, { v: string; turns: SessionTurn[] }>()
const TURN_CACHE_MAX = 400
/** The oldest chats go first when the cache is full (a Map keeps insertion order). */
function cacheTurns(id: string, v: string, turns: SessionTurn[]) {
  turnCache.delete(id)
  turnCache.set(id, { v, turns })
  while (turnCache.size > TURN_CACHE_MAX) turnCache.delete(turnCache.keys().next().value!)
}
type Versioned = { id: string; turns_n?: number; end_time?: string; chat_end_line?: number }
// The last line of the chat grows with the answer too, which can land in the
// same minute as its question and change neither of the others.
const versionOf = (s: Versioned) => `${s.turns_n ?? ''}|${s.end_time ?? ''}|${s.chat_end_line ?? ''}`

export function useSessionTurns(sessions: Versioned[]) {
  const sig = sessions.map((s) => `${s.id}@${versionOf(s)}`).join(',')
  return useQuery({
    queryKey: ['session-turns', sig],
    queryFn: async ({ signal }) => {
      const stale = sessions.filter((s) => turnCache.get(s.id)?.v !== versionOf(s)).map((s) => s.id)
      if (stale.length) {
        const got = await fetchTurns(stale, signal)
        for (const id of stale) {
          const s = sessions.find((x) => x.id === id)!
          cacheTurns(id, versionOf(s), got[id] ?? [])
        }
      }
      const out: Record<string, SessionTurn[]> = {}
      for (const s of sessions) out[s.id] = turnCache.get(s.id)?.turns ?? []
      return out
    },
    enabled: sessions.length > 0,
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  })
}
