/**
 * Round 3 (tk_bbb84183): J — I · Zoom refined, the one the operator chose.
 *
 * - Folded groups from G: only the current workspace is open in the tab
 *   strip; the others wait behind one "+N" chip (an amber dot when a chat
 *   there waits for you).
 * - The sidebar toggles never jump. They sit at the terminal's own corners,
 *   and the terminal never moves: a sidebar grows the window outward on its
 *   side; where the screen has no room on that side it opens on the other
 *   side instead. Only when neither side has room does the window slide in
 *   (said in the flash line).
 * - The title row folds (alt+T, or the small chevron, or a double click):
 *   folded, it is a 12px strip with the title in tiny type and the two
 *   toggles as dots at the same places; no close button until it unfolds.
 *   The tab strip stays: it is the navigation the operator chose.
 * - Slightly Parallel's own colours: its surfaces, text, jade, borders,
 *   fonts and its dark terminal; workspace colours are its lane colours.
 * - H's breadcrumb in the levels and the workspace colour on the top edge
 *   of a detached window; G's tab menu.
 * - Cheap: the zoom animates transform and opacity only; tiles in the
 *   levels are still snapshots, not live terminals; nothing animates at
 *   rest (no ripple on a waiting dot, a steady cursor); an Instant setting
 *   besides prefers-reduced-motion.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, ChevronUp, LayoutGrid, Menu, PanelLeft, PanelRight, Plus, Search, X, Zap } from 'lucide-react'

import { t } from '../../../../i18n/scope/aqua'
import { SESSIONS, sessionOf } from '../mock'
import { Keymap, MESSAGE_KEYS, Palette, Restore, StateDot, commonActions, shownState, STATE_WORD, useKeys, type Action } from '../parts'
import { flash, focus, useAqua } from '../store'
import {
  chatsIn, closeWin, detachWin, isCustom, liveWorkspaces, moveChat, moveWin, raise, useDesk, wsById, wsOfChat, type Win,
} from '../round2/desk'
import {
  AllLevel, CHAT_ZOOM_SETTLE_MS, Desktop, GroupMenu, Inspector, LeftTree, PaintProvider, TermArea, WsLevel, makeGroup, useDrag,
  type InspTab, type Paint, type Split,
} from '../round2/parts'
import { LineageTree } from './lineage'
import type { Theme } from '../AquaDesign'

type Level = 'chat' | 'ws' | 'all'
type Side = 'left' | 'right'

const TERM = { main: { w: 1000, h: 600 }, ws: { w: 760, h: 380 }, chat: { w: 560, h: 320 } }
export const LW = 236
export const RW = 340
const BAR = 34
const BAR_FOLDED = 12
const STRIP = 32
const TOGGLE_INSET = 6

/* Slightly Parallel's lane colours for the workspaces, keyed by the mock's hues. */
const LANE: Record<number, number> = { 195: 1, 150: 4, 265: 3, 25: 5, 330: 6, 45: 7, 280: 8, 170: 2, 100: 4, 20: 5 }
const lane = (hue: number) => `var(--lane-${LANE[hue] ?? 1})`
export const SP_PAINT: Paint = {
  ink: lane,
  tint: (hue, a = 0.14) => `color-mix(in srgb, ${lane(hue)} ${Math.round(a * 100)}%, transparent)`,
  still: true,
  plain: true,
}

const MOTION_KEY = 'sp-aqua-motion'
function readMotion(): 'fluid' | 'instant' {
  try {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return 'instant'
    return localStorage.getItem(MOTION_KEY) === 'instant' ? 'instant' : 'fluid'
  } catch { return 'fluid' }
}

/** Detach, then place the window at a lower corner of the desktop, the workspace left and the chat right, clear of the main window's tabs. */
function detachJ(kind: 'ws' | 'chat', ref: string) {
  detachWin(kind, ref)
  const deskW = typeof window !== 'undefined' ? window.innerWidth : 1680
  const deskH = typeof window !== 'undefined' ? window.innerHeight - 60 : 940
  const size = TERM[kind]
  const h = size.h + BAR + (kind === 'ws' ? STRIP : 0) + 6
  moveWin(`${kind}:${ref}`, kind === 'ws' ? 12 : deskW - size.w - 14, Math.max(140, deskH - h))
}

function inOtherWindow(d: ReturnType<typeof useDesk>, chat: string, self: Win) {
  return d.windows.some((w) => w.id !== self.id && ((w.kind === 'chat' && w.ref === chat) || (w.kind === 'ws' && w.ref === wsOfChat(d, chat))))
}

/**
 * Where a sidebar that is opening goes so the terminal never moves: its own
 * side when the screen has room there (next to any sidebar already on that
 * side), else the other side; only when neither has room does it stay on
 * its own side and the window slides by `slide`. Sidebars already open keep
 * their places.
 */
export function placeSide(x: number, w: number, deskW: number, at: { left: Side | null; right: Side | null }, side: Side) {
  const lw = (at.left === 'left' ? LW : 0) + (at.right === 'left' ? RW : 0)
  const rw = (at.left === 'right' ? LW : 0) + (at.right === 'right' ? RW : 0)
  const width = side === 'left' ? LW : RW
  const roomL = x - lw - width >= 0
  const roomR = x + w + rw + width <= deskW
  const pick: Side = side === 'left' ? (roomL ? 'left' : roomR ? 'right' : 'left') : (roomR ? 'right' : roomL ? 'left' : 'right')
  const nl = lw + (pick === 'left' ? width : 0)
  const nr = rw + (pick === 'right' ? width : 0)
  const slide = x - nl < 0 ? -(x - nl) : x + w + nr > deskW ? deskW - (x + w + nr) : 0
  return { pick, slide }
}

/**
 * With both open and no room for the new one on either side, try every way
 * of seating the two: a layout that needs no slide wins over keeping the
 * open sidebar where it was — the terminal and the toggles matter more.
 */
export function seatBoth(x: number, w: number, deskW: number) {
  const ways: Array<{ left: Side; right: Side }> = [{ left: 'left', right: 'right' }, { left: 'right', right: 'left' }, { left: 'left', right: 'left' }, { left: 'right', right: 'right' }]
  for (const at of ways) {
    const { lw, rw } = widths(at)
    if (x - lw >= 0 && x + w + rw <= deskW) return at
  }
  return null
}

const widths = (at: { left: Side | null; right: Side | null }) => ({
  lw: (at.left === 'left' ? LW : 0) + (at.right === 'left' ? RW : 0),
  rw: (at.left === 'right' ? LW : 0) + (at.right === 'right' ? RW : 0),
})

function JWindow({ win, top, instant, setInstant }: { win: Win; top: boolean; instant: boolean; setInstant: (v: boolean) => void }) {
  const st = useAqua()
  const d = useDesk()
  const drag = useDrag(win)
  const kind = win.kind
  const fixedWs = kind === 'ws' ? win.ref! : null
  const fixedChat = kind === 'chat' ? win.ref! : null
  const [picked, setChat] = useState(fixedChat ?? (fixedWs ? chatsIn(d, fixedWs)[0]?.id : st.active) ?? st.active)
  const [level, setLevel] = useState<Level>('chat')
  const [sides, setSides] = useState<{ left: Side | null; right: Side | null }>({ left: null, right: null })
  const open = { left: !!sides.left, right: !!sides.right }
  const [folded, setFolded] = useState(false)
  const [tab, setTab] = useState<InspTab>('messages')
  const [note, setNote] = useState('nt_7d21c0aa')
  const [split, setSplit] = useState<Split>(null)
  const [hints, setHints] = useState(false)
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [menu, setMenu] = useState<string | null>(null)
  const [tabMenuAt, setTabMenuAt] = useState<{ id: string; x: number } | null>(null)
  const tabMenu = tabMenuAt?.id ?? null
  const setTabMenu = (v: null) => setTabMenuAt(v)
  const frameRef = useRef<HTMLDivElement>(null)
  const [others, setOthers] = useState(false)
  const slid = useRef(0)
  // the levels stay mounted but unpainted once the zoom back in has finished
  const [settled, setSettled] = useState(true)
  useEffect(() => {
    if (level !== 'chat') { setSettled(false); return }
    const h = setTimeout(() => setSettled(true), CHAT_ZOOM_SETTLE_MS)
    return () => clearTimeout(h)
  }, [level])

  const visible = (c: string) => !inOtherWindow(d, c, win) || c === fixedChat
  const chat = fixedChat ?? (fixedWs
    ? (wsOfChat(d, picked) === fixedWs ? picked : chatsIn(d, fixedWs)[0]?.id ?? picked)
    : (visible(picked) ? picked : SESSIONS.find((x) => visible(x.id))?.id ?? picked))
  const ws = fixedWs ?? wsOfChat(d, chat)
  const s = sessionOf(chat)!
  const wsObj = wsById(d, ws)
  const size = TERM[kind]
  const deskW = typeof window !== 'undefined' ? window.innerWidth : 1680
  const place = { at: sides, ...widths(sides) }

  const go = (id: string) => {
    if (fixedChat) return
    if (fixedWs && wsOfChat(d, id) !== fixedWs) { detachJ('chat', id); return }
    setChat(id); setLevel('chat'); setOthers(false); if (kind === 'main') focus(id)
  }
  const goWs = (w: string) => { if (fixedWs) return; const first = chatsIn(d, w).find((x) => visible(x.id)); if (first) setChat(first.id); setOthers(false); setLevel('ws') }
  const openNote = (id: string) => { setNote(id); setTab('note'); toggle('right', true) }
  const out = () => setLevel(level === 'chat' ? 'ws' : fixedWs || fixedChat ? 'ws' : 'all')
  const into = () => setLevel(level === 'all' ? 'ws' : 'chat')

  /** Open or shut a sidebar. The terminal stays; the flash says where the sidebar went if not on its own side. */
  function toggle(side: Side, on = !open[side]) {
    if (!on) {
      setSides({ ...sides, [side]: null })
      if (slid.current && !sides[side === 'left' ? 'right' : 'left']) { moveWin(win.id, win.x - slid.current, win.y); slid.current = 0 }
      return
    }
    if (sides[side]) return
    const p = placeSide(win.x, size.w, deskW, sides, side)
    const other = side === 'left' ? 'right' : 'left'
    if (p.slide && sides[other]) {
      const seat = seatBoth(win.x, size.w, deskW)
      if (seat) { setSides(seat); flash(t('Both sidebars seated where the screen has room; the terminal and the toggles stay')); return }
    }
    if (p.pick !== side) flash(side === 'left' ? t('No room on the left: the sidebar opens on the right; the terminal and the toggles stay') : t('No room on the right: the sidebar opens on the left; the terminal and the toggles stay'))
    if (p.slide) { moveWin(win.id, win.x + p.slide, win.y); slid.current += p.slide; flash(t('No room on either side: the window moved in')) }
    setSides({ ...sides, [side]: p.pick })
  }

  const waitingNext = () => {
    const w = SESSIONS.filter((x) => x.state === 'waiting' && !st.asleep[x.id] && visible(x.id) && (!fixedWs || wsOfChat(d, x.id) === fixedWs))
    if (!w.length) return
    const i = w.findIndex((x) => x.id === chat)
    go(w[(i + 1) % w.length]!.id)
  }

  const actions: Action[] = useMemo(() => [
    { id: 'out', group: t('view'), label: t('Zoom out: the workspace, then every workspace'), kbd: 'Ctrl+Shift+↑', run: out },
    { id: 'left', group: t('view'), label: t('Left sidebar: workspaces and servers'), kbd: 'alt+[', run: () => toggle('left') },
    { id: 'right', group: t('view'), label: t('Right sidebar: messages, pins, branches, note, stats'), kbd: 'alt+]', run: () => toggle('right') },
    { id: 'fold', group: t('view'), label: t('Fold or unfold the title row'), kbd: 'alt+T', run: () => setFolded((f) => !f) },
    { id: 'motion', group: t('view'), label: instant ? t('Motion: fluid') : t('Motion: instant'), run: () => setInstant(!instant) },
    { id: 'editor', group: t('pane'), label: t('Editor as a split'), kbd: 'alt+E', run: () => setSplit(split === 'editor' ? null : 'editor') },
    { id: 'hints', group: t('copy'), label: t('Hints: copy an id or a path'), kbd: 'alt+H', run: () => setHints(true) },
    ...chatsIn(d, ws).filter((c) => visible(c.id) && kind !== 'chat').map((c) => ({ id: `dc-${c.id}`, group: t('window'), label: `${t('Detach')} ${c.name}`, run: () => detachJ('chat', c.id) })),
    { id: 'dws', group: t('window'), label: `${t('Detach the workspace')} ${wsObj?.name ?? ''}`, run: () => detachJ('ws', ws) },
    ...liveWorkspaces(d).map((w) => ({ id: `ws-${w.id}`, group: t('workspace'), label: w.name, run: () => goWs(w.id) })),
    ...commonActions(go, { note: openNote, server: (id) => setSplit({ server: id }) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [d, chat, open, split, level, ws, instant])

  useKeys({
    'mod+k': () => { if (top) setPalette(true) },
    'mod+shift+ArrowUp': () => { if (top) out() },
    'mod+shift+ArrowDown': () => { if (top) into() },
    'alt+[': () => { if (top) toggle('left') },
    'alt+]': () => { if (top) toggle('right') },
    'alt+t': () => { if (top) setFolded((f) => !f) },
    'alt+e': () => { if (top) setSplit(split === 'editor' ? null : 'editor') },
    'alt+h': () => { if (top) setHints((h) => !h) },
    'alt+w': () => { if (top) waitingNext() },
    '?': () => { if (top) setKeys(true) },
    Escape: () => { if (!top) return; setPalette(false); setKeys(false); setHints(false); setMenu(null); setTabMenu(null); setOthers(false); if (level !== 'chat') setLevel('chat') },
  })

  // ---- the strip: the current workspace open, the others folded behind "+N"
  const current = chatsIn(d, ws).filter((c) => visible(c.id))
  const foldedWs = kind === 'main' ? liveWorkspaces(d).filter((w) => w.id !== ws && chatsIn(d, w.id).some((c) => visible(c.id))) : []
  const waitingIn = (w: string) => chatsIn(d, w).filter((c) => c.state === 'waiting' && !st.asleep[c.id] && visible(c.id)).length
  const custom = isCustom(d, ws)
  const dropOn = (target: string, dragged: string) => {
    if (dragged === target) return
    const tw = wsOfChat(d, target)
    if (isCustom(d, tw)) { moveChat(dragged, tw); flash(`${sessionOf(dragged)!.name} ${t('moved to')} ${wsById(d, tw)!.name}`) }
    else makeGroup([target, dragged])
  }
  const strip = kind === 'chat' ? null : (
    <div className="shrink-0 flex items-end gap-2 px-6 min-w-0" style={{ height: STRIP, background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)' }} role="tablist" aria-label={t('Chats')}>
      <div className="flex items-end gap-1 min-w-0 overflow-x-auto overflow-y-hidden r2-tabs">
        {current.map((c) => {
          const on = c.id === chat
          const dim = on && level !== 'chat'
          return (
            <button key={c.id} type="button" role="tab" aria-selected={on} draggable data-nodrag
              onDragStart={(e) => e.dataTransfer.setData('text/chat', c.id)} onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { const dr = e.dataTransfer.getData('text/chat'); if (dr) dropOn(c.id, dr) }}
              onClick={() => go(c.id)} onContextMenu={(e) => { e.preventDefault(); const r = frameRef.current?.getBoundingClientRect(); setTabMenuAt({ id: c.id, x: e.currentTarget.getBoundingClientRect().left - (r?.left ?? 0) }) }} title={`${c.name} · ${STATE_WORD[shownState(st, c)]}`}
              className="h-[26px] px-10 inline-flex items-center gap-6 text-12 rounded-t-[6px] max-w-[170px] shrink-0"
              style={{ background: dim ? 'var(--aq-hover)' : on ? 'var(--aq-term-bg)' : undefined, color: dim ? 'var(--aq-ink)' : on ? 'var(--aq-term-fg)' : 'var(--aq-ink2)', boxShadow: on ? 'inset 0 2px 0 var(--brand)' : custom ? `inset 0 -2px 0 ${SP_PAINT.ink(wsObj!.hue)}` : undefined }}>
              <StateDot s={c} st={st} /><span className="truncate">{c.name}</span>
            </button>
          )
        })}
      </div>
      {foldedWs.length > 0 && (
        <span className="self-center relative ml-4 shrink-0">
          <button type="button" data-nodrag className="aq-btn line !h-[20px] text-11" aria-expanded={others} aria-haspopup="menu" onClick={() => setOthers(!others)} title={t('The other workspaces, folded')}>
            +{foldedWs.length}
            {foldedWs.some((w) => waitingIn(w.id) > 0) && <span className="w-[6px] h-[6px] rounded-full" style={{ background: 'var(--aq-wait)' }} />}
          </button>
          {others && (
            // a list under the chip: the strip keeps its width, the current tabs never shrink
            <div className="absolute top-[24px] right-0 z-[30] w-[260px] rounded-[8px] p-4 aq-fade" role="menu" aria-label={t('The other workspaces, folded')}
              style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)' }}>
              {foldedWs.map((w) => (
                <div key={w.id} className="flex items-center" onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { const dr = e.dataTransfer.getData('text/chat'); if (dr) { moveChat(dr, w.id); flash(`${sessionOf(dr)!.name} ${t('moved to')} ${w.name}`) } }}>
                  <button type="button" role="menuitem" data-nodrag className="aq-row h-[28px] px-8 text-12 flex-1 min-w-0"
                    onClick={() => { const first = chatsIn(d, w.id).find((c) => visible(c.id)); if (first) go(first.id) }}>
                    <span className="w-[8px] h-[8px] rounded-[2px] shrink-0" style={{ background: SP_PAINT.ink(w.hue) }} />
                    <span className="truncate" style={{ color: 'var(--aq-ink)' }}>{w.name}</span>
                    {!w.project && <span className="aq-chip">{t('group')}</span>}
                    <span className="ml-auto font-mono text-10 aq-ink3">{chatsIn(d, w.id).filter((c) => visible(c.id)).length}</span>
                    {waitingIn(w.id) > 0 && <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: 'var(--aq-wait)' }} aria-label={t('your turn')} />}
                  </button>
                  {!w.project && <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={`${t('Group')} ${w.name}`} onClick={() => { setOthers(false); setMenu(w.id) }}><Menu size={11} /></button>}
                </div>
              ))}
            </div>
          )}
        </span>
      )}
      <button type="button" data-nodrag className="aq-btn icon self-center shrink-0" aria-label={t('New chat')} title={t('New chat')}><Plus size={13} /></button>
      <button type="button" data-nodrag className="aq-btn self-center shrink-0 ml-auto" aria-pressed={level !== 'chat'} onClick={level === 'chat' || (level === 'ws' && kind === 'main') ? out : into}
        title={t('Workspaces (Ctrl+Shift+↑)')} aria-label={t('Workspaces')}>
        <LayoutGrid size={13} />{wsObj && <span className="text-11">{wsObj.name}</span>}
        {waitingIn(ws) > 0 && <span className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {waitingIn(ws)}</span>}
      </button>
    </div>
  )

  // ---- the levels: the terminal shrinks into its tile (transform + opacity only)
  const dur = instant ? 0 : 200
  const tileIndex = Math.max(0, chatsIn(d, ws).filter((c) => !st.asleep[c.id]).findIndex((c) => c.id === chat))
  const cols = kind === 'main' ? 3 : 2
  const tileW = (size.w - 24 - (cols - 1) * 10) / cols
  const zoomTo = `translate(${12 + (tileIndex % cols) * (tileW + 10)}px, ${84 + Math.floor(tileIndex / cols) * 178}px) scale(${tileW / size.w})`
  const body = (
    <div className="relative min-h-0 overflow-hidden" style={{ width: size.w, height: size.h }} data-level={level}>
      <div className="absolute inset-0" style={{ background: 'var(--r2-over)', opacity: level === 'chat' ? 0 : 1, transition: `opacity ${dur}ms var(--aq-ease)`, pointerEvents: level === 'chat' ? 'none' : 'auto' }}>
        {/* kept mounted (still snapshots, nothing ticking) so a zoom only animates transform and opacity */}
        {(
          <div className="absolute inset-0 flex flex-col" aria-hidden={level === 'chat'} style={{ visibility: level === 'chat' && settled ? 'hidden' : 'visible' }}>
            <div className="h-[28px] shrink-0 flex items-center gap-6 px-12 text-12" aria-label={t('Where you are')}>
              {!fixedWs && !fixedChat && <button type="button" data-nodrag className="aq-btn" data-on={level === 'all'} onClick={() => setLevel('all')}>{t('All workspaces')}</button>}
              {!fixedWs && !fixedChat && <ChevronRight size={12} className="aq-ink3" />}
              <button type="button" data-nodrag className="aq-btn" data-on={level === 'ws'} style={{ opacity: level === 'all' ? 0.55 : 1 }} onClick={() => setLevel('ws')}>{wsObj?.name}</button>
              <ChevronRight size={12} className="aq-ink3" style={{ opacity: 0.55 }} />
              <button type="button" data-nodrag className="aq-btn" style={{ opacity: 0.55 }} onClick={() => setLevel('chat')}>{s.name}</button>
              <span className="ml-auto text-10 aq-ink3 font-mono">Esc {t('back to the terminal')}</span>
            </div>
            <div className="flex-1 min-h-0 relative">
              <div className="absolute inset-0" style={{ transform: level === 'all' ? 'scale(0.94)' : 'none', opacity: level === 'all' ? 0 : 1, transition: `transform ${dur}ms var(--aq-ease), opacity ${dur}ms`, pointerEvents: level === 'ws' ? 'auto' : 'none' }}>
                <WsLevel ws={ws} current={chat} onChat={go} onServer={(id) => { setSplit({ server: id }); setLevel('chat') }} cols={cols} onMenu={() => setMenu(ws)} />
              </div>
              <div className="absolute inset-0" style={{ transform: level === 'all' ? 'none' : 'scale(1.05)', opacity: level === 'all' ? 1 : 0, transition: `transform ${dur}ms var(--aq-ease), opacity ${dur}ms`, pointerEvents: level === 'all' ? 'auto' : 'none' }}>
                <AllLevel current={chat} onWs={goWs} onChat={go} />
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="absolute inset-0 origin-top-left" style={{ transform: level === 'chat' ? 'none' : zoomTo, opacity: level === 'chat' ? 1 : 0, transition: `transform ${dur}ms var(--aq-ease), opacity ${Math.round(dur * 0.7)}ms`, pointerEvents: level === 'chat' ? 'auto' : 'none', willChange: instant ? undefined : 'transform' }}>
        <TermArea chat={chat} split={split} hints={hints && top} onHintsDone={() => setHints(false)} onNote={openNote} size={kind === 'chat' ? 12 : 13} />
      </div>
    </div>
  )

  // ---- the frame: the terminal column stays at win.x; sidebars stack on the side the screen has room
  // a sidebar that went to the other side sits outermost, so the one beside the terminal is the one that belongs there
  const leftSide = (['right', 'left'] as const).filter((k) => open[k] && place.at[k] === 'left')
  const rightSide = (['right', 'left'] as const).filter((k) => open[k] && place.at[k] === 'right')
  const frameX = win.x - place.lw
  const bar = folded ? BAR_FOLDED : BAR
  const sideH = size.h + (strip ? STRIP : 0)
  const panel = (k: Side) => (
    <aside key={k} className={`shrink-0 ${k === 'left' ? 'r2-side-l' : 'r2-side-r'}`} aria-label={k === 'left' ? t('Left sidebar') : t('Right sidebar')}
      style={{ width: k === 'left' ? LW : RW, height: sideH, background: 'var(--aq-panel)', borderLeft: '1px solid var(--aq-line)', borderRight: '1px solid var(--aq-line)', animation: instant ? 'none' : undefined }}>
      {k === 'left'
        ? <LeftTree ws={ws} chat={chat} onChat={go} onWs={goWs} onServer={(id) => setSplit({ server: id })} />
        : <Inspector chat={chat} tab={tab} setTab={setTab} note={note} onNote={openNote} onChat={go} branches={<LineageTree chat={chat} onChat={go} />} />}
    </aside>
  )
  const title = kind === 'chat' ? `${s.name} — ${t('from')} ${wsObj?.name ?? ''}` : `${s.name} — ${wsObj?.name ?? ''}`
  // the toggles' places: the terminal column's corners, whatever is open
  const lt = place.lw + TOGGLE_INSET
  const rt = place.lw + size.w - TOGGLE_INSET - 24
  // folded, a toggle is an 8px dot centred where its 24px button was

  return (
    <div ref={frameRef} className="absolute flex flex-col r2-win" role="dialog" aria-label={`${t('Window')}: ${kind === 'main' ? 'SP Aqua' : title}`}
      onPointerDown={() => raise(win.id)} style={{ left: frameX, top: win.y, zIndex: win.z }} data-folded={folded || undefined}>
      <div className="flex flex-col rounded-[8px] overflow-hidden" style={{ boxShadow: top ? 'var(--shadow-lg)' : 'var(--shadow-md)', border: '1px solid var(--border-strong)', borderTop: kind !== 'main' ? `3px solid ${SP_PAINT.ink(wsObj?.hue ?? 195)}` : undefined }}>
        {/* the title row: folds to a 12px strip */}
        <div className="relative shrink-0 select-none cursor-grab" style={{ height: bar, background: 'var(--r2-bar)', color: 'var(--r2-bar-ink)', transition: instant ? undefined : 'height 120ms var(--aq-ease)' }}
          {...drag} onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest('button')) setFolded(!folded) }}>
          {kind !== 'chat' && (
            <button type="button" data-nodrag className="absolute inline-flex items-center justify-center rounded-[6px] hover:bg-[var(--aq-hover)]" aria-pressed={open.left} aria-label={t('Left sidebar')} title={place.at.left === 'right' ? t('Left sidebar (alt+[) — opened on the right: no room on the left') : t('Left sidebar (alt+[)')} data-toggle="left"
              style={{ left: folded ? lt + 8 : lt, top: folded ? 2 : 5, width: folded ? 8 : 24, height: folded ? 8 : 24 }} onClick={() => toggle('left')}>
              {folded ? <span className="w-[8px] h-[8px] rounded-full" style={{ background: open.left ? 'var(--brand)' : 'var(--text-tertiary)' }} /> : <PanelLeft size={14} style={{ color: open.left ? 'var(--brand)' : undefined }} />}
              {!folded && place.at.left === 'right' && <span className="absolute -right-10 text-11 font-semibold" style={{ color: 'var(--brand)' }} aria-hidden>▸</span>}
            </button>
          )}
          <span className="absolute truncate text-center" style={{ left: place.lw + (kind === 'main' || folded ? 40 : 130), width: size.w - (kind === 'main' || folded ? 80 : 260), top: 0, lineHeight: `${bar}px`, fontSize: folded ? 9 : 13, fontWeight: folded ? 500 : 600, color: folded ? 'var(--text-tertiary)' : 'var(--r2-bar-ink)' }}>{title}</span>
          {!folded && (
            <span className="absolute flex items-center gap-2" style={{ right: place.rw + 40, top: 5 }}>
              {kind === 'main' && <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Command palette')} title="Ctrl+K" onClick={() => setPalette(true)}><Search size={14} /></button>}
              <button type="button" data-nodrag className="aq-btn icon" aria-pressed={instant} aria-label={instant ? t('Motion: instant') : t('Motion: fluid')} title={instant ? t('Motion: instant') : t('Motion: fluid')} onClick={() => setInstant(!instant)}><Zap size={13} /></button>
              <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Fold the title row (alt+T)')} title={t('Fold the title row (alt+T)')} onClick={() => setFolded(true)}><ChevronUp size={14} /></button>
              {kind === 'main'
                ? <span className="w-[22px] h-[22px] rounded-full inline-flex items-center justify-center" style={{ background: 'var(--r2-ctl)' }} aria-hidden><X size={12} /></span>
                : <button type="button" data-nodrag className="aq-btn" onClick={() => closeWin(win.id)} title={t('Dock back into the main window')}>{t('Dock back')}</button>}
            </span>
          )}
          {folded && (
            <button type="button" data-nodrag className="absolute r2-unfold inline-flex items-center justify-center" aria-label={t('Unfold the title row (alt+T)')} title={t('Unfold the title row (alt+T)')}
              style={{ left: place.lw + size.w / 2 + 160, top: 0, height: BAR_FOLDED, width: 24 }} onClick={() => setFolded(false)}><ChevronDown size={11} /></button>
          )}
          {kind !== 'chat' && (
            <button type="button" data-nodrag className="absolute inline-flex items-center justify-center rounded-[6px] hover:bg-[var(--aq-hover)]" aria-pressed={open.right} aria-label={t('Right sidebar')} title={place.at.right === 'left' ? t('Right sidebar (alt+]) — opened on the left: no room on the right') : t('Right sidebar (alt+])')} data-toggle="right"
              style={{ left: folded ? rt + 8 : rt, top: folded ? 2 : 5, width: folded ? 8 : 24, height: folded ? 8 : 24 }} onClick={() => toggle('right')}>
              {folded ? <span className="w-[8px] h-[8px] rounded-full" style={{ background: open.right ? 'var(--brand)' : 'var(--text-tertiary)' }} /> : <PanelRight size={14} style={{ color: open.right ? 'var(--brand)' : undefined }} />}
              {!folded && place.at.right === 'left' && <span className="absolute -left-10 text-11 font-semibold" style={{ color: 'var(--brand)' }} aria-hidden>◂</span>}
            </button>
          )}
        </div>
        <div className="flex min-h-0" style={{ background: 'var(--aq-panel)' }}>
          {leftSide.map(panel)}
          <div className="flex flex-col min-w-0 relative" style={{ width: size.w }}>
            {strip}
            {body}
          </div>
          {rightSide.map(panel)}
        </div>
      </div>
      {tabMenu && (
        <div className="absolute z-[40] aq-glass aq-float rounded-[10px] p-6 flex flex-col w-[260px] aq-fade" style={{ left: Math.min(tabMenuAt!.x, place.lw + size.w - 264), top: (folded ? BAR_FOLDED : BAR) + STRIP + 2 }} role="menu" aria-label={sessionOf(tabMenu)!.name}>
          <span className="aq-label px-6 py-4">{sessionOf(tabMenu)!.name}</span>
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { makeGroup([tabMenu]); setTabMenu(null) }}>{t('New group from this tab')}</button>
          {liveWorkspaces(d).filter((w) => isCustom(d, w.id) && w.id !== wsOfChat(d, tabMenu)).map((w) => (
            <button key={w.id} type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { moveChat(tabMenu, w.id); flash(`${sessionOf(tabMenu)!.name} ${t('moved to')} ${w.name}`); setTabMenu(null) }}>
              <span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: SP_PAINT.ink(w.hue) }} />{t('Move to')} {w.name}</button>
          ))}
          {isCustom(d, wsOfChat(d, tabMenu)) && (
            <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { const p = sessionOf(tabMenu)!.project; moveChat(tabMenu, `ws_${p}`); flash(`${sessionOf(tabMenu)!.name} ${t('back in')} ${wsById(d, `ws_${p}`)!.name}`); setTabMenu(null) }}>
              {t('Out of the group, back to')} {wsById(d, `ws_${sessionOf(tabMenu)!.project}`)!.name}</button>
          )}
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12" onClick={() => { detachJ('chat', tabMenu); setTabMenu(null) }}>{t('Detach into its own window')}</button>
          <button type="button" role="menuitem" className="aq-row px-8 h-[26px] text-12 aq-ink3" onClick={() => setTabMenu(null)}>{t('Close')}</button>
        </div>
      )}
      {menu && <GroupMenu key={menu} ws={menu} onClose={() => setMenu(null)} className="absolute top-[70px] z-[40]" />}
      {palette && <div className="absolute inset-0 z-[50]" style={{ minWidth: 700, minHeight: 500 }}><Palette open onClose={() => setPalette(false)} actions={actions} /></div>}
      {keys && <div className="absolute inset-0 z-[50]" style={{ minWidth: 700, minHeight: 500 }}><Keymap open onClose={() => setKeys(false)} keys={[
        ['Ctrl Shift ↑', t('zoom out: the workspace, then every workspace')], ['Ctrl Shift ↓', t('zoom back in')], ['Esc', t('back to the terminal')],
        ['alt [', t('left sidebar')], ['alt ]', t('right sidebar')], ['alt T', t('fold or unfold the title row')], ['alt W', t('next chat waiting on you')],
        ['alt E', t('editor as a split')], ['alt H', t('hints: copy an id or a path')], ['Ctrl K', t('command palette')], [t('drag a tab onto a tab'), t('make a group: a workspace of your own')], ...MESSAGE_KEYS,
      ]} /></div>}
    </div>
  )
}

export function J({ theme }: { theme: Theme }) {
  const d = useDesk()
  const [instant, setInstantState] = useState(readMotion)
  const setInstant = (v: boolean) => { setInstantState(v ? 'instant' : 'fluid'); try { localStorage.setItem(MOTION_KEY, v ? 'instant' : 'fluid') } catch { /* private mode */ } }
  // J paints with Slightly Parallel's own tokens: the round's theme switch sets SP's theme while J is open
  useEffect(() => {
    const root = document.documentElement
    const before = root.getAttribute('data-theme')
    root.setAttribute('data-theme', theme)
    return () => { if (before) root.setAttribute('data-theme', before); else root.removeAttribute('data-theme') }
  }, [theme])
  useEffect(() => {
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('edge')) moveWin('main', window.innerWidth - 1012, 96)
  }, [])
  const topZ = Math.max(...d.windows.map((w) => w.z))
  return (
    <PaintProvider value={SP_PAINT}>
      <Desktop>
        {d.windows.map((w) => <JWindow key={w.id} win={w} top={w.z === topZ} instant={instant === 'instant'} setInstant={setInstant} />)}
        <Restore className="absolute right-24 top-48 w-[520px] z-[200]" />
      </Desktop>
    </PaintProvider>
  )
}

