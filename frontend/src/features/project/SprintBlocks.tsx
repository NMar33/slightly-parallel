/*
 * The blocks board answers "what": its columns are the blocks themselves
 * (plus backlog), tasks moving between them with one click or a drag.
 */
import { useState, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'

import { hm } from '../../utils/format'
import { Button } from '../../components/primitives'
import { persistPref, readJsonPref } from '../../lib/uiPrefs'
import { BatchMenu, StatusDot, useBlockDialogs } from './SprintParts'
import { groupOf, verdictOf, type SprintRow } from './sprintsModel'
import type { TaskRow } from './kanban/model'
import { t, tn } from '../../i18n/scope/project'

type Column = { id: string | null; name: string; sprint?: SprintRow }

const colKey = (id: string | null) => id ?? '__backlog'

function readPair(key: string): string[] {
  const raw = readJsonPref<unknown>(key, [])
  return Array.isArray(raw) && raw.length ? raw.map(String) : []
}

/**
 * At most two columns open; the rest fold to strips. Any two of all —
 * backlog included. Opening a strip folds the column opened longest ago.
 * The open pair is a synced pref, read again for another project's key.
 */
function useOpenPair(openKey: string, cols: Column[], sprints: SprintRow[]) {
  const [held, setHeld] = useState(() => ({ key: openKey, pair: readPair(openKey) }))
  const openPair = held.key === openKey ? held.pair : readPair(openKey)
  if (held.key !== openKey) setHeld({ key: openKey, pair: openPair })
  // Default pair: the most urgent block + backlog; self-heals when a
  // remembered column disappeared (block ended).
  const validIds = cols.map((c) => colKey(c.id))
  const urgent = [...sprints].sort((a, b) => (a.days_left ?? 99) - (b.days_left ?? 99))[0]
  const effectivePair = (() => {
    const kept = openPair.filter((k) => validIds.includes(k))
    if (kept.length >= Math.min(2, validIds.length)) return kept.slice(-2)
    const fill = [urgent ? colKey(urgent.id) : null, '__backlog', ...validIds]
      .filter((k): k is string => !!k && validIds.includes(k) && !kept.includes(k))
    return [...kept, ...fill].slice(0, 2)
  })()
  const expand = (id: string | null) => {
    const k = colKey(id)
    // Most-recent two stay open: append, keep the last two distinct keys.
    const next = [...effectivePair.filter((x) => x !== k), k].slice(-2)
    setHeld({ key: openKey, pair: next })
    persistPref(openKey, JSON.stringify(next))
  }
  return { effectivePair, expand }
}

export function BlocksView({
  sprints, tasksOf, onOpen, onAssign, onAssignMany, onAdd, onEnd, onMoveMany, onSprintChanged, newSprint, openKey,
}: {
  sprints: SprintRow[]
  /** localStorage/pref key remembering which two columns are open. */
  openKey: string
  tasksOf: (id: string | null) => TaskRow[]
  onOpen: (t: TaskRow) => void
  onAssign: (taskId: string, sprintId: string) => void
  onAssignMany: (taskIds: string[], sprintId: string) => void
  onAdd: (sprintId: string | null, title: string) => void
  onEnd: (s: SprintRow, retro: string) => void
  onMoveMany: (taskIds: string[], sprintId: string) => void
  onSprintChanged: () => void
  newSprint: ReactNode
}) {
  const { edit, finish, dialogs } = useBlockDialogs({ sprints, tasksOf, onEnd, onMoveMany, onSprintChanged })
  const [adding, setAdding] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const cols: Column[] = [
    ...sprints.map((s) => ({ id: s.id as string | null, name: s.name, sprint: s })),
    { id: null, name: t('Backlog · no sprint') },
  ]
  const { effectivePair, expand } = useOpenPair(openKey, cols, sprints)
  const move = (t: TaskRow) => {
    const order: Array<string | null> = [...sprints.map((s) => s.id), null]
    const i = order.indexOf(t.sprint_id || null)
    const next = order[(i + 1) % order.length]
    onAssign(t.id, next ?? '')
  }
  return (
    <div className="flex flex-col gap-8">
      <div className="overflow-x-auto">
        <div
          className="grid gap-8"
          style={{
            gridTemplateColumns: cols.map((c) => (effectivePair.includes(colKey(c.id)) ? 'minmax(240px, 1fr)' : '36px')).join(' '),
            minWidth: `${effectivePair.length * 250 + (cols.length - effectivePair.length) * 44}px`,
          }}
        >
          {cols.map((c) => {
            const ts = tasksOf(c.id)
            if (!effectivePair.includes(colKey(c.id))) {
              const v = c.sprint ? verdictOf(c.sprint) : null
              return (
                <div
                  key={colKey(c.id)}
                  role="button"
                  tabIndex={0}
                  aria-label={`Open ${c.name}`}
                  title={t('{name} · {tasks}. Click to open, drop a card to assign.', { name: c.name, tasks: tn(ts.length, '{n} task', '{n} tasks') })}
                  onClick={() => expand(c.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') expand(c.id) }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault()
                    const id = e.dataTransfer.getData('text/plain')
                    if (id) onAssign(id, c.id ?? '')
                  }}
                  className={`rounded-card border border-dashed bg-elevated/60 flex flex-col items-center py-8 gap-6 min-h-[200px] cursor-pointer hover:border-brand ${v && v.verdict.startsWith('overdue') ? 'border-status-red/50' : 'border-border-default'}`}
                >
                  <span className="text-11 text-tertiary leading-none" aria-hidden>‹</span>
                  <span
                    className={`flex-1 flex items-center uppercase font-mono select-none ${v && v.verdict.startsWith('overdue') ? 'text-status-red/80' : 'text-tertiary/80'}`}
                    style={{ writingMode: 'vertical-rl', fontSize: 13, letterSpacing: '0.45em' }}
                  >
                    {(c.sprint ? c.name : 'backlog').toLowerCase()} · {ts.length}
                  </span>
                </div>
              )
            }
            const groups: Array<['doing' | 'todo' | 'done', TaskRow[]]> = [
              ['doing', ts.filter((t) => groupOf(t.status) === 'doing')],
              ['todo', ts.filter((t) => groupOf(t.status) === 'todo')],
              ['done', ts.filter((t) => groupOf(t.status) === 'done')],
            ]
            const v = c.sprint ? verdictOf(c.sprint) : null
            return (
              <div
                key={c.id ?? 'backlog'}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  const id = e.dataTransfer.getData('text/plain')
                  if (id) onAssign(id, c.id ?? '')
                }}
                className="rounded-card bg-elevated p-8 flex flex-col gap-6 min-h-[200px]"
              >
                <div className="flex items-baseline gap-6 border-b-2 border-border-default pb-4">
                  {c.sprint ? (
                    <button
                      type="button"
                      onClick={() => edit(c.sprint!)}
                      title={t('Edit block')}
                      className="text-11 uppercase tracking-wide font-mono text-primary font-bold truncate text-left hover:text-brand"
                    >
                      {c.name} <span className="normal-case font-normal text-tertiary">✎</span>
                    </button>
                  ) : (
                    <span className="text-11 uppercase tracking-wide font-mono text-primary font-bold truncate">{c.name}</span>
                  )}
                  {c.sprint && v && (
                    <span className={`text-10 font-mono shrink-0 ${v.cls}`}>
                      {c.sprint.days_left != null && c.sprint.days_left < 0 ? t('+{n}d', { n: -c.sprint.days_left }) : t('{n}d', { n: c.sprint.days_left ?? '—' })} · {hm(c.sprint.human_min)}{c.sprint.budget_h ? `/${c.sprint.budget_h}h` : ''}
                    </span>
                  )}
                  {c.sprint && (
                    <button
                      type="button"
                      onClick={() => finish(c.sprint!)}
                      className="ml-auto shrink-0 h-20 px-8 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-border-strong"
                      title={t('End this block and save the retro. The retro is required.')}
                    >
                      {t('finish')}
                    </button>
                  )}
                </div>
                {groups.map(([g, list]) => list.length > 0 && (
                  <div key={g} className="flex flex-col gap-3">
                    <div className="flex items-center gap-6">
                      <span className="text-10 uppercase tracking-wider font-mono text-tertiary">{g}</span>
                      <BatchMenu
                        label={`${list.length} ${g}`}
                        targets={[
                          ...sprints.filter((sp) => sp.id !== c.id).map((sp) => ({ id: sp.id, name: sp.name })),
                          ...(c.id !== null ? [{ id: '', name: t('Backlog') }] : []),
                        ]}
                        onPick={(target) => onAssignMany(list.map((t) => t.id), target)}
                      />
                    </div>
                    {list.map((task) => (
                      <div
                        key={task.id}
                        draggable
                        onDragStart={(e) => { e.dataTransfer.setData('text/plain', task.id); e.dataTransfer.effectAllowed = 'move' }}
                        className={`rounded-input bg-surface border border-border-subtle px-8 py-4 flex items-center gap-6 cursor-grab active:cursor-grabbing ${g === 'done' ? 'opacity-60' : ''}`}
                      >
                        <StatusDot status={task.status ?? ''} />
                        <button
                          type="button"
                          onClick={() => onOpen(task)}
                          title={t('Open the task')}
                          className={`text-12 flex-1 min-w-0 truncate text-left hover:underline decoration-dotted ${g === 'done' ? 'text-tertiary line-through' : 'text-primary'}`}
                        >
                          {task.title}
                        </button>
                        <Button variant="text" size="bare" onClick={() => move(task)} className="shrink-0" title={t('Move to the next block')} aria-label={t('Move to the next block')}>
                          <ArrowRight size={11} aria-hidden />
                        </Button>
                      </div>
                    ))}
                  </div>
                ))}
                {adding === (c.id ?? '__backlog') ? (
                  <form
                    onSubmit={(e) => { e.preventDefault(); if (title.trim()) { onAdd(c.id, title.trim()); setTitle(''); setAdding(null) } }}
                    className="flex items-center gap-4"
                  >
                    <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') setAdding(null) }} placeholder={t('Task…')} className="bg-surface border border-border-default rounded-input px-6 py-2 text-11 text-primary flex-1 min-w-0 outline-none" />
                    <button type="submit" className="text-11 font-mono text-brand">+</button>
                  </form>
                ) : (
                  <button type="button" onClick={() => { setAdding(c.id ?? '__backlog'); setTitle('') }} className="text-11 font-mono text-brand text-left">{t('+ task')}</button>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {newSprint}
      {dialogs}
    </div>
  )
}
