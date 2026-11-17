import { useSyncExternalStore } from 'react'

import { PROJECTS, SERVERS, SESSIONS, sessionOf } from '../mock'

/**
 * Round 2's model: workspaces and the windows on the desktop.
 *
 * A workspace is one per project by default; the operator can group chats
 * into a workspace of their own (like a browser's tab group), across
 * projects. A chat lives in exactly one workspace; ungrouping returns it
 * to its project's. Servers stay with their project and show in every
 * workspace that holds one of that project's chats.
 *
 * Every window on the desktop shows one workspace (the main window can
 * switch) or one chat. Shared by every round-2 variant, in memory.
 */

export interface Workspace { id: string; name: string; hue: number; project?: string }
export type WinKind = 'main' | 'ws' | 'chat'
export interface Win { id: string; kind: WinKind; ref?: string; x: number; y: number; z: number }

interface Desk {
  workspaces: Workspace[]
  home: Record<string, string>
  windows: Win[]
}

const projectWs = (code: string) => `ws_${code}`

function seed(): Desk {
  const workspaces: Workspace[] = PROJECTS.map((p) => ({ id: projectWs(p.code), name: p.name, hue: p.hue, project: p.code }))
  workspaces.push({ id: 'ws_release', name: 'Release week', hue: 330 })
  const home: Record<string, string> = Object.fromEntries(SESSIONS.map((s) => [s.id, projectWs(s.project)]))
  home['cc-2a6e0d93'] = 'ws_release'
  home['cc-f41a9d70'] = 'ws_release'
  return { workspaces, home, windows: [{ id: 'main', kind: 'main', x: 260, y: 96, z: 1 }] }
}

let desk = seed()
const listeners = new Set<() => void>()
const set = (patch: Partial<Desk>) => { desk = { ...desk, ...patch }; for (const l of listeners) l() }
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
export const useDesk = () => useSyncExternalStore(subscribe, () => desk, () => desk)
export const getDesk = () => desk
export function resetDesk() { desk = seed(); for (const l of listeners) l() }

export const wsById = (d: Desk, id: string) => d.workspaces.find((w) => w.id === id)
export const wsOfChat = (d: Desk, chat: string) => d.home[chat] ?? projectWs(sessionOf(chat)!.project)
export const chatsIn = (d: Desk, ws: string) => SESSIONS.filter((s) => wsOfChat(d, s.id) === ws)
/** Servers of every project that has a chat in the workspace. */
export const serversFor = (d: Desk, ws: string) => {
  const projects = new Set(chatsIn(d, ws).map((s) => s.project))
  return SERVERS.filter((s) => projects.has(s.project))
}
/** Workspaces with at least one chat, custom ones after the project ones. */
export const liveWorkspaces = (d: Desk) => d.workspaces.filter((w) => chatsIn(d, w.id).length > 0)
export const wsHue = (d: Desk, ws: string) => wsById(d, ws)?.hue ?? 200

const HUES = [330, 45, 280, 170, 100]
let made = 0
/** A new workspace of these chats (they leave their old ones); returns its id. */
export function group(chats: string[], name?: string): string {
  const id = `ws_mine${++made}`
  const hue = HUES[(made - 1) % HUES.length]!
  const home = { ...desk.home }
  for (const c of chats) home[c] = id
  set({ workspaces: [...desk.workspaces, { id, name: name ?? `Group ${made}`, hue }], home })
  return id
}
/** Put a chat into a workspace (joining a group); the old one keeps its other chats. */
export function moveChat(chat: string, ws: string) { set({ home: { ...desk.home, [chat]: ws } }) }
export function rename(ws: string, name: string) { set({ workspaces: desk.workspaces.map((w) => (w.id === ws ? { ...w, name } : w)) }) }
export function recolour(ws: string, hue: number) { set({ workspaces: desk.workspaces.map((w) => (w.id === ws ? { ...w, hue } : w)) }) }
/** Ungroup: every chat goes back to its project's workspace; the group is gone. */
export function ungroup(ws: string) {
  const home = { ...desk.home }
  for (const [c, w] of Object.entries(home)) if (w === ws) home[c] = projectWs(sessionOf(c)!.project)
  set({ home, workspaces: desk.workspaces.filter((w) => w.id !== ws || !!w.project), windows: desk.windows.filter((w) => !(w.kind === 'ws' && w.ref === ws)) })
}
export const isCustom = (d: Desk, ws: string) => !wsById(d, ws)?.project

let zTop = 1
export function raise(id: string) { set({ windows: desk.windows.map((w) => (w.id === id ? { ...w, z: ++zTop } : w)) }) }
export function moveWin(id: string, x: number, y: number) { set({ windows: desk.windows.map((w) => (w.id === id ? { ...w, x, y } : w)) }) }
/** A workspace or a chat in a window of its own, a step down and right of the last. */
export function detachWin(kind: 'ws' | 'chat', ref: string) {
  const id = `${kind}:${ref}`
  if (desk.windows.some((w) => w.id === id)) { raise(id); return }
  const n = desk.windows.filter((w) => w.kind === kind).length
  const at = kind === 'ws' ? { x: 840 - n * 60, y: 330 + n * 30 } : { x: 40 + n * 60, y: 560 - n * 40 }
  set({ windows: [...desk.windows, { id, kind, ref, ...at, z: ++zTop }] })
}
export function closeWin(id: string) { set({ windows: desk.windows.filter((w) => w.id !== id) }) }

/**
 * Sleep or wake a workspace: its chats, and the servers of its projects —
 * except a server another awake workspace still needs, which keeps running.
 * Returns the names of the servers kept running, for the flash line.
 */
export function workspaceSleepPlan(d: Desk, ws: string, asleepNow: Record<string, boolean>, asleep: boolean) {
  const chats = chatsIn(d, ws).map((s) => s.id)
  const servers: Record<string, boolean> = {}
  const kept: string[] = []
  for (const sv of serversFor(d, ws)) {
    if (!asleep) { servers[sv.id] = sv.up; continue }
    const needed = SESSIONS.some((s) => s.project === sv.project && !chats.includes(s.id) && !asleepNow[s.id])
    if (needed) kept.push(sv.name)
    else servers[sv.id] = false
  }
  return { chats, servers, kept }
}
