/**
 * E · Tide — the minimal one, for the tmux purist. "Night swim": one
 * terminal, full bleed, near-black teal; glass only on the palette.
 *
 * Over the terminal, the tide line: every chat of every project as a dot,
 * grouped by project; amber pulses when a chat waits, a hollow dot sleeps.
 * One key jumps to the next waiting chat. Panels never float over the
 * output: the left one (projects and servers) and the right one (messages,
 * pins, branches, the note, the editor, stats) push the terminal aside.
 * At the foot, a tmux-like status line with the chats as windows.
 */

import { useState } from 'react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { PROJECTS, projectOf, sessionOf, sessionsIn, serversIn, type Message } from '../mock'
import {
  Branches, Editor, Keymap, MESSAGE_KEYS, Messages, NoteBody, NoteMeta, Palette, Pins, Restore, ServerLog, Servers, StateDot, Stats,
  commonActions, nextWaiting, projectInk, sessionsWaiting, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { detach, focus, projectAsleep, setProjectAsleep, toggleSleep, useAqua } from '../store'
import { Screen } from '../term'
import type { Theme } from '../AquaDesign'

type Right = 'messages' | 'pins' | 'branches' | 'note' | 'editor' | 'stats'

export function Tide({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const active = sessionOf(st.active)!
  const [left, setLeft] = useState(false)
  const [right, setRight] = useState<Right | null>(null)
  const [note, setNote] = useState('nt_7d21c0aa')
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [hints, setHints] = useState(false)
  const [server, setServer] = useState<string | null>(null)
  const [peek, setPeek] = useState<string | null>(null)

  const go = (id: string) => focus(id)
  const openNote = (id: string) => { setNote(id); setRight('note') }
  const jump = (m: Message) => go(m.session)
  const toggleRight = (r: Right) => setRight(right === r ? null : r)
  const here = sessionsIn(active.project)
  const actions: Action[] = [
    { id: 'left', group: t('panel'), label: t('Projects and servers'), kbd: 'alt+1', run: () => setLeft((l) => !l) },
    { id: 'msg', group: t('panel'), label: t('Messages'), kbd: 'alt+2', run: () => toggleRight('messages') },
    { id: 'pins', group: t('panel'), label: t('Pins'), kbd: 'alt+3', run: () => toggleRight('pins') },
    { id: 'br', group: t('panel'), label: t('Branches'), kbd: 'alt+4', run: () => toggleRight('branches') },
    { id: 'ed', group: t('panel'), label: t('Editor'), kbd: 'alt+5', run: () => toggleRight('editor') },
    { id: 'st', group: t('panel'), label: t('Stats'), kbd: 'alt+6', run: () => toggleRight('stats') },
    { id: 'hints', group: t('copy'), label: t('Hints: copy an id or a path'), kbd: 'alt+H', run: () => setHints(true) },
    ...PROJECTS.map((p) => ({ id: `sl-${p.code}`, group: t('project'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    ...commonActions(go, { note: openNote, server: (id) => { setLeft(true); setServer(id) } }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    'alt+n': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+1': () => setLeft((l) => !l), 'alt+2': () => toggleRight('messages'), 'alt+3': () => toggleRight('pins'), 'alt+4': () => toggleRight('branches'), 'alt+5': () => toggleRight('editor'), 'alt+6': () => toggleRight('stats'),
    'alt+h': () => setHints((h) => !h),
    'alt+s': () => toggleSleep(active.id),
    'alt+ArrowRight': () => { const i = here.findIndex((s) => s.id === active.id); go(here[(i + 1) % here.length]!.id) },
    'alt+ArrowLeft': () => { const i = here.findIndex((s) => s.id === active.id); go(here[(i - 1 + here.length) % here.length]!.id) },
    '?': () => setKeys(true),
    Escape: () => { setPalette(false); setKeys(false); setHints(false); setPeek(null) },
  })

  const waiting = sessionsWaiting(st)
  const peekS = peek ? sessionOf(peek) : null
  const RIGHTS: Array<[Right, string, string]> = [['messages', t('messages'), '2'], ['pins', t('pins'), '3'], ['branches', t('branches'), '4'], ['note', t('note'), ''], ['editor', t('editor'), '5'], ['stats', t('stats'), '6']]

  return (
    <div className="absolute inset-0 flex flex-col" style={{ background: 'var(--aq-term-bg)' }}>
      {/* the tide line */}
      <div className="h-[40px] shrink-0 flex items-center gap-20 px-14 relative" role="toolbar" aria-label={t('Tide line: every chat')}
        style={{ background: 'var(--aq-tide)', borderBottom: '1px solid var(--aq-glass-line)', boxShadow: '0 1px 0 oklch(0.85 0.1 200 / 0.08), 0 8px 20px oklch(0 0 0 / 0.35)' }}>
        {PROJECTS.map((p) => (
          <div key={p.code} className="flex items-center gap-6" style={{ opacity: projectAsleep(st, p.code) ? 0.45 : 1 }}>
            <button type="button" className="text-11 font-mono font-semibold" style={{ color: projectInk(p.code) }} onClick={() => go((sessionsIn(p.code).find((s) => !st.asleep[s.id]) ?? sessionsIn(p.code)[0]!).id)}>{p.code}</button>
            {sessionsIn(p.code).map((s) => (
              <button key={s.id} type="button" className="p-2 rounded-full" aria-label={`${s.name}, ${STATE_WORD[shownState(st, s)]}`} aria-current={s.id === active.id}
                onMouseEnter={() => setPeek(s.id)} onMouseLeave={() => setPeek(null)} onFocus={() => setPeek(s.id)} onBlur={() => setPeek(null)} onClick={() => go(s.id)}
                style={{ outline: s.id === active.id ? '1.5px solid var(--aq-accent)' : undefined, outlineOffset: 1 }}>
                <StateDot s={s} st={st} size={12} />
              </button>
            ))}
          </div>
        ))}
        <span className="text-12 font-medium truncate min-w-0" style={{ color: 'var(--aq-ink)' }}>{projectOf(active.project).name} › {active.name}</span>
        <span className="ml-auto text-11 font-mono shrink-0" style={{ color: waiting.length ? 'var(--aq-wait)' : 'var(--aq-ink3)' }}>
          {waiting.length ? `${tn(waiting.length, '{n} waits', '{n} wait')} · alt+N` : t('nobody waits')}</span>
        {peekS && (
          <div className="absolute top-[44px] z-[25] w-[480px] h-[220px] rounded-[10px] overflow-hidden aq-fade aq-float pointer-events-none" style={{ left: 120 }}>
            <div className="h-[22px] flex items-center gap-6 px-8 aq-glass text-11" style={{ borderWidth: 0 }}><StateDot s={peekS} st={st} />{projectOf(peekS.project).name} › {peekS.name}</div>
            <Screen session={peekS} asleep={st.asleep[peekS.id]} size={10} tail={5} focused={false} />
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 flex">
        {left && (
          <aside className="w-[280px] shrink-0 flex flex-col aq-slide-r aq-scroll" style={{ background: 'var(--aq-panel)', borderRight: '1px solid var(--aq-line)' }} aria-label={t('Projects and servers')}>
            {PROJECTS.map((p) => {
              const asleep = projectAsleep(st, p.code)
              return (
                <section key={p.code} className="p-8 flex flex-col gap-2" style={{ borderBottom: '1px solid var(--aq-line)' }}>
                  <div className="flex items-center gap-6 h-[24px]">
                    <span className="aq-dot" style={{ background: projectInk(p.code) }} /><b className="text-12">{p.name}</b>
                    <button type="button" className="aq-btn ml-auto" onClick={() => setProjectAsleep(p.code, !asleep)}>{asleep ? t('wake all') : t('sleep all')}</button>
                  </div>
                  {sessionsIn(p.code).map((s) => (
                    <div key={s.id} className="aq-row h-[24px] px-6 text-12" aria-current={s.id === active.id} role="button" tabIndex={0} onClick={() => go(s.id)} onKeyDown={(e) => { if (e.key === 'Enter') go(s.id) }}>
                      <StateDot s={s} st={st} /><span className="truncate flex-1">{s.name}</span>
                      <button type="button" className="text-10 font-mono aq-ink3 hover:underline" onClick={(e) => { e.stopPropagation(); toggleSleep(s.id) }}>{st.asleep[s.id] ? t('wake') : t('sleep')}</button>
                    </div>
                  ))}
                  {serversIn(p.code).length > 0 && <div className="pt-4"><Servers project={p.code} compact onOpen={setServer} /></div>}
                </section>
              )
            })}
          </aside>
        )}

        <main className="flex-1 min-w-0 flex flex-col">
          <div className="flex-1 min-h-0">
            <Screen session={active} asleep={st.asleep[active.id]} size={14} hints={hints} onHintsDone={() => setHints(false)} onNote={openNote} />
          </div>
          {server && left && (
            <div className="h-[34%] shrink-0" style={{ borderTop: '1px solid var(--aq-line)' }}>
              <ServerLog id={server} />
            </div>
          )}
        </main>

        {right && (
          <aside className={`${right === 'note' || right === 'editor' ? 'w-[46%]' : 'w-[380px]'} shrink-0 flex flex-col aq-slide-r`} style={{ background: 'var(--aq-panel)', borderLeft: '1px solid var(--aq-line)' }} aria-label={t('Panel')}>
            <div className="flex-1 min-h-0 flex flex-col">
              {right === 'messages' && <Messages sessionId={active.id} onNote={openNote} onJump={jump} />}
              {right === 'pins' && <Pins onJump={jump} onNote={openNote} />}
              {right === 'branches' && <Branches sessionId={active.id} onChat={go} />}
              {right === 'note' && <div className="flex-1 aq-scroll px-24 py-20 flex flex-col gap-10"><div className="flex items-center"><NoteMeta id={note} /><button type="button" className="aq-btn ml-auto" onClick={() => detach(`note:${note}`)}>{t('detach')}</button></div><NoteBody id={note} /></div>}
              {right === 'editor' && <Editor size={14} />}
              {right === 'stats' && <div className="aq-scroll"><Stats compact /></div>}
            </div>
          </aside>
        )}
      </div>

      {/* tmux-like status line */}
      <footer className="h-[24px] shrink-0 flex items-center font-mono text-11 select-none" style={{ background: 'var(--aq-panel)', borderTop: '1px solid var(--aq-line)' }}>
        <button type="button" className="h-full px-10 font-semibold" style={{ background: projectInk(active.project), color: 'oklch(0.15 0.02 220)' }} onClick={() => setLeft((l) => !l)} title={t('Projects and servers (alt+1)')}>{active.project}</button>
        <div className="flex items-center min-w-0 overflow-hidden" role="tablist" aria-label={t('Chats of the project')}>
          {here.map((s, i) => (
            <button key={s.id} type="button" role="tab" aria-selected={s.id === active.id} onClick={() => go(s.id)} className="h-full px-8 whitespace-nowrap"
              style={{ color: s.id === active.id ? 'var(--aq-ink)' : st.asleep[s.id] ? 'var(--aq-ink3)' : s.state === 'waiting' ? 'var(--aq-wait)' : 'var(--aq-ink2)', background: s.id === active.id ? 'var(--aq-hover)' : undefined }}>
              {i + 1}:{s.name.length > 18 ? `${s.name.slice(0, 17)}…` : s.name}<span style={{ color: 'var(--aq-accent)' }}>{s.id === active.id ? '*' : st.asleep[s.id] ? ' z' : s.state === 'waiting' ? ' !' : ''}</span>
            </button>
          ))}
        </div>
        <span className="ml-auto flex items-center gap-8 px-10 aq-ink3 shrink-0">
          {RIGHTS.filter(([, , k]) => k).map(([r, w, k]) => (
            <button key={r} type="button" aria-pressed={right === r} onClick={() => toggleRight(r)} style={{ color: right === r ? 'var(--aq-accent)' : undefined }}>⌥{k} {w}</button>
          ))}
          <button type="button" onClick={() => detach(`term:${active.id}`)}>{t('detach')}</button>
          <button type="button" onClick={() => setPalette(true)}>^K</button>
          <button type="button" onClick={() => setKeys(true)}>?</button>
          <span>{t('you')} 2:09 · {t('agents')} 5:12</span>
        </span>
      </footer>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={actions} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('command palette')], ['alt N', t('next chat waiting on you')], ['alt ← →', t('chats of the project')], ['alt 1', t('projects and servers')],
        ['alt 2', t('messages')], ['alt 3', t('pins')], ['alt 4', t('branches')], ['alt 5', t('editor')], ['alt 6', t('stats')], ['alt H', t('hints: copy an id or a path')],
        ['alt S', t('sleep / wake the chat')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
