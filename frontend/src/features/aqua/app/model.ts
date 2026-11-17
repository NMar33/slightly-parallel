/**
 * SP Aqua's pure logic (tk_bbb84183): what the window derives from the
 * server's terminal rows — the workspaces, the tab strip with the other
 * workspaces folded behind "+N", the overview's levels, where a sidebar
 * opens — kept apart from React so each rule is tested on its own.
 *
 * The server's rows may carry `role`, `group` and `asleep` (the backend
 * additions of tk_bbb84183); rows from a server without them read as
 * before: a chat is a terminal with an agent or a command, a shell is a
 * plain shell, nothing is asleep, every terminal lives in its project.
 */

import type { TermSession, TermState } from '../../../lib/terminal'

export type Role = 'chat' | 'server' | 'shell'

/** A terminal row as the server sends it, with the optional additions. */
export interface AquaSession extends Omit<TermSession, 'state'> {
  state: TermState | 'asleep'
  role?: Role
  /** A workspace of the operator's own (a group id), or "" — its project. */
  group?: string
  asleep?: boolean
}

export interface Group { id: string; name: string; color: number }

export interface Workspace {
  /** `p:<project>` or `g:<group id>`: a project and a group never share an id. */
  id: string
  kind: 'project' | 'group'
  /** The project's code or the group's id. */
  key: string
  name: string
  /** A lane colour, 1–8 (`--lane-N`). */
  color: number
  sessions: AquaSession[]
}

/** What a dot shows. */
export type Shown = 'working' | 'waiting' | 'asleep' | 'ended' | 'idle'

export const roleOf = (s: AquaSession): Role =>
  s.role ?? (s.kind === 'shell' && !s.agent_id && !s.command ? 'shell' : 'chat')

export const isAsleep = (s: AquaSession) => !!s.asleep || s.state === 'asleep'

export function shownOf(s: AquaSession): Shown {
  if (isAsleep(s)) return 'asleep'
  if (s.state === 'ended') return 'ended'
  if (s.state === 'waiting') return 'waiting'
  if (s.state === 'working' || s.state === 'running') return 'working'
  return 'idle'
}

/** The lane a project wears: the same one every time, from its code. */
export function laneOf(code: string): number {
  let h = 0
  for (const ch of code) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return (h % 8) + 1
}

export const projectWs = (code: string) => `p:${code}`
export const groupWs = (gid: string) => `g:${gid}`

/** The workspace a terminal lives in: its group when the group is known, else its project. */
export function wsIdOf(s: AquaSession, groups: Group[] | null): string {
  if (s.group && groups?.some((g) => g.id === s.group)) return groupWs(s.group)
  return projectWs(s.project || '')
}

const byCreated = (a: AquaSession, b: AquaSession) => (a.created || '').localeCompare(b.created || '') || a.id.localeCompare(b.id)

/**
 * Every workspace: the registered projects, any project a terminal names
 * that is not registered, and the groups. Sessions are in creation order.
 */
export function deriveWorkspaces(sessions: AquaSession[], projects: string[], groups: Group[] | null): Workspace[] {
  const out = new Map<string, Workspace>()
  const codes = new Set(projects)
  for (const s of sessions) if (!s.group || !groups?.some((g) => g.id === s.group)) codes.add(s.project || '')
  for (const code of [...codes].sort((a, b) => a.localeCompare(b))) {
    out.set(projectWs(code), { id: projectWs(code), kind: 'project', key: code, name: code || '—', color: laneOf(code), sessions: [] })
  }
  for (const g of groups ?? []) {
    out.set(groupWs(g.id), { id: groupWs(g.id), kind: 'group', key: g.id, name: g.name, color: Math.min(8, Math.max(1, g.color || 1)), sessions: [] })
  }
  for (const s of [...sessions].sort(byCreated)) out.get(wsIdOf(s, groups))?.sessions.push(s)
  return [...out.values()]
}

/** A workspace with any terminal in it (a group always counts: it was made on purpose). */
export const isLive = (w: Workspace) => w.sessions.length > 0 || w.kind === 'group'

export const waitingIn = (w: Workspace) => w.sessions.filter((s) => shownOf(s) === 'waiting').length

/** The tabs of a workspace: chats and shells first, servers after, each in creation order. */
export function tabsOf(w: Workspace | undefined, hidden: (sid: string) => boolean = () => false): AquaSession[] {
  if (!w) return []
  const shown = w.sessions.filter((s) => !hidden(s.id))
  return [...shown.filter((s) => roleOf(s) !== 'server'), ...shown.filter((s) => roleOf(s) === 'server')]
}

export interface Folded { ws: Workspace; count: number; waiting: number }

/**
 * The strip: the current workspace open, every other live one folded
 * behind one "+N" chip that carries an amber dot when a chat there waits.
 */
export function foldTabs(workspaces: Workspace[], current: string, hidden: (sid: string) => boolean = () => false) {
  const open = workspaces.find((w) => w.id === current)
  const folded: Folded[] = workspaces
    .filter((w) => w.id !== current && isLive(w))
    .map((w) => ({ ws: w, count: tabsOf(w, hidden).length, waiting: waitingIn(w) }))
  return { tabs: tabsOf(open, hidden), folded, anyWaiting: folded.some((f) => f.waiting > 0) }
}

/** The tile order in the workspace level: awake chats and shells; sleeping ones and servers have rows of their own. */
export const tilesOf = (w: Workspace | undefined) =>
  (w?.sessions ?? []).filter((s) => !isAsleep(s) && roleOf(s) !== 'server' && s.state !== 'ended')

/* ------------------------------------------------------------- levels */

/** The overview's levels: the terminal, its workspace, every workspace. */
export type Level = 'chat' | 'ws' | 'all'

/** Ctrl+Shift+↑: one level out. A window fixed on one workspace stops at it. */
export function stepOut(level: Level, fixedWs: boolean): Level {
  if (level === 'chat') return 'ws'
  return fixedWs ? 'ws' : 'all'
}

/** The workspaces button: each press goes one level out, and from the top
 *  level back to the terminal — chat → workspace → every workspace → chat.
 *  A workspace's own window has no top level: chat → workspace → chat. */
export function cycleLevel(level: Level, fixedWs: boolean): Level {
  if (level === 'chat') return 'ws'
  if (level === 'ws') return fixedWs ? 'chat' : 'all'
  return 'chat'
}

/** Esc and Ctrl+Shift+↓: one level in, down to the terminal. */
export const stepIn = (level: Level): Level => (level === 'all' ? 'ws' : 'chat')

/** The next chat waiting on you after `from`, in strip order, across every workspace. */
export function nextWaiting(workspaces: Workspace[], from: string, hidden: (sid: string) => boolean = () => false): string | undefined {
  const all = workspaces.flatMap((w) => tabsOf(w, hidden)).filter((s) => shownOf(s) === 'waiting')
  if (!all.length) return undefined
  const i = all.findIndex((s) => s.id === from)
  return all[(i + 1) % all.length]!.id
}

/* ------------------------------------------------------------ the view */

export interface View {
  /** One chat only (a detached chat window). */
  detached: string
  /** One workspace only: a project code or a group id as given. */
  ws: string
}

export function parseView(search: string): View {
  const q = new URLSearchParams(search)
  return { detached: q.get('detached') ?? '', ws: q.get('ws') ?? '' }
}

/** `?ws=` names a project or a group: a group id that exists wins. */
export function resolveWs(raw: string, workspaces: Workspace[]): string {
  if (!raw) return ''
  if (raw.startsWith('p:') || raw.startsWith('g:')) return raw
  return workspaces.find((w) => w.kind === 'group' && w.key === raw)?.id ?? projectWs(raw)
}

/** The address of a detached window. */
export function detachUrl(kind: 'chat' | 'ws', ref: string): string {
  const base = typeof window !== 'undefined' ? `${window.location.origin}/term` : '/term'
  if (kind === 'chat') return `${base}?detached=${encodeURIComponent(ref)}`
  return `${base}?ws=${encodeURIComponent(ref.replace(/^[pg]:/, ''))}`
}

/* --------------------------------------------------- where a sidebar goes */

export type Side = 'left' | 'right'
export interface Seats { left: Side | null; right: Side | null }

export const LW = 236
export const RW = 340

export function widths(at: Seats) {
  return {
    lw: (at.left === 'left' ? LW : 0) + (at.right === 'left' ? RW : 0),
    rw: (at.left === 'right' ? LW : 0) + (at.right === 'right' ? RW : 0),
  }
}

/**
 * Where a sidebar that is opening goes so the terminal never moves (J's
 * rule, for a page in a browser where the window cannot grow past the
 * page): its own side when there is room, else the other side; only when
 * neither has room does the terminal slide by `slide`.
 */
export function placeSide(x: number, w: number, deskW: number, at: Seats, side: Side) {
  const { lw, rw } = widths(at)
  const width = side === 'left' ? LW : RW
  const roomL = x - lw - width >= 0
  const roomR = x + w + rw + width <= deskW
  const pick: Side = side === 'left' ? (roomL ? 'left' : roomR ? 'right' : 'left') : (roomR ? 'right' : roomL ? 'left' : 'right')
  const nl = lw + (pick === 'left' ? width : 0)
  const nr = rw + (pick === 'right' ? width : 0)
  const slide = x - nl < 0 ? -(x - nl) : x + w + nr > deskW ? deskW - (x + w + nr) : 0
  return { pick, slide }
}

/** Both open and no room for the new one: any seating that needs no slide wins. */
export function seatBoth(x: number, w: number, deskW: number): Seats | null {
  const ways: Seats[] = [{ left: 'left', right: 'right' }, { left: 'right', right: 'left' }, { left: 'left', right: 'left' }, { left: 'right', right: 'right' }]
  for (const at of ways) {
    const { lw, rw } = widths(at)
    if (x - lw >= 0 && x + w + rw <= deskW) return at
  }
  return null
}

/** A keyboard event as a chord: `mod+shift+ArrowUp`, `alt+BracketLeft`, by physical key so a layout never matters. */
export function chordOf(e: Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey' | 'code' | 'key'>): string {
  const mods = `${e.ctrlKey || e.metaKey ? 'mod+' : ''}${e.altKey ? 'alt+' : ''}${e.shiftKey ? 'shift+' : ''}`
  return `${mods}${e.code || e.key}`
}
