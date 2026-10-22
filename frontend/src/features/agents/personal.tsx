import { useEffect, useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { anyMs, projectRange } from './parts'
import { useAgentProfile, useAgentProfiles, type AgentProfile } from './profile'

import { t } from '../../i18n/scope/views'
export interface AgentPageData {
  p: AgentProfile
  code: string
  roster: AgentProfile[]
  /** Roster, most recently active first. */
  ordered: AgentProfile[]
  range: [number, number]
  peak: number
  byId: Map<string, AgentProfile>
  index: number
  prev?: AgentProfile
  next?: AgentProfile
}

function useAgentPage(id: string) {
  const profileQ = useAgentProfile(id)
  const p = profileQ.data ?? null
  const code = p?.agent.project ?? ''
  const rosterQ = useAgentProfiles(code)
  const roster = useMemo(() => rosterQ.data ?? (p ? [p] : []), [rosterQ.data, p])
  const data = useMemo<AgentPageData | null>(() => {
    if (!p) return null
    const ordered = roster.slice().sort((a, b) => (anyMs(b.agent.last_active) ?? 0) - (anyMs(a.agent.last_active) ?? 0))
    const byId = new Map(roster.map((x) => [x.agent.agent_id, x]))
    const index = ordered.findIndex((x) => x.agent.agent_id === p.agent.agent_id)
    return {
      p, code, roster, ordered,
      range: projectRange(roster),
      peak: Math.max(1, ...roster.flatMap((x) => x.by_day.map((d) => d.turns))),
      byId,
      index,
      prev: index > 0 ? ordered[index - 1] : undefined,
      next: index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : undefined,
    }
  }, [p, code, roster])
  return {
    data,
    loading: profileQ.isLoading,
    error: (profileQ.error as Error | null) ?? null,
    refetch: profileQ.refetch,
  }
}

/** The address of one agent's page. */
function agentHref(id: string): string {
  return `/agent/${encodeURIComponent(id)}`
}

export function PersonalFrame({
  id,
  children,
}: {
  id: string
  children: (d: AgentPageData) => ReactNode
}) {
  const { data, loading, error, refetch } = useAgentPage(id)
  useEffect(() => {
    document.title = data ? t('{v} — Slightly Parallel', { v: data.p.agent.agent_name || data.p.agent.agent_id }) : t('Agent — Slightly Parallel')
  }, [data])

  if (!id) return <EmptyState title={t('No agent at this address')} subtitle={t('Pick one from the Agents page.')} />
  if (loading) {
    return (
      <div className="flex flex-col gap-16">
        <LoadingSkeleton variant="text" count={2} label={t('Loading the agent')} />
        <LoadingSkeleton variant="kpi" label={t('Loading the numbers')} />
        <LoadingSkeleton variant="card" count={2} label={t('Loading the sections')} />
      </div>
    )
  }
  if (error || !data) {
    return (
      <ErrorBanner
        title={t('Could not load agent "{id}".', { id })}
        message={error?.message ?? t('The server returned an empty profile.')}
        onRetry={() => void refetch()}
        hideDismiss
      />
    )
  }
  return (
    <div className="flex flex-col gap-16 min-w-0">
      {children(data)}
    </div>
  )
}

/** Previous / next agent of the same project. */
export function WalkRoster({ d }: { d: AgentPageData }) {
  const { prev, next, index, ordered } = d
  return (
    <span className="inline-flex items-center gap-6 shrink-0">
      <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden">
        {prev ? (
          <Link to={agentHref(prev.agent.agent_id)} aria-label={t('Previous agent')} title={prev.agent.agent_name || prev.agent.agent_id} className="px-8 h-24 inline-flex items-center text-12 text-secondary hover:bg-hover no-underline">←</Link>
        ) : (
          <span className="px-8 h-24 inline-flex items-center text-12 text-tertiary opacity-40">←</span>
        )}
        {next ? (
          <Link to={agentHref(next.agent.agent_id)} aria-label={t('Next agent')} title={next.agent.agent_name || next.agent.agent_id} className="px-8 h-24 inline-flex items-center text-12 text-secondary hover:bg-hover border-l border-border-subtle no-underline">→</Link>
        ) : (
          <span className="px-8 h-24 inline-flex items-center text-12 text-tertiary opacity-40 border-l border-border-subtle">→</span>
        )}
      </span>
      {index >= 0 && <span className="text-10 font-mono text-tertiary tabular">{index + 1} {t('of')}{' '}{ordered.length}</span>}
    </span>
  )
}
