import { useMemo, useState, type ReactNode } from 'react'

import { Badge, Button, toast, type BadgeTone } from '../../../../components/primitives'
import { formatStamp } from '../../../../utils/dateUtils'
import { FIELD } from '../../../promptlib/taskstyle'
import { coreColor, useCoreWrites, type CoreCommit, type CoreDetail, type CoreFile, type CoreNote } from '../data'
import { AgentName, BlockLabel, NoteBody, NoteMeta, typeWord } from '../parts'
import type { CoreBodyProps } from './types'
import { t, tn } from '../../../../i18n/scope/system'

// ---------------------------------------------------------------------------
// What is connected to what (shared with MatrixBody)
// ---------------------------------------------------------------------------

export const isOperatorNote = (n: { author: string }) => n.author === 'operator' || !n.author

const TASK_ID = /\btk_[0-9a-f]{6,}\b/g

/** The tasks a note names: its task_id, and any task id in its words. */
export function tasksNamed(note: CoreNote): string[] {
  const out = new Set<string>()
  if (note.task_id) out.add(note.task_id)
  for (const m of `${note.text} ${note.comment}`.match(TASK_ID) ?? []) out.add(m)
  return [...out]
}

/** The words a note shows: the operator's text, else the agent's line. */
export const noteWords = (n: CoreNote) => (isOperatorNote(n) ? n.text || n.comment : n.comment || n.text)

/** The notes a body shows: with "operator", only the approved ones. Newest first. */
export const shownNotes = (core: CoreDetail, show: 'everyone' | 'operator') =>
  [...core.notes].filter((n) => show !== 'operator' || n.approved).reverse()

export const commitsOf = (core: CoreDetail): CoreCommit[] => core.commits ?? []

/** The files of a task: from the file rows, else from its commits. */
export function filesOfTask(core: CoreDetail, taskId: string): string[] {
  const out = new Set<string>()
  for (const f of core.files) if (f.tasks?.includes(taskId)) out.add(f.path)
  for (const c of commitsOf(core)) if (c.tasks.includes(taskId)) for (const p of c.files) out.add(p)
  return [...out]
}

export function statusTone(status: string): BadgeTone {
  if (status === 'done' || status === 'done-archived') return 'done'
  if (status === 'doing') return 'active'
  if (status === 'agent') return 'auto'
  return 'neutral'
}

export const fileLines = (f: CoreFile) => f.lines_add + f.lines_del
export const baseName = (p: string) => p.split('/').pop() || p

// ---------------------------------------------------------------------------
// The graph: nodes, edges and a fixed columnar layout
// ---------------------------------------------------------------------------

type Kind = 'core' | 'note' | 'task' | 'agent' | 'file' | 'files' | 'notes'
interface GNode { id: string; kind: Kind; key: string; col: number; top: number; height: number }
/** `chat`: every commit behind the line was found by the chat only. */
interface GEdge { a: string; b: string; weight: number; chat: boolean }

/** The columns on a 1000-wide sheet: core · notes · tasks · agents · files. */
const COLS: Array<[number, number]> = [[0, 110], [140, 400], [450, 650], [690, 820], [860, 1000]]
const GAP = 8
const NOTES_MAX = 14
const FILES_MAX = 12

interface Graph {
  nodes: GNode[]
  edges: GEdge[]
  height: number
  near: Map<string, Set<string>>
  notes: CoreNote[]
  hiddenNotes: CoreNote[]
  restFiles: CoreFile[]
}

export function buildGraph(core: CoreDetail, show: 'everyone' | 'operator'): Graph {
  const all = shownNotes(core, show)
  const notes = all.slice(0, NOTES_MAX)
  const hiddenNotes = all.slice(NOTES_MAX)
  const commits = commitsOf(core)
  const taskIds = new Set(core.tasks.map((x) => x.id))
  const files = [...core.files].sort((a, b) => fileLines(b) - fileLines(a))
  const topFiles = files.slice(0, FILES_MAX)
  const restFiles = files.slice(FILES_MAX)
  const topPaths = new Set(topFiles.map((f) => f.path))

  const agentIds: string[] = (core.agents ?? []).map((a) => a.agent_id)
  for (const n of all) if (!isOperatorNote(n) && !agentIds.includes(n.author)) agentIds.push(n.author)

  // Edges, each once, with a weight (commits behind it) and whether only
  // commits found by the chat stand behind it.
  const weights = new Map<string, number>()
  const sure = new Set<string>()
  const add = (a: string, b: string, w = 1, chat = false) => {
    const k = `${a}|${b}`
    weights.set(k, Math.max(weights.get(k) ?? 0, 0) + w)
    if (!chat) sure.add(k)
  }
  for (const n of notes) {
    add('core', `n:${n.id}`)
    for (const tid of tasksNamed(n)) if (taskIds.has(tid)) add(`n:${n.id}`, `t:${tid}`)
    if (!isOperatorNote(n)) add(`n:${n.id}`, `a:${n.author}`)
  }
  if (hiddenNotes.length) add('core', 'notes')
  for (const x of core.tasks) add('core', `t:${x.id}`)
  for (const a of core.agents ?? []) for (const tid of a.given ?? []) if (taskIds.has(tid) && !weights.has(`t:${tid}|a:${a.agent_id}`)) add(`t:${tid}`, `a:${a.agent_id}`, 0)
  // A task's files and agents come from its commits only: a file row's task
  // list counts the commits the chat found too, with no way to tell them apart.
  for (const c of commits) {
    const chat = c.how === 'chat'
    for (const tid of c.tasks) {
      if (!taskIds.has(tid)) continue
      if (c.agent) add(`t:${tid}`, `a:${c.agent}`, 1, chat)
      for (const p of c.files) add(`t:${tid}`, topPaths.has(p) ? `f:${p}` : restFiles.some((f) => f.path === p) ? 'files' : '', 1, chat)
    }
  }
  const edges: GEdge[] = [...weights.entries()]
    .map(([k, weight]) => { const [a, b] = k.split('|') as [string, string]; return { a, b, weight, chat: !sure.has(k) } })
    .filter((e) => e.b !== '')

  const near = new Map<string, Set<string>>()
  for (const e of edges) {
    if (!near.has(e.a)) near.set(e.a, new Set())
    if (!near.has(e.b)) near.set(e.b, new Set())
    near.get(e.a)!.add(e.b)
    near.get(e.b)!.add(e.a)
  }

  // Order inside a column by the mean place of the neighbours on its left: fewer crossings.
  const placeOf = new Map<string, number>()
  notes.forEach((n, i) => placeOf.set(`n:${n.id}`, i))
  const mean = (id: string, prefix: string): number => {
    const ps = [...(near.get(id) ?? [])].filter((x) => x.startsWith(prefix)).map((x) => placeOf.get(x)).filter((x): x is number => x !== undefined)
    return ps.length ? ps.reduce((s, x) => s + x, 0) / ps.length : Number.POSITIVE_INFINITY
  }
  const byMean = (ids: string[], prefix: string) => ids
    .map((id, i) => ({ id, m: mean(id, prefix), i }))
    .sort((a, b) => (a.m - b.m) || (a.i - b.i))
    .map((x) => x.id)
  const taskCommits = (tid: string) => commits.filter((c) => c.tasks.includes(tid)).length
  const tasks = byMean([...core.tasks].sort((a, b) => taskCommits(b.id) - taskCommits(a.id)).map((x) => `t:${x.id}`), 'n:')
  tasks.forEach((id, i) => placeOf.set(id, i))
  const agents = byMean(agentIds.map((a) => `a:${a}`), 't:')
  const fileNodes = byMean(topFiles.map((f) => `f:${f.path}`), 't:')

  const height = (kind: Kind, id: string): number => {
    if (kind === 'core') return 72
    if (kind === 'note') return isOperatorNote(notes.find((n) => `n:${n.id}` === id) ?? { author: '' }) ? 72 : 56
    if (kind === 'notes') return 28
    if (kind === 'file' || kind === 'files') return 30
    return 36
  }
  const columns: Array<Array<{ id: string; kind: Kind; key: string }>> = [
    [{ id: 'core', kind: 'core', key: core.id }],
    [...notes.map((n) => ({ id: `n:${n.id}`, kind: 'note' as Kind, key: n.id })),
      ...(hiddenNotes.length ? [{ id: 'notes', kind: 'notes' as Kind, key: '' }] : [])],
    tasks.map((id) => ({ id, kind: 'task' as Kind, key: id.slice(2) })),
    agents.map((id) => ({ id, kind: 'agent' as Kind, key: id.slice(2) })),
    [...fileNodes.map((id) => ({ id, kind: 'file' as Kind, key: id.slice(2) })),
      ...(restFiles.length ? [{ id: 'files', kind: 'files' as Kind, key: '' }] : [])],
  ]
  const colHeight = columns.map((col) => col.reduce((s, n) => s + height(n.kind, n.id) + GAP, 0) - GAP)
  const total = Math.max(120, ...colHeight)
  const nodes: GNode[] = []
  columns.forEach((col, ci) => {
    // The notes start at the top: they are read first. The rest sit centred on them.
    let y = ci === 1 ? 0 : Math.max(0, Math.round((Math.min(total, colHeight[1]! || total) - colHeight[ci]!) / 2))
    if (y + colHeight[ci]! > total) y = 0
    for (const n of col) {
      const h = height(n.kind, n.id)
      nodes.push({ ...n, col: ci, top: y, height: h })
      y += h + GAP
    }
  })
  return { nodes, edges, height: total, near, notes, hiddenNotes, restFiles }
}

// ---------------------------------------------------------------------------
// The body
// ---------------------------------------------------------------------------

/**
 * The core as a drawing of its connections: the core on the left, then its
 * notes (the operator's largest), the linked tasks, the agents, the files.
 * Pointing at a node lights up what it is connected to; clicking it opens
 * its details beside the drawing, with what can be done from there.
 */
/** The core as the graph shows it: without the commits found only by the
 *  chat, unless asked. Their files and their count on the agents go too. */
export function withoutChatCommits(core: CoreDetail): CoreDetail {
  const commits = commitsOf(core).filter((c) => c.how !== 'chat')
  const paths = new Set(commits.flatMap((c) => c.files))
  const anchors = new Set(core.links.filter((l) => l.kind === 'anchor').map((l) => l.target.split(':')[0]))
  const count = new Map<string, number>()
  for (const c of commits) if (c.agent) count.set(c.agent, (count.get(c.agent) ?? 0) + 1)
  return {
    ...core,
    commits,
    commits_n: commits.length,
    files: core.files.filter((f) => paths.has(f.path) || anchors.has(f.path)),
    agents: (core.agents ?? []).map((a) => ({ ...a, commits: count.get(a.agent_id) ?? 0 }))
      .filter((a) => a.commits > 0 || a.notes > 0 || (a.given ?? []).length > 0),
  }
}

export function GraphBody({ projectCode, core: full, show, onOpenTask, onNewTask }: CoreBodyProps) {
  const [withChat, setWithChat] = useState(false)
  const chatN = useMemo(() => commitsOf(full).filter((c) => c.how === 'chat').length, [full])
  const core = useMemo(() => (withChat ? full : withoutChatCommits(full)), [full, withChat])
  const graph = useMemo(() => buildGraph(core, show), [core, show])
  const [hot, setHot] = useState<string | null>(null)
  const [picked, setPicked] = useState<string>('core')
  const lit = hot ?? picked
  const litSet = useMemo(() => new Set([lit, ...(graph.near.get(lit) ?? [])]), [graph, lit])
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph])
  const pickedNode = byId.get(picked) ?? byId.get('core')!
  const dim = lit !== 'core'

  return (
    <div className="grid gap-20 min-w-0" style={{ gridTemplateColumns: 'minmax(0, 1fr) 300px' }}>
      <section aria-label={t('Connections')} className="flex flex-col gap-10 min-w-0">
        <div className="flex items-center gap-14 flex-wrap text-11 font-mono text-tertiary">
          <label className="flex items-center gap-6">
            <input type="checkbox" checked={withChat} onChange={(e) => setWithChat(e.target.checked)} disabled={chatN === 0} />
            {tn(chatN, 'Show {n} commit found by the chat only', 'Show {n} commits found by the chat only')}
          </label>
          <span className="flex items-center gap-6"><i aria-hidden="true" className="block w-[18px] border-t border-secondary" />{t('signed or linked')}</span>
          {withChat && <span className="flex items-center gap-6"><i aria-hidden="true" className="block w-[18px] border-t border-dashed border-secondary" />{t('found by the chat')}</span>}
          {!withChat && chatN > 0 && core.commits.length === 0 && (
            <span>{t('No commit of this core names its task yet. Only the chat links them.')}</span>
          )}
        </div>
        <div className="relative h-[16px]" aria-hidden="true">
          {[t('core'), t('notes'), t('tasks'), t('agents'), t('files')].map((label, i) => (
            <span key={label} className="absolute text-10 font-mono uppercase tracking-wider text-tertiary truncate"
              style={{ left: `${COLS[i]![0] / 10}%`, width: `${(COLS[i]![1] - COLS[i]![0]) / 10}%` }}>{label}</span>
          ))}
        </div>
        <div className="relative min-w-0" style={{ height: graph.height }}>
          <svg aria-hidden="true" className="absolute inset-0 w-full overflow-visible" style={{ height: graph.height }}
            viewBox={`0 0 1000 ${graph.height}`} preserveAspectRatio="none">
            {graph.edges.map((e) => {
              const a = byId.get(e.a)
              const b = byId.get(e.b)
              if (!a || !b) return null
              const [l, r] = a.col <= b.col ? [a, b] : [b, a]
              const x1 = COLS[l.col]![1]
              const x2 = COLS[r.col]![0]
              const y1 = l.top + l.height / 2
              const y2 = r.top + r.height / 2
              const mid = (x1 + x2) / 2
              const on = litSet.has(e.a) && litSet.has(e.b) && (e.a === lit || e.b === lit)
              const fromCore = e.a === 'core'
              return (
                <path key={`${e.a}|${e.b}`} data-edge={`${e.a}|${e.b}`} data-on={on ? '1' : '0'}
                  d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                  fill="none" vectorEffect="non-scaling-stroke"
                  stroke={on ? 'var(--brand)' : 'var(--border-strong)'}
                  strokeWidth={on ? Math.min(2.5, 1.25 + e.weight * 0.25) : 1}
                  strokeOpacity={on ? 1 : dim ? 0.35 : fromCore ? 0.6 : 1}
                  strokeDasharray={e.chat ? '4 3' : undefined} />
              )
            })}
          </svg>
          {graph.nodes.map((n) => (
            <div key={n.id} className="absolute" style={{
              left: `${COLS[n.col]![0] / 10}%`, width: `${(COLS[n.col]![1] - COLS[n.col]![0]) / 10}%`, top: n.top, height: n.height,
              opacity: dim && !litSet.has(n.id) ? 0.3 : 1,
            }}>
              <NodeButton node={n} core={core} graph={graph} picked={picked === n.id}
                onHot={setHot} onPick={setPicked} />
            </div>
          ))}
        </div>
        <p className="m-0 text-10 font-mono text-tertiary">
          {t('Point at a box to see what it is connected to. Click it for the details. Lines show: a note names a task or was written by an agent; an agent worked on a task; a task changed a file.')}
        </p>
      </section>

      <aside aria-label={t('Details')} className="flex flex-col gap-12 min-w-0 border-l border-border-subtle pl-20">
        <Panel node={pickedNode} core={core} graph={graph} projectCode={projectCode}
          onPick={setPicked} onOpenTask={onOpenTask} onNewTask={onNewTask} />
      </aside>
    </div>
  )
}

function NodeButton({ node, core, graph, picked, onHot, onPick }: {
  node: GNode; core: CoreDetail; graph: Graph; picked: boolean
  onHot: (id: string | null) => void; onPick: (id: string) => void
}) {
  const base = `w-full h-full text-left rounded-input border px-8 flex flex-col justify-center gap-2 min-w-0 overflow-hidden focus-visible:outline-2 focus-visible:outline-offset-1 ${picked ? 'border-brand' : 'border-border-default hover:border-border-strong'}`
  const handlers = {
    onMouseEnter: () => onHot(node.id), onMouseLeave: () => onHot(null),
    onFocus: () => onHot(node.id), onBlur: () => onHot(null),
    onClick: () => onPick(node.id), 'aria-pressed': picked, type: 'button' as const,
  }
  const links = graph.near.get(node.id)?.size ?? 0
  const linkWord = tn(links, '{n} connection', '{n} connections')

  if (node.kind === 'core') {
    return (
      <button {...handlers} aria-label={t('Core {name}, {links}', { name: core.name, links: linkWord })}
        className={`${base} bg-surface`}>
        <span className="text-10 font-mono uppercase tracking-wider truncate" style={{ color: coreColor(core.type) }}>{typeWord(core.type)}</span>
        <span className="text-13 font-semibold text-primary line-clamp-2 break-words">{core.name}</span>
      </button>
    )
  }
  if (node.kind === 'note') {
    const note = graph.notes.find((x) => x.id === node.key)!
    const op = isOperatorNote(note)
    const words = noteWords(note)
    const label = op
      ? t('Your note, {date}: {words}', { date: formatStamp(note.at), words })
      : t('Agent note, {date}: {words}', { date: formatStamp(note.at), words })
    return (
      <button {...handlers} aria-label={label}
        className={`${base} ${op ? 'bg-base' : 'bg-elevated'} ${!op && !note.approved ? 'border-dashed' : ''}`}
        style={op ? { borderColor: picked ? undefined : 'var(--brand)', borderWidth: 1.5 } : undefined}>
        <span className={`${op ? 'text-13 text-primary' : 'text-12 text-secondary'} line-clamp-2 break-words`}>{words}</span>
        <span className="text-10 font-mono text-tertiary truncate">
          {note.at.slice(5, 10)} · {op ? t('you') : <AgentName id={note.author} />}
          {!op && !note.approved && <span className="text-brand"> · {t('awaiting approval')}</span>}
        </span>
      </button>
    )
  }
  if (node.kind === 'notes') {
    return (
      <button {...handlers} aria-label={tn(graph.hiddenNotes.length, '{n} earlier note', '{n} earlier notes')} className={`${base} bg-surface`}>
        <span className="text-11 font-mono text-tertiary">{tn(graph.hiddenNotes.length, '+{n} earlier note', '+{n} earlier notes')}</span>
      </button>
    )
  }
  if (node.kind === 'task') {
    const task = core.tasks.find((x) => x.id === node.key)!
    return (
      <button {...handlers} aria-label={t('Task {title}, {status}, {links}', { title: task.title, status: task.status, links: linkWord })}
        className={`${base} bg-surface`}>
        <span className="flex items-center gap-6 min-w-0">
          <span className="text-10 font-mono text-tertiary shrink-0">{task.status}</span>
          <span className="text-12 text-primary truncate">{task.title}</span>
        </span>
      </button>
    )
  }
  if (node.kind === 'agent') {
    const agent = (core.agents ?? []).find((a) => a.agent_id === node.key)
    return (
      <button {...handlers} aria-label={t('Agent {id}, {links}', { id: node.key, links: linkWord })} className={`${base} bg-surface`}>
        <span className="text-12 text-primary truncate"><AgentName id={node.key} /></span>
        {agent && <span className="text-10 font-mono text-tertiary truncate">{tn(agent.commits, '{n} commit', '{n} commits')}</span>}
      </button>
    )
  }
  if (node.kind === 'file') {
    const file = core.files.find((f) => f.path === node.key)!
    return (
      <button {...handlers} title={file.path} aria-label={t('File {path}, {links}', { path: file.path, links: linkWord })} className={`${base} bg-surface`}>
        <span className="flex items-center justify-between gap-6 min-w-0">
          <span className="text-11 font-mono text-primary truncate">{baseName(file.path)}</span>
          <span className="text-10 font-mono text-tertiary shrink-0">±{fileLines(file)}</span>
        </span>
      </button>
    )
  }
  return (
    <button {...handlers} aria-label={tn(graph.restFiles.length, '{n} more file', '{n} more files')} className={`${base} bg-surface`}>
      <span className="text-11 font-mono text-tertiary">{tn(graph.restFiles.length, '+{n} file', '+{n} files')}</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// The side panel
// ---------------------------------------------------------------------------

function Panel({ node, core, graph, projectCode, onPick, onOpenTask, onNewTask }: {
  node: GNode; core: CoreDetail; graph: Graph; projectCode: string
  onPick: (id: string) => void; onOpenTask: (id: string) => void; onNewTask: () => void
}) {
  const writes = useCoreWrites(projectCode, core.id)
  const [draft, setDraft] = useState('')
  const off = core.status !== 'view'
  const fail = (e: unknown, title: string) => toast.error(title, { description: e instanceof Error ? e.message : String(e) })
  const approve = (id: string) => writes.approve.mutate(id, { onError: (e) => fail(e, t('Could not approve the note.')) })
  const taskId = node.kind === 'task' ? node.key : ''
  const addNote = async () => {
    const text = draft.trim()
    if (!text) return
    try { await writes.note.mutateAsync(taskId ? { text, task_id: taskId } : { text }); setDraft('') } catch (e) { fail(e, t('Could not add the note.')) }
  }
  const commits = commitsOf(core)
  const near = [...(graph.near.get(node.id) ?? [])]
  const neighbours = (prefix: string) => near.filter((x) => x.startsWith(prefix))

  let body: ReactNode
  if (node.kind === 'core') {
    const waiting = core.notes.filter((n) => !n.approved).length
    body = (
      <>
        <PanelHead kind={t('core')} title={core.name} />
        {core.reason && <p className="m-0 text-12 text-secondary">{core.reason}</p>}
        <dl className="m-0 grid gap-x-10 gap-y-4 text-11 font-mono" style={{ gridTemplateColumns: 'auto minmax(0, 1fr)' }}>
          <Fact k={t('notes')}>{core.notes.length}{waiting ? ` · ${tn(waiting, '{n} awaits approval', '{n} await approval')}` : ''}</Fact>
          <Fact k={t('tasks')}>{core.tasks.length}</Fact>
          <Fact k={t('agents')}>{(core.agents ?? []).length}</Fact>
          <Fact k={t('commits')}>{core.commits_n}</Fact>
          <Fact k={t('files')}>{core.files.length}</Fact>
        </dl>
        {!off && <Button size="sm" variant="ghost" className="self-start" onClick={onNewTask}>{t('New task')}</Button>}
      </>
    )
  } else if (node.kind === 'note') {
    const note = graph.notes.find((x) => x.id === node.key)!
    const named = neighbours('t:')
    body = (
      <>
        <PanelHead kind={isOperatorNote(note) ? t('your note') : t('agent note')} />
        <NoteBody note={note} />
        <NoteMeta note={note} onApprove={approve} busy={writes.approve.isPending} />
        <Related label={t('names')} empty={t('Names no task.')} ids={named} onPick={onPick} core={core} />
        {named.length > 0 && <Button size="sm" variant="ghost" className="self-start" onClick={() => onOpenTask(named[0]!.slice(2))}>{t('Open task')}</Button>}
      </>
    )
  } else if (node.kind === 'notes') {
    body = (
      <>
        <PanelHead kind={t('earlier notes')} />
        <ol className="m-0 p-0 list-none flex flex-col gap-10">
          {graph.hiddenNotes.map((n) => (
            <li key={n.id} className="flex flex-col gap-4 border-t border-border-subtle pt-8">
              <NoteBody note={n} />
              <NoteMeta note={n} onApprove={approve} busy={writes.approve.isPending} />
            </li>
          ))}
        </ol>
      </>
    )
  } else if (node.kind === 'task') {
    const task = core.tasks.find((x) => x.id === node.key)!
    const mine = commits.filter((c) => c.tasks.includes(task.id))
    body = (
      <>
        <PanelHead kind={t('task')} title={task.title} aside={<Badge tone={statusTone(task.status)}>{task.status}</Badge>} />
        <Button size="sm" className="self-start" onClick={() => onOpenTask(task.id)}>{t('Open task')}</Button>
        <Related label={t('notes')} empty={t('No note names it.')} ids={neighbours('n:')} onPick={onPick} core={core} graph={graph} />
        <Related label={t('agents')} empty={t('No agent yet.')} ids={neighbours('a:')} onPick={onPick} core={core} />
        <Related label={t('files')} empty={t('No files yet.')} ids={[...neighbours('f:'), ...neighbours('files')]} onPick={onPick} core={core} graph={graph} />
        <CommitList commits={mine} />
      </>
    )
  } else if (node.kind === 'agent') {
    const agent = (core.agents ?? []).find((a) => a.agent_id === node.key)
    const mine = commits.filter((c) => c.agent === node.key)
    body = (
      <>
        <PanelHead kind={t('agent')} title={<AgentName id={node.key} />} />
        {agent && (
          <dl className="m-0 grid gap-x-10 gap-y-4 text-11 font-mono" style={{ gridTemplateColumns: 'auto minmax(0, 1fr)' }}>
            <Fact k={t('commits')}>{agent.commits}</Fact>
            <Fact k={t('chats')}>{tn(agent.turns, '{n} turn', '{n} turns')} · {tn(agent.sessions, '{n} chat', '{n} chats')}</Fact>
            <Fact k={t('notes')}>{agent.notes}</Fact>
            {agent.last_at && <Fact k={t('last')}>{formatStamp(agent.last_at)}</Fact>}
          </dl>
        )}
        <Related label={t('tasks')} empty={t('No linked task.')} ids={neighbours('t:')} onPick={onPick} core={core} />
        <Related label={t('notes')} empty={t('No notes.')} ids={neighbours('n:')} onPick={onPick} core={core} graph={graph} />
        <CommitList commits={mine} />
      </>
    )
  } else if (node.kind === 'file') {
    const file = core.files.find((f) => f.path === node.key)!
    const mine = commits.filter((c) => c.files.includes(file.path))
    const agents = [...new Set(mine.map((c) => c.agent).filter(Boolean))]
    body = (
      <>
        <PanelHead kind={t('file')} title={<span className="font-mono text-12 break-all">{file.path}</span>} />
        <span className="text-11 font-mono text-secondary">+{file.lines_add} −{file.lines_del}</span>
        <Related label={t('tasks')} empty={t('No linked task.')} ids={neighbours('t:')} onPick={onPick} core={core} />
        <Related label={t('agents')} empty={t('No agent yet.')} ids={agents.map((a) => `a:${a}`)} onPick={onPick} core={core} />
        <CommitList commits={mine} />
      </>
    )
  } else {
    body = (
      <>
        <PanelHead kind={t('more files')} />
        <ul className="m-0 p-0 list-none flex flex-col gap-2">
          {graph.restFiles.map((f) => (
            <li key={f.path} className="flex justify-between gap-8 text-11 font-mono text-secondary">
              <span className="truncate" title={f.path}>{f.path}</span><span className="text-tertiary shrink-0">±{fileLines(f)}</span>
            </li>
          ))}
        </ul>
      </>
    )
  }

  return (
    <>
      {body}
      {!off && (
        <div className="flex flex-col gap-6 border-t border-border-subtle pt-12">
          <label className="flex flex-col gap-4">
            <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{taskId ? t('Note on this task') : t('Note on the core')}</span>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3}
              placeholder={t('Write the note here, or type #core-note in a chat')}
              className={`${FIELD} w-full font-sans`} />
          </label>
          {draft.trim() && (
            <Button size="sm" className="self-end" disabled={writes.note.isPending} onClick={() => void addNote()}>{t('Add note')}</Button>
          )}
        </div>
      )}
    </>
  )
}

function PanelHead({ kind, title, aside }: { kind: string; title?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <BlockLabel aside={aside}>{kind}</BlockLabel>
      {title && <h3 className="m-0 text-14 font-semibold text-primary break-words">{title}</h3>}
    </div>
  )
}

function Fact({ k, children }: { k: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-tertiary">{k}</dt>
      <dd className="m-0 text-primary min-w-0 truncate">{children}</dd>
    </>
  )
}

/** Neighbour nodes as buttons that move the panel to them. */
function Related({ label, empty, ids, onPick, core, graph }: {
  label: string; empty: string; ids: string[]; onPick: (id: string) => void; core: CoreDetail; graph?: Graph
}) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <BlockLabel aside={ids.length || undefined}>{label}</BlockLabel>
      {ids.length === 0 && <span className="text-11 text-tertiary">{empty}</span>}
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => onPick(id)}
          className="text-left text-12 text-primary truncate hover:text-brand min-w-0">
          {nameOf(id, core, graph)}
        </button>
      ))}
    </div>
  )
}

function nameOf(id: string, core: CoreDetail, graph?: Graph): ReactNode {
  const key = id.slice(2)
  if (id.startsWith('t:')) return core.tasks.find((x) => x.id === key)?.title ?? key
  if (id.startsWith('a:')) return <AgentName id={key} />
  if (id.startsWith('f:')) return <span className="font-mono text-11">{key}</span>
  if (id.startsWith('n:')) {
    const n = graph?.notes.find((x) => x.id === key)
    return n ? noteWords(n) : key
  }
  if (id === 'files') return <span className="font-mono text-11">{tn(graph?.restFiles.length ?? 0, '+{n} file', '+{n} files')}</span>
  return id
}

function CommitList({ commits }: { commits: CoreCommit[] }) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <BlockLabel aside={commits.length || undefined}>{t('commits')}</BlockLabel>
      {commits.length === 0 && <span className="text-11 text-tertiary">{t('No commits.')}</span>}
      {commits.slice(0, 12).map((c) => (
        <div key={c.sha} className="flex flex-col text-11 min-w-0">
          <span className="text-primary break-words">{c.subject}</span>
          <span className="font-mono text-10 text-tertiary">{c.sha.slice(0, 7)} · {c.at.slice(0, 10)} · {howWord(c.how)}</span>
        </div>
      ))}
      {commits.length > 12 && <span className="text-10 font-mono text-tertiary">{tn(commits.length - 12, '{n} more', '{n} more')}</span>}
    </div>
  )
}

export function howWord(how: string): string {
  if (how === 'signed') return t('signed')
  if (how === 'linked') return t('linked')
  if (how === 'chat') return t('found in a chat')
  return how
}
