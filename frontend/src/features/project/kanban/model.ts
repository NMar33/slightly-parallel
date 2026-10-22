/**
 * The kanban's model layer — the task row shape, clipboard text, stored
 * view/modal preferences, stack folding, lane ordering, sorting and the
 * little judgments (today, quick win, age) — everything that is true
 * about the board without rendering it.
 */

import { persistPref, removePref } from '../../../lib/uiPrefs'
import { isoDay } from '../../../utils/dateUtils'
import { type Turn, turnRef } from '../../tasks/turns'
import type { MentionAgent } from '../mentions'
import { t } from '../../../i18n/scope/project'

export type KanbanView = 'classic' | 'workflow' | 'lanes'

export type TaskRow = {
  id: string
  project?: string
  agent_id?: string
  title?: string
  status?: string
  priority?: string
  impact?: string
  effort?: string
  tokens?: string
  novelty?: string
  projects?: string
  sprint_id?: string
  archived_at?: string
  resurface_on?: string
  resurface_to?: string
  resurface_every_days?: string | number
  resurfaced_at?: string
  remember?: string
  today_on?: string
  stack_id?: string
  stack_head_at?: string
  /** 'yes' lets an agent's done-report move the card to review. */
  auto_manage?: string
  /** 'yes' asks a reporting agent for proof, guided by the evidence prompt. */
  evidence_required?: string
  /** Named evidence-prompt id this task uses; empty = the default prompt. */
  evidence_prompt?: string
  /** The agent's opinion — stamped by /report, cleared by your next verdict. */
  agent_done_at?: string
  agent_done_by?: string
  agent_done_note?: string
  /** When an auto-managed card was moved by an agent (badge, 2 days). */
  agent_moved_at?: string
  assignee?: string
  due_date?: string
  lane?: string
  tags?: string
  position?: string | number
  created_date?: string
  created_time?: string
  /** The task's text (turn 1), the newest round and the round count —
   *  present only when the list was fetched with ?with_desc=1. */
  description?: string
  turns_n?: number
  turn_last?: Turn | null
}

/** The newest round of a task as the list carries it. */
function lastRound(t: TaskRow): Turn | null {
  if (t.turn_last) return t.turn_last
  const d = String(t.description ?? '').trim()
  return d ? { n: 1, date: '', time: '', text: d } : null
}

/** Clipboard text for one task: id · title, then description when it has
 *  one. The id travels with the text so a captured chat that quotes it can
 *  be linked back to the task (mentions, task timeline). */
/**
 * A task's evidence instructions, or '' when it wants none.
 *
 * The prompt text lives in the operator's evidence prompts, not on the
 * row, so the board resolves it and hands it in — see
 * `useEvidenceAsk` in TasksKanban.
 */
export type EvidenceAsk = (t: TaskRow) => string

/**
 * The evidence line a copied task carries.
 *
 * A task that wants proof used to say so only in the *response* to
 * /report — after the work was finished, when a screenshot means
 * rebuilding the state that is already gone. Copying the ask with the
 * task lets the agent collect it while the context is live.
 */
export function evidenceNote(t: TaskRow, ask?: EvidenceAsk): string {
  if (String(t.evidence_required ?? '') !== 'yes') return ''
  const prompt = (ask?.(t) ?? '').trim()
  const head = 'Evidence required — collect it as you work, then report and attach it.'   // copied for an agent: stays English
  return prompt ? `${head}\n${prompt}` : head
}

export function taskText(t: TaskRow, ask?: EvidenceAsk): string {
  // A task asked more than once copies only its newest round, under the
  // reference that names it (tk_….2), so pasting it into an agent asks
  // for the next thing rather than repeating everything already done.
  const title = String(t.title ?? '').trim()
  const last = lastRound(t)
  const id = String(t.id ?? '')
  const head = id ? `${turnRef(id, last?.n ?? 1)} · ${title}` : title
  const body = last?.text ?? ''
  return [body ? `${head}\n${body}` : head, evidenceNote(t, ask)].filter(Boolean).join('\n\n')
}

/** Clipboard text for a whole column — numbered, blank line between items. */
export function columnText(items: TaskRow[], ask?: EvidenceAsk): string {
  return items.map((t, i) => `${i + 1}. ${taskText(t, ask)}`).join('\n\n')
}

/**
 * How many Done cards to render before the rest collapse.
 *
 * - "all"   → everything, always
 * - "fixed" → the operator's count
 * - "match" → no taller than the busiest other column (min 3), so Done
 *             grows with the board instead of swamping it
 */
export function doneVisibleLimit(
  mode: string,
  fixed: number,
  otherColumnCounts: number[],
  expanded: boolean,
): number {
  if (expanded || mode === 'all') return Number.POSITIVE_INFINITY
  if (mode === 'fixed') return Math.max(1, fixed)
  return Math.max(3, ...otherColumnCounts, 0)
}

/**
 * The chosen board view is remembered per project, with the most recent
 * choice as the fallback for projects never opened before — so the board
 * comes back the way it was left, and a new project inherits the habit
 * rather than snapping back to the default.
 */
const VIEW_KEY = (project: string) => `sp-kanban-view:${project}`
const LAST_VIEW_KEY = 'sp-kanban-view'

const isKanbanView = (v: unknown): v is KanbanView =>
  v === 'classic' || v === 'workflow' || v === 'lanes'

export function readStoredView(project: string): KanbanView {
  try {
    const mine = localStorage.getItem(VIEW_KEY(project))
    if (isKanbanView(mine)) return mine
    const last = localStorage.getItem(LAST_VIEW_KEY)
    if (isKanbanView(last)) return last
  } catch {
    /* private mode — fall through to the default */
  }
  return 'classic'
}

export function storeView(project: string, view: KanbanView): void {
  try {
    persistPref(VIEW_KEY(project), view)
    persistPref(LAST_VIEW_KEY, view)
  } catch {
    /* the choice just won't persist */
  }
}

/**
 * Task-editor window preferences — the popup is where a task is actually
 * written, and a one-line title needs a different window than a spec with
 * acceptance criteria. The gear in its header regulates the window; the
 * choice is remembered across sessions.
 */
export type ModalWidth = 'compact' | 'normal' | 'wide'
export type ModalDescSize = 's' | 'm' | 'l'
export type Axis = 'impact' | 'effort' | 'tokens' | 'novelty'
export const AXES: Axis[] = ['impact', 'effort', 'tokens', 'novelty']
export type ChainMode = 'next' | 'group'
export type ModalSection = 'evidence' | 'links' | 'story' | 'chat' | 'history'
export const MODAL_SECTIONS: ModalSection[] = ['evidence', 'links', 'story', 'chat', 'history']

export interface ModalPrefs {
  width: ModalWidth
  desc: ModalDescSize
  /** Which value axes are shown — in the editor and on cards. Priority is always on. */
  axes: Record<Axis, boolean>
  /** What ▶ does after saving: open a fresh task, or open one and queue it
   *  behind the task just written. */
  chain: ChainMode
  /** Which collapsible lines the window shows — minimalism is a choice. */
  sections: Record<ModalSection, boolean>
  /** Ticks a NEW task starts with: auto-manage and evidence-required. */
  autoNew: boolean
  evidenceNew: boolean
}

const MODAL_PREFS_KEY = 'sp-task-modal'
export const DEFAULT_MODAL_PREFS: ModalPrefs = {
  width: 'normal', desc: 's',
  axes: { impact: true, effort: true, tokens: false, novelty: false },
  chain: 'next',
  sections: { evidence: true, links: true, story: true, chat: true, history: true },
  autoNew: false,
  evidenceNew: false,
}

export const MODAL_WIDTH_PX: Record<ModalWidth, number> = {
  compact: 520,
  normal: 720,
  wide: 1040,
}
// A gentle progression: L is a roomier M, not a wall of empty box — the
// textarea is still hand-resizable past it when a task needs more.
export const MODAL_DESC_PX: Record<ModalDescSize, number> = {
  s: 80,
  m: 180,
  l: 250,
}

export function readModalPrefs(): ModalPrefs {
  try {
    const raw = JSON.parse(localStorage.getItem(MODAL_PREFS_KEY) || '{}')
    const sections = { ...DEFAULT_MODAL_PREFS.sections }
    if (raw.sections && typeof raw.sections === 'object') {
      for (const k of MODAL_SECTIONS) {
        if (typeof raw.sections[k] === 'boolean') sections[k] = raw.sections[k]
      }
    }
    const axes = { ...DEFAULT_MODAL_PREFS.axes }
    if (raw.axes && typeof raw.axes === 'object') {
      for (const a of AXES) if (typeof raw.axes[a] === 'boolean') axes[a] = raw.axes[a]
    }
    return {
      width: raw.width in MODAL_WIDTH_PX ? raw.width : DEFAULT_MODAL_PREFS.width,
      desc: raw.desc in MODAL_DESC_PX ? raw.desc : DEFAULT_MODAL_PREFS.desc,
      axes,
      chain: raw.chain === 'group' ? 'group' : DEFAULT_MODAL_PREFS.chain,
      sections,
      autoNew: raw.autoNew === true,
      evidenceNew: raw.evidenceNew === true,
    }
  } catch {
    return { ...DEFAULT_MODAL_PREFS, axes: { ...DEFAULT_MODAL_PREFS.axes } }
  }
}

export function storeModalPrefs(prefs: ModalPrefs): void {
  try {
    persistPref(MODAL_PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* the choice just won't persist */
  }
}

/**
 * The pinned sprint — the block new tasks of a project join by default,
 * so a run of work does not need the same chip picked twelve times. One
 * per project, remembered like every other view choice.
 */
const PIN_KEY = (project: string) => `sp-sprint-pin:${project}`
export function readPinnedSprint(project: string): string {
  try { return localStorage.getItem(PIN_KEY(project)) || '' } catch { return '' }
}
export function writePinnedSprint(project: string, sprintId: string) {
  try {
    if (sprintId) persistPref(PIN_KEY(project), sprintId)
    else removePref(PIN_KEY(project))
  } catch { /* the choice just does not outlive the tab */ }
}

/** Bulk-move drag payload: the whole column travels as one token. The
 *  fourth segment narrows it to the day's plan, so the Today lane can move
 *  its own cell without dragging the column it borrows from. */
const BULK = '__sp_bulk__'
/** Dragging any selected card moves the whole selection: the payload only
 *  has to say so, since the board holds the ids and their picked order. */
export const SELECTION = '__sp_selection__'
export const bulkPayload = (statusKey: string, lane?: string, onlyToday?: boolean) =>
  `${BULK}:${statusKey}:${lane ?? ''}:${onlyToday ? 'today' : ''}`
export const parseBulk = (raw: string): { status: string; lane: string; onlyToday: boolean } | null => {
  if (!raw.startsWith(`${BULK}:`)) return null
  const [, status = '', lane = '', scope = ''] = raw.split(':')
  return { status, lane, onlyToday: scope === 'today' }
}

// Each folded strip has a color identity — the board reads by tint:
// amber = for the future, purple = check later, green = done but hidden,
// gray = archived away.
export const STRIP_HINTS: Record<string, string> = {
  agent: t('Tasks agents write with #task. Drag a card out to classify it.'),
  parked: t('Drop a card here to park it for later.'),
  'review-later': t('Drop a card here to review it later.'),
  'done-archived': t('Drop a done card here to archive it.'),
}

export const STRIP_TONES: Record<string, string> = {
  agent: 'var(--brand)',
  parked: 'var(--status-amber)',
  'review-later': 'var(--status-purple)',
  'done-archived': 'var(--status-green)',
  __archive__: 'var(--text-tertiary)',
}

// `strip: true` marks a column that folds to a thin drop strip by default
// (Parked): tasks can land in it without it taking board space.
export const VIEW_COLUMNS: Record<KanbanView, { key: string; label: string; className?: string; strip?: boolean }[]> = {
  classic: [
    { key: 'unclassified',  label: t('Unclassified') },
    { key: 'agent',         label: t('From agents'),    strip: true },
    { key: 'todo',          label: t('To do'),          className: 'state-todo' },
    { key: 'parked',        label: t('To do · parked'), strip: true },
    { key: 'doing',         label: t('Doing'),          className: 'state-doing' },
    { key: 'review-later',  label: t('Review later'),   strip: true },
    { key: 'done',          label: t('Done'),           className: 'state-done' },
    { key: 'done-archived', label: t('Done archived'),  strip: true },
  ],
  workflow: [
    { key: 'unclassified',  label: t('Unclassified') },
    { key: 'backlog',       label: t('Backlog') },
    { key: 'next',          label: t('Next') },
    { key: 'agent',         label: t('From agents'),    strip: true },
    { key: 'todo',          label: t('To do'),          className: 'state-todo' },
    { key: 'parked',        label: t('To do · parked'), strip: true },
    { key: 'doing',         label: t('Doing'),          className: 'state-doing' },
    { key: 'review',        label: t('Review'),         className: 'state-review' },
    { key: 'review-later',  label: t('Review later'),   strip: true },
    { key: 'done',          label: t('Done'),           className: 'state-done' },
    { key: 'done-archived', label: t('Done archived'),  strip: true },
  ],
  lanes: [
    { key: 'unclassified',  label: t('Unclassified') },
    { key: 'agent',         label: t('From agents'),    strip: true },
    { key: 'todo',          label: t('To do'),          className: 'state-todo' },
    { key: 'parked',        label: t('To do · parked'), strip: true },
    { key: 'doing',         label: t('Doing'),          className: 'state-doing' },
    { key: 'review',        label: t('Review'),         className: 'state-review' },
    { key: 'review-later',  label: t('Review later'),   strip: true },
    { key: 'done',          label: t('Done'),           className: 'state-done' },
    { key: 'done-archived', label: t('Done archived'),  strip: true },
  ],
}

/**
 * Canonical status key for a task. Single source of truth for grouping,
 * drop handling, and column counts — lowercased, trimmed, empty maps to
 * 'unclassified'.
 */
export function normalizeStatus(s: unknown): string {
  const key = String(s ?? '').trim().toLowerCase()
  return key === '' ? 'unclassified' : key
}

export const laneOf = (t: TaskRow): string => t.assignee || 'unassigned'

/**
 * What a card dropped into a lane writes. The unassigned lane clears the
 * assignee — the lane is read from it — as renaming a lane already did; a
 * drop there used to write nothing, and the card went back to its old lane.
 * No lane (the board without swim lanes) writes nothing.
 */
export function laneUpdate(targetLane: string | undefined): { assignee: string; lane: string } | Record<string, never> {
  if (!targetLane) return {}
  return targetLane === 'unassigned' ? { assignee: '', lane: '' } : { assignee: targetLane, lane: targetLane }
}

/**
 * Today — a lens, not a place. Ctrl/⌘-click a card and it joins the Today
 * lane while staying exactly where it lives; the two are one task drawn
 * twice, so moving either moves both. The mark is a date, so tomorrow the
 * lane is empty again without anyone tidying it.
 */
/**
 * A stack is an ordered queue of tasks living in one column: only the
 * earliest member is drawn, the rest wait behind it. Nothing is written
 * when the head moves on — the next card simply becomes the earliest one
 * still there, so the queue advances by itself and cannot race.
 *
 * Folding happens on the board's columns only. Everywhere else — the Today
 * lane, sprint views, the gantt, analytics — every member counts, because a
 * stack of five is five tasks of work and hiding them would make the
 * numbers lie.
 */
type Folded = { task: TaskRow; behind: TaskRow[]; ordinal: number; total: number }

export function foldStacks(items: TaskRow[], all: TaskRow[] = items): Folded[] {
  const out: Folded[] = []
  const seen = new Set<string>()
  for (const t of items) {
    const sid = t.stack_id || ''
    if (!sid) { out.push({ task: t, behind: [], ordinal: 1, total: 1 }); continue }
    if (seen.has(sid)) continue
    seen.add(sid)
    const here = items.filter((x) => x.stack_id === sid)
    const whole = all.filter((x) => x.stack_id === sid && !x.archived_at)
    const byPos = (a: TaskRow, b: TaskRow) => (Number(a.position) || 0) - (Number(b.position) || 0)
    here.sort(byPos)
    whole.sort(byPos)
    const head = here[0]!
    out.push({
      task: head,
      behind: here.slice(1),
      ordinal: Math.max(1, whole.findIndex((x) => x.id === head.id) + 1),
      total: whole.length,
    })
  }
  return out
}

export function todayISO(now: Date = new Date()): string {
  return isoDay(now)
}
export function isToday(t: TaskRow, today: string = todayISO()): boolean {
  return !!t.today_on && t.today_on === today
}

/** Placed lanes first in the saved order, then the rest alphabetically,
 *  "unassigned" last among the unplaced. Exported for tests. */
export function orderLanes(present: string[], saved: string[]): string[] {
  const set = new Set(present)
  const placed = saved.filter((l) => set.has(l))
  const rest = present
    .filter((l) => !placed.includes(l))
    .sort((a, b) => (a === 'unassigned' ? 1 : b === 'unassigned' ? -1 : a.localeCompare(b)))
  return [...placed, ...rest]
}

/** Per task: how often its id was named in a chat, and by whom last. The
 *  agent behind the last mention rides along, so a card can name it. */
export type MentionSummary = {
  n: number
  last_at: string
  last_agent: string
  last_role: string
  agent?: MentionAgent | null
}

export type LinkKind = 'blocks' | 'relates' | 'parent'
export type TaskLink = {
  id: string
  from_id: string
  to_id: string
  kind: LinkKind
  created_at?: string
  from: { id: string; title?: string; status?: string; project?: string }
  to: { id: string; title?: string; status?: string; project?: string }
}

/** What one card needs to know about its links, from its own point of view. */
export type LinkInfo = {
  n: number
  blockedBy: Array<{ id: string; title: string; open: boolean }>
  blocks: Array<{ id: string; title: string }>
  parent: { id: string; title: string } | null
  children: Array<{ id: string; title: string; done: boolean }>
  relates: Array<{ id: string; title: string }>
  neighbors: Set<string>
}

/** Fold the edge list into per-task views. Exported for tests. */
export function linkInfoByTask(links: TaskLink[]): Record<string, LinkInfo> {
  const out: Record<string, LinkInfo> = {}
  const get = (id: string): LinkInfo =>
    (out[id] ??= { n: 0, blockedBy: [], blocks: [], parent: null, children: [], relates: [], neighbors: new Set() })
  const isDone = (st?: string) => normalizeStatus(st) === 'done'
  for (const l of links) {
    const a = get(l.from_id), b = get(l.to_id)
    a.n += 1; b.n += 1
    a.neighbors.add(l.to_id); b.neighbors.add(l.from_id)
    const ft = String(l.from.title || l.from_id), tt = String(l.to.title || l.to_id)
    if (l.kind === 'blocks') {
      a.blocks.push({ id: l.to_id, title: tt })
      b.blockedBy.push({ id: l.from_id, title: ft, open: !isDone(l.from.status) })
    } else if (l.kind === 'parent') {
      a.children.push({ id: l.to_id, title: tt, done: isDone(l.to.status) })
      b.parent = { id: l.from_id, title: ft }
    } else {
      a.relates.push({ id: l.to_id, title: tt })
      b.relates.push({ id: l.from_id, title: ft })
    }
  }
  return out
}


/** Every task reachable from `start` over links of any kind, either way,
 *  with its distance: 0 for `start`, 1 for a direct link, 2+ beyond. */
export function linkGraph(links: TaskLink[], start: string): Map<string, number> {
  const next = new Map<string, string[]>()
  for (const l of links) {
    ;(next.get(l.from_id) ?? next.set(l.from_id, []).get(l.from_id)!).push(l.to_id)
    ;(next.get(l.to_id) ?? next.set(l.to_id, []).get(l.to_id)!).push(l.from_id)
  }
  const depth = new Map([[start, 0]])
  const queue = [start]
  while (queue.length) {
    const id = queue.shift()!
    for (const n of next.get(id) ?? []) {
      if (!depth.has(n)) { depth.set(n, depth.get(id)! + 1); queue.push(n) }
    }
  }
  return depth
}

/** How a card shows while another card is hovered: its direct links
 *  strong, the rest of its graph lighter, everything else faded. */
export type Glow = 'direct' | 'near' | 'off'
export function glowOf(graph: Map<string, number> | null, hovered: string | null, id: string): Glow | undefined {
  if (!graph || !hovered || id === hovered) return undefined
  const d = graph.get(id)
  return d === undefined ? 'off' : d === 1 ? 'direct' : 'near'
}

/** A board: one project (the default) or several seen as one. */
export interface KanbanBoard {
  id: string
  name: string
  projects: string[]
}

export type SortMode = 'manual' | 'oldest' | 'priority' | 'impact' | 'quickwins' | 'newest'
export const SORT_MODES: Array<[SortMode, string]> = [
  ['manual', t('manual (your order)')],
  ['oldest', t('oldest first')],
  ['priority', 'priority'],
  ['impact', 'impact'],
  ['quickwins', t('quick wins')],
  ['newest', t('newest first')],
]

const _LEVEL: Record<string, number> = { high: 0, med: 1, low: 2 }
const _EFFORT: Record<string, number> = { S: 0, M: 1, L: 2 }

/** Sort a column's tasks for a view mode. 'manual' returns the input
 *  (position order); everything else is a stable resort over it. */
export function sortTasks(items: TaskRow[], mode: SortMode, since?: Record<string, string>): TaskRow[] {
  if (mode === 'manual') return items
  const createdOf = (t: TaskRow) => `${t.created_date ?? ''}T${t.created_time ?? ''}`
  const sinceOf = (t: TaskRow) => since?.[t.id] || createdOf(t)
  const level = (v?: string) => _LEVEL[String(v || '').toLowerCase()] ?? 3
  const effort = (v?: string) => _EFFORT[String(v || '').toUpperCase()] ?? 3
  const cmp: Record<Exclude<SortMode, 'manual'>, (a: TaskRow, b: TaskRow) => number> = {
    oldest: (a, b) => sinceOf(a).localeCompare(sinceOf(b)),
    newest: (a, b) => createdOf(b).localeCompare(createdOf(a)),
    priority: (a, b) => level(a.priority) - level(b.priority),
    impact: (a, b) => level(a.impact) - level(b.impact),
    quickwins: (a, b) =>
      (isQuickWin(a.impact, a.effort) ? 0 : 1) - (isQuickWin(b.impact, b.effort) ? 0 : 1) ||
      level(a.impact) - level(b.impact) ||
      effort(a.effort) - effort(b.effort),
  }
  return [...items].sort(cmp[mode]) // Array.sort is stable: ties keep manual order
}

/** Aging bucket for the card corner: days in the current column → color. */
export function ageBucket(sinceIso: string | undefined, now: number): { days: number; color: string } | null {
  if (!sinceIso) return null
  const ms = Date.parse(sinceIso)
  if (!Number.isFinite(ms)) return null
  const days = Math.floor((now - ms) / 86400e3)
  if (days < 1) return null
  const color =
    days >= 14 ? 'var(--status-red)'
    : days >= 7 ? 'var(--status-amber)'
    : days >= 3 ? 'var(--text-tertiary)'
    : 'color-mix(in oklab, var(--text-tertiary) 45%, transparent)'
  return { days, color }
}

export function isQuickWin(impact?: string, effort?: string): boolean {
  return String(impact || '').toLowerCase() === 'high' && String(effort || '').toUpperCase() === 'S'
}

