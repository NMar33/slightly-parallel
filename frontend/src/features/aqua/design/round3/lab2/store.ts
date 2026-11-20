/**
 * Round 3 lab 2 (tk_83077846, tk_91fe214d, tk_a69a8c7a): what the scheme
 * picker and the message menus remember while the page is open. Mock only:
 * the real app would keep the scheme in settings and the marks on the
 * captured messages.
 */

import { useSyncExternalStore } from 'react'

import { t } from '../../../../../i18n/scope/aqua'
import { TASKS } from '../../mock'
import { flash } from '../../store'
import { DEFAULT_SCHEME, SCHEMES } from './schemes'

export type Scope = 'term' | 'window'
export type MenuKind = 'a' | 'b' | 'c'
export type Carry = 'verbatim' | 'summary'
export type Column = 'todo' | 'doing' | 'done'

/** One message block on the screen: the operator's message, or the agent's reply up to the next message. */
export interface Block { id: string; chat: string; who: 'you' | 'agent'; text: string }

export type OpenMenu =
  | { kind: 'msg'; block: Block; x: number; y: number }
  | { kind: 'task'; id: string; chat: string; x: number; y: number; card?: boolean }

export interface Lab2State {
  scheme: string
  scope: Scope
  menu: MenuKind
  open: OpenMenu | null
  pinned: Record<string, boolean>
  carry: Record<string, Carry>
  later: Record<string, boolean>
  branched: Record<string, boolean>
  /** block → the task made from it */
  tasked: Record<string, string>
  column: Record<string, Column>
  /** tasks made in the mock: id → title */
  made: Record<string, string>
}

const seed = (): Lab2State => ({
  scheme: DEFAULT_SCHEME, scope: 'term', menu: 'a', open: null,
  pinned: {}, carry: {}, later: {}, branched: {}, tasked: {},
  column: Object.fromEntries(TASKS.map((x) => [x.id, x.status])), made: {},
})

let state = seed()
const ls = new Set<() => void>()
const set = (p: Partial<Lab2State>) => { state = { ...state, ...p }; for (const l of ls) l() }
const sub = (l: () => void) => { ls.add(l); return () => { ls.delete(l) } }
export const useLab2 = () => useSyncExternalStore(sub, () => state, () => state)
export const getLab2 = () => state
export function resetLab2() { state = seed(); for (const l of ls) l() }

export const isScheme = (v: string | null): v is string => !!v && SCHEMES.some((s) => s.id === v)
export const isMenu = (v: string | null): v is MenuKind => v === 'a' || v === 'b' || v === 'c'
export const setScheme = (scheme: string) => set({ scheme })
export const setScope = (scope: Scope) => set({ scope })
export const setMenu = (menu: MenuKind) => set({ menu, open: null })
export const openMenu = (open: OpenMenu | null) => set({ open })
export const closeMenu = () => { if (state.open) set({ open: null }) }

/* ------------------------------------------------------------ actions */

function copyText(text: string, said: string) {
  try { void navigator.clipboard?.writeText(text) } catch { /* the mock: no clipboard in tests */ }
  flash(said)
}

export function pin(b: Block) {
  const on = !state.pinned[b.id]
  set({ pinned: { ...state.pinned, [b.id]: on }, open: null })
  flash(on ? t('Message pinned') : t('Message unpinned'))
}

/** Carry the block past the next compaction, word for word or as a summary; the same choice again takes it off. */
export function carry(b: Block, how: Carry) {
  const next = { ...state.carry }
  if (next[b.id] === how) { delete next[b.id]; flash(t('Not carried after compaction')) }
  else { next[b.id] = how; flash(how === 'verbatim' ? t('After compaction: word for word') : t('After compaction: as a summary')) }
  set({ carry: next, open: null })
}

export function later(b: Block) {
  const on = !state.later[b.id]
  set({ later: { ...state.later, [b.id]: on }, open: null })
  flash(on ? t('Will be handed over later') : t('Not handed over later'))
}

export function branch(b: Block) {
  set({ branched: { ...state.branched, [b.id]: true }, open: null })
  flash(t('Branch opened in a new window'))
}

/** A task id made from the block's id: the same block always gives the same task. */
function taskIdFor(blockId: string) {
  let h = 2166136261
  for (const c of blockId) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return `tk_${(h >>> 0).toString(16).padStart(8, '0')}`
}

export function makeTask(b: Block) {
  if (state.tasked[b.id]) { set({ open: null }); flash(`${t('Already a task:')} ${state.tasked[b.id]}`); return }
  const id = taskIdFor(b.id)
  const title = b.text.split('\n')[0]!.slice(0, 80)
  set({ tasked: { ...state.tasked, [b.id]: id }, made: { ...state.made, [id]: title }, column: { ...state.column, [id]: 'todo' }, open: null })
  flash(`${t('Task made in todo:')} ${id}`)
}

export function copyBlock(b: Block) { set({ open: null }); copyText(b.text, t('Message copied')) }

export function moveTask(id: string, col: Column) {
  set({ column: { ...state.column, [id]: col }, open: null })
  flash(`${id} → ${col}`)
}

export function copyTaskId(id: string) { set({ open: null }); copyText(id, `${t('Copied')} ${id}`) }

export function showTask(id: string) { if (state.open?.kind === 'task' && state.open.id === id) set({ open: { ...state.open, card: true } }) }

export const taskTitle = (id: string) => TASKS.find((x) => x.id === id)?.title ?? state.made[id] ?? null
