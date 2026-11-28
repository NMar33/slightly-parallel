import { isAgentMention } from '../../aqua/app/agentTerminals'
import type { FoundId } from './ids'

type Agent = { agent_id: string; agent_name?: string; chat_title?: string }
export type AgentNameLinks = (row: string) => FoundId[]

const noNames: AgentNameLinks = () => []
const index = new WeakMap<readonly Agent[], AgentNameLinks>()

/** Display names identify a chat only while the name belongs to one agent. */
export function namedAgents(agents?: readonly Agent[]): AgentNameLinks {
  if (!agents) return noNames
  const cached = index.get(agents)
  if (cached) return cached
  const labels = new Map<string, string>()
  for (const agent of agents) {
    if (!isAgentMention(agent.agent_id)) continue
    for (const name of [agent.agent_name, agent.chat_title]) {
      const label = name?.trim()
      if (!label || label === agent.agent_id || /[\r\n]/.test(label)) continue
      const known = labels.get(label)
      labels.set(label, known === undefined || known === agent.agent_id ? agent.agent_id : '')
    }
  }
  const names = [...labels.keys()].filter((label) => labels.get(label)).sort((a, b) => b.length - a.length)
  if (!names.length) {
    index.set(agents, noNames)
    return noNames
  }
  const escaped = names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const match = new RegExp(String.raw`(?<![\p{L}\p{N}_.\-/])(?:${escaped.join('|')})(?![\p{L}\p{N}_\-/])`, 'gu')
  const find: AgentNameLinks = (row) => Array.from(row.matchAll(match), (m) => ({
    id: labels.get(m[0])!, kind: 'agent', start: m.index!, length: m[0].length,
  }))
  index.set(agents, find)
  return find
}
