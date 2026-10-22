/**
 * The terminal, read and driven (backend termlib.py, routers/terminal.py).
 *
 * One small store holds where the terminal is shown — the drawer on every
 * page: open or not, how tall, maximised or not, which terminal is in
 * front — so a Resume on any page can bring its terminal forward. The
 * terminals themselves are the server's. One watch, mounted once in the
 * app shell, asks for the list every five seconds on every page; a place
 * that shows terminals (the open drawer, the Terminal page) asks every two,
 * so a state (working → waiting) turns up quickly where it is looked at.
 */

import { useEffect, useSyncExternalStore } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { askToTrack } from './timer'
import { getJson, postJson } from './getJson'
import { persistPref, readPref } from './uiPrefs'
import { SETTINGS_QUERY_KEY, saveSettings } from './settings'
import { t } from '../i18n/scope/shell'
import { isTypingTarget } from './typing'

export type TermState = 'shell' | 'working' | 'waiting' | 'running' | 'ended'

export interface TermSession {
  id: string
  kind: 'shell' | 'resume' | 'start'
  label: string
  project: string
  cwd: string
  command: string
  agent_id: string
  task_id: string
  created: string
  backend: 'tmux' | 'plain'
  state: TermState
  program: string
  last_output: number
}

interface TermStatus {
  enabled: boolean
  /** False on Windows: the terminal is a Unix pty. */
  supported?: boolean
  forced: boolean
  token: string
  tmux: boolean
  tmux_version: string
  keep: 'tmux' | 'plain'
  launch: 'run' | 'type'
  agent: 'claude' | 'codex' | 'opencode'
  font_size: number
  /** Lines a new terminal keeps (Settings › Terminal history). */
  scrollback: number
  /** The editor a printed path opens in ("" = off or none installed). */
  editor: string
  projects: Record<string, string>
}

export const STATE_WORD: Record<TermState, string> = {
  shell: t('a prompt'), working: t('working'), waiting: t('your turn'), running: t('running'), ended: t('ended'),
}
export const STATE_COLOR: Record<TermState, string> = {
  shell: 'var(--text-tertiary)', working: 'var(--brand)', waiting: 'var(--status-amber)', running: 'var(--m-cpu)', ended: 'var(--border-strong)',
}

/* ------------------------------------------------------------------ store */

interface Dock {
  open: boolean
  height: number
  max: boolean
  /** Focus mode: the terminal alone, over the whole screen. */
  full: boolean
  active: string
  /** Opened for, while the terminal is off: done once it is switched on. */
  pending: OpenRequest | null
}

const DOCK_KEY = 'sp-terminal-dock'
let dock: Dock = (() => {
  try {
    const d = JSON.parse(readPref(DOCK_KEY) ?? 'null') ?? {}
    return { open: !!d.open, height: Math.max(160, Math.min(1200, Number(d.height) || 320)), max: !!d.max, full: !!d.full, active: String(d.active || ''), pending: null }
  } catch {
    return { open: false, height: 320, max: false, full: false, active: '', pending: null }
  }
})()
const listeners = new Set<() => void>()

export function setDock(patch: Partial<Dock>) {
  dock = { ...dock, ...patch }
  persistPref(DOCK_KEY, JSON.stringify({ ...dock, pending: null }))
  listeners.forEach((l) => l())
}

export function useDock(): Dock {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l) }, () => dock)
}

/** ` shows and hides the drawer; in focus mode it leaves focus first. */
export const toggleDock = () => (dock.full ? setDock({ full: false }) : setDock({ open: !dock.open }))
export const showTerminal = (id?: string) => setDock({ open: true, ...(id ? { active: id } : {}) })

/* ------------------------------------------------------------------ reads */

const TERM_KEY = ['terminal'] as const

export function useTerminalStatus() {
  return useQuery({
    queryKey: [...TERM_KEY, 'state'],
    queryFn: ({ signal }) => getJson<TermStatus>('/api/terminal/state', signal),
    staleTime: 10_000,
  })
}

/** Every two seconds where terminals are on screen; five for the watch. */
const TERMINALS_LIVE_MS = 2000
const TERMINALS_WATCH_MS = 5000

interface TerminalList { sessions: TermSession[]; counts: Record<TermState, number> }

/**
 * The terminal list. Without `live` it only reads what the watch keeps
 * (no poll of its own); with it, the list is asked for every two seconds
 * while this is mounted.
 */
export function useTerminals(live = false) {
  const st = useTerminalStatus()
  return useQuery({
    queryKey: [...TERM_KEY, 'sessions'],
    queryFn: ({ signal }) => getJson<TerminalList>('/api/terminal/sessions', signal),
    enabled: !!st.data,
    refetchInterval: live && st.data?.enabled ? TERMINALS_LIVE_MS : false,
    refetchIntervalInBackground: false,
  })
}

/**
 * The one poll every page has (the waiting notice mounts it). `hidden`
 * keeps it going in a tab that is not in front — a desktop notification is
 * for exactly that tab, so it has to keep looking while nobody does.
 */
export function useTerminalsWatch(hidden: boolean) {
  const st = useTerminalStatus()
  return useQuery({
    queryKey: [...TERM_KEY, 'sessions'],
    queryFn: ({ signal }) => getJson<TerminalList>('/api/terminal/sessions', signal),
    enabled: !!st.data,
    refetchInterval: st.data?.enabled ? TERMINALS_WATCH_MS : false,
    refetchIntervalInBackground: hidden,
  })
}

/** The terminal an agent runs in, if any (the newest that is not over). */
export function terminalOfAgent(sessions: TermSession[] | undefined, agentId: string): TermSession | undefined {
  return (sessions ?? []).filter((s) => s.agent_id === agentId && s.state !== 'ended').slice(-1)[0]
}

/* ------------------------------------------------------------------ acts */

interface OpenRequest {
  kind: 'shell' | 'resume' | 'start'
  project?: string
  cwd?: string
  agent_id?: string
  task_id?: string
  label?: string
  command?: string
}

/** `what` is already a translated sentence; the reason is the server's own. */
const saidFailed = (what: string, e: unknown) => toast.error([what, e instanceof Error ? e.message : String(e)].join(': '))

export function useTerminalActions() {
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries({ queryKey: TERM_KEY })
  const open = useMutation({
    // The agent goes as `agent`: an `agent_id` in a body reads as the agent writing.
    mutationFn: ({ quiet: _q, agent_id, ...req }: OpenRequest & { quiet?: boolean }) =>
      postJson<{ session: TermSession; existing: boolean }>('/api/terminal/sessions', { ...req, agent: agent_id, actor: 'operator' }),
    // `quiet`: the caller shows the terminal itself (focus mode's split).
    onSuccess: (d, v) => {
      if (!v.quiet) showTerminal(d.session.id)
      refresh()
      // Starting an agent or resuming one is starting work: the timer may ask.
      if (!d.existing) askToTrack({ project: d.session.project, taskId: d.session.task_id, title: d.session.label })
    },
    onError: (e: Error) => toast.error(t('Could not open the terminal: {error}', { error: e.message })),
  })
  // Read through the hook: before it loads, an open waits on the drawer's switch
  // instead of going to the server and coming back refused.
  const status = useTerminalStatus().data
  return {
    /** Open a terminal; while the terminal is off, the drawer asks first and then does it. */
    open: (req: OpenRequest, opts: { quiet?: boolean } = {}) => {
      if (!status || !status.enabled) { setDock({ open: true, pending: req }); return }
      open.mutate({ ...req, quiet: opts.quiet })
    },
    opening: open.isPending,
    /** Open one and hand it back, without showing it (a split places it itself). */
    openAsync: async (req: OpenRequest): Promise<TermSession | null> => {
      try {
        const d = await open.mutateAsync({ ...req, quiet: true })
        return d.session
      } catch {
        return null
      }
    },
    // The bar and the tabs fire these and move on: a refusal is said here,
    // in the server's words, not left as an unhandled rejection.
    close: async (id: string) => {
      try { await postJson(`/api/terminal/sessions/${id}/close`, { actor: 'operator' }) } catch (e) { saidFailed(t('The terminal could not close'), e) }
      refresh()
    },
    rename: async (id: string, label: string) => {
      try { await postJson(`/api/terminal/sessions/${id}/rename`, { label, actor: 'operator' }) } catch (e) { saidFailed(t('The terminal could not be renamed'), e) }
      refresh()
    },
    /** Throws: the caller says what was not typed. */
    type: async (id: string, text: string, enter = false) => { await postJson(`/api/terminal/sessions/${id}/type`, { text, enter, actor: 'operator' }) },
    turnOn: async () => {
      try {
        await saveSettings({ 'terminal.enabled': true })
      } catch (e) {
        saidFailed(t('The terminal could not be switched on'), e)
        return
      }
      await qc.invalidateQueries({ queryKey: TERM_KEY })
      await qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
      const req = dock.pending
      setDock({ pending: null, open: true })
      if (req) open.mutate(req)
    },
    setting: async (values: Record<string, string | number | boolean>) => {
      try {
        await saveSettings(values)
      } catch (e) {
        saidFailed(t('The setting was not saved'), e)
      }
      await qc.invalidateQueries({ queryKey: TERM_KEY })
      await qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
    },
  }
}

/** ` (or Ctrl+`) shows and hides the drawer, from anywhere but a text box. */
export function useDockShortcut() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '`' || e.altKey || e.metaKey) return
      const typing = isTypingTarget(e)
      // Inside a terminal ` is a character; Ctrl+` still toggles.
      if (typing && !e.ctrlKey) return
      e.preventDefault()
      toggleDock()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
