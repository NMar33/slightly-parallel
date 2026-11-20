/**
 * Round 2 (tk_bbb84183): A · Rail as a medium terminal window on a desktop.
 *
 * Settled by the operator: a sidebar grows the window outward and the
 * terminal keeps its exact size; chats are a tab strip; a button (and a
 * key) zooms out to the workspace and to every workspace; a workspace of
 * your own is a coloured group in the tab strip. The three variants differ
 * on what is still open:
 *
 *   G · Quiet  — GNOME Terminal until you press a key: one open group in the strip (the current
 *                workspace), the others folded behind a "+N" chip; the levels crossfade in place.
 *   H · Pill   — the strip holds only the current workspace, a coloured pill at its left names it
 *                and opens the levels as a sheet with a breadcrumb; groups as chips at the strip's
 *                end; the workspace colour on the window's top edge.
 *   I · Zoom   — the furthest fluid: the terminal shrinks into its own tile, the workspace into its
 *                pool; the plainest strip at rest, the workspace's name and waiting count on the
 *                zoom button, the dot map of every workspace only in the levels.
 *
 * In all three a sidebar never covers the terminal: at a screen edge the window moves in (I glides).
 * A detached window carries its workspace's colour on its top edge; a chat window names it.
 *
 * Every window on the desktop is one workspace (the main one switches) or one chat.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ChevronLeft, ChevronRight, LayoutGrid, Menu, Minimize2, Moon, PanelLeft, PanelRight, Plus, Search,
} from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { SESSIONS, sessionOf } from '../mock'
import { Keymap, MESSAGE_KEYS, Palette, Restore, StateDot, commonActions, shownState, STATE_WORD, useKeys, type Action } from '../parts'
import { flash, focus, useAqua } from '../store'
import {
  chatsIn, closeWin, detachWin, getDesk, isCustom, liveWorkspaces, moveChat, moveWin, raise, useDesk, wsById, wsOfChat,
  type Win,
} from './desk'
import {
  AllLevel, Desktop, GroupMenu, Inspector, LeftTree, TermArea, WsLevel, makeGroup, useDrag, wsAsleep, wsInk, wsTint,
  type InspTab, type Split,
} from './parts'

export type Look = 'g' | 'h' | 'i'
type Level = 'chat' | 'ws' | 'all'

const TERM = { main: { w: 1000, h: 600 }, ws: { w: 820, h: 460 }, chat: { w: 640, h: 360 } }
const LW = 236
const RW = 340
const BAR = 34
const STRIP = 32

/** The chats a window's strip may show: not those living in a window of their own. */
function inOtherWindow(d: ReturnType<typeof useDesk>, chat: string, self: Win) {
  return d.windows.some((w) => w.id !== self.id && ((w.kind === 'chat' && w.ref === chat) || (w.kind === 'ws' && w.ref === wsOfChat(d, chat))))
}

function R2Window({ win, look, top }: { win: Win; look: Look; top: boolean }) {
  const st = useAqua()
  const d = useDesk()
  const drag = useDrag(win)
  const kind = win.kind
  const fixedWs = kind === 'ws' ? win.ref! : null
  const fixedChat = kind === 'chat' ? win.ref! : null
  const firstChat = fixedChat ?? (fixedWs ? chatsIn(d, fixedWs)[0]?.id : st.active) ?? st.active
  const [picked, setChat] = useState(firstChat)
  const [level, setLevel] = useState<Level>('chat')
  const [left, setLeft] = useState(false)
  const [right, setRight] = useState(false)
  const [tab, setTab] = useState<InspTab>('messages')
  const [note, setNote] = useState('nt_7d21c0aa')
  const [split, setSplit] = useState<Split>(null)
  const [hints, setHints] = useState(false)
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [menu, setMenu] = useState<string | null>(null)
  const [tabMenu, setTabMenu] = useState<string | null>(null)
  const [others, setOthers] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const shiftRef = useRef(0)

  // a chat that left this window's workspace (moved, detached) gives way to a neighbour
  const visible = (c: string) => !inOtherWindow(d, c, win) || c === fixedChat
  const chat = fixedChat ?? (fixedWs
    ? (wsOfChat(d, picked) === fixedWs ? picked : chatsIn(d, fixedWs)[0]?.id ?? picked)
    : (visible(picked) ? picked : SESSIONS.find((x) => visible(x.id))?.id ?? picked))
  const ws = fixedWs ?? wsOfChat(d, chat)
  const s = sessionOf(chat)!
  const wsObj = wsById(d, ws)
  const size = TERM[kind]

  const go = (id: string) => {
    if (fixedChat) return
    if (fixedWs && wsOfChat(d, id) !== fixedWs) { detachWin('chat', id); return }
    setChat(id); setLevel('chat'); if (kind === 'main') focus(id)
    const target = wsOfChat(d, id)
    setCollapsed(look === 'g' ? Object.fromEntries(liveWorkspaces(d).map((x) => [x.id, x.id !== target])) : (c) => ({ ...c, [target]: false }))
  }
  const goWs = (w: string) => { if (fixedWs) return; const first = chatsIn(d, w).find((x) => visible(x.id)); if (first) { setChat(first.id); setCollapsed((c) => ({ ...c, [w]: false })) } setLevel('ws') }
  const openNote = (id: string) => { setNote(id); setTab('note'); openSide('right', true) }
  const out = () => setLevel(level === 'chat' ? 'ws' : fixedWs || fixedChat ? 'ws' : 'all')
  const into = () => setLevel(level === 'all' ? 'ws' : 'chat')

  /** Grow outward: the terminal stays where it is on screen; at a screen edge the window moves in rather than cover the terminal. */
  function openSide(side: 'left' | 'right', on: boolean) {
    const deskW = typeof window !== 'undefined' ? window.innerWidth : 1680
    const set = side === 'left' ? setLeft : setRight
    if (!on) {
      set(false)
      if (shiftRef.current && look !== 'h') { moveWin(win.id, win.x - shiftRef.current, win.y); shiftRef.current = 0 }
      return
    }
    const lw = side === 'left' || left ? LW : 0
    const rw = side === 'right' || right ? RW : 0
    const frameL = win.x - lw
    const frameR = win.x + size.w + rw
    const over = frameL < 0 ? -frameL : frameR > deskW ? deskW - frameR : 0
    // the terminal is never covered: at a screen edge the window moves in (I glides, G and H jump)
    if (over) { moveWin(win.id, win.x + over, win.y); shiftRef.current += over; flash(t('Moved in to fit the screen; the terminal keeps its size')) }
    set(true)
  }

  const waitingNext = () => {
    const w = SESSIONS.filter((x) => x.state === 'waiting' && !st.asleep[x.id] && visible(x.id) && (!fixedWs || wsOfChat(d, x.id) === fixedWs))
    if (!w.length) return
    const i = w.findIndex((x) => x.id === chat)
    go(w[(i + 1) % w.length]!.id)
  }

  const actions: Action[] = useMemo(() => [
    { id: 'out', group: t('view'), label: t('Zoom out: the workspace, then every workspace'), kbd: 'Ctrl+Shift+↑', run: out },
    { id: 'left', group: t('view'), label: t('Left sidebar: workspaces and servers'), kbd: 'alt+[', run: () => openSide('left', !left) },
    { id: 'right', group: t('view'), label: t('Right sidebar: messages, pins, branches, note, stats'), kbd: 'alt+]', run: () => openSide('right', !right) },
    { id: 'editor', group: t('pane'), label: t('Editor as a split'), kbd: 'alt+E', run: () => setSplit(split === 'editor' ? null : 'editor') },
    { id: 'hints', group: t('copy'), label: t('Hints: copy an id or a path'), kbd: 'alt+H', run: () => setHints(true) },
    ...chatsIn(d, ws).filter((c) => visible(c.id) && kind !== 'chat').map((c) => ({ id: `dc-${c.id}`, group: t('window'), label: `${t('Detach')} ${c.name}`, run: () => detachWin('chat', c.id) })),
    { id: 'dws', group: t('window'), label: `${t('Detach the workspace')} ${wsObj?.name ?? ''}`, run: () => detachWin('ws', ws) },
    ...liveWorkspaces(d).map((w) => ({ id: `ws-${w.id}`, group: t('workspace'), label: w.name, run: () => goWs(w.id) })),
    ...commonActions(go, { note: openNote, server: (id) => setSplit({ server: id }) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [d, chat, left, right, split, level, ws])

  useKeys({
    'mod+k': () => { if (top) setPalette(true) },
    'mod+shift+ArrowUp': () => { if (top) out() },
    'mod+shift+ArrowDown': () => { if (top) into() },
    'alt+[': () => { if (top) openSide('left', !left) },
    'alt+]': () => { if (top) openSide('right', !right) },
    'alt+e': () => { if (top) setSplit(split === 'editor' ? null : 'editor') },
    'alt+h': () => { if (top) setHints((h) => !h) },
    'alt+w': () => { if (top) waitingNext() },
    '?': () => { if (top) setKeys(true) },
    Escape: () => { if (!top) return; setPalette(false); setKeys(false); setHints(false); setMenu(null); setTabMenu(null); if (level !== 'chat') setLevel('chat') },
  })

  // ---- the tab strip
  const stripWs: string[] = kind === 'chat' ? [] : fixedWs ? [fixedWs]
    : look === 'g' ? liveWorkspaces(d).map((w) => w.id).filter((w) => chatsIn(d, w).some((c) => visible(c.id)))
      : [ws]
  const otherGroups = look === 'h' && kind === 'main' ? liveWorkspaces(d).filter((w) => isCustom(d, w.id) && w.id !== ws && chatsIn(d, w.id).some((c) => visible(c.id))) : []

  const isFolded = (w: string) => look === 'g' && !fixedWs && (collapsed[w] ?? w !== ws)
  const onDropTab = (target: string, dragged: string) => {
    if (dragged === target) return
    const tw = wsOfChat(d, target)
    if (isCustom(d, tw)) { moveChat(dragged, tw); flash(`${sessionOf(dragged)!.name} ${t('moved to')} ${wsById(d, tw)!.name}`) }
    else makeGroup([target, dragged])
  }
  const dropOnGroup = (w: string, dragged: string) => { moveChat(dragged, w); flash(`${sessionOf(dragged)!.name} ${t('moved to')} ${wsById(getDesk(), w)!.name}`) }

  const tabEl = (c: string, hue: number, custom: boolean) => {
    const x = sessionOf(c)!
    const on = c === chat && level === 'chat'
    return (
      <button key={c} type="button" role="tab" aria-selected={on} draggable data-nodrag
        onDragStart={(e) => e.dataTransfer.setData('text/chat', c)}
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { const dr = e.dataTransfer.getData('text/chat'); if (dr) onDropTab(c, dr) }}
        onClick={() => go(c)} onContextMenu={(e) => { e.preventDefault(); setTabMenu(c) }} title={`${x.name} · ${STATE_WORD[shownState(st, x)]}`}
        className="relative h-[26px] px-10 inline-flex items-center gap-6 text-12 rounded-t-[6px] max-w-[170px] shrink-0"
        style={{ background: on ? 'var(--aq-term-bg)' : undefined, color: on ? 'var(--aq-term-fg)' : 'var(--aq-ink2)', boxShadow: on ? 'inset 0 2px 0 var(--aq-accent)' : custom && look !== 'h' ? `inset 0 -2px 0 ${wsInk(hue)}` : undefined }}>
        <StateDot s={x} st={st} /><span className="truncate">{x.name}</span>
      </button>
    )
  }

  const chip = (w: string) => {
    const wo = wsById(d, w)!
    const n = chatsIn(d, w).filter((c) => visible(c.id))
    const isCollapsed = look === 'g' ? (collapsed[w] ?? w !== ws) : true
    const waiting = n.filter((c) => c.state === 'waiting' && !st.asleep[c.id]).length
    const asleep = wsAsleep(st, d, w)
    return (
      <span key={`chip-${w}`} className="inline-flex items-center shrink-0 relative">
        <button type="button" data-nodrag onClick={() => {
            if (look !== 'g') { goWs(w); return }
            if (!isCollapsed) { setCollapsed({ ...collapsed, [w]: true }); return }
            // opening a folded group makes it the current workspace: the others fold, its first chat comes up
            const first = chatsIn(d, w).find((c) => visible(c.id))
            setCollapsed(Object.fromEntries(liveWorkspaces(d).map((x) => [x.id, x.id !== w])))
            if (first) { setChat(first.id); setLevel('chat'); if (kind === 'main') focus(first.id) }
          }}
          onContextMenu={(e) => { e.preventDefault(); setMenu(w) }} onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { const dr = e.dataTransfer.getData('text/chat'); if (dr) dropOnGroup(w, dr) }}
          title={`${wo.name} · ${tn(n.length, '{n} chat', '{n} chats')}${isCustom(d, w) ? ` · ${t('right-click: the group menu')}` : ''}`}
          className="h-[20px] px-8 rounded-[6px] text-11 font-semibold inline-flex items-center gap-4 whitespace-nowrap"
          style={isCollapsed
            ? { background: wsInk(wo.hue), color: 'oklch(0.18 0.03 250)', opacity: asleep ? 0.5 : 1, filter: asleep ? 'saturate(0.3)' : undefined }
            : { color: 'var(--aq-ink2)', boxShadow: `inset 0 0 0 1px ${wsTint(wo.hue, 0.5)}` }}>
          {!isCollapsed && <span className="w-[7px] h-[7px] rounded-full" style={{ background: wsInk(wo.hue) }} />}
          {asleep && <Moon size={10} />}{wo.name}{isCollapsed && <span className="font-mono opacity-80">{n.length}</span>}
          {isCollapsed && waiting > 0 && <span className="w-[7px] h-[7px] rounded-full" style={{ background: 'var(--aq-wait)', boxShadow: '0 0 0 1.5px oklch(0.18 0.03 250)' }} />}
        </button>
        {isCustom(d, w) && <button type="button" data-nodrag className="aq-btn icon !w-[16px] !h-[18px]" aria-label={`${t('Group')} ${wo.name}`} onClick={() => setMenu(w)}><Menu size={10} /></button>}
      </span>
    )
  }

  const zoomButton = (
    <button type="button" data-nodrag className="aq-btn shrink-0" aria-pressed={level !== 'chat'} onClick={level === 'chat' ? out : level === 'ws' && kind === 'main' ? out : into}
      title={t('Workspaces (Ctrl+Shift+↑)')} aria-label={t('Workspaces')}>
      <LayoutGrid size={13} />{look === 'i' && wsObj && <span className="text-11">{wsObj.name}</span>}
      {look === 'i' && (() => { const n = chatsIn(d, ws).filter((c) => c.state === 'waiting' && !st.asleep[c.id]).length; return n ? <span className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {n}</span> : null })()}
    </button>
  )

  const strip = kind === 'chat' ? null : (
    <div className="shrink-0 flex items-end gap-2 px-6 min-w-0" style={{ height: STRIP, background: 'var(--r2-strip)' }} role="tablist" aria-label={t('Chats')}>
      {look === 'h' && wsObj && (
        <button type="button" data-nodrag onClick={level === 'chat' ? out : () => setLevel(level === 'ws' && !fixedWs ? 'all' : 'chat')} aria-label={`${t('Workspace')} ${wsObj.name}`}
          className="self-center h-[22px] px-10 rounded-full text-12 font-semibold inline-flex items-center gap-6 shrink-0 mr-4" title={t('Workspaces (Ctrl+Shift+↑)')}
          style={{ background: wsTint(wsObj.hue, 0.25), color: 'var(--aq-ink)', boxShadow: `inset 0 0 0 1px ${wsTint(wsObj.hue, 0.6)}` }}>
          <span className="w-[8px] h-[8px] rounded-full" style={{ background: wsInk(wsObj.hue) }} />{wsObj.name}
          <LayoutGrid size={11} className="opacity-70" />
        </button>
      )}
      {look === 'g' && kind === 'main' && <span className="self-center">{zoomButton}</span>}
      <div className="flex items-end gap-2 min-w-0 overflow-x-auto overflow-y-hidden r2-tabs">
        {stripWs.filter((w) => !isFolded(w)).map((w) => {
          const wo = wsById(d, w)!
          const tabs = chatsIn(d, w).filter((c) => visible(c.id))
          const isCollapsed = look === 'g' && !fixedWs ? (collapsed[w] ?? w !== ws) : false
          return (
            <span key={w} className="flex items-end gap-1 shrink-0" style={{ boxShadow: look === 'g' && !isCollapsed ? `inset 0 2px 0 ${wsTint(wo.hue, 0.0)}` : undefined }}>
              {look === 'g' && !fixedWs && <span className="self-center mr-2">{chip(w)}</span>}
              {!isCollapsed && tabs.map((c) => tabEl(c.id, wo.hue, isCustom(d, w)))}
            </span>
          )
        })}
      </div>
      {look === 'g' && stripWs.some(isFolded) && (
        <span className="self-center flex items-center gap-4 ml-6 shrink-0">
          {others && stripWs.filter(isFolded).map((w) => chip(w))}
          <button type="button" data-nodrag className="aq-btn line !h-[20px] text-11" aria-expanded={others} onClick={() => setOthers(!others)}
            title={t('The other workspaces, folded')}>
            {others ? '‹' : `+${stripWs.filter(isFolded).length}`}
            {!others && stripWs.filter(isFolded).some((w) => chatsIn(d, w).some((c) => c.state === 'waiting' && !st.asleep[c.id] && visible(c.id))) && <span className="w-[6px] h-[6px] rounded-full" style={{ background: 'var(--aq-wait)' }} />}
          </button>
        </span>
      )}
      {otherGroups.length > 0 && <span className="self-center flex items-center gap-4 ml-6 pl-6" style={{ borderLeft: '1px solid var(--aq-line)' }}>{otherGroups.map((w) => chip(w.id))}</span>}
      <button type="button" data-nodrag className="aq-btn icon self-center shrink-0" aria-label={t('New chat')} title={t('New chat')}><Plus size={13} /></button>
      <span className="ml-auto self-center flex items-center gap-1 shrink-0">
        {look === 'i' && zoomButton}
      </span>
    </div>
  )

  // ---- the levels
  const levelView = () => {
    if (level === 'ws') return <WsLevel ws={ws} current={chat} onChat={go} onServer={(id) => { setSplit({ server: id }); setLevel('chat') }} cols={kind === 'main' ? 3 : 2} onMenu={() => setMenu(ws)} />
    if (level === 'all') return <AllLevel current={chat} onWs={goWs} onChat={go} cols={3} />
    return null
  }
  const termView = <TermArea chat={chat} split={split} hints={hints && top} onHintsDone={() => setHints(false)} onNote={openNote} size={kind === 'chat' ? 12 : 13} />

  // I: the terminal shrinks toward its own tile; the workspace toward its pool
  const tileIndex = Math.max(0, chatsIn(d, ws).findIndex((c) => c.id === chat))
  const zoomTo = `translate(${12 + (tileIndex % 3) * 330}px, ${44 + Math.floor(tileIndex / 3) * 170}px) scale(0.32)`
  const body = (
    <div className="relative min-h-0" style={{ width: size.w, height: size.h }}>
      {look === 'i' ? (
        <>
          <div className="absolute inset-0" style={{ background: 'var(--r2-over)', opacity: level === 'chat' ? 0 : 1, transition: 'opacity 200ms var(--aq-ease)', pointerEvents: level === 'chat' ? 'none' : 'auto' }}>
            <div className="absolute inset-0" style={{ transform: level === 'all' ? 'scale(0.92)' : 'none', opacity: level === 'all' ? 0 : 1, transition: 'transform 220ms var(--aq-ease), opacity 180ms', pointerEvents: level === 'ws' ? 'auto' : 'none' }}>
              {level !== 'chat' && <WsLevel ws={ws} current={chat} onChat={go} onServer={(id) => { setSplit({ server: id }); setLevel('chat') }} cols={3} onMenu={() => setMenu(ws)} />}
            </div>
            {level === 'all' && <div className="absolute inset-0 aq-fade" style={{ animation: 'r2-grow 220ms var(--aq-ease)' }}><AllLevel current={chat} onWs={goWs} onChat={go} /></div>}
            {kind === 'main' && <div className="absolute right-14 bottom-10 flex items-center gap-6 text-10 aq-ink3"><DotMap current={ws} />{t('every workspace, one dot a chat')}</div>}
          </div>
          <div className="absolute inset-0 origin-top-left" style={{ transform: level === 'chat' ? 'none' : zoomTo, opacity: level === 'chat' ? 1 : 0, transition: 'transform 220ms var(--aq-ease), opacity 160ms 60ms', pointerEvents: level === 'chat' ? 'auto' : 'none', borderRadius: level === 'chat' ? 0 : 24, overflow: 'hidden' }}>
            {termView}
          </div>
        </>
      ) : look === 'h' ? (
        <>
          {termView}
          {level !== 'chat' && (
            <div className="absolute inset-0 flex flex-col r2-sheet" style={{ background: 'var(--r2-over)' }}>
              <div className="h-[28px] shrink-0 flex items-center gap-6 px-12 text-12" aria-label={t('Where you are')}>
                {!fixedWs && <button type="button" data-nodrag className="aq-btn" data-on={level === 'all'} onClick={() => setLevel('all')}>{t('All workspaces')}</button>}
                {!fixedWs && <ChevronRight size={12} className="aq-ink3" />}
                <button type="button" data-nodrag className="aq-btn" data-on={level === 'ws'} onClick={() => setLevel('ws')}>{wsObj?.name}</button>
                <ChevronRight size={12} className="aq-ink3" />
                <button type="button" data-nodrag className="aq-btn" onClick={() => setLevel('chat')}>{s.name}</button>
                <span className="ml-auto text-10 aq-ink3 font-mono">Esc {t('back to the terminal')}</span>
              </div>
              <div className="flex-1 min-h-0">{levelView()}</div>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="absolute inset-0" style={{ opacity: level === 'chat' ? 1 : 0, transition: 'opacity 120ms' }}>{termView}</div>
          {level !== 'chat' && <div className="absolute inset-0 aq-fade" style={{ background: 'var(--r2-over)' }}>{levelView()}</div>}
        </>
      )}
    </div>
  )

  // ---- the frame: grows outward, the terminal stays put
  const lOpen = left
  const rOpen = right
  const frameX = win.x - (lOpen ? LW : 0)
  const title = kind === 'chat' ? `${s.name} — ${t('from')} ${wsObj?.name ?? ''}` : `${s.name} — ${wsObj?.name ?? ''}`
  const edgeHue = wsObj?.hue ?? 200
  const sideH = size.h + (strip ? STRIP : 0)

  return (
    <div className="absolute flex flex-col overflow-visible r2-win" role="dialog" aria-label={`${t('Window')}: ${kind === 'main' ? 'SP Aqua' : title}`}
      onPointerDown={() => raise(win.id)}
      style={{ left: frameX, top: win.y, zIndex: win.z, transition: look === 'i' ? 'left 220ms var(--aq-ease), top 220ms var(--aq-ease)' : undefined }}>
      <div className="flex flex-col rounded-[10px] overflow-hidden" style={{ boxShadow: top ? 'var(--r2-shadow-top)' : 'var(--r2-shadow)', border: '1px solid var(--r2-edge)', borderTop: look === 'h' || kind !== 'main' ? `3px solid ${wsInk(edgeHue)}` : undefined }}>
        {/* the title bar: the only chrome a terminal has */}
        <div className="shrink-0 flex items-center gap-8 px-8 select-none cursor-grab" style={{ height: BAR, background: 'var(--r2-bar)', color: 'var(--r2-bar-ink)' }} {...drag}>
          {kind === 'main' && <button type="button" data-nodrag className="aq-btn icon" aria-pressed={left} aria-label={t('Left sidebar')} title={t('Left sidebar (alt+[)')} onClick={() => openSide('left', !left)}><PanelLeft size={14} /></button>}
          {kind !== 'main' && <span className="w-[10px] h-[10px] rounded-[3px] ml-4" style={{ background: wsInk(edgeHue) }} />}
          <span className="flex-1 text-center text-13 font-semibold truncate" style={{ color: 'var(--r2-bar-ink)' }}>{title}</span>
          {kind === 'main' && <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Command palette')} title="Ctrl+K" onClick={() => setPalette(true)}><Search size={14} /></button>}
          {kind !== 'main' && <button type="button" data-nodrag className="aq-btn" onClick={() => closeWin(win.id)} title={t('Dock back into the main window')}><Minimize2 size={12} />{t('Dock back')}</button>}
          {kind !== 'chat' && <button type="button" data-nodrag className="aq-btn icon" aria-pressed={right} aria-label={t('Right sidebar')} title={t('Right sidebar (alt+])')} onClick={() => openSide('right', !right)}><PanelRight size={14} /></button>}
          <span className="w-[22px] h-[22px] ml-4 rounded-full inline-flex items-center justify-center text-12" style={{ background: 'var(--r2-ctl)', color: 'var(--r2-bar-ink)' }} aria-hidden>×</span>
        </div>
        <div className="flex min-h-0" style={{ background: 'var(--aq-panel)' }}>
          {lOpen && <aside className="shrink-0 r2-side-l" style={{ width: LW, height: sideH, borderRight: '1px solid var(--aq-line)' }} aria-label={t('Left sidebar')}>
            <LeftTree ws={ws} chat={chat} onChat={go} onWs={goWs} onServer={(id) => setSplit({ server: id })} /></aside>}
          <div className="flex flex-col min-w-0 relative" style={{ width: size.w }}>
            {strip}
            {body}
            {/* quiet edge handles: hover the window's side to see them */}
            {kind !== 'chat' && !left && <button type="button" data-nodrag className="r2-handle left-0" aria-label={t('Left sidebar')} onClick={() => openSide('left', true)}><ChevronRight size={12} /></button>}
            {kind !== 'chat' && !right && <button type="button" data-nodrag className="r2-handle right-0" aria-label={t('Right sidebar')} onClick={() => openSide('right', true)}><ChevronLeft size={12} /></button>}
          </div>
          {rOpen && <aside className="shrink-0 r2-side-r" style={{ width: RW, height: sideH, borderLeft: '1px solid var(--aq-line)' }} aria-label={t('Right sidebar')}>
            <Inspector chat={chat} tab={tab} setTab={setTab} note={note} onNote={openNote} onChat={go} /></aside>}
        </div>
      </div>
      <PanelHost open={palette}><Palette open={palette} onClose={() => setPalette(false)} actions={actions} /></PanelHost>
      <PanelHost open={keys}><Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl Shift ↑', t('zoom out: the workspace, then every workspace')], ['Ctrl Shift ↓', t('zoom back in')], ['Esc', t('back to the terminal')],
        ['alt [', t('left sidebar')], ['alt ]', t('right sidebar')], ['alt W', t('next chat waiting on you')], ['alt E', t('editor as a split')],
        ['alt H', t('hints: copy an id or a path')], ['Ctrl K', t('command palette')], [t('drag a tab onto a tab'), t('make a group: a workspace of your own')], ...MESSAGE_KEYS,
      ]} /></PanelHost>
      {tabMenu && (
        <div className="absolute top-[70px] z-[40] aq-glass aq-float rounded-[10px] p-6 flex flex-col w-[260px] aq-fade" style={{ left: (lOpen ? LW : 0) + 24 }} role="menu" aria-label={sessionOf(tabMenu)!.name}>
          <span className="aq-label px-6 py-4">{sessionOf(tabMenu)!.name}</span>
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { makeGroup([tabMenu]); setTabMenu(null) }}>{t('New group from this tab')}</button>
          {liveWorkspaces(d).filter((w) => isCustom(d, w.id) && w.id !== wsOfChat(d, tabMenu)).map((w) => (
            <button key={w.id} type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { dropOnGroup(w.id, tabMenu); setTabMenu(null) }}>
              <span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: wsInk(w.hue) }} />{t('Move to')} {w.name}</button>
          ))}
          {isCustom(d, wsOfChat(d, tabMenu)) && (
            <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { const p = sessionOf(tabMenu)!.project; moveChat(tabMenu, `ws_${p}`); flash(`${sessionOf(tabMenu)!.name} ${t('back in')} ${wsById(d, `ws_${p}`)!.name}`); setTabMenu(null) }}>
              {t('Out of the group, back to')} {wsById(d, `ws_${sessionOf(tabMenu)!.project}`)!.name}</button>
          )}
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { detachWin('chat', tabMenu); setTabMenu(null) }}>{t('Detach into its own window')}</button>
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12 aq-ink3" onClick={() => setTabMenu(null)}>{t('Close')}</button>
        </div>
      )}
      {menu && <GroupMenu key={menu} ws={menu} onClose={() => setMenu(null)} className="absolute top-[70px] right-16 z-[40]" />}
    </div>
  )
}

/** The palette and the keymap draw over the window they belong to. */
function PanelHost({ open, children }: { open: boolean; children: ReactNode }) {
  if (!open) return null
  return <div className="absolute inset-0 z-[50]" style={{ minWidth: 700, minHeight: 500 }}>{children}</div>
}

/** I's zoom button carries a dot map: every workspace a cluster, the current one ringed. */
function DotMap({ current }: { current: string }) {
  const st = useAqua()
  const d = useDesk()
  return (
    <span className="inline-flex items-center gap-6 ml-4" aria-hidden>
      {liveWorkspaces(d).map((w) => (
        <span key={w.id} className="inline-flex gap-1 px-2 rounded-full" style={{ boxShadow: w.id === current ? `0 0 0 1px ${wsInk(w.hue)}` : undefined }}>
          {chatsIn(d, w.id).map((c) => (
            <span key={c.id} className="w-[5px] h-[5px] rounded-full" style={{ background: st.asleep[c.id] ? 'transparent' : c.state === 'waiting' ? 'var(--aq-wait)' : wsInk(w.hue), border: st.asleep[c.id] ? `1px solid ${wsInk(w.hue)}` : undefined }} />
          ))}
        </span>
      ))}
    </span>
  )
}

export function R2({ look }: { look: Look }) {
  const d = useDesk()
  // ?edge puts the main window against the right screen edge, to try a sidebar there
  useEffect(() => {
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('edge')) moveWin('main', window.innerWidth - 1012, 96)
  }, [])
  const topZ = Math.max(...d.windows.map((w) => w.z))
  return (
    <Desktop>
      {d.windows.map((w) => <R2Window key={w.id} win={w} look={look} top={w.z === topZ} />)}
      <Restore className="absolute right-24 top-48 w-[520px] z-[200]" />
    </Desktop>
  )
}

