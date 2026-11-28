import { useSyncExternalStore } from 'react'
import { getJson } from '../../../lib/getJson'
import { findIds } from '../../terminal/messageMenu/ids'
import { openNativeAgentTerminal } from './bridge'
import { isAsleep, type AquaSession } from './model'
import type { TabInfo } from './tabs/facts'

declare global {
  interface Window {
    __spDashboardAgentMenus?: boolean
  }
}

const nativeDashboard = () => typeof window !== 'undefined' && window.__spDashboardAgentMenus === true
const subscribe = (changed: () => void) => {
  window.addEventListener('sp-dashboard-agent-menus', changed)
  return () => window.removeEventListener('sp-dashboard-agent-menus', changed)
}

export const useDashboardAgentMenus = () => useSyncExternalStore(subscribe, nativeDashboard, () => false)
export const isAgentMention = (id: string) => findIds(id).some((match) => match.kind === 'agent' && match.id === id)

export function requestAgentTerminal(agent: string, tab?: string): boolean {
  if (!isAgentMention(agent)) return false
  if (openNativeAgentTerminal(agent, tab)) return true
  if (!nativeDashboard()) return false
  // Electron intercepts this request from the isolated dashboard before loading it.
  const suffix = tab ? `/${encodeURIComponent(tab)}` : ''
  window.location.assign(`/_sp/terminal-agent/${encodeURIComponent(agent)}${suffix}`)
  return true
}

const recent = (s: AquaSession) => Math.max(
  (s.last_output || 0) * 1000,
  Date.parse(s.woken_at || s.created) || 0,
)

export function agentTerminals(agent: string, sessions: AquaSession[], tabs: Record<string, TabInfo> | null) {
  return sessions.filter((s) => (s.state !== 'ended' || isAsleep(s)) && (tabs?.[s.id]?.agent_id || s.agent_id) === agent)
    .sort((a, b) => recent(b) - recent(a) || (b.created || '').localeCompare(a.created || '') || b.id.localeCompare(a.id))
}

/** Resolve again when an operation crosses into the terminal window. */
export async function readAgentTerminals(agent: string) {
  const [rows, info] = await Promise.all([
    getJson<{ sessions: AquaSession[] }>('/api/terminal/sessions'),
    getJson<{ tabs: Record<string, TabInfo> }>('/api/terminal/tabs'),
  ])
  return agentTerminals(agent, rows.sessions ?? [], info.tabs ?? null)
}
