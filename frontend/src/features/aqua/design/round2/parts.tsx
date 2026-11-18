/**
 * Round 2's shared parts: the desktop the windows sit on, the drag of a
 * window, the terminal with its split, the two overview levels (one
 * workspace; every workspace), the left tree, the inspector with the
 * master message on top of the pins, and the menu of a workspace.
 */

import { createContext, useContext, useRef, useState, type ReactNode } from 'react'
import { Check, ExternalLink, FileText, Flag, GitBranch, Moon, MessageSquare, Pin, Activity, Sun, X } from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { MESSAGES, messagesOf, projectOf, sessionOf } from '../mock'
import { Branches, Editor, MessageRow, Messages, NoteBody, NoteMeta, Pins, ServerLog, StateDot, Stats, shownState, STATE_WORD } from '../parts'
import { flash, setChatsAsleep, toggleServer, useAqua, type AquaState } from '../store'
import { Screen } from '../term'
import { LabMenus, useScreenLab } from '../round3/lab2/MsgMenu'
import { Lab2Panel } from '../round3/lab2/Panel'
import { schemeOf, termVars, windowVars } from '../round3/lab2/schemes'
import { useLab2 } from '../round3/lab2/store'
import {
  chatsIn, detachWin, group, isCustom, liveWorkspaces, moveWin, raise, recolour, rename, serversFor, ungroup, useDesk, workspaceSleepPlan, wsById, wsHue,
  type Win,
} from './desk'

export const wsInk = (hue: number) => `oklch(0.70 0.13 ${hue})`
export const wsTint = (hue: number, a = 0.14) => `oklch(0.70 0.13 ${hue} / ${a})`

/**
 * How a workspace's colour is painted, by its hue. Round 2 paints the hue
 * itself; round 3 (J) maps it onto Slightly Parallel's own categorical lane
 * colours. Also whether a tile is a live terminal or a still snapshot.
 */
export interface Paint { ink: (hue: number) => string; tint: (hue: number, a?: number) => string; still?: boolean
  /** Pools on the app's plain surface, the colour only as a dot and a left edge (J). */
  plain?: boolean
  /** The labs of 18.11 switched on: colour schemes, the message menu, the «Схема» panel (K). */
  lab?: boolean }
const PaintCtx = createContext<Paint>({ ink: wsInk, tint: wsTint })
export const PaintProvider = PaintCtx.Provider
export const usePaint = () => useContext(PaintCtx)

/** A tile's still picture: the last lines of the chat as text, drawn once — no clock, no live terminal. */
export function Snapshot({ id, lines = 7 }: { id: string; lines?: number }) {
  const s = sessionOf(id)!
  const text = s.script.slice(-lines).map((l) => {
    switch (l.k) {
      case 'you': return `> ${l.text}`
      case 'say': return `⏺ ${l.text}`
      case 'tool': return `⏺ ${l.name}(${l.arg})${l.out ? `\n  ⎿ ${l.out}` : ''}`
      case 'note': return `⏺ ${l.text}`
      case 'compact': return `✻ ${l.text}`
      default: return ''
    }
  }).filter(Boolean).join('\n')
  return <pre className="m-0 h-full overflow-hidden px-8 py-6 font-mono text-[11px] leading-snug whitespace-pre-wrap" style={{ background: 'var(--aq-term-bg)', color: 'var(--aq-term-dim)' }}>{text}</pre>
}

/* ------------------------------------------------------------ desktop */

/**
 * The page is the desktop: a neutral wallpaper and the system's top bar; the app is only its windows.
 * In K (the lab paint) the lab's colour scheme paints the windows — the terminal only, or the whole
 * window — and the lab's panel sits beside them.
 */
export function Desktop({ children }: { children: ReactNode }) {
  const paint = usePaint()
  const lab = useLab2()
  const scheme = schemeOf(lab.scheme)
  const vars = paint.lab ? { ...termVars(scheme), ...(lab.scope === 'window' ? windowVars(scheme) : {}) } as React.CSSProperties : undefined
  return (
    <div className="absolute inset-0 overflow-hidden" style={{ background: 'var(--r2-wall)' }}>
      <div className="h-[26px] flex items-center px-12 text-12 font-medium" style={{ background: 'var(--r2-topbar)', color: 'var(--r2-topbar-ink)' }} aria-hidden>
        <span>{t('Activities')}</span>
        <span className="mx-auto tabular-nums">Mon 16 Nov  10:48</span>
        <span className="opacity-80">⏻</span>
      </div>
      {vars ? <div className="contents" style={vars} data-scheme={scheme.id} data-scope={lab.scope}>{children}</div> : children}
      {paint.lab && <Lab2Panel />}
    </div>
  )
}

/** Drag a window by its bar; a click raises it. */
export function useDrag(win: Win) {
  const at = useRef<{ dx: number; dy: number } | null>(null)
  return {
    onPointerDown: (e: React.PointerEvent) => {
      if ((e.target as HTMLElement).closest('button,input,select,[data-nodrag]')) return
      raise(win.id)
      at.current = { dx: e.clientX - win.x, dy: e.clientY - win.y }
      ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
    },
    onPointerMove: (e: React.PointerEvent) => { if (at.current) moveWin(win.id, Math.max(-200, e.clientX - at.current.dx), Math.max(26, e.clientY - at.current.dy)) },
    onPointerUp: () => { at.current = null },
  }
}

/* ------------------------------------------------------------ terminal */

export type Split = null | 'editor' | { server: string }

/** The terminal of one chat, plain and opaque, with an optional split under it (the editor or a server's log). */
export function TermArea({ chat, split, hints, onHintsDone, onNote, size = 13 }: {
  chat: string; split: Split; hints?: boolean; onHintsDone?: () => void; onNote?: (id: string) => void; size?: number
}) {
  const st = useAqua()
  const s = sessionOf(chat)!
  // K's lab (round3/lab2): ANSI output, message blocks with their menu, task menus
  const area = useRef<HTMLDivElement>(null)
  const lab = useScreenLab(chat, area, !!usePaint().lab)
  return (
    <div className="h-full flex flex-col min-h-0" style={{ background: 'var(--aq-term-bg)' }}>
      <div ref={area} className="flex-1 min-h-0 relative">
        <Screen session={s} asleep={st.asleep[chat]} hints={hints} onHintsDone={onHintsDone} onNote={onNote} size={size} lab={lab}
          draft={chat === 'cc-b03d55e1' && !st.asleep[chat] ? 'staff are exempt, same as /login' : ''} />
        {lab && <LabMenus chat={chat} root={area} />}
        {hints && <div className="absolute top-6 right-10 aq-chip" style={{ background: 'var(--aq-term-hint)', color: 'var(--aq-term-hint-ink)' }}>{t('press a letter to copy · Esc')}</div>}
      </div>
      {split && (
        <div className="h-[38%] shrink-0 aq-fade" style={{ borderTop: '1px solid var(--aq-term-box)' }}>
          {split === 'editor' ? <Editor size={size - 1} /> : <ServerLog id={split.server} size={size - 1} />}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------- workspace sleep */

export const wsAsleep = (st: AquaState, d: ReturnType<typeof useDesk>, ws: string) => chatsIn(d, ws).every((s) => st.asleep[s.id])

export function sleepWorkspace(st: AquaState, d: ReturnType<typeof useDesk>, ws: string, asleep: boolean) {
  const plan = workspaceSleepPlan(d, ws, st.asleep, asleep)
  setChatsAsleep(plan.chats, asleep, plan.servers)
  const name = wsById(d, ws)?.name ?? ws
  if (asleep && plan.kept.length) flash(`${name} ${t('asleep')} · ${t('kept running for another awake workspace:')} ${plan.kept.join(', ')}`)
  else flash(`${name} ${asleep ? t('asleep') : t('awake')}`)
}

/* ------------------------------------------------------ the two levels */

function Tile({ id, on, onPick, selectable, selected, onSelect, frozen = true }: {
  id: string; on?: boolean; onPick: () => void; selectable?: boolean; selected?: boolean; onSelect?: () => void; frozen?: boolean
}) {
  const st = useAqua()
  const paint = usePaint()
  const s = sessionOf(id)!
  const k = shownState(st, s)
  return (
    <div className="relative flex flex-col min-h-0 min-w-0 rounded-[8px] overflow-hidden cursor-pointer transition-transform duration-150 hover:-translate-y-2"
      role="button" tabIndex={0} aria-label={`${s.name}, ${STATE_WORD[k]}`} onClick={onPick} onKeyDown={(e) => { if (e.key === 'Enter') onPick() }}
      style={{ boxShadow: `${k === 'waiting' ? 'inset 3px 0 0 var(--aq-wait), ' : ''}0 0 0 ${on ? 2 : 1}px ${on ? 'var(--aq-accent)' : 'var(--aq-line)'}, 0 8px 20px oklch(0 0 0 / 0.18)`, opacity: k === 'asleep' ? 0.6 : 1 }}>
      <div className="h-[24px] shrink-0 flex items-center gap-6 px-8" style={{ background: 'var(--aq-raise)' }}>
        <StateDot s={s} st={st} />
        <span className="text-12 truncate font-medium" style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
        <span className="text-10 font-mono aq-ink3 ml-auto shrink-0">{STATE_WORD[k]}</span>
        {selectable && (
          <button type="button" data-nodrag className="w-[16px] h-[16px] rounded-[4px] inline-flex items-center justify-center shrink-0" aria-pressed={!!selected} aria-label={`${t('Select')} ${s.name}`}
            onClick={(e) => { e.stopPropagation(); onSelect?.() }} style={{ border: '1.5px solid var(--aq-ink3)', background: selected ? 'var(--aq-accent)' : undefined }}>
            {selected && <Check size={11} style={{ color: 'var(--aq-accent-ink)' }} />}</button>
        )}
      </div>
      <div className="flex-1 min-h-0 pointer-events-none">{paint.still ? <Snapshot id={id} /> : <Screen session={s} asleep={st.asleep[id]} size={11} tail={6} focused={false} />}{frozen && null}</div>
    </div>
  )
}

/** Servers of the workspace's projects, each labelled with its project. */
export function WsServers({ ws, onOpen }: { ws: string; onOpen?: (id: string) => void }) {
  const st = useAqua()
  const d = useDesk()
  const list = serversFor(d, ws)
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <span className="aq-label">{t('servers')}</span>
      {list.map((s) => (
        <span key={s.id} className="inline-flex items-center rounded-[6px]" style={{ background: 'var(--aq-hover)' }}>
          <button type="button" data-nodrag className="h-[22px] px-8 inline-flex items-center gap-6 text-11" onClick={() => onOpen?.(s.id)}>
            <span className={`aq-dot ${st.up[s.id] ? 'up' : 'down'}`} /><span style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
            {s.port && <span className="font-mono aq-ink3">:{s.port}</span>}<span className="text-10 aq-ink3">{projectOf(s.project).name}</span>
          </button>
          <button type="button" data-nodrag className="aq-btn icon" aria-label={`${st.up[s.id] ? t('Stop') : t('Start')} ${s.name}`} onClick={() => toggleServer(s.id)}>{st.up[s.id] ? '■' : '▶'}</button>
        </span>
      ))}
      {!list.length && <span className="text-11 aq-ink3">{t('none')}</span>}
    </div>
  )
}

/** One workspace: its chats as tiles where the terminal was, its servers, sleep and wake, and for a group its menu. */
export function WsLevel({ ws, current, onChat, onServer, cols = 3, onMenu, selectable, sel, onSel }: {
  ws: string; current?: string; onChat: (id: string) => void; onServer?: (id: string) => void; cols?: number; onMenu?: () => void
  selectable?: boolean; sel?: string[]; onSel?: (id: string) => void
}) {
  const st = useAqua()
  const paint = usePaint()
  const d = useDesk()
  const w = wsById(d, ws)
  const chats = chatsIn(d, ws)
  const asleep = wsAsleep(st, d, ws)
  return (
    <div className="h-full flex flex-col gap-10 p-12 min-h-0 aq-fade">
      <div className="flex items-center gap-8 shrink-0">
        <span className="w-[10px] h-[10px] rounded-[3px]" style={{ background: paint.ink(w?.hue ?? 200) }} />
        <b className="text-14" style={{ color: 'var(--aq-ink)' }}>{w?.name}</b>
        <span className="text-11 aq-ink3">{tn(chats.length, '{n} chat', '{n} chats')}{isCustom(d, ws) ? ` · ${t('your group')}` : ''}</span>
        <span className="ml-auto flex items-center gap-4">
          {onMenu && isCustom(d, ws) && <button type="button" data-nodrag className="aq-btn line" onClick={onMenu}>{t('Group…')}</button>}
          <button type="button" data-nodrag className="aq-btn line" onClick={() => detachWin('ws', ws)}><ExternalLink size={12} />{t('Detach the workspace')}</button>
          <button type="button" data-nodrag className="aq-btn line" onClick={() => sleepWorkspace(st, d, ws, !asleep)}>{asleep ? <><Sun size={12} />{t('Wake the workspace')}</> : <><Moon size={12} />{t('Sleep the workspace')}</>}</button>
        </span>
      </div>
      <div className="flex-1 min-h-0 aq-scroll flex flex-col gap-10">
        <div className="grid gap-10 content-start" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: '168px' }}>
          {chats.filter((s) => !st.asleep[s.id]).map((s) => <Tile key={s.id} id={s.id} on={s.id === current} onPick={() => onChat(s.id)} selectable={selectable} selected={sel?.includes(s.id)} onSelect={() => onSel?.(s.id)} />)}
        </div>
        {chats.some((s) => st.asleep[s.id]) && (
          <ul className="m-0 p-0 list-none flex flex-wrap gap-6" aria-label={t('Asleep')}>
            {chats.filter((s) => st.asleep[s.id]).map((s) => (
              <li key={s.id} className="flex items-center gap-6 h-[26px] pl-8 pr-2 rounded-[6px] text-12" style={{ background: 'var(--aq-raise)', border: '1px solid var(--aq-line)' }}>
                <StateDot s={s} st={st} /><span style={{ color: 'var(--aq-ink2)' }}>{s.name}</span>
                <button type="button" data-nodrag className="aq-btn !h-[20px]" onClick={() => setChatsAsleep([s.id], false)}><Sun size={11} />{s.gone ? t('id gone') : t('Wake')}</button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="shrink-0"><WsServers ws={ws} onOpen={onServer} /></div>
    </div>
  )
}

/** Every workspace as a pool of its chats; a sleeping one sunk and frosted, a waiting chat with an amber edge. */
export function AllLevel({ current, onWs, onChat, selectable, sel, onSel, onGroup, cols = 3 }: {
  current?: string; onWs: (ws: string) => void; onChat: (id: string) => void; selectable?: boolean; sel?: string[]; onSel?: (id: string) => void; onGroup?: () => void; cols?: number
}) {
  const st = useAqua()
  const paint = usePaint()
  const d = useDesk()
  return (
    <div className="h-full flex flex-col gap-10 p-12 min-h-0 aq-fade">
      <div className="flex items-center gap-8 shrink-0">
        <b className="text-14" style={{ color: 'var(--aq-ink)' }}>{t('Every workspace')}</b>
        <span className="text-11 aq-ink3">{t('one per project, and your groups')}</span>
        {selectable && (
          <button type="button" data-nodrag className="aq-btn solid ml-auto" disabled={!sel?.length} style={{ opacity: sel?.length ? 1 : 0.5 }} onClick={onGroup}>
            {t('New workspace from selection')}{sel?.length ? ` · ${sel.length}` : ''}</button>
        )}
      </div>
      <div className="flex-1 min-h-0 aq-scroll grid gap-12 content-start items-start" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {liveWorkspaces(d).map((w) => {
          const chats = chatsIn(d, w.id)
          const asleep = wsAsleep(st, d, w.id)
          const waiting = chats.filter((s) => s.state === 'waiting' && !st.asleep[s.id]).length
          return (
            <section key={w.id} className="rounded-[12px] p-8 flex flex-col gap-6 transition-all duration-300"
              style={paint.plain
                ? { background: asleep ? 'var(--aq-panel)' : 'var(--aq-raise)', border: '1px solid var(--aq-line)', boxShadow: `inset 3px 0 0 ${paint.ink(w.hue)}`, transform: asleep ? 'translateY(6px)' : undefined, opacity: asleep ? 0.8 : 1 }
                : { background: paint.tint(w.hue, 0.1), border: `1px solid ${paint.tint(w.hue, 0.35)}`, transform: asleep ? 'translateY(10px) scale(0.97)' : undefined, filter: asleep ? 'saturate(0.2) blur(1.2px)' : undefined, opacity: asleep ? 0.55 : 1 }}
              aria-label={w.name}>
              <div className="flex items-center gap-6">
                <button type="button" data-nodrag className="flex items-center gap-6 min-w-0" onClick={() => onWs(w.id)}>
                  <span className="w-[9px] h-[9px] rounded-[3px] shrink-0" style={{ background: paint.ink(w.hue) }} />
                  <b className="text-13 truncate" style={{ color: 'var(--aq-ink)' }}>{w.name}</b>
                </button>
                {!w.project && <span className="aq-chip">{t('group')}</span>}
                {waiting > 0 && <span className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {waiting}</span>}
                <span className="text-10 aq-ink3 ml-auto">{asleep ? t('asleep') : tn(chats.length, '{n} chat', '{n} chats')}</span>
              </div>
              <ul className="m-0 p-0 list-none flex flex-col gap-2">
                {chats.map((s) => {
                  const k = shownState(st, s)
                  return (
                    <li key={s.id} className="flex items-center gap-6 rounded-[6px] px-6 h-[24px] cursor-pointer text-12" role="button" tabIndex={0}
                      onClick={() => onChat(s.id)} onKeyDown={(e) => { if (e.key === 'Enter') onChat(s.id) }}
                      style={{ background: s.id === current ? 'var(--aq-accent-soft)' : 'var(--aq-raise)', boxShadow: k === 'waiting' ? 'inset 3px 0 0 var(--aq-wait)' : undefined }}>
                      <StateDot s={s} st={st} /><span className="truncate flex-1" style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
                      {!w.project && <span className="text-10 aq-ink3 shrink-0">{projectOf(s.project).name}</span>}
                      {selectable && (
                        <button type="button" data-nodrag className="w-[14px] h-[14px] rounded-[3px] inline-flex items-center justify-center shrink-0" aria-pressed={!!sel?.includes(s.id)} aria-label={`${t('Select')} ${s.name}`}
                          onClick={(e) => { e.stopPropagation(); onSel?.(s.id) }} style={{ border: '1.5px solid var(--aq-ink3)', background: sel?.includes(s.id) ? 'var(--aq-accent)' : undefined }}>
                          {sel?.includes(s.id) && <Check size={10} style={{ color: 'var(--aq-accent-ink)' }} />}</button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          )
        })}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- the tree */

/** The left sidebar: workspaces with their chats, and the servers of the open one apart, labelled by project. */
export function LeftTree({ ws, chat, onChat, onWs, onServer }: { ws: string; chat: string; onChat: (id: string) => void; onWs: (ws: string) => void; onServer?: (id: string) => void }) {
  const st = useAqua()
  const paint = usePaint()
  const d = useDesk()
  return (
    <nav className="h-full flex flex-col min-h-0 text-12" aria-label={t('Workspaces')}>
      <div className="flex-1 min-h-0 aq-scroll p-6">
        {liveWorkspaces(d).map((w) => {
          const open = w.id === ws
          return (
            <section key={w.id} className="mb-4">
              <button type="button" data-nodrag className="aq-row h-[26px] px-6" aria-current={open} onClick={() => onWs(w.id)}>
                <span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: paint.ink(w.hue) }} />
                <b className="truncate flex-1" style={{ color: 'var(--aq-ink)' }}>{w.name}</b>
                {!w.project && <span className="aq-chip">{t('group')}</span>}
                <span className="font-mono text-10 aq-ink3">{chatsIn(d, w.id).length}</span>
              </button>
              {open && chatsIn(d, w.id).map((s) => (
                <button key={s.id} type="button" data-nodrag className="aq-row h-[24px] pl-20 pr-6" aria-current={s.id === chat} onClick={() => onChat(s.id)}>
                  <StateDot s={s} st={st} /><span className="truncate flex-1">{s.name}</span>
                  {s.tool === 'codex' && <span className="aq-chip">cx</span>}
                </button>
              ))}
            </section>
          )
        })}
      </div>
      <div className="p-8 flex flex-col gap-2" style={{ borderTop: '1px solid var(--aq-line)' }}>
        <span className="aq-label pb-2">{t('servers')}</span>
        {serversFor(d, ws).map((s) => (
          <div key={s.id} className="aq-row h-[24px] px-6" role="button" tabIndex={0} onClick={() => onServer?.(s.id)} onKeyDown={(e) => { if (e.key === 'Enter') onServer?.(s.id) }}>
            <span className={`aq-dot ${st.up[s.id] ? 'up' : 'down'}`} /><span className="truncate flex-1">{s.name}</span>
            <span className="text-10 aq-ink3">{projectOf(s.project).name}</span>
          </div>
        ))}
      </div>
    </nav>
  )
}

/* ------------------------------------------------------------- inspector */

export type InspTab = 'messages' | 'pins' | 'branches' | 'note' | 'stats'

/** The master message (pinned and important, else the first pin) held on top, then every pin of the workspace. */
export function PinsMaster({ chat, onNote, onJump }: { chat: string; onNote?: (id: string) => void; onJump?: (id: string) => void }) {
  const st = useAqua()
  const msgs = messagesOf(chat)
  const master = msgs.find((m) => st.pinned[m.id] && st.important[m.id]) ?? msgs.find((m) => st.pinned[m.id])
  return (
    <div className="flex flex-col min-h-0 h-full">
      {master && (
        <div className="m-8 p-10 rounded-[8px] flex flex-col gap-4" style={{ background: 'var(--aq-accent-soft)' }}>
          <span className="aq-label flex items-center gap-6 aq-accent"><Pin size={11} />{t('master message')} · {master.at}{st.important[master.id] && <Flag size={10} style={{ color: 'var(--aq-important)' }} />}</span>
          <span className="text-13 leading-snug" style={{ color: 'var(--aq-ink)' }}>{master.text}</span>
        </div>
      )}
      <div className="flex-1 min-h-0 aq-scroll"><Pins project={sessionOf(chat)!.project} onNote={onNote} onJump={(m) => onJump?.(m.session)} /></div>
    </div>
  )
}

export function Inspector({ chat, tab, setTab, note, onNote, onChat, branches }: {
  chat: string; tab: InspTab; setTab: (t: InspTab) => void; note: string; onNote: (id: string) => void; onChat: (id: string) => void
  /** Another picture of the branches (J: F's lineage tree). */
  branches?: ReactNode
}) {
  const TABS: Array<[InspTab, string, typeof Pin]> = [['messages', t('Messages'), MessageSquare], ['pins', t('Pins'), Pin], ['branches', t('Branches'), GitBranch], ['note', t('Note'), FileText], ['stats', t('Stats'), Activity]]
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-[30px] shrink-0 flex items-center gap-1 px-4" role="tablist" aria-label={t('Inspector')} style={{ borderBottom: '1px solid var(--aq-line)' }}>
        {TABS.map(([k, w, Icon]) => (
          <button key={k} type="button" data-nodrag role="tab" aria-selected={tab === k} aria-label={w} title={w} className="aq-btn" data-on={tab === k} onClick={() => setTab(k)}>
            <Icon size={12} />{tab === k && w}</button>
        ))}
      </div>
      <div className="flex-1 min-h-0 flex flex-col">
        {tab === 'messages' && <Messages sessionId={chat} onNote={onNote} onJump={(m) => onChat(m.session)} dense />}
        {tab === 'pins' && <PinsMaster chat={chat} onNote={onNote} onJump={onChat} />}
        {tab === 'branches' && (branches ? <div className="flex-1 min-h-0 aq-scroll p-8">{branches}</div> : <Branches sessionId={chat} onChat={onChat} />)}
        {tab === 'note' && <div className="flex-1 aq-scroll p-14 flex flex-col gap-8"><NoteMeta id={note} /><NoteBody id={note} size={13} /></div>}
        {tab === 'stats' && <div className="aq-scroll"><Stats compact /></div>}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------- group menu */

const HUE_CHOICES = [330, 45, 280, 170, 100, 20]

/** A group's menu: its name, its colour, ungroup (and where the chats go), detach. */
export function GroupMenu({ ws, onClose, className = '' }: { ws: string; onClose: () => void; className?: string }) {
  const paint = usePaint()
  const d = useDesk()
  const st = useAqua()
  const w = wsById(d, ws)
  const [name, setName] = useState(w?.name ?? '')
  if (!w) return null
  const back = Array.from(new Set(chatsIn(d, ws).map((s) => projectOf(s.project).name)))
  return (
    <div className={`aq-glass aq-float rounded-[10px] p-10 flex flex-col gap-8 w-[280px] aq-fade ${className}`} role="dialog" aria-label={`${t('Group')} ${w.name}`} data-nodrag>
      <div className="flex items-center gap-6"><b className="text-12">{t('Group')}</b><button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={12} /></button></div>
      <input value={name} onChange={(e) => setName(e.target.value)} onBlur={() => rename(ws, name)} onKeyDown={(e) => { if (e.key === 'Enter') { rename(ws, name); onClose() } }}
        aria-label={t('Name')} className="h-[26px] px-8 rounded-[6px] text-12 outline-none" style={{ background: 'var(--aq-raise)', border: '1px solid var(--aq-line)', color: 'var(--aq-ink)' }} />
      <div className="flex gap-6" role="radiogroup" aria-label={t('Colour')}>
        {HUE_CHOICES.map((h) => (
          <button key={h} type="button" role="radio" aria-checked={w.hue === h} aria-label={`${t('Colour')} ${h}`} onClick={() => recolour(ws, h)}
            className="w-[18px] h-[18px] rounded-full" style={{ background: paint.ink(h), outline: w.hue === h ? '2px solid var(--aq-ink)' : undefined, outlineOffset: 2 }} />
        ))}
      </div>
      <button type="button" className="aq-btn line justify-start" onClick={() => { detachWin('ws', ws); onClose() }}><ExternalLink size={12} />{t('Detach the workspace')}</button>
      <button type="button" className="aq-btn line justify-start" onClick={() => { sleepWorkspace(st, d, ws, !wsAsleep(st, d, ws)); onClose() }}>{wsAsleep(st, d, ws) ? <><Sun size={12} />{t('Wake the workspace')}</> : <><Moon size={12} />{t('Sleep the workspace')}</>}</button>
      <button type="button" className="aq-btn line justify-start" onClick={() => { ungroup(ws); flash(`${t('Ungrouped: the chats are back in')} ${back.join(', ')}`); onClose() }}>{t('Ungroup')} · {t('back to')} {back.join(', ')}</button>
    </div>
  )
}

/** Make a group of these chats and say so. */
export function makeGroup(chats: string[], name?: string) {
  const id = group(chats, name)
  flash(`${t('New workspace with')} ${chats.map((c) => sessionOf(c)!.name).join(', ')}`)
  return id
}

export { MESSAGES, MessageRow, wsHue }
