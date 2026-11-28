import { DashboardAgentMention } from '../features/terminal/messageMenu/AgentTerminalMenu'
import { useAgentNames } from '../lib/useAgentNames'

/**
 * An agent named the way the pages name it, for a row that carries only the
 * id. The id stays one hover away, in the title.
 */
export function AgentName({ id, className }: { id: string | null | undefined; className?: string }) {
  const nameOf = useAgentNames()
  const agentId = String(id ?? '')
  if (!agentId) return null
  const label = nameOf(agentId)
  return <DashboardAgentMention agent={agentId} label={label} className={className}
    fallback={<span className={className} title={agentId}>{label}</span>} />
}
