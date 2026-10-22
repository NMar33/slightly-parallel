import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { agentLabel } from '../utils/agentLabel'
import { api, qk } from './api'

/**
 * An agent's id as the pages name it: the operator's rename, else the
 * chat's title, else "Claude Code · Sep 14", else the id.
 *
 * For rows that carry only `agent_id`. It reads the snapshot every page
 * already polls, so it costs no request of its own. Until that arrives, or
 * for an agent the snapshot does not hold, the id stands — never a worse
 * label than before.
 */
export function useAgentNames(): (agentId: string | null | undefined) => string {
  const snapshot = useQuery({
    queryKey: qk.snapshot(),
    queryFn: ({ signal }) => api.snapshot(signal),
    staleTime: 5 * 60_000,
  })
  const agents = snapshot.data?.agents
  const byId = useMemo(
    () => new Map((agents ?? []).map((a) => [a.agent_id, a])),
    [agents],
  )
  return useCallback((agentId) => {
    const id = String(agentId ?? '')
    if (!id) return ''
    const agent = byId.get(id)
    return agent ? agentLabel(agent) : id
  }, [byId])
}
