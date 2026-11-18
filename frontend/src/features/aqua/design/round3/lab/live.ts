/**
 * Round 3 lab (tk_3d4a834b, tk_c50ff865): the mock facts the tab strip shows
 * and the variants the operator clicks through. Mock data only.
 *
 * - A tab's title is the chat's own name, the one the agent's program sets
 *   as the terminal title (a Claude Code chat renamed "hbr-2611-18", or the
 *   title it made itself). When the program sets none (Codex), the tab falls
 *   back to the chat's name in Slightly Parallel. Never the project's name.
 * - Facts per chat: branches (chats forked from it), tasks closed of all,
 *   minutes the agent has waited for an answer, context used, minutes since
 *   the last commit, the agent's activity over the last ten minutes.
 * - The facts move slowly (one mock minute every few seconds): a waiting
 *   chat waits longer, now and then a task closes. Nothing else moves.
 */

import { useEffect, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'

import { SESSIONS, TASKS, projectOf, type Session } from '../../mock'
import { getAqua } from '../../store'

/* ------------------------------------------------------------ titles */

/** What each mock chat's program set as its terminal title. Codex sets none: those fall back to the chat's name. */
const TITLES: Record<string, string> = {
  'cc-4e7a19d2': 'hbr-2611-18',
  'cc-b03d55e1': 'hbr-2611-17',
  'cc-7f2b8c40': 'kelp-2611-18',
  'cc-2a6e0d93': 'kelp release 0.9',
  'cc-d18c7b25': 'lum-2611-16',
  'cc-5a0f7e19': 'Booking confirmation emails',
  'cc-c37d2e86': 'hbr-2611-15',
  'cc-8b1e6f04': 'Pricing page copy',
  'cc-e95c0a2b': 'kelp-2611-12',
  'cc-f41a9d70': 'lum-2611-17',
  'cc-60e9a4f8': 'otr-2611-09',
}
const added: Record<string, string> = {}
export const tabTitle = (s: Session) => added[s.id] ?? TITLES[s.id] ?? s.name

/* ------------------------------------------------------------ facts */

export interface Facts { branches: number; done: number; all: number; waited: number; ctx: number; commit: number; active: number }

/** Branches: the chats work was forked to (the board's "forked" links) plus a few invented ones. */
const BRANCHES: Record<string, number> = { 'cc-4e7a19d2': 2, 'cc-7f2b8c40': 1, 'cc-c37d2e86': 1 }
const WAITED: Record<string, number> = { 'cc-b03d55e1': 4, 'cc-2a6e0d93': 17, 'cc-c37d2e86': 26, 'cc-f41a9d70': 9 }
const COMMIT: Record<string, number> = { 'cc-4e7a19d2': 12, 'cc-7f2b8c40': 48, 'cx-0d4b8e37': 95, 'cc-5a0f7e19': 30 }
const EXTRA_TASKS: Record<string, [number, number]> = { 'cc-7f2b8c40': [2, 2], 'cx-0d4b8e37': [1, 3], 'cc-5a0f7e19': [0, 2], 'cc-c37d2e86': [3, 4], 'cc-f41a9d70': [1, 2] }

function seedFacts(s: Session): Facts {
  const own = TASKS.filter((x) => x.from === s.id)
  const [d0, a0] = EXTRA_TASKS[s.id] ?? [0, 0]
  return {
    branches: BRANCHES[s.id] ?? TASKS.filter((x) => x.from === s.id && x.via === 'forked' && x.chat !== s.id).length,
    done: own.filter((x) => x.status === 'done').length + d0,
    all: own.length + a0,
    waited: WAITED[s.id] ?? 0,
    ctx: s.ctx,
    commit: COMMIT[s.id] ?? 180,
    active: s.state === 'working' ? 0.55 + (s.ctx % 40) / 100 : s.state === 'waiting' ? 0.15 : 0,
  }
}

interface Lab { facts: Record<string, Facts>; closed: Record<string, boolean>; tick: number }
const fresh = (): Lab => ({ facts: Object.fromEntries(SESSIONS.map((s) => [s.id, seedFacts(s)])), closed: {}, tick: 0 })
let lab = fresh()
const listeners = new Set<() => void>()
const emit = () => { for (const l of listeners) l() }
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
export const useLab = () => useSyncExternalStore(subscribe, () => lab, () => lab)
export const factsOf = (l: Lab, s: Session) => l.facts[s.id] ?? seedFacts(s)

/** A mock minute. The waiting chats wait longer; every eighth minute a task closes in a working chat. */
export function tickLab() {
  const st = getAqua()
  const facts = { ...lab.facts }
  const n = lab.tick + 1
  for (const s of SESSIONS) {
    const f = facts[s.id] ?? seedFacts(s)
    const waiting = s.state === 'waiting' && !st.asleep[s.id]
    facts[s.id] = { ...f, waited: waiting ? Math.min(f.waited + 1, 60) : f.waited, commit: Math.min(f.commit + 1, 240) }
  }
  if (n % 8 === 0) {
    const open = SESSIONS.filter((s) => s.state === 'working' && !st.asleep[s.id] && facts[s.id] && facts[s.id]!.done < facts[s.id]!.all)
    const s = open[(n / 8) % Math.max(open.length, 1)]
    if (s) facts[s.id] = { ...facts[s.id]!, done: facts[s.id]!.done + 1, commit: 0 }
  }
  lab = { ...lab, facts, tick: n }
  emit()
}

export const TICK_MS = 4000
/** Runs the mock clock while a lab tab strip is on screen. */
export function useLabClock() {
  useEffect(() => {
    const h = setInterval(tickLab, TICK_MS)
    return () => clearInterval(h)
  }, [])
}

export function closeTab(id: string) { lab = { ...lab, closed: { ...lab.closed, [id]: true } }; emit() }
export function openTab(id: string) { if (!lab.closed[id]) return; const closed = { ...lab.closed }; delete closed[id]; lab = { ...lab, closed }; emit() }

/* ------------------------------------------------------------ new chats from the "+" */

export type NewKind = 'claude' | 'codex' | 'opencode' | 'shell' | 'server' | 'branch' | 'task' | 'worktree'
const ABBR: Record<string, string> = { harbor: 'hbr', kelp: 'kelp', lumen: 'lum', otter: 'otr' }
let made = 0

/** A new mock chat in a project; returns its id. It joins SESSIONS, so every part of the mock sees it. */
export function newChat(project: string, kind: NewKind, from?: Session, extra?: string): Session {
  made += 1
  const id = `cc-new${String(made).padStart(4, '0')}`
  const p = projectOf(project)
  const abbr = ABBR[project] ?? project.slice(0, 3)
  const title = kind === 'shell' ? `bash — ${p.path}`
    : kind === 'server' ? `${extra ?? 'dev'} — ${p.path}`
    : kind === 'branch' && from ? `${tabTitle(from)} ⑂`
    : kind === 'codex' ? `codex — ${p.path}`
    : kind === 'opencode' ? `opencode — ${p.path}`
    : `${abbr}-2611-${18 + made}`
  added[id] = title
  const first = kind === 'branch' && from ? `Branched from ${tabTitle(from)}: the conversation so far is carried in.`
    : kind === 'task' ? `Started from the board task ${extra ?? ''}: its text and briefing are the first message.`
    : kind === 'worktree' ? `A new git worktree: ${p.path}-wt${made} on branch wt/${abbr}-${made}. The other chats keep their files.`
    : kind === 'shell' ? `${p.path} $`
    : kind === 'server' ? `$ ${extra ?? 'npm run dev'}`
    : 'A new chat. Type the first message.'
  const s: Session = {
    id, project, name: title, tool: kind === 'codex' ? 'codex' : 'claude', state: 'idle', model: kind === 'codex' ? 'gpt-5' : 'opus',
    ctx: kind === 'branch' && from ? from.ctx : 0, tokens: 0, today: 0, task: '', sessionRef: `new-${made}`,
    script: [{ k: 'say', text: first }], bg: [],
  }
  SESSIONS.push(s)
  lab = { ...lab, facts: { ...lab.facts, [id]: { ...seedFacts(s), commit: from ? factsOf(lab, from).commit : 0 } } }
  emit()
  return s
}

/** Back to the start: the added chats leave SESSIONS, the facts and the closed tabs are seeded again. */
export function resetLab() {
  for (let i = SESSIONS.length - 1; i >= 0; i--) if (SESSIONS[i]!.id.startsWith('cc-new')) SESSIONS.splice(i, 1)
  for (const k of Object.keys(added)) delete added[k]
  made = 0
  lab = fresh()
  emit()
}

/* ------------------------------------------------------------ the status strip's settings */

export type PartKind = 'closed' | 'context' | 'activity' | 'commit' | 'waiting'
export const PART_KINDS: PartKind[] = ['closed', 'context', 'activity', 'commit', 'waiting']
export interface StripSettings { parts: 1 | 2 | 3; kinds: [PartKind, PartKind, PartKind]; px: 1 | 2 | 3 | 4 }
export const STRIP_DEFAULT: StripSettings = { parts: 3, kinds: ['closed', 'context', 'waiting'], px: 2 }
const STRIP_KEY = 'sp-aqua-lab-strip'

function readStrip(): StripSettings {
  try {
    const v = JSON.parse(localStorage.getItem(STRIP_KEY) ?? 'null') as StripSettings | null
    if (v && [1, 2, 3].includes(v.parts) && [1, 2, 3, 4].includes(v.px) && v.kinds?.length === 3 && v.kinds.every((k) => PART_KINDS.includes(k))) return v
  } catch { /* private mode */ }
  return STRIP_DEFAULT
}
let strip: StripSettings = STRIP_DEFAULT
let stripRead = false
const stripListeners = new Set<() => void>()
export const useStripSettings = () => useSyncExternalStore(
  (l) => { stripListeners.add(l); return () => { stripListeners.delete(l) } },
  () => { if (!stripRead) { strip = readStrip(); stripRead = true } return strip },
  () => strip,
)
export function setStrip(patch: Partial<StripSettings>) {
  strip = { ...strip, ...patch }
  stripRead = true
  try { localStorage.setItem(STRIP_KEY, JSON.stringify(strip)) } catch { /* private mode */ }
  for (const l of stripListeners) l()
}
export function resetStrip() { strip = STRIP_DEFAULT; stripRead = true; for (const l of stripListeners) l() }
/** Which of the three slots show: with two parts the first and the last (closed tasks, waiting), with one the last. */
export const shownSlots = (s: StripSettings): number[] => (s.parts === 3 ? [0, 1, 2] : s.parts === 2 ? [0, 2] : [2])

/* ------------------------------------------------------------ the variants */

export const LAB_VARIANTS = { tabs: ['a', 'b', 'c'], strip: ['a', 'b', 'c'], plus: ['a', 'b', 'c'], plusmenu: ['a', 'b'] } as const
export type LabKey = keyof typeof LAB_VARIANTS
export type LabPick = { [K in LabKey]: (typeof LAB_VARIANTS)[K][number] }
/** The ones I think best: the Alt view inline, three segments, the split button, the list. */
export const LAB_DEFAULT: LabPick = { tabs: 'a', strip: 'a', plus: 'a', plusmenu: 'a' }

/** The variants from the address (`&tabs=b&strip=c&plus=b&plusmenu=b`); a pick writes the address back. */
export function useLabVariants(): [LabPick, (k: LabKey, v: string) => void] {
  const [params, setParams] = useSearchParams()
  const pick = Object.fromEntries((Object.keys(LAB_VARIANTS) as LabKey[]).map((k) => {
    const v = params.get(k)
    return [k, (LAB_VARIANTS[k] as readonly string[]).includes(v ?? '') ? v : LAB_DEFAULT[k]]
  })) as LabPick
  const set = (k: LabKey, v: string) => {
    setParams((prev) => { const next = new URLSearchParams(prev); next.set(k, v); return next }, { replace: true })
  }
  return [pick, set]
}
