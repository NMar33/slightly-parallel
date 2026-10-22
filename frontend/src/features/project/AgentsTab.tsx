import { AgentsStage } from '../agents/AgentsStage'
import type { Agent } from './types'

/**
 * AgentsTab — the project's agents: the cards, and a click lifts one onto
 * the stage with everything under its id (chats, files, decisions, tasks,
 * features & fixes, links).
 */
export function AgentsTab({ projectCode }: { agents: Agent[]; projectCode?: string }) {
  if (!projectCode) return null
  return (
    <div className="flex flex-col gap-16">
      <AgentsStage code={projectCode} hashPrefix="agents" />
    </div>
  )
}
