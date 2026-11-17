/**
 * A · Rail — the dense, keyboard-first one. "Deep water": matte panels,
 * one teal accent, glass only on the palette and overlays.
 *
 * Left, the projects as a tree: each project's agent chats, then its
 * servers apart. Middle, the chats of the project as tabs, a split for a
 * second pane (another chat, a server's log, the editor), zoom, find and
 * hints. Right, the inspector: Messages, Pins, Branches, Note, Stats —
 * shut with one key when the terminal wants the width. At the foot, the
 * keys, as Zellij shows them.
 */

import { useState } from 'react'
import {
  Activity, ChevronDown, ChevronRight, Columns2, Command, ExternalLink, FileText, GitBranch, Keyboard, Maximize2, MessageSquare,
  Moon, PanelRight, Pin, Plus, Search, Sun, Type, X,
} from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { PROJECTS, SERVERS, SESSIONS, messagesOf, projectOf, serverOf, sessionOf, sessionsIn, serversIn, type Message } from '../mock'
import {
  Branches, Editor, Keymap, Kbd, MESSAGE_KEYS, Messages, NoteBody, NoteMeta, Palette, Pins, ProjectSwatch, Restore, ServerLog, StateDot,
  Stats, ToolBadge, WindowControls, commonActions, nextWaiting, sessionsWaiting, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { detach, focus, projectAsleep, restoreAll, setProjectAsleep, toggleServer, toggleSleep, useAqua } from '../store'
import { Screen, fmtTokens } from '../term'
import type { Theme } from '../AquaDesign'

type Insp = 'messages' | 'pins' | 'branches' | 'note' | 'stats'
type Pane = { kind: 'term'; id: string } | { kind: 'server'; id: string } | { kind: 'editor' }

export function Rail({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const active = sessionOf(st.active)!
  const project = active.project
  const [insp, setInsp] = useState<Insp | null>('messages')
  const [note, setNote] = useState('nt_7d21c0aa')
  const [split, setSplit] = useState<Pane | null>(null)
  const [zoom, setZoom] = useState(false)
  const [find, setFind] = useState<string | null>(null)
  const [hints, setHints] = useState(false)
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [folded, setFolded] = useState<Record<string, boolean>>({ otter: true })
  const [size, setSize] = useState(13)
  const [center, setCenter] = useState<'term' | 'editor'>('term')

  const openNote = (id: string) => { setNote(id); setInsp('note') }
  const go = (id: string) => { focus(id); setCenter('term') }
  const tabs = sessionsIn(project)
  const walk = (d: number) => {
    const all = SESSIONS.filter((s) => !st.asleep[s.id])
    const i = all.findIndex((s) => s.id === st.active)
    go(all[(i + d + all.length) % all.length]!.id)
  }
  const jump = (m: Message) => { go(m.session); setFind(m.text.split(' ').slice(0, 3).join(' ')) }

  const actions: Action[] = [
    { id: 'split', group: t('pane'), label: t('Split right'), kbd: 'alt+\\', run: () => setSplit(split ? null : { kind: 'server', id: serversIn(project)[0]?.id ?? 'ew_h1' }) },
    { id: 'zoom', group: t('pane'), label: t('Zoom the pane'), kbd: 'alt+Z', run: () => setZoom((z) => !z) },
    { id: 'insp', group: t('view'), label: t('Show or hide the inspector'), kbd: 'alt+I', run: () => setInsp(insp ? null : 'messages') },
    { id: 'edit', group: t('view'), label: t('Open the editor'), kbd: 'alt+E', run: () => setCenter('editor') },
    { id: 'hints', group: t('copy'), label: t('Hints: copy an id or a path'), kbd: 'alt+H', run: () => setHints(true) },
    { id: 'wait', group: t('chat'), label: t('Next chat waiting on you'), kbd: 'alt+W', run: () => { const n = nextWaiting(st, st.active); if (n) go(n) } },
    { id: 'sleep', group: t('chat'), label: `${t('Sleep or wake')} ${active.name}`, kbd: 'alt+S', run: () => toggleSleep(active.id) },
    ...PROJECTS.map((p) => ({ id: `ps-${p.code}`, group: t('project'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    { id: 'restore', group: t('app'), label: t('Restore all'), run: () => restoreAll() },
    { id: 'detach', group: t('pane'), label: `${t('Detach')} ${active.name}`, run: () => detach(`term:${active.id}`) },
    ...commonActions(go, { note: openNote, server: (id) => setSplit({ kind: 'server', id }) }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    'mod+f': () => setFind(find === null ? '' : null),
    'alt+h': () => setHints((h) => !h),
    'alt+\\': () => setSplit(split ? null : { kind: 'server', id: serversIn(project)[0]?.id ?? 'ew_h1' }),
    'alt+z': () => setZoom((z) => !z),
    'alt+i': () => setInsp(insp ? null : 'messages'),
    'alt+e': () => setCenter(center === 'editor' ? 'term' : 'editor'),
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+s': () => toggleSleep(active.id),
    'alt+j': () => walk(1),
    'alt+k': () => walk(-1),
    'alt+1': () => setInsp('messages'), 'alt+2': () => setInsp('pins'), 'alt+3': () => setInsp('branches'), 'alt+4': () => setInsp('note'), 'alt+5': () => setInsp('stats'),
    'mod+=': () => setSize((s) => Math.min(16, s + 1)), 'mod+-': () => setSize((s) => Math.max(11, s - 1)),
    '?': () => setKeys(true),
    Escape: () => { setPalette(false); setKeys(false); setHints(false); setFind(null) },
  })

  const waiting = sessionsWaiting(st)
  const INSP: Array<[Insp, string, typeof MessageSquare, string]> = [
    ['messages', t('Messages'), MessageSquare, '1'], ['pins', t('Pins'), Pin, '2'], ['branches', t('Branches'), GitBranch, '3'], ['note', t('Note'), FileText, '4'], ['stats', t('Stats'), Activity, '5'],
  ]
  const pane = (p: Pane) => p.kind === 'term'
    ? <Screen session={sessionOf(p.id)!} asleep={st.asleep[p.id]} size={size} focused={false} onNote={openNote} />
    : p.kind === 'server' ? <ServerLog id={p.id} size={size - 1} /> : <Editor size={size} />

  return (
    <div className="absolute inset-0 flex flex-col text-12">
      {/* window bar */}
      <div className="h-[36px] shrink-0 flex items-center gap-12 px-12">
        <WindowControls />
        <span className="font-semibold tracking-tight" style={{ color: 'var(--aq-ink)' }}>SP Aqua</span>
        <span className="aq-ink3 flex items-center gap-6 min-w-0"><ProjectSwatch code={project} size={8} />{projectOf(project).name}<ChevronRight size={12} /><span className="aq-ink2 truncate">{active.name}</span></span>
        <button type="button" className="aq-btn line mx-auto w-[340px] justify-start aq-ink3" onClick={() => setPalette(true)}>
          <Search size={12} />{t('Go to a chat, a server, a note…')}<span className="ml-auto flex gap-2"><Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>
        </button>
        {waiting.length > 0 && (
          <button type="button" className="aq-btn" style={{ color: 'var(--aq-wait)' }} onClick={() => go(nextWaiting(st, st.active)!)} title={t('Next chat waiting on you (alt+W)')}>
            <span className="aq-dot waiting" />{tn(waiting.length, '{n} waiting', '{n} waiting')}</button>
        )}
        <span className="font-mono text-11 aq-ink3 tabular-nums">{t('you')} 2:09 · {t('agents')} 5:12 · {fmtTokens(SESSIONS.reduce((a, s) => a + s.tokens, 0))}</span>
        <button type="button" className="aq-btn icon" aria-label={t('Keys')} title={t('Keys (?)')} onClick={() => setKeys(true)}><Keyboard size={14} /></button>
      </div>

      <div className="flex-1 min-h-0 flex gap-6 px-6">
        {/* the tree — panes float on the water; the gutters between them are its channels */}
        {!zoom && (
          <nav className="w-[264px] shrink-0 flex flex-col aq-panel rounded-[10px] overflow-hidden" aria-label={t('Projects')}>
            <div className="flex-1 min-h-0 aq-scroll py-6">
              {PROJECTS.map((p) => {
                const asleep = projectAsleep(st, p.code)
                const open = !folded[p.code]
                return (
                  <section key={p.code} className="px-6 mb-6" style={{ opacity: asleep ? 0.62 : 1 }}>
                    <div className="group flex items-center gap-4 h-[26px] px-4">
                      <button type="button" className="aq-btn icon" aria-expanded={open} aria-label={p.name} onClick={() => setFolded({ ...folded, [p.code]: open })}>
                        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</button>
                      <ProjectSwatch code={p.code} size={9} />
                      <span className="font-semibold truncate" style={{ color: 'var(--aq-ink)' }}>{p.name}</span>
                      <span className="font-mono text-10 aq-ink3 truncate">{p.branch}</span>
                      <button type="button" className="aq-btn icon ml-auto opacity-0 group-hover:opacity-100 focus:opacity-100" aria-pressed={asleep}
                        title={asleep ? t('Wake the project: its chats and servers') : t('Put the project to sleep: its chats and servers')}
                        aria-label={`${asleep ? t('Wake') : t('Sleep')} ${p.name}`} onClick={() => setProjectAsleep(p.code, !asleep)}>
                        {asleep ? <Sun size={12} /> : <Moon size={12} />}</button>
                    </div>
                    {open && (
                      <ul className="m-0 p-0 list-none flex flex-col">
                        {sessionsIn(p.code).map((s) => (
                          <li key={s.id}>
                            <button type="button" className="aq-row h-[26px] pl-24 pr-6" aria-current={s.id === st.active} onClick={() => go(s.id)}
                              title={`${s.name} · ${STATE_WORD[shownState(st, s)]}`}>
                              <StateDot s={s} st={st} />
                              <span className="truncate flex-1">{s.name}</span>
                              {s.tool === 'codex' && <ToolBadge s={s} />}
                              {!st.asleep[s.id] && <span className="font-mono text-10 aq-ink3 tabular-nums">{s.ctx}%</span>}
                            </button>
                          </li>
                        ))}
                        {serversIn(p.code).length > 0 && <li className="aq-label pl-24 pt-6 pb-2">{t('servers')}</li>}
                        {serversIn(p.code).map((s) => (
                          <li key={s.id}>
                            <button type="button" className="aq-row h-[24px] pl-24 pr-6" onClick={() => setSplit({ kind: 'server', id: s.id })}>
                              <span className={`aq-dot ${st.up[s.id] ? 'up' : 'down'}`} />
                              <span className="truncate flex-1">{s.name}</span>
                              {s.port && <span className="font-mono text-10 aq-ink3">:{s.port}</span>}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                )
              })}
            </div>
            <div className="p-8 flex flex-col gap-6" style={{ borderTop: '1px solid var(--aq-line)' }}>
              <button type="button" className="aq-btn line justify-start"><Plus size={12} />{t('New chat in')} {projectOf(project).name}</button>
            </div>
          </nav>
        )}

        {/* the panes */}
        <main className="flex-1 min-w-0 flex flex-col rounded-[10px] overflow-hidden" style={{ background: 'var(--aq-term-bg)', boxShadow: '0 0 0 1px var(--aq-line), 0 10px 30px oklch(0 0 0 / 0.25)' }}>
          <div className="h-[32px] shrink-0 flex items-end gap-1 px-6 aq-panel" style={{ borderWidth: 0, borderBottomWidth: 1 }} role="tablist" aria-label={t('Chats of the project')}>
            <div className="flex items-end gap-1 min-w-0 overflow-hidden">
            {tabs.map((s, i) => (
              <button key={s.id} type="button" role="tab" aria-selected={center === 'term' && s.id === st.active} className="aq-tab" onClick={() => go(s.id)}>
                <StateDot s={s} st={st} /><span className="truncate">{s.name}</span>{i < 9 && <span className="font-mono text-10 aq-ink3">{i + 1}</span>}
              </button>
            ))}
            <button type="button" role="tab" aria-selected={center === 'editor'} className="aq-tab" onClick={() => setCenter('editor')}><Type size={12} />{t('editor')}</button>
            </div>
            <div className="ml-auto flex items-center gap-1 pb-4 shrink-0">
              <button type="button" className="aq-btn icon" aria-pressed={find !== null} title={t('Find (Ctrl+F)')} aria-label={t('Find')} onClick={() => setFind(find === null ? '' : null)}><Search size={13} /></button>
              <button type="button" className="aq-btn icon" aria-pressed={hints} title={t('Hints: copy an id or a path (alt+H)')} aria-label={t('Hints')} onClick={() => setHints(!hints)}><Command size={13} /></button>
              <button type="button" className="aq-btn icon" aria-pressed={!!split} title={t('Split (alt+\\)')} aria-label={t('Split')} onClick={() => setSplit(split ? null : { kind: 'server', id: serversIn(project)[0]?.id ?? 'ew_h1' })}><Columns2 size={13} /></button>
              <button type="button" className="aq-btn icon" aria-pressed={zoom} title={t('Zoom (alt+Z)')} aria-label={t('Zoom')} onClick={() => setZoom(!zoom)}><Maximize2 size={13} /></button>
              <button type="button" className="aq-btn icon" title={t('Detach into its own window')} aria-label={t('Detach')} onClick={() => detach(center === 'editor' ? 'editor' : `term:${active.id}`)}><ExternalLink size={13} /></button>
              <button type="button" className="aq-btn icon" aria-pressed={!!insp} title={t('Inspector (alt+I)')} aria-label={t('Inspector')} onClick={() => setInsp(insp ? null : 'messages')}><PanelRight size={13} /></button>
            </div>
          </div>
          {find !== null && (
            <div className="flex items-center gap-8 px-10 h-[30px] aq-panel aq-fade" style={{ borderWidth: 0, borderBottomWidth: 1 }}>
              <Search size={12} className="aq-ink3" />
              <input autoFocus value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('Find in the scrollback')} aria-label={t('Find in the scrollback')}
                onKeyDown={(e) => { if (e.key === 'Escape') setFind(null) }}
                className="flex-1 bg-transparent outline-none border-0 font-mono text-12" style={{ color: 'var(--aq-ink)' }} />
              <span className="aq-chip">.*</span><span className="aq-chip">Aa</span>
              <button type="button" className="aq-btn icon" aria-label={t('Close')} onClick={() => setFind(null)}><X size={12} /></button>
            </div>
          )}
          <div className={`flex-1 min-h-0 flex ${split?.kind === 'server' ? 'flex-col' : ''}`}>
            <div className="flex-1 min-w-0 min-h-0 relative">
              {center === 'editor' ? <Editor size={size} /> : (
                <Screen session={active} asleep={st.asleep[active.id]} size={size} query={find ?? ''} hints={hints} onHintsDone={() => setHints(false)} onNote={openNote}
                  draft={active.state === 'waiting' ? 'staff are exempt, same as /login' : ''} />
              )}
              {hints && <div className="absolute top-8 right-12 aq-chip" style={{ background: 'var(--aq-term-hint)', color: 'var(--aq-term-hint-ink)' }}>{t('press a letter to copy · Esc')}</div>}
            </div>
            {split && (
              <div className={`${split.kind === 'server' ? 'h-[220px] shrink-0' : 'w-[42%]'} min-w-0 flex flex-col aq-slide-r`} style={split.kind === 'server' ? { borderTop: '1px solid var(--aq-line)' } : { borderLeft: '1px solid var(--aq-line)' }}>
                <div className="h-[26px] shrink-0 flex items-center gap-6 px-8 aq-panel" style={{ borderWidth: 0, borderBottomWidth: 1 }}>
                  <select aria-label={t('What the second pane shows')} className="bg-transparent text-11 font-mono outline-none" style={{ color: 'var(--aq-ink2)' }}
                    value={split.kind === 'editor' ? 'editor' : `${split.kind}:${split.id}`}
                    onChange={(e) => {
                      const [k, id] = e.target.value.split(':')
                      setSplit(k === 'editor' ? { kind: 'editor' } : { kind: k as 'term' | 'server', id: id! })
                    }}>
                    {serversIn(project).map((s) => <option key={s.id} value={`server:${s.id}`}>{t('server')} · {s.name}</option>)}
                    {SESSIONS.filter((s) => s.id !== active.id).map((s) => <option key={s.id} value={`term:${s.id}`}>{t('chat')} · {s.name}</option>)}
                    <option value="editor">{t('editor')}</option>
                  </select>
                  <button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} title={t('Detach into its own window')}
                    onClick={() => { detach(split.kind === 'editor' ? 'editor' : `${split.kind}:${split.id}`); setSplit(null) }}><ExternalLink size={12} /></button>
                  <button type="button" className="aq-btn icon" aria-label={t('Close the pane')} onClick={() => setSplit(null)}><X size={12} /></button>
                </div>
                <div className="flex-1 min-h-0">{pane(split)}</div>
              </div>
            )}
          </div>
        </main>

        {/* the inspector */}
        {insp && !zoom && (
          <aside className={`${insp === 'note' ? 'w-[460px]' : 'w-[340px]'} shrink-0 flex flex-col aq-panel aq-slide-r rounded-[10px] overflow-hidden`} aria-label={t('Inspector')}>
            <div className="h-[32px] shrink-0 flex items-center gap-1 px-4" style={{ borderBottom: '1px solid var(--aq-line)' }} role="tablist" aria-label={t('Inspector')}>
              {INSP.map(([k, w, Icon, n]) => (
                <button key={k} type="button" role="tab" aria-selected={insp === k} aria-label={w} className="aq-btn" data-on={insp === k} onClick={() => setInsp(k)} title={`${w} (alt+${n})`}>
                  <Icon size={12} />{insp === k && w}
                </button>
              ))}
            </div>
            <div className="flex-1 min-h-0 flex flex-col">
              {insp === 'messages' && <Messages sessionId={active.id} onNote={openNote} onJump={jump} />}
              {insp === 'pins' && <Pins onJump={jump} onNote={openNote} />}
              {insp === 'branches' && <Branches sessionId={active.id} onChat={go} />}
              {insp === 'stats' && <div className="aq-scroll"><Stats compact /></div>}
              {insp === 'note' && (
                <div className="flex-1 min-h-0 aq-scroll p-16 flex flex-col gap-10">
                  <div className="flex items-center gap-6">
                    <NoteMeta id={note} />
                    <button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`note:${note}`)}><ExternalLink size={12} /></button>
                  </div>
                  <NoteBody id={note} size={13} />
                </div>
              )}
            </div>
            {insp === 'messages' && (
              <div className="px-10 py-6 text-10 font-mono aq-ink3 flex gap-8 flex-wrap" style={{ borderTop: '1px solid var(--aq-line)' }}>
                {tn(messagesOf(active.id).length, '{n} message', '{n} messages')} · p {t('pin')} · i {t('important')} · t {t('task')} · f {t('fork')} · m {t('memory')}
              </div>
            )}
          </aside>
        )}
      </div>

      {/* the key bar */}
      <div className="h-[26px] shrink-0 flex items-center gap-12 px-12 font-mono text-10 aq-ink3">
        {[['^K', t('palette')], ['^F', t('find')], ['alt H', t('hints')], ['alt \\', t('split')], ['alt Z', t('zoom')], ['alt I', t('inspector')], ['alt W', t('next waiting')], ['alt J/K', t('walk')], ['?', t('keys')]].map(([k, w]) => (
          <span key={k} className="whitespace-nowrap"><span style={{ color: 'var(--aq-accent)' }}>{k}</span> {w}</span>
        ))}
        <span className="ml-auto flex items-center gap-8">
          {SERVERS.filter((s) => s.project === project).map((s) => (
            <button key={s.id} type="button" className="flex items-center gap-4" onClick={() => toggleServer(s.id)} title={`${serverOf(s.id)!.command}`}>
              <span className={`aq-dot ${st.up[s.id] ? 'up' : 'down'}`} />{s.name}</button>
          ))}
          <span>{size}px</span>
        </span>
      </div>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={actions} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('command palette')], ['Ctrl F', t('find in the scrollback')], ['alt H', t('hints: copy an id or a path')], ['alt \\', t('split / unsplit')],
        ['alt Z', t('zoom the pane')], ['alt I', t('inspector on / off')], ['alt 1…5', t('inspector tabs')], ['alt E', t('editor')],
        ['alt J', t('next chat')], ['alt K', t('previous chat')], ['alt W', t('next chat waiting on you')], ['alt S', t('sleep / wake the chat')],
        ['Ctrl =', t('bigger text')], ['Ctrl -', t('smaller text')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
