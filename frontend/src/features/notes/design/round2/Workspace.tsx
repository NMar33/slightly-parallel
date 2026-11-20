/**
 * Round 2 of the Notes design (tk_3e544086), on the basis of A · Reader:
 * the list on the left, an endless feed of whole notes in the middle, the
 * outline rail on the right following the note in view. The list and the
 * feed can be hidden; with the feed hidden the page becomes shelves of
 * tiles, and a tile opens the note back in the feed. Four variants differ
 * in how the hiding is done, what the shelves group by and where the task
 * window's view of notes sits:
 *
 *   F  Scroll   — a two-button switch; shelves by project; the rail holds the task of the note in view
 *   G  Waiting  — a hide button on each column, a strip to bring it back; the feed opens with what waits
 *                 on you, task by task, in the task window's form; shelves by what you do
 *   H  Tasks    — the switch; list and feed grouped by task under a task band; shelves of tasks,
 *                 a tile opening the task window's notes in place
 *   I  Modes    — one control with four modes; a "by task" filter that puts the task window's
 *                 notes on top of the feed; shelves by entry point
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

import { FilterPill } from '../../../../components/FilterPill'
import { Segmented } from '../../../../components/Segmented'
import { Button } from '../../../../components/primitives/Button'
import { EmptyState } from '../../../../components/states'
import { LABEL } from '../../../../components/ui'
import { t, tn } from '../../../../i18n/scope/notes'
import { IdChip } from '../blocks'
import { SUPERSEDED_BY } from '../mock'
import { ACT_TONE, ACT_WORD, actOf, byTask, ListRow, TaskBox, type Act } from '../../render/listing'
import type { Note, NoteKind } from '../model'
import {
  FindBox, goTo, KindPills, LinksLine, matches, newestFirst, Outline, ProjectMark, ProjectPills,
} from '../parts'
import { openOf, useMarks, type Open } from '../store'
import { TaskNotes } from '../TaskNotes'
import { ColumnSwitch, KeysLine, useColumns, usePageKeys } from './columns'
import { NoteFeed, scrollToNote, useFeedPages, useInView } from './feed'
import { NoteTile, ShelfHead, Shelves, TaskHead, type Shelf } from './tiles'

export type R2 = 'f' | 'g' | 'h' | 'i'

const waits = (o: Open) => o.toAnswer + o.toTick + o.toCopy > 0

// The list's parts moved to the shared module (../../render/listing); F–I import them from there.
export { ACT_TONE, ACT_WORD, actOf, byTask, ListRow, TaskBox, type Act } from '../../render/listing'

/* ------------------------------------------------------------- the shell */

export function Workspace({ v, notes, initial }: { v: R2; notes: Note[]; initial?: string }) {
  const cols = useColumns()
  const marks = useMarks()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [project, setProject] = useState('')
  const [kind, setKind] = useState<NoteKind | ''>('')
  const task = v === 'i' ? params.get('task') ?? '' : ''
  const pickTask = (id: string) => {
    const next = new URLSearchParams(params)
    if (id) next.set('task', id)
    else next.delete('task')
    setParams(next, { replace: true })
  }
  const filtered = notes.filter((n) => (!project || n.project === project) && (!kind || n.kind === kind) && matches(n, q)
    && (!task || n.task === task || n.refs.includes(task)))
  // The order of the feed is fixed when the filters change, not on every tick: a note does not jump away under the reader.
  const fkey = filtered.map((n) => n.id).join()
  const order = useMemo(() => byTask(filtered, marks).map((g) => [g.task, g.notes.map((n) => n.id)] as const), [fkey]) // eslint-disable-line react-hooks/exhaustive-deps
  // The counts are live (an answer changes them at once); only the order waits for the filters.
  const groups = order.map(([task, nids]) => {
    const ns = nids.map((id) => filtered.find((n) => n.id === id)!).filter(Boolean)
    return { task, notes: ns, waiting: ns.filter((n) => openOf(n, marks).toAnswer > 0).length }
  })
  const ordered = v === 'h' ? groups.flatMap((g) => g.notes) : [...filtered].sort(newestFirst)
  const idKey = ordered.map((n) => n.id).join()
  const ids = useMemo(() => (idKey ? idKey.split(',') : []), [idKey])
  const pages = useFeedPages(ids)
  const inView = useInView(initial && ids.includes(initial) ? initial : ids[0], `${pages.count}|${cols.list}|${cols.feed}|${idKey}`)
  const current = ordered.find((n) => n.id === inView.note) ?? ordered[0]

  // A note to bring into view once it is drawn: a click in the list, on a tile, a key, the ?note= of a link.
  const [target, setTarget] = useState<string | null>(initial ?? null)
  const { through } = pages
  // Runs again after a filter is cleared for it: the new order is in `through` by then.
  useEffect(() => { if (target) through(target) }, [target, through])
  useEffect(() => {
    if (!target) return
    if (document.querySelector(`[data-feed-note="${target}"]`)) { scrollToNote(target, false); setTarget(null) }
  }, [target, pages.count, cols.feed])
  const go = (id: string) => {
    if (!ids.includes(id)) { setQ(''); setProject(''); setKind(''); if (task) pickTask('') }
    if (!cols.feed) cols.toggle('feed')
    through(id)
    setTarget(id)
    last.current = id
  }
  // j / k step from the note last gone to while it is still the one in view or below it: a short last note never reaches the reading line.
  const last = useRef<string | null>(null)
  const step = (d: number) => {
    const from = last.current && ids.indexOf(last.current) > ids.indexOf(current?.id ?? '') ? last.current : current?.id
    const at = from ? ids.indexOf(from) : -1
    const next = ids[Math.max(0, Math.min(ids.length - 1, at + d))]
    if (next && cols.feed) go(next)
  }
  const [openTask, setOpenTask] = useState<string | null>(null)
  usePageKeys({
    list: () => cols.toggle('list'),
    feed: () => cols.toggle('feed'),
    next: cols.feed ? () => step(1) : undefined,
    prev: cols.feed ? () => step(-1) : undefined,
    escape: openTask ? () => setOpenTask(null) : undefined,
  })

  /* the controls over the columns */
  const modes = [
    ['all', t('All three'), t('The list, the feed, the outline')],
    ['read', t('Reading'), t('The feed and the outline, the list hidden')],
    ['listtiles', t('List and tiles'), t('The list beside the tiles')],
    ['tiles', t('Tiles'), t('Only the tiles, the whole width')],
  ] as const
  type Mode = typeof modes[number][0]
  const mode: Mode = cols.feed ? (cols.list ? 'all' : 'read') : (cols.list ? 'listtiles' : 'tiles')
  const setMode = (m: Mode) => cols.set(m === 'all' ? [] : m === 'read' ? ['list'] : m === 'listtiles' ? ['feed'] : ['list', 'feed'])
  const switcher = v === 'i'
    ? <Segmented label={t('Columns')} shape="pill" value={mode} onChange={setMode} options={[...modes]} />
    : v === 'g' ? null : <ColumnSwitch list={cols.list} feed={cols.feed} onList={() => cols.toggle('list')} onFeed={() => cols.toggle('feed')} />

  const taskPills = v === 'i' && (
    <div className="flex items-center gap-4 flex-wrap" role="group" aria-label={t('By task')}>
      <span className={`${LABEL} mr-4`}>{t('By task')}</span>
      <FilterPill on={!task} onClick={() => pickTask('')} count={notes.length}>{t('all')}</FilterPill>
      {byTask(notes, marks).filter((g) => g.task).map((g) => (
        <FilterPill key={g.task} on={task === g.task} onClick={() => pickTask(task === g.task ? '' : g.task)} count={g.notes.length}
          dot={g.waiting ? 'var(--status-amber)' : undefined} title={g.waiting ? tn(g.waiting, '{n} waits on an answer', '{n} wait on an answer') : undefined}>
          {g.task}
        </FilterPill>
      ))}
    </div>
  )

  const filters = (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center gap-12 flex-wrap min-w-0">
        {switcher}
        <FindBox value={q} onChange={setQ} found={filtered.length} of={notes.length} className="flex-1 min-w-[200px] max-w-[520px]" />
        <KeysLine />
      </div>
      <div className="flex items-center gap-12 flex-wrap">
        <ProjectPills notes={notes} value={project} onChange={setProject} />
        <KindPills notes={notes} value={kind} onChange={setKind} />
      </div>
      {taskPills}
    </div>
  )

  /* the list */
  const hideBtn = (what: 'list' | 'feed') => v === 'g' && (
    <button type="button" onClick={() => cols.toggle(what)} title={`${what === 'list' ? t('Hide the list') : t('Hide the feed: tiles')} · ${what === 'list' ? 'l' : 'f'}`}
      aria-label={what === 'list' ? t('Hide the list') : t('Hide the feed: tiles')}
      className="ml-auto inline-flex items-center gap-2 h-20 px-6 rounded-pill text-10 font-mono text-tertiary hover:text-primary hover:bg-hover">
      <ChevronLeft size={12} aria-hidden />{what === 'list' ? 'l' : 'f'}
    </button>
  )
  const rows = v === 'h'
    ? groups.map((g) => (
      <div key={g.task || 'none'} className="flex lg:flex-col gap-4 min-w-0 shrink-0 lg:shrink">
        <div className="pt-6 pb-2 min-w-[200px] lg:min-w-0 self-center lg:self-auto"><TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} /></div>
        {g.notes.map((n) => <ListRow key={n.id} note={n} current={n.id === current?.id && cols.feed} onPick={() => go(n.id)} />)}
      </div>
    ))
    : ordered.map((n) => <ListRow key={n.id} note={n} current={n.id === current?.id && cols.feed} onPick={() => go(n.id)} />)
  const list = cols.list && (
    <nav aria-label={t('Notes')} data-col="list"
      className="flex lg:flex-col gap-6 min-w-0 overflow-x-auto lg:overflow-x-visible lg:sticky lg:top-0 lg:max-h-[calc(100vh-24px)] lg:overflow-y-auto lg:pr-4 pb-4">
      {v === 'g' && <div className="flex items-center gap-6 shrink-0 max-lg:self-start"><span className={LABEL}>{t('List')}</span>{hideBtn('list')}</div>}
      {rows}
      {!ordered.length && <EmptyState compact title={t('Nothing matches.')} />}
    </nav>
  )
  /** G: a hidden column leaves a strip that brings it back. */
  const strip = (what: 'list' | 'feed') => (
    <button type="button" onClick={() => cols.toggle(what)} data-strip={what}
      aria-label={what === 'list' ? t('Show the list') : t('Show the feed')} title={`${what === 'list' ? t('Show the list') : t('Show the feed')} · ${what === 'list' ? 'l' : 'f'}`}
      className="sticky top-0 self-start flex shrink-0 flex-col items-center gap-6 w-[28px] py-10 rounded-card border border-border-subtle bg-surface text-tertiary hover:text-primary hover:bg-hover">
      <ChevronRight size={12} aria-hidden />
      <span className="text-10 font-mono uppercase tracking-wide" style={{ writingMode: 'vertical-rl' }}>{what === 'list' ? t('List') : t('Feed')}</span>
    </button>
  )

  /* the feed's openings */
  const waitingBand = v === 'g' && (() => {
    const gs = byTask(filtered.filter((n) => !SUPERSEDED_BY[n.id] && waits(openOf(n, marks))), marks)
    if (!gs.length) return <p className="m-0 text-12 text-status-green">{t('Nothing waits on you.')}</p>
    return (
      <section aria-label={t('Waits on you')} data-testid="waits-band" className="flex flex-col gap-12 rounded-card border border-status-amber/40 bg-surface px-16 py-12 min-w-0">
        <div className="flex items-baseline gap-8 flex-wrap">
          <span className={`${LABEL} text-status-amber`}>{t('Waits on you')}</span>
          <span className="text-12 text-secondary">{t('task by task, as in the task window; the notes in full follow below')}</span>
        </div>
        {gs.map((g) => (
          <div key={g.task || 'none'} className="flex flex-col gap-4 min-w-0">
            <TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} />
            <TaskNotes taskId={g.task} notes={g.notes} />
          </div>
        ))}
      </section>
    )
  })()
  const taskOpening = v === 'i' && task && (
    <section aria-label={t('The task')} data-testid="task-opening" className="flex flex-col gap-8 rounded-card border border-border-subtle bg-surface px-16 py-12 min-w-0">
      <div className="flex items-center gap-8 min-w-0 flex-wrap">
        <IdChip id={task} full />
        <Button variant="ghost" size="sm" iconLeft={<X size={12} aria-hidden />} className="ml-auto" onClick={() => pickTask('')}>{t('Every task')}</Button>
      </div>
      <TaskNotes taskId={task} notes={notes} />
    </section>
  )
  const band = v === 'h' ? (n: Note) => {
    const g = groups.find((x) => x.notes[0]?.id === n.id)
    return g ? <div className="pt-8 pb-4 sticky top-0 z-10 bg-base" data-testid="task-band"><TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} /></div> : null
  } : undefined

  const feed = cols.feed && (
    <div data-col="feed" className="flex gap-8 min-w-0">
      {v === 'g' && !cols.list && strip('list')}
      <div className="flex flex-col gap-8 min-w-0 flex-1">
        {v === 'g' && <div className="flex items-center gap-6 max-w-[760px] w-full mx-auto"><span className={LABEL}>{t('Feed')}</span>{hideBtn('feed')}</div>}
        <NoteFeed notes={ordered} all={notes} pages={pages} onGo={go} prelude={<>{waitingBand}{taskOpening}</>} above={band} />
      </div>
    </div>
  )
  const rail = cols.feed && current && (
    <aside aria-label={t('Outline and links')} data-col="rail" className="hidden xl:flex flex-col gap-12 min-w-0 sticky top-0 max-h-[calc(100vh-24px)] overflow-y-auto">
      <div className="flex flex-col gap-4">
        <span className={LABEL}>{t('In view')}</span>
        <span className="text-13 text-primary font-medium leading-snug">{current.title}</span>
        <Outline note={current} onGo={goTo} current={inView.section} />
      </div>
      {v === 'f' && <div className="flex flex-col gap-4"><span className={LABEL}>{t('Its task')}</span><TaskBox note={current} notes={notes} onGo={go} /></div>}
      <div className="flex flex-col gap-4">
        <span className={LABEL}>{t('Links')}</span>
        <LinksLine note={current} max={5} />
      </div>
    </aside>
  )

  /* the tiles */
  const tile = (n: Note) => <NoteTile key={n.id} note={n} current={n.id === current?.id} onOpen={() => go(n.id)} />
  const shelves: Shelf[] = (() => {
    if (v === 'g') {
      const acts: Act[] = ['answer', 'hands', 'paste', 'read', 'replaced']
      return acts.map((a) => {
        const ns = ordered.filter((n) => actOf(n, openOf(n, marks)) === a)
        return { key: a, head: <ShelfHead count={ns.length} tone={ACT_TONE[a]}>{ACT_WORD[a]}</ShelfHead>, items: ns.map(tile) }
      }).filter((s) => s.items.length)
    }
    if (v === 'h') {
      return groups.map((g) => ({
        key: g.task || 'none',
        head: <TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} />,
        items: [(
          <TaskTile key="t" task={g.task} notes={g.notes} open={openTask === g.task}
            onToggle={() => setOpenTask(openTask === g.task ? null : g.task)} onRead={() => g.notes[0] && go(g.notes[0].id)} />
        ), ...g.notes.map(tile)],
        after: openTask === g.task && (
          <div className="rounded-card border border-brand/50 bg-surface px-16 py-12 flex flex-col gap-8 min-w-0" data-testid="task-card">
            <div className="flex items-center gap-8 min-w-0 flex-wrap">
              {g.task ? <IdChip id={g.task} full /> : <span className={LABEL}>{t('No task')}</span>}
              <span className="ml-auto flex items-center gap-8">
                <Button variant="ghost" size="sm" onClick={() => g.notes[0] && go(g.notes[0].id)}>{t('Read in the feed')}</Button>
                <Button variant="ghost" size="sm" iconLeft={<X size={12} aria-hidden />} onClick={() => setOpenTask(null)}>{t('Close · Esc')}</Button>
              </span>
            </div>
            <TaskNotes taskId={g.task} notes={g.notes} />
          </div>
        ),
      }))
    }
    if (v === 'i') {
      const eps = [...new Set(ordered.map((n) => n.entrypoint ?? ''))]
      return eps.map((ep) => {
        const ns = ordered.filter((n) => (n.entrypoint ?? '') === ep)
        return { key: ep || 'none', head: ep ? <h2 className="m-0 flex items-center gap-8 min-w-0"><IdChip id={ep} /><span className="text-11 font-mono text-tertiary">{tn(ns.length, '{n} note', '{n} notes')}</span><span className="flex-1 border-t border-border-subtle" /></h2> : <ShelfHead count={ns.length}>{t('No entry point')}</ShelfHead>, items: ns.map(tile) }
      })
    }
    const codes = [...new Set(ordered.map((n) => n.project))]
    return codes.map((c) => {
      const ns = ordered.filter((n) => n.project === c)
      return { key: c, head: <ShelfHead count={ns.length}><ProjectMark code={c} /></ShelfHead>, items: ns.map(tile) }
    })
  })()
  const tiles = !cols.feed && (
    <div data-col="tiles" className="flex gap-8 min-w-0">
      {v === 'g' && !cols.list && strip('list')}
      {v === 'g' && strip('feed')}
      <div className="flex flex-col gap-12 min-w-0 flex-1">
        {taskOpening}
        {ordered.length ? <Shelves shelves={shelves} label={t('Tiles')} /> : <EmptyState compact title={t('Nothing matches.')} />}
      </div>
    </div>
  )

  const grid = cols.feed
    ? (cols.list ? 'lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_240px]' : 'xl:grid-cols-[minmax(0,1fr)_240px]')
    : (cols.list ? 'lg:grid-cols-[280px_minmax(0,1fr)]' : '')
  return (
    <div className="flex flex-col gap-12 min-w-0" data-columns={mode}>
      {filters}
      <div className={`grid gap-16 min-w-0 items-start ${grid}`}>
        {list}
        {feed}
        {rail}
        {tiles}
      </div>
    </div>
  )
}

/** H: a task as the first tile of its shelf; it opens the task window's notes across the shelf. */
function TaskTile({ task, notes, open, onToggle, onRead }: { task: string; notes: Note[]; open: boolean; onToggle: () => void; onRead: () => void }) {
  const marks = useMarks()
  const sum = notes.reduce((a, n) => { const o = openOf(n, marks); return { ans: a.ans + o.toAnswer, tick: a.tick + o.toTick } }, { ans: 0, tick: 0 })
  return (
    <div data-testid="task-tile" className={`rounded-input border border-dashed p-10 flex flex-col gap-8 min-w-0 ${open ? 'border-brand bg-brand-glow/40' : 'border-border-default bg-surface'}`}>
      <span className={LABEL}>{t('The task window')}</span>
      {task ? <IdChip id={task} full /> : <span className="text-13 text-secondary">{t('Notes without a task')}</span>}
      <span className="text-12 text-secondary">{tn(notes.length, '{n} note', '{n} notes')}</span>
      {sum.ans > 0 && <span className="text-11 font-mono text-status-amber">{tn(sum.ans, '{n} choice waits', '{n} choices wait')}</span>}
      {sum.tick > 0 && <span className="text-11 font-mono text-status-amber">{t('{n} to tick', { n: sum.tick })}</span>}
      <span className="mt-auto flex items-center gap-12 flex-wrap">
        <Button variant="link" size="bare" className="text-12" aria-expanded={open} onClick={onToggle}>{open ? t('Fold') : t('Open its notes here')}</Button>
        <Button variant="link" size="bare" className="text-12" onClick={onRead}>{t('Read in the feed')}</Button>
      </span>
    </div>
  )
}
