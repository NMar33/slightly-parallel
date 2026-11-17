/**
 * C · Spine — conversation-first. "Sea glass on paper": warm paper, a
 * light terminal (a dark one in the dark theme), one sea-glass accent.
 *
 * Three columns: the live terminal; the spine — the chat SP captured, one
 * line per message, an index and never a second transcript, with the
 * memory light, the pin and the important flag in its gutter and the
 * pinned master message held at the top; the paper — the note the agent
 * wrote, the task branches, the editor, the servers, the stats. A click
 * on a spine row finds it in the terminal. Spread folds the spine to its
 * lights so the terminal takes the width.
 */

import { useState } from 'react'
import {
  Activity, ChevronsLeft, ChevronsRight, ExternalLink, FileText, Flag, GitBranch, GitFork, Keyboard, ListPlus, Moon, Pin, Search, Server, Sun, Type,
} from 'lucide-react'

import { t } from '../../../../i18n/scope/aqua'
import { MESSAGES, NOTES, PROJECTS, messagesOf, noteOf, projectOf, sessionOf, sessionsIn, type Message } from '../mock'
import {
  Branches, CarryKey, Editor, Keymap, Kbd, MESSAGE_KEYS, MemoryLight, NoteBody, NoteMeta, Palette, Restore, ServerLog, Servers, StateDot, Stats,
  commonActions, nextWaiting, projectInk, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { cycleMark, detach, focus, projectAsleep, setProjectAsleep, toTask, toggleForkLater, toggleImportant, togglePin, toggleSleep, useAqua } from '../store'
import { Screen } from '../term'
import type { Theme } from '../AquaDesign'

type Paper = 'note' | 'branches' | 'editor' | 'servers' | 'stats'

export function Spine({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const active = sessionOf(st.active)!
  const [paper, setPaper] = useState<Paper>('note')
  const [note, setNote] = useState('nt_7d21c0aa')
  const [spread, setSpread] = useState(false)
  const [sel, setSel] = useState<string | null>('m4')
  const [find, setFind] = useState('')
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [server, setServer] = useState<string | null>(null)

  const msgs = messagesOf(active.id)
  const master = msgs.find((m) => st.pinned[m.id] && st.important[m.id]) ?? msgs.find((m) => st.pinned[m.id])
  const go = (id: string) => { focus(id); setSel(null); setFind('') }
  const openNote = (id: string) => { setNote(id); setPaper('note') }
  const pick = (m: Message) => { setSel(m.id); setFind(m.text.split(' ').slice(0, 4).join(' ')); if (m.note) openNote(m.note) }
  const walk = (d: number) => {
    const i = msgs.findIndex((m) => m.id === sel)
    const n = msgs[Math.max(0, Math.min(msgs.length - 1, (i < 0 ? msgs.length : i) + d))]
    if (n) pick(n)
  }
  const onSel = (f: (id: string) => void) => () => { if (sel) f(sel) }

  const actions: Action[] = [
    { id: 'spread', group: t('view'), label: t('Spread: fold the spine to its lights'), kbd: 'alt+S', run: () => setSpread((s) => !s) },
    ...([['note', t('Note')], ['branches', t('Branches')], ['editor', t('Editor')], ['servers', t('Servers')], ['stats', t('Stats')]] as Array<[Paper, string]>).map(([p, w]) => ({ id: `pp-${p}`, group: t('paper'), label: w, run: () => setPaper(p) })),
    ...PROJECTS.map((p) => ({ id: `sl-${p.code}`, group: t('project'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    ...commonActions(go, { note: openNote, server: (id) => { setServer(id); setPaper('servers') } }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    j: () => walk(1), k: () => walk(-1),
    p: onSel(togglePin), i: onSel(toggleImportant), t: onSel(toTask), f: onSel(toggleForkLater), m: onSel(cycleMark),
    'alt+s': () => setSpread((s) => !s),
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+1': () => setPaper('note'), 'alt+2': () => setPaper('branches'), 'alt+3': () => setPaper('editor'), 'alt+4': () => setPaper('servers'), 'alt+5': () => setPaper('stats'),
    '?': () => setKeys(true),
    Escape: () => { setPalette(false); setKeys(false); setFind(''); setSel(null) },
  })

  const PAPERS: Array<[Paper, string, typeof Pin]> = [['note', t('Note'), FileText], ['branches', t('Branches'), GitBranch], ['editor', t('Editor'), Type], ['servers', t('Servers'), Server], ['stats', t('Stats'), Activity]]
  const notesHere = NOTES.filter((n) => n.session === active.id)

  return (
    <div className="absolute inset-0 flex flex-col" style={{ background: 'var(--aq-bg)' }}>
      {/* the chat bar: projects, then the chats of this one */}
      <header className="h-[44px] shrink-0 flex items-center gap-14 px-16" style={{ borderBottom: '1px solid var(--aq-line)' }}>
        <b className="text-14 tracking-tight" style={{ fontFamily: 'Georgia, var(--font-sans)' }}>Aqua</b>
        <nav className="flex items-center gap-4" aria-label={t('Projects')}>
          {PROJECTS.map((p) => {
            const asleep = projectAsleep(st, p.code)
            const here = active.project === p.code
            return (
              <span key={p.code} className="group inline-flex items-center">
                <button type="button" aria-current={here} onClick={() => go((sessionsIn(p.code).find((s) => !st.asleep[s.id]) ?? sessionsIn(p.code)[0]!).id)}
                  className="h-[28px] px-10 rounded-[8px] text-13 inline-flex items-center gap-6"
                  style={{ background: here ? 'var(--aq-raise)' : undefined, boxShadow: here ? '0 1px 2px oklch(0.3 0.02 70 / 0.12)' : undefined, color: here ? 'var(--aq-ink)' : 'var(--aq-ink2)', opacity: asleep ? 0.55 : 1 }}>
                  <span className="aq-dot" style={{ background: projectInk(p.code) }} />{p.name}
                </button>
                <button type="button" className="aq-btn icon opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={`${asleep ? t('Wake') : t('Sleep')} ${p.name}`}
                  title={asleep ? t('Wake the project: its chats and servers') : t('Put the project to sleep: its chats and servers')} onClick={() => setProjectAsleep(p.code, !asleep)}>
                  {asleep ? <Sun size={12} /> : <Moon size={12} />}</button>
              </span>
            )
          })}
        </nav>
        <button type="button" className="aq-btn line ml-auto w-[300px] justify-start aq-ink3" onClick={() => setPalette(true)}><Search size={12} />{t('Find a chat, a message, a note')}<span className="ml-auto"><Kbd>Ctrl K</Kbd></span></button>
        <button type="button" className="aq-btn icon" aria-label={t('Keys')} onClick={() => setKeys(true)}><Keyboard size={14} /></button>
      </header>
      <div className="h-[36px] shrink-0 flex items-center gap-2 px-14" role="tablist" aria-label={t('Chats of the project')} style={{ borderBottom: '1px solid var(--aq-line)' }}>
        {sessionsIn(active.project).map((s) => (
          <button key={s.id} type="button" role="tab" aria-selected={s.id === active.id} onClick={() => go(s.id)}
            className="h-[26px] px-10 rounded-[6px] text-12 inline-flex items-center gap-6 max-w-[220px]"
            style={{ background: s.id === active.id ? 'var(--aq-accent-soft)' : undefined, color: s.id === active.id ? 'var(--aq-ink)' : 'var(--aq-ink2)' }} title={STATE_WORD[shownState(st, s)]}>
            <StateDot s={s} st={st} /><span className="truncate">{s.name}</span>
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 flex">
        {/* terminal */}
        <section className="flex-1 min-w-0 flex flex-col" aria-label={t('Terminal')} style={{ borderRight: '1px solid var(--aq-line)' }}>
          <div className="h-[30px] shrink-0 flex items-center gap-8 px-12 text-11 aq-ink3 font-mono" style={{ borderBottom: '1px solid var(--aq-line)' }}>
            <StateDot s={active} st={st} /><span>{active.name}</span><span>·</span><span>{projectOf(active.project).path}</span>
            {find && <span className="aq-chip">{t('found')}: {find}</span>}
            <button type="button" className="aq-btn ml-auto" onClick={() => toggleSleep(active.id)}>{st.asleep[active.id] ? <><Sun size={12} />{t('Wake')}</> : <><Moon size={12} />{t('Sleep')}</>}</button>
            <button type="button" className="aq-btn icon" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`term:${active.id}`)}><ExternalLink size={12} /></button>
          </div>
          <div className="flex-1 min-h-0"><Screen session={active} asleep={st.asleep[active.id]} query={find} onNote={openNote} size={13} /></div>
        </section>

        {/* the spine */}
        <section className={`${spread ? 'w-[44px]' : 'w-[380px]'} shrink-0 flex flex-col transition-[width] duration-200`} aria-label={t('Spine')} style={{ background: 'var(--aq-panel)', borderRight: '1px solid var(--aq-line)' }}>
          <div className="h-[30px] shrink-0 flex items-center gap-6 px-8" style={{ borderBottom: '1px solid var(--aq-line)' }}>
            {!spread && <span className="aq-label">{t('Spine')} · {msgs.length}</span>}
            <button type="button" className="aq-btn icon ml-auto" aria-label={spread ? t('Open the spine') : t('Spread: fold the spine')} title={t('Spread (alt+S)')} onClick={() => setSpread(!spread)}>
              {spread ? <ChevronsLeft size={13} /> : <ChevronsRight size={13} />}</button>
          </div>
          {!spread && master && (
            <button type="button" className="text-left px-12 py-10 flex flex-col gap-4" style={{ background: 'var(--aq-accent-soft)', borderBottom: '1px solid var(--aq-line)' }} onClick={() => pick(master)}>
              <span className="aq-label flex items-center gap-6 aq-accent"><Pin size={11} />{t('master message')} · {master.at}</span>
              <span className="text-13 leading-snug line-clamp-3" style={{ color: 'var(--aq-ink)' }}>{master.text}</span>
            </button>
          )}
          <ol className="m-0 p-0 list-none flex-1 min-h-0 aq-scroll relative" aria-label={t('Messages')}>
            {!spread && <span aria-hidden className="absolute left-[27px] top-0 bottom-0 w-[1px]" style={{ background: 'var(--aq-line)' }} />}
            {msgs.map((m) => {
              const on = sel === m.id
              if (spread) {
                return (
                  <li key={m.id} className="flex justify-center py-6">
                    <button type="button" className="flex flex-col items-center gap-2" onClick={() => pick(m)} title={m.text} aria-label={m.text}>
                      <MemoryLight m={st.marks[m.id] ?? null} />
                      {st.pinned[m.id] && <Pin size={10} className="aq-accent" />}
                    </button>
                  </li>
                )
              }
              return (
                <li key={m.id} className="group relative flex items-stretch gap-8 pl-8 pr-8 py-6 cursor-pointer" aria-selected={on}
                  style={{ background: on ? 'var(--aq-raise)' : undefined }} onClick={() => pick(m)}>
                  <span className="w-[14px] shrink-0 flex flex-col items-center gap-3 pt-3">
                    {st.pinned[m.id] ? <Pin size={11} className="aq-accent" /> : <span className="w-[11px] h-[11px]" />}
                    {st.important[m.id] && <Flag size={10} style={{ color: 'var(--aq-important)' }} />}
                  </span>
                  <span className="relative z-[1] px-2 flex" style={{ background: on ? 'var(--aq-raise)' : 'var(--aq-panel)' }}><MemoryLight m={st.marks[m.id] ?? null} onClick={() => cycleMark(m.id)} /></span>
                  <span className="flex-1 min-w-0 flex flex-col">
                    <span className="flex items-center gap-6 text-10 font-mono aq-ink3 h-[20px]">
                      <span style={{ color: m.who === 'you' ? 'var(--aq-accent)' : undefined }}>{m.who === 'you' ? t('you') : t('agent')}</span>{m.at}
                      {st.tasked[m.id] && <span className="aq-chip">{st.tasked[m.id]}</span>}
                      {st.forkLater[m.id] && <span className="aq-chip" style={{ color: 'var(--aq-fork)' }}><GitFork size={9} />{t('fork later')}</span>}
                      {!on && (
                        <span className="ml-auto hidden group-hover:flex gap-1">
                          <button type="button" className="aq-btn icon !h-[20px] !w-[20px]" aria-pressed={!!st.pinned[m.id]} aria-label={t('Pin (p)')} title={t('Pin (p)')} onClick={(e) => { e.stopPropagation(); togglePin(m.id) }}><Pin size={12} /></button>
                          <button type="button" className="aq-btn icon !h-[20px] !w-[20px]" aria-pressed={!!st.important[m.id]} aria-label={t('Important (i)')} title={t('Important (i)')} onClick={(e) => { e.stopPropagation(); toggleImportant(m.id) }}><Flag size={12} /></button>
                          <button type="button" className="aq-btn icon !h-[20px] !w-[20px]" aria-pressed={!!st.tasked[m.id]} aria-label={t('To a task (t)')} title={t('To a task (t)')} onClick={(e) => { e.stopPropagation(); toTask(m.id) }}><ListPlus size={12} /></button>
                          <button type="button" className="aq-btn icon !h-[20px] !w-[20px]" aria-pressed={!!st.forkLater[m.id]} aria-label={t('Fork later (f)')} title={t('Fork later (f)')} onClick={(e) => { e.stopPropagation(); toggleForkLater(m.id) }}><GitFork size={12} /></button>
                        </span>
                      )}
                    </span>
                    <span className={`text-12 leading-snug ${on ? '' : 'truncate'}`} style={{ color: 'var(--aq-ink)' }}>{m.text}</span>
                    {m.note && <span className="text-11 aq-accent flex items-center gap-4"><FileText size={11} />{noteOf(m.note)?.title}</span>}
                    {on && (
                      <span className="flex items-center gap-2 mt-4 flex-wrap">
                        <button type="button" className="aq-btn line" aria-pressed={!!st.pinned[m.id]} onClick={(e) => { e.stopPropagation(); togglePin(m.id) }}><Pin size={11} />{t('pin')}</button>
                        <button type="button" className="aq-btn line" aria-pressed={!!st.important[m.id]} onClick={(e) => { e.stopPropagation(); toggleImportant(m.id) }}><Flag size={11} />{t('important')}</button>
                        <button type="button" className="aq-btn line" aria-pressed={!!st.tasked[m.id]} onClick={(e) => { e.stopPropagation(); toTask(m.id) }}><ListPlus size={11} />{t('task')}</button>
                        <button type="button" className="aq-btn line" aria-pressed={!!st.forkLater[m.id]} onClick={(e) => { e.stopPropagation(); toggleForkLater(m.id) }}><GitFork size={11} />{t('fork later')}</button>
                      </span>
                    )}
                  </span>
                </li>
              )
            })}
          </ol>
          {!spread && (
            <div className="px-10 py-6 text-10 font-mono aq-ink3" style={{ borderTop: '1px solid var(--aq-line)' }}>
              j/k {t('walk')} · p {t('pin')} · i {t('important')} · t {t('task')} · f {t('fork')} · m {t('memory')}
              <CarryKey className="mt-4" />
            </div>
          )}
        </section>

        {/* the paper */}
        <section className={`${spread ? 'w-[46%]' : 'w-[38%]'} shrink-0 flex flex-col min-w-0`} aria-label={t('Paper')} style={{ background: 'var(--aq-raise)' }}>
          <div className="h-[30px] shrink-0 flex items-center gap-2 px-8" role="tablist" aria-label={t('Paper')} style={{ borderBottom: '1px solid var(--aq-line)' }}>
            {PAPERS.map(([k, w, Icon]) => <button key={k} type="button" role="tab" aria-selected={paper === k} className="aq-btn" data-on={paper === k} onClick={() => setPaper(k)}><Icon size={12} />{w}</button>)}
          </div>
          <div className="flex-1 min-h-0 flex flex-col">
            {paper === 'note' && (
              <div className="flex-1 aq-scroll px-32 py-24 flex flex-col gap-14">
                <div className="flex items-center gap-8 flex-wrap">
                  {(notesHere.length ? notesHere : NOTES).map((n) => <button key={n.id} type="button" className="aq-btn line" data-on={note === n.id} onClick={() => setNote(n.id)}><FileText size={12} />{n.title}</button>)}
                  <button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`note:${note}`)}><ExternalLink size={12} /></button>
                </div>
                <NoteMeta id={note} />
                <NoteBody id={note} size={15} />
              </div>
            )}
            {paper === 'branches' && <Branches sessionId={active.id} onChat={go} />}
            {paper === 'editor' && <Editor />}
            {paper === 'servers' && (
              <div className="flex-1 min-h-0 flex flex-col">
                <div className="p-8"><Servers project={active.project} onOpen={setServer} /></div>
                {server && <div className="flex-1 min-h-0" style={{ borderTop: '1px solid var(--aq-line)' }}><ServerLog id={server} /></div>}
              </div>
            )}
            {paper === 'stats' && <div className="aq-scroll"><Stats compact /></div>}
          </div>
        </section>
      </div>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={[...actions, ...MESSAGES.map((m) => ({ id: `ms-${m.id}`, group: t('message'), label: m.text, run: () => { go(m.session); pick(m) } }))]} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('find a chat, a message, a note')], ['j', t('next message')], ['k', t('previous message')], ['alt S', t('spread: fold the spine')],
        ['alt 1…5', t('paper: note, branches, editor, servers, stats')], ['alt W', t('next chat waiting on you')], ['Esc', t('clear the selection')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
