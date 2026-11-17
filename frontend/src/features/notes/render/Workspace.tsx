/**
 * The Notes page's workspace (tk_3e544086). The operator chose K · Zoom from
 * the third design round; J and L stay drawable here for the design switch
 * (/notes/design?v=j|l). Built on round 2's F:
 * the list, an endless feed of whole notes, the outline rail following the
 * note in view. Common to the three variants:
 *
 *  - a "group by task" switch: off, the list and the feed run newest first;
 *    on, both are grouped under task bands (the feed's band stays at the top
 *    while its notes scroll) and the tiles stand on one shelf per task. The
 *    task's chip is drawn once per group: the note's head, its tile and the
 *    rail leave it out.
 *  - the line between two columns folds the side column (l the list, r the
 *    outline rail); below the wide layout a disclosure button folds the list.
 *  - the tiles: the whole width, shelved by what you do (answer, by hand,
 *    paste, read, replaced) or by task; the note you left is ringed and has
 *    the focus; going back to reading puts the same section under the
 *    reading line, at the same height.
 *
 * The three differ in how the reader moves between reading and the tiles:
 *
 *   J  Switch — the Entry points page's two-icon switch in the toolbar (read | tiles),
 *               kept in this browser; o flips it; a short fade
 *   K  Zoom   — reading and the tiles are two equal screens: one switch, Reading | Tiles,
 *               first in the toolbar in both, flips them (o and Esc too); the line you
 *               were reading flies into its tile and back; a tile reads it; Back undoes a flip
 *   L  Shelves first — the page opens on the shelves (what waits on you first); a tile
 *               drills into reading under a breadcrumb; Esc, the breadcrumb or Back
 *               returns to the shelves; a link to a note opens straight in reading
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { ArrowLeft, BookOpen, ChevronRight, LayoutGrid } from 'lucide-react'

import { Switch } from '../../../components/Switch'
import { EmptyState } from '../../../components/states'
import { LABEL } from '../../../components/ui'
import { isTypingTarget, letter } from '../../../lib/typing'
import { t, tn } from '../../../i18n/scope/notes'
import { Divider, ListBar } from './Divider'
import { openOf, useMarks } from './env'
import { FeedNote, Sentinel, useFeedPages, useInView } from './feed'
import { ACT_TONE, ACT_WORD, actOf, byTask as groupByTask, ListRow, TaskBox, type Act } from './listing'
import type { Note, NoteKind } from './model'
import { FindBox, goTo, KindPills, LinksLine, matches, newestFirst, Outline, ProjectPills } from './parts'
import { anchorOf, keep, LINE, read, reducedMotion, restore, useMedia, usePageState, useView, type Anchor, type View } from './state'
import { NoteTile, ShelfHead, Shelves, TaskHead, type Shelf } from './tiles'
import './notes.css'

export type R3 = 'j' | 'k' | 'l'
export const VIEW_KEY = 'notes-r3-view'

/** A note to put on the screen once it is drawn: its top, or a remembered anchor. */
type Pending = { note: string; anchor?: Anchor }

const tileOf = (id: string) => document.querySelector<HTMLElement>(`[data-testid="note-tile"][data-note="${id}"]`)
const seen = (el: Element) => { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight }

/** The block under the reading line in a note (a paragraph, a list item, a heading, a table): it flies into the tile. */
function heroOf(note: string): HTMLElement | null {
  const art = document.querySelector<HTMLElement>(`[data-feed-note="${note}"]`)
  if (!art) return null
  const r = art.getBoundingClientRect()
  const y = Math.max(r.top + 8, Math.min(r.bottom - 8, window.innerHeight * 0.25))
  const at = typeof document.elementFromPoint === 'function' ? document.elementFromPoint(r.left + r.width / 2, y) : null
  const block = at?.closest<HTMLElement>('h1, h2, h3, p, li, pre, table, figure, details, header')
  if (block && art.contains(block) && block.getBoundingClientRect().height < window.innerHeight / 2) return block
  const head = art.querySelector<HTMLElement>('header')
  return head && seen(head) ? head : null
}

/**
 * K's move, drawn by the browser's view transitions: the main column shrinks
 * away (zooming out) or grows in (zooming in) while the block read morphs
 * into its tile or out of it. No motion when the reader asks for none.
 */
function zoom(dir: 'in' | 'out', update: () => void, from: HTMLElement | null, to: () => HTMLElement | null) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }
  if (reducedMotion() || typeof doc.startViewTransition !== 'function') { flushSync(update); return }
  const root = document.documentElement
  // The app's main column as one picture: only what is on the screen moves, the top bar and the sidebar stay.
  const page = () => document.getElementById('main')
  root.dataset.zoom = dir
  if (from) from.style.viewTransitionName = 'nt-hero'
  const p0 = page(); if (p0) p0.style.viewTransitionName = 'nt-page'
  let landed: HTMLElement | null = null
  const vt = doc.startViewTransition(() => {
    if (from) from.style.viewTransitionName = ''
    flushSync(update)
    landed = to()
    if (landed && from) landed.style.viewTransitionName = 'nt-hero'
    const p1 = page(); if (p1) p1.style.viewTransitionName = 'nt-page'
  })
  void vt.finished.finally(() => {
    if (landed) landed.style.viewTransitionName = ''
    const p1 = page(); if (p1) p1.style.viewTransitionName = ''
    delete root.dataset.zoom
  })
}

export function Workspace3({ v, notes, initial, initialAt, keysLine }: {
  v: R3; notes: Note[]; initial?: string; initialAt?: string
  /** J and L print the page's keys in the toolbar (the design round's line); K has its Tiles button instead. */
  keysLine?: ReactNode
}) {
  const page = usePageState()
  const marks = useMarks()
  const wide = useMedia('(min-width: 1024px)')
  const wider = useMedia('(min-width: 1280px)')
  const [q, setQ] = useState('')
  const [project, setProject] = useState('')
  const [kind, setKind] = useState<NoteKind | ''>('')

  // The first view: J keeps it in this browser; K reads; L opens on the shelves, unless a link names a note.
  const [first] = useState<View>(() => (v === 'j' ? (read(VIEW_KEY) === 'tiles' ? 'tiles' : 'read') : v === 'k' ? 'read' : initial ? 'read' : 'tiles'))
  const [view, setView] = useView(first, v === 'l')
  const tiles = view === 'tiles'

  const filtered = notes.filter((n) => (!project || n.project === project) && (!kind || n.kind === kind) && matches(n, q))
  // The order is fixed when the filters or the grouping change, not on every tick: a note does not jump away under the reader.
  const fkey = filtered.map((n) => n.id).join()
  const order = useMemo(() => groupByTask(filtered, marks).map((g) => [g.task, g.notes.map((n) => n.id)] as const), [fkey]) // eslint-disable-line react-hooks/exhaustive-deps
  const groups = order.map(([task, nids]) => {
    const ns = nids.map((id) => filtered.find((n) => n.id === id)!).filter(Boolean)
    return { task, notes: ns, waiting: ns.filter((n) => openOf(n, marks).toAnswer > 0).length }
  })
  const ordered = page.byTask ? groups.flatMap((g) => g.notes) : [...filtered].sort(newestFirst)
  const idKey = ordered.map((n) => n.id).join()
  const ids = useMemo(() => (idKey ? idKey.split(',') : []), [idKey])
  const pages = useFeedPages(ids)
  const { through } = pages
  const inView = useInView(initial && ids.includes(initial) ? initial : ids[0], `${pages.count}|${page.list}|${page.rail}|${view}|${idKey}|${page.byTask}`)
  const current = ordered.find((n) => n.id === inView.note) ?? ordered[0]

  /* --- where the reader was, and where to put them back --- */
  /** The note opened last (a tile, the list, j / k). */
  const lastGo = useRef<string | null>(null)
  const left = useRef<Anchor | null>(initial ? { note: initial, at: initialAt, offset: 0 } : null)
  const pending = useRef<Pending | null>(initial && !tiles ? { note: initial, anchor: initialAt ? { note: initial, at: initialAt, offset: 0 } : undefined } : null)
  const [tick, setTick] = useState(0)
  // Back (or a link) from the tiles to reading with no tile picked: the line left comes back.
  const wasTiles = useRef(tiles)
  if (wasTiles.current !== tiles) {
    if (!tiles && !pending.current && left.current) pending.current = { note: left.current.note, anchor: left.current }
    wasTiles.current = tiles
  }
  useEffect(() => { if (pending.current && !tiles) through(pending.current.note) }, [through, tiles, tick])
  useLayoutEffect(() => {
    const p = pending.current
    if (!p || tiles) return
    // A note opened at its top lands just under what sticks over the feed (the toolbar, K's tab or L's path, a task band).
    const room = 40 + (v === 'l' ? 32 : 0) + (page.byTask ? 36 : 0) + 8
    const done = restore(p.anchor ?? { note: p.note, offset: room - window.innerHeight * LINE })
    if (done) {
      pending.current = null
      // The note's heading takes the focus without moving the page: a screen reader starts there.
      document.querySelector<HTMLElement>(`[data-feed-note="${p.note}"] h1`)?.focus({ preventScroll: true })
    }
  }, [tiles, pages.count, tick, v, page.byTask])
  // In the tiles, the tile of the note left has the focus, in the middle of the screen (a page that opens on the tiles stays at its top).
  useLayoutEffect(() => {
    if (!tiles) return
    const id = left.current?.note
    const el = id ? tileOf(id) : null
    el?.querySelector('button')?.focus({ preventScroll: true })
    el?.scrollIntoView?.({ block: 'center' })
  }, [tiles])

  const push = v !== 'j'
  /** Leave reading for the tiles, remembering the line read. */
  const toTiles = () => {
    if (tiles) return
    // The note opened last counts while it is on the screen below the one at the reading line: a short last note never reaches the line.
    const last = lastGo.current
    const el = last ? document.querySelector(`[data-feed-note="${last}"]`) : null
    const below = !!el && !!last && last !== current?.id && ids.indexOf(last) > ids.indexOf(current?.id ?? '')
    const mine = below && el && (seen(el) || el.getBoundingClientRect().height === 0) ? last! : current?.id
    const a = anchorOf(mine, mine === current?.id ? inView.section : undefined)
    if (a) left.current = a
    const go = () => setView('tiles', { note: a?.note ?? null, at: a?.at ?? null }, push)
    if (v === 'j') keep(VIEW_KEY, 'tiles')
    if (v === 'k' && a) zoom('out', go, heroOf(a.note), () => tileOf(a.note))
    else go()
  }
  /** Read a note: the one left comes back at the same line; another opens at its top. */
  const openNote = (id: string) => {
    lastGo.current = id
    const back = left.current?.note === id ? left.current : null
    pending.current = { note: id, anchor: back ?? undefined }
    if (!ids.includes(id)) { setQ(''); setProject(''); setKind('') }
    if (v === 'j') keep(VIEW_KEY, 'read')
    const go = () => { through(id); setView('read', { note: id, at: back?.at ?? null }, push && tiles); setTick((x) => x + 1) }
    if (v === 'k' && tiles) zoom('in', go, tileOf(id), () => heroOf(id))
    else go()
  }
  const toRead = () => { const id = left.current?.note ?? current?.id ?? ids[0]; if (id) openNote(id) }
  const flip = () => (tiles ? toRead() : toTiles())

  // A click in the list, j / k: bring the note to the top.
  const go = openNote
  const step = (d: number) => {
    const from = lastGo.current && ids.indexOf(lastGo.current) > ids.indexOf(current?.id ?? '') ? lastGo.current : current?.id
    const at = from ? ids.indexOf(from) : -1
    const next = ids[Math.max(0, Math.min(ids.length - 1, at + d))]
    if (next) { left.current = null; go(next) }
  }

  const live = useRef({ flip, step, toRead, toggle: page.toggle, tiles })
  useEffect(() => { live.current = { flip, step, toRead, toggle: page.toggle, tiles } })
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e)) return
      const k = live.current
      const run = (f: () => void) => { e.preventDefault(); f() }
      if (e.key === 'Escape') {
        if (v === 'l' ? !k.tiles : k.tiles) run(k.flip)
        return
      }
      const l = letter(e)
      if (l === 'o') run(k.flip)
      else if (k.tiles) return
      else if (l === 'l') run(() => k.toggle('list'))
      else if (l === 'r') run(() => k.toggle('rail'))
      else if (l === 'j') run(() => k.step(1))
      else if (l === 'k') run(() => k.step(-1))
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [v])

  /* --- the toolbar --- */
  const switcher = v === 'j' && (
    <div role="group" aria-label={t('View')} className="inline-flex items-center gap-2 rounded-pill border border-border-subtle bg-elevated p-2 shrink-0">
      {([['read', BookOpen, t('Read the notes')], ['tiles', LayoutGrid, t('The notes as tiles')]] as const).map(([key, Icon, label]) => (
        <button key={key} type="button" aria-pressed={view === key} aria-label={label} title={`${label} · o`}
          onClick={() => (key === 'tiles' ? toTiles() : toRead())}
          className={`h-24 w-[28px] inline-flex items-center justify-center rounded-pill transition-colors ${view === key ? 'bg-brand text-on-brand' : 'text-tertiary hover:text-primary hover:bg-hover'}`}>
          <Icon size={13} aria-hidden />
        </button>
      ))}
    </div>
  )
  // K: reading and the tiles are two equal screens, flipped by one switch that stays where it is in both (o, Esc, a tile too); the zoom plays on every flip.
  const kSwitch = v === 'k' && (
    <div role="group" aria-label={t('View')} data-testid="view-switch" className="inline-flex items-center gap-2 rounded-pill border border-border-subtle bg-elevated p-2 shrink-0">
      {([['read', BookOpen, t('Reading')], ['tiles', LayoutGrid, t('Tiles')]] as const).map(([key, Icon, label]) => (
        <button key={key} type="button" aria-pressed={view === key} title={`${label} · o`}
          onClick={() => (key === 'tiles' ? toTiles() : toRead())}
          className={`h-24 px-10 inline-flex items-center gap-6 rounded-pill text-12 transition-colors ${view === key ? 'bg-brand text-on-brand' : 'text-secondary hover:text-primary hover:bg-hover'}`}>
          <Icon size={12} aria-hidden />{label}
        </button>
      ))}
    </div>
  )
  const leftNote = left.current?.note ? notes.find((n) => n.id === left.current?.note) : undefined
  const tilesBack = (
    <>
      {v === 'l' && leftNote && (
        <button type="button" onClick={toRead} data-testid="continue" className="inline-flex items-center gap-6 min-w-0 max-w-[360px] h-24 px-10 rounded-pill border border-brand/50 bg-brand-glow/40 text-12 text-primary hover:bg-brand-glow">
          <BookOpen size={12} className="text-brand shrink-0" aria-hidden /><span className="text-tertiary shrink-0">{t('Continue reading')}</span><span className="truncate">{leftNote.title}</span>
        </button>
      )}
    </>
  )
  // The toolbar row stays at the top in every view (the switch, the way back, find and grouping at hand deep in a feed or a shelf); the sticky columns sit under it.
  const top = 40
  const filters = (
    <>
      <div data-testid="toolbar" className={`flex items-center gap-12 flex-wrap min-w-0 lg:sticky lg:top-0 lg:z-30 lg:bg-base lg:h-[40px]`}>
        {switcher}{kSwitch}
        {tiles && tilesBack}
        <FindBox value={q} onChange={setQ} found={filtered.length} of={notes.length} className="flex-1 min-w-[200px] max-w-[520px]" />
        <Switch on={page.byTask} onChange={page.group} label={t('Group by task')} title={t('The list, the feed and the tiles grouped under their tasks')} />
        {v !== 'k' && keysLine}
      </div>
      <div className="flex items-center gap-12 flex-wrap">
        <ProjectPills notes={notes} value={project} onChange={setProject} />
        <KindPills notes={notes} value={kind} onChange={setKind} />
      </div>
    </>
  )

  /* --- reading --- */
  const rows = page.byTask
    ? groups.map((g) => (
      <div key={g.task || 'none'} className="flex lg:flex-col gap-4 min-w-0 shrink-0 lg:shrink">
        <div className="pt-6 pb-2 min-w-[200px] lg:min-w-0 self-center lg:self-auto"><TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} /></div>
        {g.notes.map((n) => <ListRow key={n.id} note={n} current={n.id === current?.id} onPick={() => go(n.id)} />)}
      </div>
    ))
    : ordered.map((n) => <ListRow key={n.id} note={n} current={n.id === current?.id} onPick={() => go(n.id)} />)
  const list = page.list && (
    <nav id="r3-list" aria-label={t('Notes')} data-col="list"
      className="flex lg:flex-col gap-6 min-w-0 overflow-x-auto lg:overflow-x-visible lg:sticky lg:max-h-[calc(100vh-120px)] lg:overflow-y-auto lg:pr-4 pb-4" style={{ top }}>
      {rows}
      {!ordered.length && <EmptyState compact title={t('Nothing matches.')} />}
    </nav>
  )

  const crumbs = v === 'l' && current && (
    <nav aria-label={t('Where you are')} data-testid="crumbs"
      className="sticky z-20 bg-base flex items-center gap-6 min-w-0 h-32 text-12 max-w-[760px] w-full mx-auto" style={{ top }}>
      <button type="button" onClick={toTiles} className="inline-flex items-center gap-4 h-24 px-8 -ml-8 rounded-pill text-brand hover:bg-hover shrink-0" title={`${t('All notes')} · Esc`}>
        <ArrowLeft size={12} aria-hidden />{t('All notes')}
      </button>
      {/* The shelf the note stands on; grouped by task, the task's band right below names it. */}
      {!page.byTask && <>
        <ChevronRight size={12} className="text-tertiary shrink-0" aria-hidden />
        <span className="text-tertiary shrink-0">{ACT_WORD[actOf(current, openOf(current, marks))]}</span>
      </>}
      <ChevronRight size={12} className="text-tertiary shrink-0" aria-hidden />
      <span className="text-primary truncate min-w-0" aria-current="page">{current.title}</span>
    </nav>
  )
  const bandTop = v === 'l' ? top + 32 : top
  const shown = pages.shown.map((id) => ordered.find((n) => n.id === id)).filter((n): n is Note => !!n)
  const feedNote = (n: Note) => <FeedNote key={n.id} note={n} notes={notes} onGo={go} index={ids.indexOf(n.id)} of={ordered.length} omitTask={page.byTask} />
  const feedBody = page.byTask
    ? groups.map((g) => {
      const mine = shown.filter((n) => g.notes.includes(n))
      if (!mine.length) return null
      return (
        <section key={g.task || 'none'} aria-label={g.task || t('No task')} className="flex flex-col gap-20 min-w-0">
          <div data-testid="task-band" className="sticky z-10 bg-base pt-8 pb-6 border-b border-border-subtle" style={{ top: bandTop }}><TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} /></div>
          {mine.map(feedNote)}
        </section>
      )
    })
    : shown.map(feedNote)
  const feed = (
    <div id="r3-feed" data-col="feed" className="flex flex-col gap-0 min-w-0">
      {crumbs}
      <div data-testid="note-feed" className="flex flex-col gap-20 min-w-0 max-w-[760px] w-full mx-auto">
        {feedBody}
        {pages.left > 0 || pages.loading
          ? <Sentinel onSee={pages.more} loading={pages.loading} left={pages.left} />
          : ordered.length > 0 && <p className="m-0 pt-12 pb-[50vh] text-center text-12 font-mono text-tertiary">{tn(ordered.length, 'That is every note: {n}.', 'That is every note: {n}.')}</p>}
        {!ordered.length && <EmptyState compact title={t('Nothing matches.')} />}
      </div>
    </div>
  )
  const rail = page.rail && current && (
    <aside id="r3-rail" aria-label={t('Outline and links')} data-col="rail" className="flex flex-col gap-12 min-w-0 sticky max-h-[calc(100vh-120px)] overflow-y-auto" style={{ top }}>
      <div className="flex flex-col gap-4">
        <span className={LABEL}>{t('In view')}</span>
        <span className="text-13 text-primary font-medium leading-snug">{current.title}</span>
        <Outline note={current} onGo={goTo} current={inView.section} />
      </div>
      <div className="flex flex-col gap-4"><span className={LABEL}>{t('Its task')}</span><TaskBox note={current} notes={notes} onGo={go} chip={!page.byTask} /></div>
      <div className="flex flex-col gap-4">
        <span className={LABEL}>{t('Links')}</span>
        <LinksLine note={current} max={5} omit={page.byTask ? current.task : undefined} />
      </div>
    </aside>
  )

  let reading: ReactNode
  if (wide) {
    const cols = [page.list ? '280px' : '', '16px', 'minmax(0,1fr)', wider ? '16px' : '', wider && page.rail ? '240px' : ''].filter(Boolean).join(' ')
    reading = (
      <div className="grid gap-x-4 min-w-0 items-start" style={{ gridTemplateColumns: cols }}>
        {list}
        <Divider side="list" open={page.list} onToggle={() => page.toggle('list')} controls="r3-list" top={top} />
        {feed}
        {wider && <Divider side="rail" open={page.rail} onToggle={() => page.toggle('rail')} controls="r3-rail" top={top} />}
        {wider && rail}
      </div>
    )
  } else {
    reading = (
      <div className="flex flex-col gap-12 min-w-0">
        <ListBar open={page.list} onToggle={() => page.toggle('list')} count={ordered.length} controls="r3-list" />
        {list}
        {feed}
      </div>
    )
  }

  /* --- the tiles --- */
  const leftId = left.current?.note
  const leftAt = (() => {
    const n = leftId ? notes.find((x) => x.id === leftId) : undefined
    const at = left.current?.at
    return n && at ? n.sections.find((s) => at === `${n.id}-${s.id}`)?.title || '' : ''
  })()
  const tile = (n: Note) => (
    <NoteTile key={n.id} note={n} current={n.id === leftId} onOpen={() => openNote(n.id)} hideTask={page.byTask}
      extra={n.id === leftId ? <span className="text-11 font-mono text-brand leading-snug">{leftAt ? t('You were reading: {section}', { section: leftAt }) : t('You were reading this note')}</span> : undefined} />
  )
  const shelves: Shelf[] = page.byTask
    ? groups.map((g) => ({ key: g.task || 'none', head: <TaskHead id={g.task} count={g.notes.length} waiting={g.waiting} />, items: g.notes.map(tile) }))
    : (['answer', 'hands', 'paste', 'read', 'replaced'] as Act[]).map((a) => {
      const ns = ordered.filter((n) => actOf(n, openOf(n, marks)) === a)
      return { key: a, head: <ShelfHead count={ns.length} tone={ACT_TONE[a]}>{ACT_WORD[a]}</ShelfHead>, items: ns.map(tile) }
    }).filter((s) => s.items.length)
  const overview = (
    <div data-col="tiles" className={`flex flex-col gap-12 min-w-0 ${v === 'j' ? 'r3-fade' : v === 'l' ? 'r3-back' : ''}`}>
      {ordered.length ? <Shelves shelves={shelves} label={t('Tiles')} /> : <EmptyState compact title={t('Nothing matches.')} />}
    </div>
  )

  const said = tiles
    ? tn(ordered.length, 'Tiles: {n} note', 'Tiles: {n} notes')
    : t('Reading: {title}', { title: current?.title ?? '' })
  return (
    <div className="flex flex-col gap-12 min-w-0" data-view={view} data-r3={v}>
      {filters}
      <p role="status" aria-live="polite" className="sr-only">{said}</p>
      {tiles ? overview : <div key="read" className={v === 'j' ? 'r3-fade' : v === 'l' ? 'r3-drill' : ''}>{reading}</div>}
    </div>
  )
}
