import { useSyncExternalStore } from 'react'

import { ApiError } from './getJson'

export const TERMINAL_AGENT_KINDS = ['claude', 'codex', 'opencode', 'shell'] as const
export type TerminalAgentKind = typeof TERMINAL_AGENT_KINDS[number]

export interface TerminalLimitSession {
  id: string
  label: string
  project: string
  agent_id: string
  agent_kind: TerminalAgentKind
  created: string
  last_activity: number | null
  last_opened: number | null
  attached: boolean
  attachment_known?: boolean
  running: boolean
  recent_output: boolean
  activity: number
  memory_bytes: number | null
}

export interface TerminalMemory {
  total: number | null
  available: number | null
  used: number
  kinds: Record<TerminalAgentKind, { count: number; measured: number; bytes: number }>
}

interface TerminalRequest {
  label?: string
  project?: string
  kind?: string
  agent_kind?: TerminalAgentKind
}

interface LimitRefusal {
  count: number
  limit: number
  maximum: number
  sessions: TerminalLimitSession[]
  requested?: TerminalRequest
}

export interface TerminalLimitSnapshot extends LimitRefusal {
  memory: TerminalMemory
}

export interface PendingTerminal extends LimitRefusal {
  requested: TerminalRequest
  retry: () => Promise<void>
  cancel: () => void
}

let current: PendingTerminal | null = null
const listeners = new Set<() => void>()

function publish(limit: PendingTerminal | null) {
  current = limit
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export const terminalLimitPending = () => current

export function useTerminalLimit() {
  return useSyncExternalStore(subscribe, terminalLimitPending)
}

function refusal(error: unknown): LimitRefusal | undefined {
  if (!(error instanceof ApiError) || error.status !== 429) return
  const body = error.body as Partial<LimitRefusal> | null
  if (!body || typeof body.count !== 'number' || typeof body.limit !== 'number'
    || typeof body.maximum !== 'number' || !Array.isArray(body.sessions)) return
  return { count: body.count, limit: body.limit, maximum: body.maximum, sessions: body.sessions, requested: body.requested }
}

/** The caller still owns the open result, including where to put its tab. */
export async function openWithTerminalLimit<T>(requested: TerminalRequest, send: () => Promise<T>): Promise<T | null> {
  if (current) return null
  try {
    return await send()
  } catch (error) {
    const info = refusal(error)
    if (!info) throw error
    if (current) return null
    return new Promise((resolve, reject) => {
      let retrying = false
      const cancel = () => {
        if (!retrying && current?.cancel === cancel) {
          publish(null)
          resolve(null)
        }
      }
      const retry = async () => {
        if (retrying || current?.retry !== retry) return
        retrying = true
        try {
          const opened = await send()
          publish(null)
          resolve(opened)
        } catch (e) {
          const limit = refusal(e)
          if (limit) publish({ ...limit, requested: { ...requested, ...limit.requested }, retry, cancel })
          else {
            publish(null)
            reject(e)
          }
        } finally {
          retrying = false
        }
      }
      publish({ ...info, requested: { ...requested, ...info.requested }, retry, cancel })
    })
  }
}
