/**
 * The tab strip's facts (tk_a9306fb1, from the round 3 lab's `live.ts`, on
 * real data).
 *
 * - A tab's title is the chat's own name: the title the program in the
 *   terminal set (OSC 0/2 — Claude Code sets the chat's name). The page sees
 *   it live for the terminal in front (xterm's onTitleChange); tmux keeps it
 *   for every terminal (`GET /api/terminal/tabs`, pane_title). When no
 *   program set one, the chat's name in Slightly Parallel; never the
 *   project's name. A name the operator gave the tab (rename) wins over all.
 * - Facts per tab: branches, tasks closed of all (the chat's, as its profile
 *   counts them), minutes waited for an answer (since the terminal last
 *   printed, while it waits), context used (Claude Code's status line; null
 *   when not known), and the chat's last six hours for the six dots
 *   (tk_d2e11125, ./rhythm.ts).
 */

import { useQuery } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'

import { getJson } from '../../../../lib/getJson'
import { persistPref } from '../../../../lib/uiPrefs'
import { roleOf, shownOf, type AquaSession } from '../model'
import type { Period, Rhythm } from './rhythm'

export interface ChatFacts {
  name: string
  tool: string
  tasks_done: number
  tasks_all: number
  branches: number
  ctx_pct: number | null
  ctx_size: number | null
  ctx_at: string
  /** The last six clock hours (tk_d2e11125); absent on an older server. */
  rhythm?: Rhythm
}
export interface TabInfo { title: string; agent_id: string; chat: ChatFacts | null }

/** The strip's read: every terminal's title and chat facts. Absent on an older server: null. */
export function useTabInfo() {
  const q = useQuery({
    queryKey: ['terminal', 'tabs-info'],
    queryFn: ({ signal }) => getJson<{ tabs: Record<string, TabInfo> }>('/api/terminal/tabs', signal).then((d) => d.tabs ?? {}),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 4000,
    retry: false,
  })
  return q.data ?? null
}

/* ------------------------------------------------------------ titles the page saw */

const OSC_KEY = 'spw-osc-titles'
let osc: Record<string, string> = {}
let oscRaw: string | null | undefined
const oscListeners = new Set<() => void>()
/** The cache follows localStorage: a value written elsewhere (or cleared) is read again. */
function readOsc(): Record<string, string> {
  let raw: string | null = null
  try { raw = localStorage.getItem(OSC_KEY) } catch { /* private mode */ }
  if (raw === oscRaw) return osc
  oscRaw = raw
  try {
    const v = JSON.parse(raw ?? 'null') as unknown
    osc = v && typeof v === 'object' ? v as Record<string, string> : {}
  } catch { osc = {} }
  return osc
}
/** The program in terminal `sid` set its title (xterm's onTitleChange). Kept, so a tab out of front keeps it. */
export function noteOscTitle(sid: string, title: string) {
  const cur = readOsc()
  const clean = title.trim().slice(0, 120)
  if ((cur[sid] ?? '') === clean) return
  const next = { ...cur }
  if (clean) next[sid] = clean
  else delete next[sid]
  // the newest 200 only
  const keys = Object.keys(next)
  for (const k of keys.slice(0, Math.max(0, keys.length - 200))) delete next[k]
  osc = next
  oscRaw = JSON.stringify(next)
  try { localStorage.setItem(OSC_KEY, oscRaw) } catch { /* private mode */ }
  for (const l of oscListeners) l()
}
export const useOscTitles = () => useSyncExternalStore(
  (l) => { oscListeners.add(l); return () => { oscListeners.delete(l) } }, readOsc, readOsc,
)

/* ------------------------------------------------------------ the operator's own names */

const NAMED_KEY = 'sp-term-named'
let named: string[] = []
let namedRaw: string | null | undefined
const namedListeners = new Set<() => void>()
function readNamed(): string[] {
  let raw: string | null = null
  try { raw = localStorage.getItem(NAMED_KEY) } catch { /* private mode */ }
  if (raw === namedRaw) return named
  namedRaw = raw
  try {
    const v = JSON.parse(raw ?? 'null') as unknown
    named = Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch { named = [] }
  return named
}
/** The operator renamed tab `sid`: its label wins over every title from now on. */
export function markNamed(sid: string) {
  const cur = readNamed()
  if (cur.includes(sid)) return
  named = [...cur, sid].slice(-300)
  namedRaw = JSON.stringify(named)
  persistPref(NAMED_KEY, namedRaw)
  for (const l of namedListeners) l()
}
export const useNamed = () => useSyncExternalStore(
  (l) => { namedListeners.add(l); return () => { namedListeners.delete(l) } }, readNamed, readNamed,
)

/** Labels the window gives a new terminal on its own: an agent's command, "shell", "server". Not names. */
const MADE_UP = new Set(['claude', 'codex', 'opencode', 'shell', 'server', 'оболочка', 'сервер'])

/**
 * A tab's title: the operator's name, else what the program set (seen live,
 * else tmux's), else the chat's name in SP, else the label unless it is only
 * the project's code or a made-up word, else the label anyway.
 */
export function tabTitle(s: AquaSession, info: TabInfo | undefined, oscTitles: Record<string, string>, namedIds: string[]): string {
  if (namedIds.includes(s.id)) return s.label
  const set = oscTitles[s.id] || info?.title || ''
  if (set) return set
  if (info?.chat?.name) return info.chat.name
  const label = (s.label || '').trim()
  if (label && label !== s.project && !MADE_UP.has(label.toLowerCase())) return label
  if (roleOf(s) === 'server') return label || 'server'
  return label || s.project || '—'
}

/* ------------------------------------------------------------ facts */

export interface Facts {
  branches: number
  done: number
  all: number
  /** Minutes the chat has waited for an answer (0 when not waiting). */
  waited: number
  /** Context used, 0–100; null when not known. */
  ctx: number | null
  waiting: boolean
  /** The chat's last six hours, oldest first (the tab's six dots); null when not known. */
  rhythm?: Period[] | null
  /** The chat's id, for its hue; the terminal's id when no chat is known. */
  chatId?: string
}

/** Facts of one tab at `nowMs`. Waiting time: since the terminal last printed. */
export function factsOf(s: AquaSession, info: TabInfo | undefined, nowMs: number): Facts {
  const c = info?.chat
  const waiting = shownOf(s) === 'waiting'
  const last = Number(s.last_output) || 0
  const waited = waiting && last > 0 ? Math.max(0, Math.floor((nowMs / 1000 - last) / 60)) : 0
  return {
    branches: c?.branches ?? 0,
    done: c?.tasks_done ?? 0,
    all: c?.tasks_all ?? 0,
    waited,
    ctx: typeof c?.ctx_pct === 'number' ? Math.max(0, Math.min(100, c.ctx_pct)) : null,
    waiting,
    rhythm: Array.isArray(c?.rhythm?.periods) ? c.rhythm.periods : null,
    chatId: info?.agent_id || s.agent_id || s.id,
  }
}
