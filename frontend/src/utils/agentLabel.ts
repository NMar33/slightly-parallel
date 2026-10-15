import { safeParseMs } from './dateUtils'
import { dayMonth } from '../lib/months'

/**
 * Human display label for an agent.
 *
 * Priority: an operator-chosen name (agent_name differing from the raw id)
 * → the name the user gave the chat in their tool (chat_title, e.g. Claude
 * Code /rename) → a readable default for capture agents ("Claude Code ·
 * Aug 14") → the id. The id itself stays the immutable key everywhere;
 * this is presentation.
 */
export function agentLabel(agent: {
  agent_id: string
  agent_name?: string | null
  chat_title?: string | null
  created_date?: string | null
}): string {
  const name = (agent.agent_name ?? '').trim()
  if (name && name !== agent.agent_id) return name

  const title = (agent.chat_title ?? '').trim()
  if (title) return title

  // Rows written by hand or by an old version can lack an agent id.
  const id = agent.agent_id ?? ''
  const tool = toolOf(id)
  if (!tool) return id

  const ms = safeParseMs(agent.created_date ?? '')
  const day = ms
    ? dayMonth(new Date(ms))
    : ''
  return day ? `${tool} · ${day}` : tool
}

/** Which capture tool an agent id came from, by prefix; '' when unknown. */
export function toolOf(agentId: string | null | undefined): string {
  if (!agentId) return ''
  return agentId.startsWith('cc-')
    ? 'Claude Code'
    : agentId.startsWith('oc-')
      ? 'OpenCode'
      : agentId.startsWith('codex-')
        ? 'Codex'
        : agentId.startsWith('cursor-')
          ? 'Cursor'
          : ''
}
