/**
 * The terminal, in the three places it lives:
 *
 * - **Drawer** — at the bottom of every page, like an editor's panel: the
 *   ` key or the top bar's button shows it; drag its top edge; maximise it.
 *   The app shell mounts it through `Dock.tsx`, which loads this file the
 *   first time the drawer opens.
 * - **TerminalPage** — /terminal and the project's Terminals tab: every
 *   terminal in a list by project, with its agent and task, beside the one
 *   open.
 * - **Wall** — every live terminal at once, in a grid: a glance at all the
 *   agents working (a Lab look).
 *
 * All three are one Deck — tabs over screens — so a terminal reads the same
 * wherever it is. Screens stay mounted while hidden (their scrollback), and
 * are dropped when the surface closes: tmux keeps the terminal meanwhile.
 */

import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, Columns2, Focus, LayoutList, ListOrdered, Minimize2, Rows2, Search, Settings2, X } from 'lucide-react'

import {
  STATE_WORD, setDock, useDock, useTerminalActions, useTerminalStatus, useTerminals,
  type TermSession, type TermState,
} from '../../lib/terminal'
import { Screen, TERMINAL_GROUND, type ScreenApi } from './Screen'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { MAX_PANES, isLeaf, leaves, parse, prune, remove, replace, resize, splitAt, type Node, type Split as SplitNode } from './split'
import { Launcher, NewButton, StateDot, Tab, TerminalSettings, TurnOn } from './parts'
import { t, tn } from '../../i18n/scope/system'

const DARK_BAR = 'bg-[var(--term-bar)] border-white/10'

function Popover({ open, onClose, children, align = 'right' }: { open: boolean; onClose: () => void; children: ReactNode; align?: 'right' | 'left' }) {
  if (!open) return null
  return (
    <>
      <button type="button" aria-label={t('Close')} className="fixed inset-0 z-[88] cursor-default" onClick={onClose} />
      <div className={`absolute bottom-full mb-6 ${align === 'right' ? 'right-0' : 'left-0'} z-[89] rounded-card border border-border-default bg-base shadow-lg`}>{children}</div>
    </>
  )
}

/* ---------------------------------------------------------------- layout */

/** How a surface splits (split.ts), and which pane has the keyboard. */
interface Layout { tree: Node | null; focus: string }

function readLayout(key: string): Layout {
  try {
    const l = JSON.parse(readPref(`sp-term-layout:${key}`) ?? 'null') ?? {}
    return { tree: parse(l.tree), focus: String(l.focus || '') }
  } catch {
    return { tree: null, focus: '' }
  }
}

function useLayout(key: string): [Layout, (l: Layout) => void] {
  const [held, setHeld] = useState(() => ({ key, l: readLayout(key) }))
  // Another surface (the next project's page) reads its own split.
  const l = held.key === key ? held.l : readLayout(key)
  if (held.key !== key) setHeld({ key, l })
  const set = (next: Layout) => {
    setHeld({ key, l: next })
    persistPref(`sp-term-layout:${key}`, JSON.stringify(next))
  }
  return [l, set]
}

/** aA: the text smaller or bigger, for every terminal, right away. */
function TextSize() {
  const st = useTerminalStatus().data
  const act = useTerminalActions()
  if (!st) return null
  const size = st.font_size
  const step = (d: number) => void act.setting({ 'terminal.font_size': Math.max(10, Math.min(22, size + d)) })
  return (
    <span className="inline-flex items-center h-24 rounded-input border border-white/10 overflow-hidden" role="group" aria-label={t('Terminal text size')}>
      <button type="button" onClick={() => step(-1)} disabled={size <= 10} title={t('Smaller text (Ctrl −)')} aria-label={t('Smaller text')}
        className="h-full px-6 text-[11px] leading-none text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5 disabled:opacity-30">a</button>
      <span className="px-4 text-[10px] font-mono tabular-nums text-[var(--term-muted)]" title={t('Text size in px')}>{size}</span>
      <button type="button" onClick={() => step(1)} disabled={size >= 22} title={t('Bigger text (Ctrl +)')} aria-label={t('Bigger text')}
        className="h-full px-6 text-[15px] leading-none font-semibold text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5 disabled:opacity-30">A</button>
    </span>
  )
}

/**
 * Tabs over panes: the core every surface shares.
 *
 * One pane, or two to four side by side (split right) or stacked (split
 * down), each its own terminal with its own state; drag between them to
 * share the room. A tab puts its terminal in the pane in focus. Splitting
 * opens a new shell in the focused terminal's folder.
 */
function Deck({ sessions, active, onActive, bar, project, empty, layoutKey = 'drawer' }: {
  sessions: TermSession[]
  active: string
  onActive: (id: string) => void
  /** Right end of the tab bar: the surface's own buttons. */
  bar?: ReactNode
  project?: string
  /** What stands in the screen when there is no terminal. */
  empty?: ReactNode
  /** Where the split is remembered (drawer, page:<project>). */
  layoutKey?: string
}) {
  const st = useTerminalStatus().data
  const act = useTerminalActions()
  const [launching, setLaunching] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [layout, setLayout] = useLayout(layoutKey)
  const live = sessions.filter((s) => s.state !== 'ended' || s.id === active)
  const known = new Set(live.map((s) => s.id))
  let tree = prune(layout.tree, known)
  if (!tree) {
    const first = live.find((s) => s.id === active) ?? live[live.length - 1]
    tree = first ? { id: first.id } : null
  }
  const shownIds = leaves(tree)
  const focus = shownIds.includes(layout.focus) ? layout.focus : shownIds[0] ?? ''
  const tabs = useRef<HTMLDivElement>(null)
  /** Each pane's actions (find, select lines), for the bar to reach the focused one. */
  const apis = useRef(new Map<string, ScreenApi>())
  useEffect(() => { tabs.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' }) }, [focus])
  // The terminal that asks to be shown (Resume, a status click) comes into the focused pane.
  // A terminal just launched is asked for before the list holds it: the
  // effect runs again when it arrives.
  const activeKnown = !!active && known.has(active)
  useEffect(() => {
    if (!activeKnown || shownIds.includes(active) || !tree) return
    setLayout({ tree: replace(tree, focus, active), focus: active })
    // Only a new ask moves a pane; the layout itself changing must not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, activeKnown])
  if (!st) return null
  if (!st.enabled) return <div className="h-full bg-base overflow-auto"><TurnOn /></div>
  const launch = launching || !live.length
  const many = shownIds.length > 1

  const setFocus = (id: string) => { if (id !== focus) setLayout({ tree, focus: id }) }
  const pick = (id: string) => {
    setLaunching(false)
    onActive(id)
    if (shownIds.includes(id) || !tree) { setLayout({ tree: tree ?? { id }, focus: id }); return }
    setLayout({ tree: replace(tree, focus, id), focus: id })
  }
  const split = async (dir: 'row' | 'col') => {
    if (splitting || shownIds.length >= MAX_PANES || !tree) return
    const from = live.find((s) => s.id === focus)
    const where = from?.project || project || ''
    setSplitting(true)
    const made = await act.openAsync({ kind: 'shell', project: where, cwd: from?.cwd, label: where || 'shell' }).finally(() => setSplitting(false))
    if (!made) return
    setLayout({ tree: splitAt(tree, focus, made.id, dir), focus: made.id })
  }
  const unsplit = (id: string) => {
    const next = remove(tree, id)
    const rest = leaves(next)
    setLayout({ tree: next, focus: rest.includes(focus) ? focus : rest[0] ?? '' })
  }

  const drag = (path: number[], node: SplitNode, i: number, el: HTMLElement | null) => (e: React.PointerEvent) => {
    e.preventDefault()
    const r = el?.getBoundingClientRect()
    if (!r || !tree) return
    const row = node.dir === 'row'
    const total = row ? r.width : r.height
    const start = row ? r.left : r.top
    const before = node.sizes.slice(0, i).reduce((a, b) => a + b, 0)
    const pair = node.sizes[i]! + node.sizes[i + 1]!
    const base = tree
    const move = (ev: PointerEvent) => {
      const at = ((row ? ev.clientX : ev.clientY) - start) / total - before
      const a = Math.max(0.1, Math.min(pair - 0.1, at))
      const sizes = [...node.sizes]
      sizes[i] = a
      sizes[i + 1] = pair - a
      setLayout({ tree: resize(base, path, sizes), focus })
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const pane = (id: string) => {
    const s = live.find((x) => x.id === id)
    if (!s) return null
    const on = id === focus
    return (
      <div key={id} className={`relative w-full h-full min-w-0 min-h-0 flex flex-col ${many && on ? 'ring-1 ring-inset ring-brand/60' : ''}`}
        onPointerDown={() => setFocus(id)}>
        {many && (
          <div className="shrink-0 h-[22px] px-8 flex items-center gap-6 bg-[var(--term-bar)] border-b border-white/10 text-11 text-[var(--term-soft)]">
            <StateDot state={s.state} size={6} />
            <span className={`truncate ${on ? 'text-[var(--term-text)]' : ''}`}>{s.label}</span>
            <span className="text-10 font-mono text-[var(--term-muted)]">{STATE_WORD[s.state]}</span>
            <button type="button" onClick={(e) => { e.stopPropagation(); unsplit(id) }} title={t('Close this pane; the terminal stays open as a tab')}
              aria-label={t('Close this pane')} className="ml-auto w-16 h-16 inline-flex items-center justify-center rounded-input text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/10">
              <X size={10} />
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0">
          <Screen sid={s.id} token={st.token} fontSize={st.font_size} scrollback={st.scrollback} editor={st.editor} project={s.project} taskId={s.task_id} backend={s.backend}
            visible={!launch} autoFocus={on}
            bind={(a) => { if (a) apis.current.set(s.id, a); else apis.current.delete(s.id) }}
            onFocus={() => { onActive(s.id); setFocus(s.id) }}
            onZoom={(d) => void act.setting({ 'terminal.font_size': Math.max(10, Math.min(22, st.font_size + d)) })} />
        </div>
      </div>
    )
  }

  const draw = (node: Node, path: number[]): ReactNode => {
    if (isLeaf(node)) return pane(node.id)
    return <SplitView key={path.join('.') || 'root'} node={node} path={path} draw={draw} drag={drag} />
  }

  return (
    <div className="h-full min-h-0 flex flex-col" style={{ background: TERMINAL_GROUND }}>
      <div className={`shrink-0 h-[32px] flex items-stretch border-b ${DARK_BAR}`}>
        <div ref={tabs} role="tablist" aria-label={t('Terminals')} className="min-w-0 flex overflow-x-auto">
          {live.map((s) => (
            <Tab key={s.id} s={s} on={!launch && s.id === focus} shown={!launch && shownIds.includes(s.id)} onPick={() => pick(s.id)}
              onClose={() => void act.close(s.id)} onRename={(l) => void act.rename(s.id, l)} />
          ))}
        </div>
        <NewButton open={launch} onClick={() => setLaunching((v) => !v)} />
        <div className="ml-auto flex items-center gap-2 px-6">
          {live.length > 0 && (
            <>
              <BarButton onClick={() => void split('row')} disabled={splitting || shownIds.length >= MAX_PANES}
                title={shownIds.length >= MAX_PANES ? t('Four panes at most') : t('Split right: a new shell beside the pane in focus')}>
                <Columns2 size={13} />
              </BarButton>
              <BarButton onClick={() => void split('col')} disabled={splitting || shownIds.length >= MAX_PANES}
                title={shownIds.length >= MAX_PANES ? t('Four panes at most') : t('Split down: a new shell under the pane in focus')}>
                <Rows2 size={13} />
              </BarButton>
              <span className="w-px h-16 bg-white/10 mx-2" />
            </>
          )}
          {live.length > 0 && (
            <>
              <BarButton onClick={() => apis.current.get(focus)?.find()} title={t('Find in this terminal (Ctrl+Shift+F)')}>
                <Search size={13} />
              </BarButton>
              <BarButton onClick={() => apis.current.get(focus)?.range()} title={t('Click a first and a last line to copy the lines between')}>
                <ListOrdered size={13} />
              </BarButton>
              <span className="w-px h-16 bg-white/10 mx-2" />
            </>
          )}
          <TextSize />
          {bar}
        </div>
      </div>
      <div className="relative flex-1 min-h-0 flex">
        {launch && (
          <div className="absolute inset-0 z-10 overflow-auto bg-base">
            {empty && !live.length ? empty : null}
            <Launcher project={project} wide onDone={() => setLaunching(false)} />
          </div>
        )}
        {tree && draw(tree, [])}
      </div>
    </div>
  )
}

/** One split: its children with a handle between each two. */
function SplitView({ node, path, draw, drag }: {
  node: SplitNode
  path: number[]
  draw: (n: Node, path: number[]) => ReactNode
  drag: (path: number[], node: SplitNode, i: number, el: HTMLElement | null) => (e: React.PointerEvent) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const row = node.dir === 'row'
  return (
    <div ref={box} className={`w-full h-full min-w-0 min-h-0 flex ${row ? 'flex-row' : 'flex-col'}`}>
      {node.kids.map((k, i) => (
        <Fragment key={isLeaf(k) ? k.id : `s${i}`}>
          {i > 0 && (
            <div role="separator" aria-orientation={row ? 'vertical' : 'horizontal'} onPointerDown={drag(path, node, i - 1, box.current)}
              className={`shrink-0 bg-white/10 hover:bg-brand ${row ? 'w-[3px] cursor-col-resize' : 'h-[3px] cursor-row-resize'}`} />
          )}
          <div className="min-w-0 min-h-0 flex" style={{ flex: `${node.sizes[i]} 1 0` }}>{draw(k, [...path, i])}</div>
        </Fragment>
      ))}
    </div>
  )
}

function BarButton({ onClick, title, children, on = false, disabled = false }: { onClick: () => void; title: string; children: ReactNode; on?: boolean; disabled?: boolean }) {
  return (
    // A bar button lets go of the keyboard once clicked: it belongs to the
    // terminal, and a space typed next must not click the button again.
    <button type="button" onClick={(e) => { e.currentTarget.blur(); onClick() }} title={title} aria-label={title} disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      className={`h-24 min-w-[24px] px-4 inline-flex items-center justify-center rounded-input disabled:opacity-30 ${on ? 'text-[var(--term-text)] bg-white/10' : 'text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5'}`}>
      {children}
    </button>
  )
}

/* ================================================================ Drawer */

/** The drawer's body — mounted by `Dock.tsx` while the drawer is open, so it is loaded when first shown. */
export function Drawer() {
  const dock = useDock()
  const list = useTerminals(dock.open).data
  const sessions = list?.sessions ?? []
  const [gear, setGear] = useState(false)
  const [drag, setDrag] = useState(false)
  if (!dock.open) return null
  const start = (e: React.PointerEvent) => {
    e.preventDefault()
    setDrag(true)
    const bottom = window.innerHeight
    const move = (ev: PointerEvent) => setDock({ height: Math.round(Math.max(160, Math.min(bottom - 120, bottom - ev.clientY))), max: false })
    const up = () => { setDrag(false); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  return (
    <section aria-label={t('Terminal')}
      className={dock.full ? 'fixed inset-0 z-[75] flex flex-col' : 'relative shrink-0 border-t border-border-default flex flex-col'}
      style={dock.full ? { background: TERMINAL_GROUND } : { height: dock.max ? 'calc(100vh - 56px)' : dock.height }}>
      {!dock.full && <div role="separator" aria-orientation="horizontal" aria-label={t("Drag to change the terminal's height")} onPointerDown={start}
        onDoubleClick={() => setDock({ max: !dock.max })}
        className="absolute -top-4 inset-x-0 h-8 z-20 cursor-row-resize group">
        <span className={`absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 transition-colors ${drag ? 'bg-brand' : 'group-hover:bg-border-strong'}`} />
      </div>}
      <div className="flex-1 min-h-0">
        <Deck sessions={sessions} active={dock.active} onActive={(id) => setDock({ active: id })}
          empty={dock.pending ? null : undefined}
          bar={<>
            <span className="relative">
              <BarButton onClick={() => setGear((v) => !v)} title={t('Terminal settings')} on={gear}><Settings2 size={13} /></BarButton>
              <Popover open={gear} onClose={() => setGear(false)}><TerminalSettings /></Popover>
            </span>
            <Link to="/terminal" onClick={() => setDock({ open: false, full: false })} title={t('Every terminal, on its own page')} aria-label={t('Every terminal, on its own page')}
              className="h-24 min-w-[24px] px-4 inline-flex items-center justify-center rounded-input text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5"><LayoutList size={13} /></Link>
            <BarButton onClick={() => setDock({ full: !dock.full })} on={dock.full}
              title={dock.full ? t('Leave focus mode (Ctrl+`)') : t('Focus mode: the terminal alone, full screen')}>
              {dock.full ? <Minimize2 size={13} /> : <Focus size={13} />}
            </BarButton>
            <BarButton onClick={() => setDock({ open: false, full: false })} title={t('Hide the terminal (`) — it keeps running')}><ChevronDown size={14} /></BarButton>
          </>} />
      </div>
    </section>
  )
}

/* ============================================================== pages */

const ORDER: TermState[] = ['waiting', 'working', 'running', 'shell', 'ended']

function SessionList({ sessions, active, onPick, grouped }: { sessions: TermSession[]; active: string; onPick: (id: string) => void; grouped: boolean }) {
  const byProject = useMemo(() => {
    const m = new Map<string, TermSession[]>()
    for (const s of sessions) m.set(s.project || '—', [...(m.get(s.project || '—') ?? []), s])
    return [...m.entries()]
  }, [sessions])
  const row = (s: TermSession) => (
    <li key={s.id}>
      <button type="button" onClick={() => onPick(s.id)} aria-current={s.id === active}
        className={`w-full text-left px-10 py-6 flex items-start gap-8 border-l-2 ${s.id === active ? 'border-brand bg-brand-glow' : 'border-transparent hover:bg-hover'}`}>
        <span className="pt-4"><StateDot state={s.state} /></span>
        <span className="min-w-0 flex-1 flex flex-col gap-2">
          <span className="text-13 text-primary truncate">{s.label}</span>
          <span className="text-10 font-mono text-tertiary truncate">
            {STATE_WORD[s.state]}{s.program && s.state !== 'shell' ? ` · ${s.program}` : ''} · {s.cwd.replace(/^\/home\/[^/]+/, '~')}
          </span>
          {(s.agent_id || s.task_id) && (
            <span className="flex items-center gap-6 text-10 font-mono">
              {s.agent_id && <Link to={`/agent/${encodeURIComponent(s.agent_id)}`} onClick={(e) => e.stopPropagation()} className="text-brand hover:underline">{s.agent_id}</Link>}
              {s.task_id && <span className="text-secondary">{s.task_id}</span>}
            </span>
          )}
        </span>
      </button>
    </li>
  )
  if (!grouped) return <ul className="flex flex-col">{sessions.map(row)}</ul>
  return (
    <div className="flex flex-col gap-8">
      {byProject.map(([p, ss]) => (
        <div key={p} className="flex flex-col">
          <span className="px-10 pb-2 text-10 uppercase tracking-wide font-mono text-tertiary">{p}</span>
          <ul className="flex flex-col">{ss.map(row)}</ul>
        </div>
      ))}
    </div>
  )
}

/** Every terminal in a list beside the one open. `project` narrows it. */
export function TerminalPage({ project, below }: { project?: string; below?: (active: string) => ReactNode }) {
  const st = useTerminalStatus().data
  // On screen: the states are read every two seconds.
  const list = useTerminals(true).data
  const dock = useDock()
  const sessions = (list?.sessions ?? []).filter((s) => !project || s.project === project)
  const [active, setActive] = useState(dock.active)
  const sorted = [...sessions].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state) || b.created.localeCompare(a.created))
  // The drawer and the page never show the same terminal twice at once.
  // On this page the page IS the terminal: a request to show one (a launch,
  // Resume, a notification) selects it here instead of opening the drawer
  // over it — the same terminal twice was confusing.
  useEffect(() => {
    if (!dock.open) return
    if (dock.active) setActive(dock.active)
    setDock({ open: false })
  }, [dock.open, dock.active])
  if (st && !st.enabled) return <div className="rounded-card border border-border-subtle bg-surface"><TurnOn /></div>
  return (
    <div className="grid gap-12 min-w-0 lg:grid-cols-[280px_minmax(0,1fr)]" style={{ height: project ? 560 : 'calc(100vh - 160px)' }}>
      <aside className="min-h-0 overflow-y-auto rounded-card border border-border-subtle bg-surface py-8">
        <div className="px-10 pb-6 flex items-center gap-8 text-11 font-mono text-tertiary">
          <span>{tn(sessions.length, '{n} terminal', '{n} terminals')}</span>
          {(['waiting', 'working'] as const).map((k) => sessions.some((s) => s.state === k) && (
            <span key={k} className="inline-flex items-center gap-4"><StateDot state={k} size={6} />{sessions.filter((s) => s.state === k).length} {STATE_WORD[k]}</span>
          ))}
        </div>
        {sessions.length === 0 && <p className="px-10 text-12 text-tertiary">{t('No terminals. Click + to open one.')}</p>}
        <SessionList sessions={sorted} active={active} onPick={setActive} grouped={!project} />
      </aside>
      <div className="min-h-0 rounded-card overflow-hidden border border-border-default">
        <Deck sessions={sessions} active={active} onActive={setActive} project={project}
          layoutKey={`page:${project ?? ''}`} />
      </div>
      {below && <div className="lg:col-start-2">{below(sessions.some((x) => x.id === active && x.state !== 'ended') ? active : sessions.filter((x) => x.state !== 'ended').slice(-1)[0]?.id ?? '')}</div>}
    </div>
  )
}
