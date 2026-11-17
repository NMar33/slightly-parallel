/**
 * D · Mosaic — every live chat at once. "Pools": a charcoal wall, each
 * project a pool tinted with its hue (a hue no state uses), every tile an
 * opaque terminal.
 *
 * The working and waiting chats are tiles; idle and sleeping ones are
 * strips at the foot of their pool, so the wall stays readable at fifteen
 * chats. A click focuses a tile and it grows in place (the others keep
 * their places); Enter or the button zooms it to the whole wall, where
 * the drawer for messages, pins, branches and the note opens beside it.
 * Arrow keys walk the tiles; the server tray at the bottom holds every
 * server with its light.
 */

import { useState } from 'react'
import {
  Activity, ExternalLink, FileText, GitBranch, Keyboard, Maximize2, MessageSquare, Minimize2, Moon, Pin, Radio, Search, Sun, Type, X,
} from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { PROJECTS, SERVERS, SESSIONS, projectOf, sessionOf, sessionsIn, type Message, type Session } from '../mock'
import {
  Branches, Editor, Keymap, Kbd, MESSAGE_KEYS, Messages, NoteBody, NoteMeta, Palette, Pins, Restore, ServerLog, StateDot, Stats,
  commonActions, nextWaiting, projectInk, projectTint, sessionsWaiting, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { detach, focus, projectAsleep, setProjectAsleep, toggleServer, toggleSleep, useAqua, type AquaState } from '../store'
import { Screen, fmtTokens } from '../term'
import type { Theme } from '../AquaDesign'

type Drawer = 'messages' | 'pins' | 'branches' | 'note' | 'editor' | 'stats'
const live = (st: AquaState, s: Session) => !st.asleep[s.id] && s.state !== 'idle'

export function Mosaic({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const [zoom, setZoom] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<Drawer | null>(null)
  const [note, setNote] = useState('nt_7d21c0aa')
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [server, setServer] = useState<string | null>(null)
  const [broadcast, setBroadcast] = useState<string | null>(null)
  const order = SESSIONS.filter((s) => live(st, s))

  const go = (id: string) => { focus(id) }
  const openNote = (id: string) => { setNote(id); setDrawer('note'); if (!zoom) setZoom(st.active) }
  const walk = (d: number) => {
    const i = order.findIndex((s) => s.id === st.active)
    const n = order[(i + d + order.length) % order.length]
    if (n) go(n.id)
  }
  const jump = (m: Message) => { go(m.session); setZoom(m.session) }

  const actions: Action[] = [
    { id: 'zoom', group: t('tile'), label: t('Zoom the focused tile'), kbd: '⏎', run: () => setZoom(zoom ? null : st.active) },
    { id: 'stats', group: t('view'), label: t('Stats'), run: () => setDrawer('stats') },
    { id: 'editor', group: t('view'), label: t('Open the editor'), run: () => { setZoom(st.active); setDrawer('editor') } },
    ...PROJECTS.map((p) => ({ id: `sl-${p.code}`, group: t('pool'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    ...commonActions((id) => { go(id); setZoom(id) }, { note: openNote, server: setServer }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    ArrowRight: () => walk(1), ArrowLeft: () => walk(-1), ArrowDown: () => walk(2), ArrowUp: () => walk(-2),
    Enter: () => setZoom(zoom ? null : st.active),
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+m': () => { setZoom(zoom ?? st.active); setDrawer(drawer ? null : 'messages') },
    'alt+s': () => toggleSleep(st.active),
    '?': () => setKeys(true),
    Escape: () => { if (palette || keys) { setPalette(false); setKeys(false) } else if (drawer) setDrawer(null); else setZoom(null); setServer(null) },
  })

  const zoomed = zoom ? sessionOf(zoom)! : null
  const DRAWERS: Array<[Drawer, string, typeof Pin]> = [['messages', t('Messages'), MessageSquare], ['pins', t('Pins'), Pin], ['branches', t('Branches'), GitBranch], ['note', t('Note'), FileText], ['editor', t('Editor'), Type], ['stats', t('Stats'), Activity]]
  const waiting = sessionsWaiting(st)

  const tile = (s: Session, big: boolean) => {
    const on = s.id === st.active
    const k = shownState(st, s)
    return (
      <section key={s.id} aria-label={s.name} onClick={() => go(s.id)} onDoubleClick={() => setZoom(s.id)}
        className="flex flex-col min-h-0 min-w-0 overflow-hidden rounded-[8px] transition-[box-shadow,transform] duration-150"
        style={{
          gridColumn: big ? 'span 2' : undefined, gridRow: big ? 'span 2' : undefined,
          boxShadow: on ? `0 0 0 2px var(--aq-accent), 0 10px 30px oklch(0 0 0 / 0.45)` : k === 'waiting' ? 'inset 3px 0 0 var(--aq-wait), 0 0 0 1px var(--aq-line)' : '0 0 0 1px var(--aq-line)',
        }}>
        <div className="h-[26px] shrink-0 flex items-center gap-6 px-8" style={{ background: projectTint(s.project, on ? 0.28 : 0.14) }}>
          <StateDot s={s} st={st} />
          <span className="text-12 truncate font-medium" style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
          {s.tool === 'codex' && <span className="aq-chip">cx</span>}
          <span className="text-10 font-mono aq-ink3 ml-auto shrink-0">{STATE_WORD[k]} · {s.ctx}%</span>
          {broadcast === s.project && <Radio size={11} style={{ color: 'var(--aq-wait)' }} aria-label={t('broadcast')} />}
          <button type="button" className="aq-btn icon" aria-label={t('Zoom')} title={t('Zoom (Enter)')} onClick={(e) => { e.stopPropagation(); setZoom(s.id) }}><Maximize2 size={11} /></button>
        </div>
        <div className="flex-1 min-h-0"><Screen session={s} size={big ? 12 : 11} tail={big ? undefined : 7} focused={on} onNote={(id) => { go(s.id); openNote(id) }} /></div>
      </section>
    )
  }

  return (
    <div className="absolute inset-0 flex flex-col" style={{ background: 'var(--aq-bg)' }}>
      <header className="h-[36px] shrink-0 flex items-center gap-12 px-12" style={{ borderBottom: '1px solid var(--aq-line)' }}>
        <b className="text-13 tracking-tight">SP Aqua <span className="aq-ink3 font-regular">mosaic</span></b>
        <span className="text-11 aq-ink3 font-mono">{tn(order.length, '{n} tile', '{n} tiles')} · {tn(SESSIONS.length - order.length, '{n} strip', '{n} strips')}</span>
        {waiting.length > 0 && <button type="button" className="aq-btn" style={{ color: 'var(--aq-wait)' }} onClick={() => go(nextWaiting(st, st.active)!)}><span className="aq-dot waiting" />{tn(waiting.length, '{n} waits for you', '{n} wait for you')}</button>}
        <button type="button" className="aq-btn line ml-auto w-[280px] justify-start aq-ink3" onClick={() => setPalette(true)}><Search size={12} />{t('Go to any tile')}<span className="ml-auto"><Kbd>Ctrl K</Kbd></span></button>
        <span className="text-11 font-mono aq-ink3">{t('you')} 2:09 · {t('agents')} 5:12 · {fmtTokens(SESSIONS.reduce((a, s) => a + s.tokens, 0))}</span>
        <button type="button" className="aq-btn icon" aria-label={t('Stats')} onClick={() => { setZoom(zoom ?? st.active); setDrawer('stats') }}><Activity size={14} /></button>
        <button type="button" className="aq-btn icon" aria-label={t('Keys')} onClick={() => setKeys(true)}><Keyboard size={14} /></button>
      </header>

      <div className="flex-1 min-h-0 relative">
        {/* the wall */}
        {!zoomed && (
          <div className="absolute inset-0 p-10 flex gap-10 aq-fade overflow-x-auto aq-scroll">
            {PROJECTS.map((p) => {
              const ss = sessionsIn(p.code)
              const tiles = ss.filter((s) => live(st, s))
              const strips = ss.filter((s) => !live(st, s))
              const asleep = projectAsleep(st, p.code)
              const grow = tiles.some((s) => s.id === st.active) && tiles.length > 1
              const cols = tiles.length > 3 ? 2 : 1
              if (asleep) {
                // a sleeping pool is a narrow strip: its name on its side, and wake
                return (
                  <div key={p.code} className="shrink-0 w-[44px] flex flex-col items-center gap-10 py-10 rounded-[12px] aq-glass" style={{ borderColor: projectTint(p.code, 0.3) }}>
                    <button type="button" className="aq-btn icon" aria-label={`${t('Wake')} ${p.name}`} title={t('Wake the project: its chats and servers')} onClick={() => setProjectAsleep(p.code, false)}><Sun size={13} /></button>
                    <span className="text-12 font-semibold aq-ink2 whitespace-nowrap" style={{ writingMode: 'vertical-rl' }}>{p.name} · {t('asleep')}</span>
                  </div>
                )
              }
              return (
                <div key={p.code} className="flex flex-col min-w-0 rounded-[12px] p-6 gap-6"
                  style={{ flex: `${Math.max(1.5, tiles.length)} 1 0`, minWidth: 440, background: projectTint(p.code, 0.09), border: `1px solid ${projectTint(p.code, 0.3)}`, backdropFilter: 'blur(10px)' }}>
                  <div className="h-[24px] shrink-0 flex items-center gap-6 px-4">
                    <span className="aq-dot" style={{ background: projectInk(p.code) }} />
                    <b className="text-12 truncate">{p.name}</b>
                    <span className="text-10 font-mono aq-ink3">{p.branch}</span>
                    <button type="button" className="aq-btn icon ml-auto" aria-pressed={broadcast === p.code} title={t('Broadcast: what you type goes to every tile of the pool')} aria-label={t('Broadcast')}
                      onClick={() => setBroadcast(broadcast === p.code ? null : p.code)}><Radio size={12} /></button>
                    <button type="button" className="aq-btn icon" aria-label={`${asleep ? t('Wake') : t('Sleep')} ${p.name}`} title={asleep ? t('Wake the project: its chats and servers') : t('Put the project to sleep: its chats and servers')}
                      onClick={() => setProjectAsleep(p.code, !asleep)}>{asleep ? <Sun size={12} /> : <Moon size={12} />}</button>
                  </div>
                  {tiles.length > 0 && (
                    <div className="flex-1 min-h-0 grid gap-6" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: 'minmax(0, 1fr)' }}>
                      {tiles.map((s) => tile(s, grow && cols === 2 && s.id === st.active))}
                    </div>
                  )}
                  {!tiles.length && <div className="flex-1 flex items-center justify-center text-12 aq-ink3">{asleep ? t('asleep') : t('nothing working')}</div>}
                  <ul className="m-0 p-0 list-none flex flex-col gap-2 shrink-0">
                    {strips.map((s) => (
                      <li key={s.id}>
                        <div className="aq-row h-[24px] px-6 text-11" role="button" tabIndex={0} onClick={() => toggleSleep(s.id)} title={st.asleep[s.id] ? t('Wake') : t('Sleep')}
                          onKeyDown={(e) => { if (e.key === 'Enter') toggleSleep(s.id) }} style={{ background: 'var(--aq-panel)' }}>
                          <StateDot s={s} st={st} /><span className="truncate flex-1">{s.name}</span>
                          <span className="font-mono text-10 aq-ink3">{st.asleep[s.id] ? (s.gone ? t('id gone') : t('wake')) : t('idle')}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        )}

        {/* zoomed: one tile, the drawer beside it */}
        {zoomed && (
          <div className="absolute inset-0 p-10 flex gap-10 aq-fade">
            <section className="flex-1 min-w-0 flex flex-col rounded-[10px] overflow-hidden" style={{ boxShadow: '0 0 0 1px var(--aq-line)' }} aria-label={zoomed.name}>
              <div className="h-[30px] shrink-0 flex items-center gap-8 px-10" style={{ background: projectTint(zoomed.project, 0.22) }}>
                <StateDot s={zoomed} st={st} /><b className="text-12">{zoomed.name}</b><span className="text-11 aq-ink3">{projectOf(zoomed.project).name} · {zoomed.model}</span>
                <span className="ml-auto flex items-center gap-2" role="tablist" aria-label={t('Drawer')}>
                  {DRAWERS.map(([k, w, Icon]) => <button key={k} type="button" role="tab" aria-selected={drawer === k} className="aq-btn" data-on={drawer === k} onClick={() => setDrawer(drawer === k ? null : k)}><Icon size={12} />{w}</button>)}
                </span>
                <button type="button" className="aq-btn icon" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`term:${zoomed.id}`)}><ExternalLink size={12} /></button>
                <button type="button" className="aq-btn" onClick={() => { setZoom(null); setDrawer(null) }}><Minimize2 size={12} />{t('Back to the wall')} <Kbd>Esc</Kbd></button>
              </div>
              <div className="flex-1 min-h-0 flex">
                <div className="flex-1 min-w-0"><Screen session={zoomed} asleep={st.asleep[zoomed.id]} onNote={openNote} /></div>
                {drawer && (
                  <aside className={`${drawer === 'note' || drawer === 'editor' ? 'w-[46%]' : 'w-[380px]'} shrink-0 flex flex-col aq-slide-r`} style={{ background: 'var(--aq-panel)', borderLeft: '1px solid var(--aq-line)' }} aria-label={t('Drawer')}>
                    <div className="flex items-center px-8 h-[28px] shrink-0" style={{ borderBottom: '1px solid var(--aq-line)' }}>
                      <span className="aq-label">{DRAWERS.find(([k]) => k === drawer)![1]}</span>
                      <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => setDrawer(null)}><X size={12} /></button>
                    </div>
                    <div className="flex-1 min-h-0 flex flex-col">
                      {drawer === 'messages' && <Messages sessionId={zoomed.id} onNote={openNote} onJump={jump} />}
                      {drawer === 'pins' && <Pins onJump={jump} onNote={openNote} />}
                      {drawer === 'branches' && <Branches sessionId={zoomed.id} onChat={(id) => { go(id); setZoom(id) }} />}
                      {drawer === 'note' && <div className="flex-1 aq-scroll p-20 flex flex-col gap-10"><div className="flex items-center"><NoteMeta id={note} /><button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} onClick={() => detach(`note:${note}`)}><ExternalLink size={12} /></button></div><NoteBody id={note} /></div>}
                      {drawer === 'editor' && <Editor />}
                      {drawer === 'stats' && <div className="aq-scroll"><Stats compact /></div>}
                    </div>
                  </aside>
                )}
              </div>
            </section>
          </div>
        )}

        {server && (
          <div className="absolute left-1/2 -translate-x-1/2 bottom-8 w-[760px] h-[300px] z-[15] rounded-[10px] overflow-hidden shadow-lg aq-fade" style={{ boxShadow: '0 0 0 1px var(--aq-line), 0 20px 50px oklch(0 0 0 / 0.5)' }}>
            <div className="absolute right-6 top-4 z-[1] flex gap-2">
              <button type="button" className="aq-btn icon" aria-label={t('Detach')} onClick={() => { detach(`server:${server}`); setServer(null) }}><ExternalLink size={12} /></button>
              <button type="button" className="aq-btn icon" aria-label={t('Close')} onClick={() => setServer(null)}><X size={12} /></button>
            </div>
            <ServerLog id={server} />
          </div>
        )}
      </div>

      {/* the server tray */}
      <footer className="h-[34px] shrink-0 flex items-center gap-6 px-10" style={{ borderTop: '1px solid var(--aq-line)', background: 'var(--aq-panel)' }} aria-label={t('Servers')}>
        <span className="aq-label mr-4">{t('servers')}</span>
        {SERVERS.map((s) => (
          <span key={s.id} className="inline-flex items-center rounded-[6px]" style={{ background: projectTint(s.project, 0.12) }}>
            <button type="button" className="h-[24px] px-8 inline-flex items-center gap-6 text-11" onClick={() => setServer(server === s.id ? null : s.id)} aria-pressed={server === s.id}>
              <span className={`aq-dot ${st.up[s.id] ? 'up' : 'down'}`} /><span style={{ color: 'var(--aq-ink)' }}>{s.name}</span>{s.port && <span className="font-mono aq-ink3">:{s.port}</span>}
            </button>
            <button type="button" className="aq-btn icon" aria-label={`${st.up[s.id] ? t('Stop') : t('Start')} ${s.name}`} onClick={() => toggleServer(s.id)}>{st.up[s.id] ? '■' : '▶'}</button>
          </span>
        ))}
        <span className="ml-auto text-10 font-mono aq-ink3">← → ↑ ↓ {t('walk')} · ⏎ {t('zoom')} · alt+M {t('messages')} · ? {t('keys')}</span>
      </footer>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={actions} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('go to any tile')], ['← →', t('walk the tiles')], ['⏎', t('zoom the focused tile')], ['Esc', t('back to the wall')], ['alt M', t('messages drawer')],
        ['alt W', t('next chat waiting on you')], ['alt S', t('sleep / wake the focused chat')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
