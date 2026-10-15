/*
 * One line per thing on a day — a task (coloured by why it is there), an
 * entry (by its kind), a milestone — the drag that moves them, the
 * project's dot, and the density bars of the work under a day.
 */
import type { DragEvent } from 'react'
import { Flag } from 'lucide-react'

import { projectColor } from '../../utils/projectColor'
import {
  KIND_COLOR, KIND_GLYPH, LAYER_COLOR, factLine, isDone,
  type CalEntry, type CalTask, type DayFacts, type DayItem, type Milestone, type Why,
} from './model'

import { t } from '../../i18n/scope/views'
// ---------------------------------------------------------------------------
// Density — the work under a day
// ---------------------------------------------------------------------------

/** Four hairline bars: sessions · commits · lines · hours, each against the
 *  range's busiest day. Reads as texture from afar, as numbers on hover. */
export function DensityBar({ facts, max, height = 14, className = '' }: { facts: DayFacts; max: { sessions: number; commits: number; lines: number; hours: number }; height?: number; className?: string }) {
  const bars = [
    { v: facts.sessions, m: max.sessions, c: 'var(--brand)' },
    { v: facts.commits, m: max.commits, c: 'var(--status-green)' },
    { v: facts.add + facts.del, m: max.lines, c: 'var(--status-purple)' },
    { v: facts.hours_min, m: max.hours, c: 'var(--status-amber)' },
  ]
  const line = factLine(facts)
  if (!line) return <div className={className} style={{ height }} aria-hidden />
  return (
    <div role="img" className={`flex items-end gap-1 ${className}`} style={{ height }} title={line} aria-label={line}>
      {bars.map((b, i) => b.v > 0 && (
        <span
          key={i}
          className="inline-block w-4"
          style={{ height: Math.max(2, Math.round((b.v / (b.m || 1)) * height)), backgroundColor: b.c, opacity: 0.85 }}
        />
      ))}
    </div>
  )
}

export function densityMax(days: Record<string, DayFacts>): { sessions: number; commits: number; lines: number; hours: number } {
  const m = { sessions: 0, commits: 0, lines: 0, hours: 0 }
  for (const f of Object.values(days)) {
    m.sessions = Math.max(m.sessions, f.sessions)
    m.commits = Math.max(m.commits, f.commits)
    m.lines = Math.max(m.lines, f.add + f.del)
    m.hours = Math.max(m.hours, f.hours_min)
  }
  return m
}

// ---------------------------------------------------------------------------
// Pills — one line per thing on a day
// ---------------------------------------------------------------------------

const WHY_GLYPH: Record<Why, string> = { due: '⚑', planned: '☀', done: '✓', created: '+', resurface: '↻' }
const WHY_WORD: Record<Why, string> = { due: 'due', planned: 'planned', done: 'done', created: 'written', resurface: t('comes back') }

/** HTML5 drag of a task id — every variant's day cell accepts it. */
export function dragTask(e: DragEvent, id: string): void {
  e.dataTransfer.setData('text/sp-task', id)
  e.dataTransfer.effectAllowed = 'move'
}
export function droppedTask(e: DragEvent): string {
  return e.dataTransfer.getData('text/sp-task')
}
function dragEntry(e: DragEvent, id: string): void {
  e.dataTransfer.setData('text/sp-entry', id)
  e.dataTransfer.effectAllowed = 'move'
}
export function droppedEntry(e: DragEvent): string {
  return e.dataTransfer.getData('text/sp-entry')
}

/** The project's colour, the one the whole dashboard uses for it. */
export function ProjectDot({ code, className = '' }: { code: string; className?: string }) {
  const color = projectColor(code)
  return <span role="img" aria-label={code} title={code} className={`inline-block w-6 h-6 rounded-pill shrink-0 ${className}`} style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}` }} />
}

function TaskPill({ task, why, onClick, dense = false, showWhy = false, showProject = false }: { task: CalTask; why: Why; onClick?: () => void; dense?: boolean; showWhy?: boolean; showProject?: boolean }) {
  const color = LAYER_COLOR[why]
  const done = isDone(task)
  return (
    <button
      type="button"
      draggable
      onDragStart={(e) => dragTask(e, task.id)}
      onClick={onClick}
      title={`${task.title} · ${WHY_WORD[why]} · ${task.status}${task.assignee ? ` · ${task.assignee}` : ''}`}
      className={`w-full min-w-0 flex items-center gap-4 rounded-input text-left hover:bg-hover ${dense ? 'h-20 px-4 text-10' : 'h-24 px-6 text-11'} ${done ? 'text-tertiary' : 'text-primary'}`}
      style={{ boxShadow: `inset 2px 0 0 ${color}` }}
    >
      <span aria-hidden className="shrink-0 font-mono" style={{ color }}>{WHY_GLYPH[why]}</span>
      {showProject && task.project && <ProjectDot code={task.project} />}
      <span className={`truncate ${done ? 'line-through' : ''}`}>{task.title}</span>
      {showWhy && <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{WHY_WORD[why]}</span>}
    </button>
  )
}

function EntryPill({ entry, onClick, dense = false, showProject = false }: { entry: CalEntry; onClick?: () => void; dense?: boolean; showProject?: boolean }) {
  const color = KIND_COLOR[entry.kind] ?? KIND_COLOR.note
  const off = entry.status !== 'open'
  return (
    <button
      type="button"
      draggable={entry.source === 'calendar'}
      onDragStart={(e) => dragEntry(e, entry.id)}
      onClick={onClick}
      title={`${entry.kind}${entry.time ? ` · ${entry.time}` : ''} · ${entry.title}${entry.people ? ` · ${entry.people}` : ''}`}
      className={`w-full min-w-0 flex items-center gap-4 rounded-input text-left hover:bg-hover ${dense ? 'h-20 px-4 text-10' : 'h-24 px-6 text-11'} ${off ? 'text-tertiary' : 'text-primary'}`}
      style={{ backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)` }}
    >
      <span aria-hidden className="shrink-0" style={{ color }}>{KIND_GLYPH[entry.kind] ?? '▪'}</span>
      {showProject && entry.project && <ProjectDot code={entry.project} />}
      {entry.time && <span className="font-mono text-tertiary shrink-0 tabular">{entry.time}</span>}
      <span className={`truncate ${off ? 'line-through' : ''}`}>{entry.title}</span>
    </button>
  )
}

function MilestonePill({ milestone, onClick, dense = false, showProject = false }: { milestone: Milestone; onClick?: () => void; dense?: boolean; showProject?: boolean }) {
  const reached = milestone.status === 'reached'
  return (
    <button
      type="button"
      onClick={onClick}
      title={t('milestone · {title} · {done_n}/{tasks_n} tasks done{v}', { title: milestone.title, done_n: milestone.done_n, tasks_n: milestone.tasks_n, v: milestone.outcome ? ` · ${milestone.outcome}` : '' })}
      className={`w-full min-w-0 flex items-center gap-4 rounded-input text-left font-medium hover:bg-hover ${dense ? 'h-20 px-4 text-10' : 'h-24 px-6 text-11'} ${reached ? 'text-status-green' : 'text-primary'}`}
      style={{ border: `1px solid ${reached ? 'var(--status-green)' : 'var(--status-red)'}` }}
    >
      <Flag size={dense ? 9 : 11} aria-hidden className="shrink-0" style={{ color: reached ? 'var(--status-green)' : 'var(--status-red)' }} />
      {showProject && milestone.project && <ProjectDot code={milestone.project} />}
      <span className="truncate">{milestone.title}</span>
      {milestone.tasks_n > 0 && <span className="ml-auto font-mono text-tertiary tabular shrink-0">{milestone.done_n}/{milestone.tasks_n}</span>}
    </button>
  )
}

/** One item, whichever kind — the day cells and the panels all use this. */
export function ItemPill({ item, dense, onTask, onEntry, onMilestone, showWhy, showProject }: {
  item: DayItem
  dense?: boolean
  showWhy?: boolean
  /** More than one project in view: the project's dot on every pill. */
  showProject?: boolean
  onTask?: (it: CalTask) => void
  onEntry?: (e: CalEntry) => void
  onMilestone?: (m: Milestone) => void
}) {
  if (item.kind === 'task') return <TaskPill task={item.task} why={item.why} dense={dense} showWhy={showWhy} showProject={showProject} onClick={() => onTask?.(item.task)} />
  if (item.kind === 'entry') return <EntryPill entry={item.entry} dense={dense} showProject={showProject} onClick={() => onEntry?.(item.entry)} />
  return <MilestonePill milestone={item.milestone} dense={dense} showProject={showProject} onClick={() => onMilestone?.(item.milestone)} />
}
