/**
 * F · Lineage — the tree is the navigation. "Channels": clean surfaces,
 * the branches drawn as water channels in the accent.
 *
 * Left, a project's lineage: each chat with the tasks it spawned, the
 * background agents, the chats it forked work to (nested under the task
 * that forked them), and ghost nodes for messages queued to fork later.
 * A chat node opens its terminal on the right; a task node shows its card
 * over the terminal; a ghost hands the work to a new agent. A note opens
 * in place of the tree, beside the terminal. Under the terminal, a strip
 * for messages, pins, servers, the editor and stats.
 */

import { Fragment, useState, type ReactNode } from 'react'
import {
  Activity, ArrowLeft, Bot, ExternalLink, FileText, GitFork, Keyboard, MessageSquare, Moon, Pin, Play, Search, Server, Sun, Type, X,
} from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { MESSAGES, PROJECTS, TASKS, noteOf, sessionOf, sessionsIn, type Message, type Session, type Task } from '../mock'
import {
  Editor, Keymap, Kbd, MESSAGE_KEYS, Messages, NoteBody, NoteMeta, Palette, Pins, Restore, ServerLog, Servers, StateDot, Stats,
  commonActions, nextWaiting, projectInk, sessionsWaiting, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { detach, flash, focus, projectAsleep, setProjectAsleep, toggleForkLater, toggleSleep, useAqua } from '../store'
import { Screen } from '../term'
import type { Theme } from '../AquaDesign'

type Strip = 'messages' | 'pins' | 'servers' | 'editor' | 'stats'
const STATUS_INK: Record<Task['status'], string> = { todo: 'var(--aq-ink3)', doing: 'var(--aq-accent)', done: 'var(--aq-up)' }

function Channel({ depth, last, children }: { depth: number; last: boolean; children: ReactNode }) {
  return (
    <li className="relative list-none" style={{ paddingLeft: depth ? 22 : 0 }}>
      {depth > 0 && (
        <svg aria-hidden className="absolute left-[6px] top-0" width="18" height="100%" style={{ height: last ? 18 : '100%' }} preserveAspectRatio="none">
          <path d={last ? 'M2 0 V8 Q2 16 12 16 H18' : 'M2 0 V200'} stroke="var(--aq-accent)" strokeOpacity="0.45" strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      {depth > 0 && !last && <svg aria-hidden className="absolute left-[6px] top-0" width="18" height="18"><path d="M2 8 Q2 16 12 16 H18" stroke="var(--aq-accent)" strokeOpacity="0.45" strokeWidth="2" fill="none" /></svg>}
      {children}
    </li>
  )
}

export function Lineage({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const active = sessionOf(st.active)!
  const [project, setProject] = useState(active.project)
  const [task, setTask] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [strip, setStrip] = useState<Strip | null>(null)
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [server, setServer] = useState<string | null>(null)

  const go = (id: string) => { focus(id); setProject(sessionOf(id)!.project); setTask(null) }
  const openNote = (id: string) => setNote(id)
  const jump = (m: Message) => go(m.session)
  const chats = sessionsIn(project)
  const forkedInto = new Set(TASKS.filter((x) => x.chat && x.chat !== x.from).map((x) => x.chat!))
  const roots = chats.filter((s) => !forkedInto.has(s.id))

  const actions: Action[] = [
    ...PROJECTS.map((p) => ({ id: `pr-${p.code}`, group: t('project'), label: p.name, run: () => setProject(p.code) })),
    ...PROJECTS.map((p) => ({ id: `sl-${p.code}`, group: t('project'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    ...([['messages', t('Messages')], ['pins', t('Pins')], ['servers', t('Servers')], ['editor', t('Editor')], ['stats', t('Stats')]] as Array<[Strip, string]>).map(([k, w]) => ({ id: `st-${k}`, group: t('strip'), label: w, run: () => setStrip(k) })),
    ...commonActions(go, { note: openNote, server: (id) => { setStrip('servers'); setServer(id) } }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+1': () => setStrip('messages'), 'alt+2': () => setStrip('pins'), 'alt+3': () => setStrip('servers'), 'alt+4': () => setStrip('editor'), 'alt+5': () => setStrip('stats'),
    'alt+s': () => toggleSleep(active.id),
    '?': () => setKeys(true),
    Escape: () => { setPalette(false); setKeys(false); setTask(null); setNote(null) },
  })

  const chatNode = (s: Session, depth: number, last: boolean): ReactNode => {
    const tasks = TASKS.filter((x) => x.from === s.id && x.chat !== s.id)
    const top = tasks.filter((x) => !x.parent || !tasks.some((y) => y.id === x.parent))
    const queued = MESSAGES.filter((m) => m.session === s.id && st.forkLater[m.id])
    const made = Object.entries(st.tasked).filter(([mid, tk]) => MESSAGES.find((m) => m.id === mid)?.session === s.id && !TASKS.some((x) => x.id === tk))
    const notes = s.script.filter((l) => l.k === 'note').map((l) => (l.k === 'note' ? l.note : ''))
    const on = s.id === st.active
    const k = shownState(st, s)
    const taskNode = (x: Task, d: number, isLast: boolean): ReactNode => {
      const kids = tasks.filter((y) => y.parent === x.id)
      const forked = x.chat && x.chat !== s.id ? sessionOf(x.chat) : undefined
      return (
        <Channel key={x.id} depth={d} last={isLast}>
          <button type="button" className="aq-row px-8 py-4 text-12" aria-selected={task === x.id} onClick={() => setTask(x.id)}>
            <span className="w-[8px] h-[8px] rounded-[2px] shrink-0" style={{ background: STATUS_INK[x.status] }} />
            <span className="truncate" style={{ color: 'var(--aq-ink)' }}>{x.title}</span>
            {x.via === 'background agent' && <Bot size={12} className="aq-ink3 shrink-0" aria-label={t('background agent')} />}
            <span className="text-10 font-mono aq-ink3 ml-auto shrink-0">{x.status}</span>
          </button>
          {(kids.length > 0 || forked) && (
            <ul className="m-0 p-0">
              {kids.map((y, i) => taskNode(y, 1, i === kids.length - 1 && !forked))}
              {forked && chatNode(forked, 1, true)}
            </ul>
          )}
        </Channel>
      )
    }
    return (
      <Channel key={s.id} depth={depth} last={last}>
        <div className="group rounded-[10px] my-4" style={{ background: on ? 'var(--aq-accent-soft)' : 'var(--aq-raise)', border: `1px solid ${on ? 'var(--aq-accent)' : 'var(--aq-line)'}` }}>
          <button type="button" className="w-full flex items-center gap-8 px-10 py-8 text-left" aria-current={on} onClick={() => go(s.id)}>
            <StateDot s={s} st={st} />
            <span className="text-13 font-semibold truncate" style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
            {s.tool === 'codex' && <span className="aq-chip">cx</span>}
            <span className="text-10 font-mono aq-ink3 ml-auto shrink-0">{STATE_WORD[k]} · {s.ctx}%</span>
          </button>
          <div className="flex items-center gap-6 px-10 pb-8 -mt-4 flex-wrap">
            <span className="aq-chip">{s.id}</span>
            {notes.map((n) => <button key={n} type="button" className="aq-chip" onClick={() => openNote(n)} title={noteOf(n)?.title}><FileText size={10} />{t('note')}</button>)}
            {s.bg.filter((b) => !b.done).map((b) => <span key={b.label} className="aq-chip" title={b.label}><Bot size={10} />{b.label.slice(0, 22)}…</span>)}
            <button type="button" className="aq-btn ml-auto opacity-0 group-hover:opacity-100 focus:opacity-100" onClick={() => toggleSleep(s.id)}>{st.asleep[s.id] ? t('wake') : t('sleep')}</button>
          </div>
        </div>
        {(top.length > 0 || queued.length > 0 || made.length > 0) && (
          <ul className="m-0 p-0 pl-8">
            {top.map((x, i) => taskNode(x, 1, i === top.length - 1 && !queued.length && !made.length))}
            {made.map(([mid, tk], i) => (
              <Channel key={tk} depth={1} last={i === made.length - 1 && !queued.length}>
                <div className="aq-row px-8 py-4 text-12 aq-fade"><span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: STATUS_INK.todo }} /><span className="truncate">{MESSAGES.find((m) => m.id === mid)?.text}</span><span className="aq-chip ml-auto">{tk}</span></div>
              </Channel>
            ))}
            {queued.map((m, i) => (
              <Channel key={m.id} depth={1} last={i === queued.length - 1}>
                <div className="flex items-center gap-8 px-8 py-6 my-2 rounded-[8px] text-12" style={{ border: '1.5px dashed var(--aq-fork)' }}>
                  <GitFork size={12} style={{ color: 'var(--aq-fork)' }} className="shrink-0" />
                  <span className="truncate flex-1" style={{ color: 'var(--aq-ink2)' }}>{m.text}</span>
                  <button type="button" className="aq-btn line shrink-0" onClick={() => { toggleForkLater(m.id); flash(t('Handed to a new agent with the chat\'s briefing')) }}><Play size={11} />{t('Hand to an agent')}</button>
                </div>
              </Channel>
            ))}
          </ul>
        )}
      </Channel>
    )
  }

  const tk = task ? TASKS.find((x) => x.id === task) : null
  const STRIPS: Array<[Strip, string, typeof Pin]> = [['messages', t('Messages'), MessageSquare], ['pins', t('Pins'), Pin], ['servers', t('Servers'), Server], ['editor', t('Editor'), Type], ['stats', t('Stats'), Activity]]
  const waiting = sessionsWaiting(st)

  return (
    <div className="absolute inset-0 flex flex-col" style={{ background: 'var(--aq-bg)' }}>
      <header className="h-[42px] shrink-0 flex items-center gap-10 px-14" style={{ borderBottom: '1px solid var(--aq-line)', background: 'var(--aq-panel)' }}>
        <b className="text-14 tracking-tight">SP Aqua</b>
        <nav className="flex items-center gap-2" role="tablist" aria-label={t('Projects')}>
          {PROJECTS.map((p) => {
            const asleep = projectAsleep(st, p.code)
            return (
              <span key={p.code} className="group inline-flex items-center">
                <button type="button" role="tab" aria-selected={project === p.code} onClick={() => setProject(p.code)} className="h-[28px] px-10 rounded-[8px] text-13 inline-flex items-center gap-6"
                  style={{ background: project === p.code ? 'var(--aq-accent-soft)' : undefined, color: project === p.code ? 'var(--aq-ink)' : 'var(--aq-ink2)', opacity: asleep ? 0.55 : 1 }}>
                  <span className="aq-dot" style={{ background: projectInk(p.code) }} />{p.name}
                </button>
                <button type="button" className="aq-btn icon opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={`${asleep ? t('Wake') : t('Sleep')} ${p.name}`} onClick={() => setProjectAsleep(p.code, !asleep)}>{asleep ? <Sun size={12} /> : <Moon size={12} />}</button>
              </span>
            )
          })}
        </nav>
        {waiting.length > 0 && <button type="button" className="aq-btn" style={{ color: 'var(--aq-wait)' }} onClick={() => go(nextWaiting(st, st.active)!)}><span className="aq-dot waiting" />{tn(waiting.length, '{n} waits for you', '{n} wait for you')}</button>}
        <button type="button" className="aq-btn line ml-auto w-[280px] justify-start aq-ink3" onClick={() => setPalette(true)}><Search size={12} />{t('Find a chat, a task, a note')}<span className="ml-auto"><Kbd>Ctrl K</Kbd></span></button>
        <button type="button" className="aq-btn icon" aria-label={t('Keys')} onClick={() => setKeys(true)}><Keyboard size={14} /></button>
      </header>

      <div className="flex-1 min-h-0 flex">
        <section className="w-[500px] shrink-0 flex flex-col min-h-0" style={{ borderRight: '1px solid var(--aq-line)' }} aria-label={note ? t('Note') : t('Lineage')}>
          {note ? (
            <div className="flex-1 min-h-0 aq-scroll px-24 py-16 flex flex-col gap-12 aq-fade" style={{ background: 'var(--aq-panel)' }}>
              <div className="flex items-center gap-6">
                <button type="button" className="aq-btn" onClick={() => setNote(null)}><ArrowLeft size={12} />{t('Back to the lineage')}</button>
                <button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`note:${note}`)}><ExternalLink size={12} /></button>
              </div>
              <NoteMeta id={note} />
              <NoteBody id={note} />
            </div>
          ) : (
            <div className="flex-1 min-h-0 aq-scroll p-14">
              {tk && (
                <div className="aq-glass aq-float rounded-[12px] p-14 mb-12 aq-fade flex flex-col gap-8" role="dialog" aria-label={tk.title}>
                  <div className="flex items-center gap-8"><span className="aq-chip">{tk.id}</span><span className="text-11 font-mono" style={{ color: STATUS_INK[tk.status] }}>{tk.status}</span>
                    <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => setTask(null)}><X size={12} /></button></div>
                  <b className="text-14">{tk.title}</b>
                  <span className="text-12 aq-ink2">{t('from')} {sessionOf(tk.from)?.name}{tk.via ? ` · ${tk.via}` : ''}</span>
                  {tk.chat && <button type="button" className="aq-btn line self-start" onClick={() => go(tk.chat!)}>{t('Open its chat')} · {sessionOf(tk.chat)?.name}</button>}
                </div>
              )}
              <div className="flex items-baseline gap-8 mb-8"><span className="aq-label">{t('Lineage')}</span><span className="text-11 aq-ink3">{t('chats, the tasks they spawned, the work they forked')}</span></div>
              <ul className="m-0 p-0">{roots.map((s, i) => <Fragment key={s.id}>{chatNode(s, 0, i === roots.length - 1)}</Fragment>)}</ul>
            </div>
          )}
        </section>

        <main className="flex-1 min-w-0 flex flex-col relative">
          <div className="h-[30px] shrink-0 flex items-center gap-8 px-12 text-12" style={{ borderBottom: '1px solid var(--aq-line)', background: 'var(--aq-panel)' }}>
            <StateDot s={active} st={st} /><b>{active.name}</b><span className="aq-ink3 font-mono text-11">{active.model} · {active.ctx}%</span>
            <button type="button" className="aq-btn ml-auto" onClick={() => toggleSleep(active.id)}>{st.asleep[active.id] ? <><Sun size={12} />{t('Wake')}</> : <><Moon size={12} />{t('Sleep')}</>}</button>
            <button type="button" className="aq-btn icon" aria-label={t('Detach')} title={t('Detach into its own window')} onClick={() => detach(`term:${active.id}`)}><ExternalLink size={12} /></button>
          </div>
          <div className="flex-1 min-h-0"><Screen session={active} asleep={st.asleep[active.id]} onNote={openNote} /></div>
          <div className="shrink-0 flex flex-col" style={{ height: strip ? '34%' : 32, borderTop: '1px solid var(--aq-line)', background: 'var(--aq-panel)' }}>
            <div className="h-[32px] shrink-0 flex items-center gap-2 px-8" role="tablist" aria-label={t('Strip')}>
              {STRIPS.map(([k, w, Icon]) => <button key={k} type="button" role="tab" aria-selected={strip === k} className="aq-btn" data-on={strip === k} onClick={() => setStrip(strip === k ? null : k)}><Icon size={12} />{w}</button>)}
            </div>
            {strip && (
              <div className="flex-1 min-h-0 flex flex-col">
                {strip === 'messages' && <Messages sessionId={active.id} onNote={openNote} onJump={jump} dense />}
                {strip === 'pins' && <div className="aq-scroll"><Pins project={project} onJump={jump} onNote={openNote} /></div>}
                {strip === 'servers' && <div className="flex-1 min-h-0 flex"><div className="w-[45%] p-6 aq-scroll"><Servers project={project} compact onOpen={setServer} /></div><div className="flex-1 min-w-0">{server && <ServerLog id={server} />}</div></div>}
                {strip === 'editor' && <Editor />}
                {strip === 'stats' && <div className="aq-scroll"><Stats /></div>}
              </div>
            )}
          </div>
        </main>
      </div>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={actions} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('find a chat, a task, a note')], ['alt 1…5', t('strip: messages, pins, servers, editor, stats')], ['alt W', t('next chat waiting on you')],
        ['alt S', t('sleep / wake the chat')], ['Esc', t('close the task card or the note')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
