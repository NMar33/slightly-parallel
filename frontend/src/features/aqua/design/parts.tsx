/**
 * The parts every variant arranges in its own way: the message list with
 * its marks and quick actions, pins, the task branches of a chat, a note
 * beside the terminal, the editor, the servers, the stats, the command
 * palette, the keymap, the restore after a reboot, detached windows and
 * the flash line. They paint with the variant's --aq-* tokens.
 */

import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ArrowUpRight, Copy, ExternalLink, FileText, Flag, GitFork, ListPlus, Minimize2, Pin, Play, RotateCcw, Square, X,
} from 'lucide-react'

import { t, tn } from '../../../i18n/scope/aqua'
import {
  FILES, HOURS, MESSAGES, NOTES, PROJECTS, SERVERS, SESSIONS, TASKS, messagesOf, noteOf, projectOf, serverOf, sessionOf, tasksFrom,
  type Message, type Session, type Task,
} from './mock'
import {
  closeRestore, cycleMark, dock, flash, restoreAll, toTask, toggleForkLater, toggleImportant, togglePin, toggleServer, useAqua,
  type AquaState,
} from './store'
import { Screen, fmtTokens } from './term'

/* ------------------------------------------------------------ keyboard */

const typing = (e: KeyboardEvent) => {
  const el = e.target as HTMLElement | null
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
}

/**
 * Keys for a variant: "mod+k" is Ctrl or Cmd with k, "alt+1" Alt, a bare
 * key works only when the focus is not in a text field.
 */
export function useKeys(map: Record<string, (e: KeyboardEvent) => void>) {
  const ref = useRef(map)
  ref.current = map
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mods = `${e.ctrlKey || e.metaKey ? 'mod+' : ''}${e.altKey ? 'alt+' : ''}${e.shiftKey && e.key.length > 1 ? 'shift+' : ''}`
      const key = `${mods}${e.key.length === 1 ? e.key.toLowerCase() : e.key}`
      const f = ref.current[key]
      if (!f) return
      if (!mods && typing(e) && e.key !== 'Escape') return
      e.preventDefault()
      f(e)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

/* ---------------------------------------------------------- small bits */

export type Shown = 'working' | 'waiting' | 'idle' | 'asleep'
export const shownState = (st: AquaState, s: Session): Shown => (st.asleep[s.id] ? 'asleep' : s.state)
export const STATE_WORD: Record<Shown, string> = { working: t('working'), waiting: t('your turn'), idle: t('idle'), asleep: t('asleep') }

export function StateDot({ s, st, size }: { s: Session; st: AquaState; size?: number }) {
  const k = shownState(st, s)
  return <span className={`aq-dot ${k}`} title={STATE_WORD[k]} aria-label={STATE_WORD[k]} style={size ? { width: size, height: size } : undefined} />
}

export function ToolBadge({ s }: { s: Session }) {
  return <span className="aq-chip" title={s.tool === 'codex' ? 'Codex' : 'Claude Code'} style={s.tool === 'codex' ? { color: 'var(--aq-ink)' } : undefined}>{s.tool === 'codex' ? 'cx' : 'cc'}</span>
}

export function ProjectSwatch({ code, size = 10 }: { code: string; size?: number }) {
  const p = projectOf(code)
  return <span aria-hidden className="inline-block shrink-0 rounded-[3px]" style={{ width: size, height: size, background: `oklch(0.72 0.12 ${p.hue})` }} />
}

export const projectTint = (code: string, a = 0.16) => `oklch(0.72 0.12 ${projectOf(code).hue} / ${a})`
export const projectInk = (code: string) => `oklch(0.75 0.12 ${projectOf(code).hue})`

export function Kbd({ children }: { children: ReactNode }) { return <kbd className="aq-kbd">{children}</kbd> }

export function MemoryLight({ m, onClick }: { m: Message['mark']; onClick?: () => void }) {
  const word = m === 'red' ? t('carried whole over a compaction') : m === 'yellow' ? t('carried as a brief over a compaction') : t('not carried')
  return (
    <button type="button" className="aq-light cursor-pointer" data-m={m ?? ''} title={word} aria-label={word} onClick={(e) => { e.stopPropagation(); onClick?.() }} />
  )
}

/* ------------------------------------------------------------ messages */

/** What the rule beside a message says: carried whole, carried as a brief, not carried over a compaction. */
export function CarryKey({ className = 'px-14 pb-4' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-12 text-10 font-mono aq-ink3 ${className}`}>
      <span className="flex items-center gap-4"><span className="aq-light-key" data-m="red" />{t('carried whole')}</span>
      <span className="flex items-center gap-4"><span className="aq-light-key" data-m="yellow" />{t('carried as a brief')}</span>
      <span className="flex items-center gap-4"><span className="aq-light-key" />{t('not carried')}</span>
    </div>
  )
}

type Filter = 'all' | 'pinned' | 'marked' | 'fork'

/**
 * A chat's messages as SP captured them: one row each, an index rather
 * than a second transcript. Hover or focus shows the quick actions; the
 * keys p, i, t, f and m do the same on a focused row.
 */
export function Messages({ sessionId, onNote, onJump, dense = false, initial = 'all' }: {
  sessionId: string; onNote?: (id: string) => void; onJump?: (m: Message) => void; dense?: boolean; initial?: Filter
}) {
  const st = useAqua()
  const [filter, setFilter] = useState<Filter>(initial)
  const all = messagesOf(sessionId)
  const rows = all.filter((m) => filter === 'all' || (filter === 'pinned' && st.pinned[m.id]) || (filter === 'marked' && st.marks[m.id]) || (filter === 'fork' && st.forkLater[m.id]))
  const counts: Record<Filter, number> = {
    all: all.length, pinned: all.filter((m) => st.pinned[m.id]).length, marked: all.filter((m) => st.marks[m.id]).length, fork: all.filter((m) => st.forkLater[m.id]).length,
  }
  const words: Record<Filter, string> = { all: t('All'), pinned: t('Pinned'), marked: t('Carried'), fork: t('Fork later') }
  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="flex items-center gap-2 px-8 py-6 shrink-0 flex-wrap" role="tablist" aria-label={t('Which messages')}>
        {(Object.keys(words) as Filter[]).map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className="aq-btn" data-on={filter === f}
            onClick={() => setFilter(f)}>{words[f]} <span className="aq-ink3 tabular-nums">{counts[f]}</span></button>
        ))}
      </div>
      <CarryKey />
      <ol className="m-0 p-0 list-none flex-1 min-h-0 aq-scroll px-6 pb-8 flex flex-col gap-2">
        {rows.map((m) => <MessageRow key={m.id} m={m} st={st} onNote={onNote} onJump={onJump} dense={dense} />)}
        {!rows.length && <li className="aq-ink3 text-12 p-12">{t('Nothing here in this chat.')}</li>}
      </ol>
    </div>
  )
}

export function MessageRow({ m, st, onNote, onJump, dense }: { m: Message; st: AquaState; onNote?: (id: string) => void; onJump?: (m: Message) => void; dense?: boolean }) {
  const tk = st.tasked[m.id]
  const onKey = (e: React.KeyboardEvent) => {
    const k = e.key.toLowerCase()
    if (k === 'p') togglePin(m.id)
    else if (k === 'i') toggleImportant(m.id)
    else if (k === 't') toTask(m.id)
    else if (k === 'f') toggleForkLater(m.id)
    else if (k === 'm') cycleMark(m.id)
    else if (k === 'enter') { if (m.note) onNote?.(m.note); else onJump?.(m) }
    else return
    e.preventDefault()
  }
  return (
    <li className="group aq-row items-stretch px-6 py-6 relative" tabIndex={0} onKeyDown={onKey} aria-label={m.text}
      onClick={() => onJump?.(m)} data-pinned={st.pinned[m.id] || undefined}>
      <MemoryLight m={st.marks[m.id] ?? null} onClick={() => cycleMark(m.id)} />
      <div className="flex-1 min-w-0 flex flex-col gap-2">
        <div className="flex items-center gap-6 text-10 font-mono aq-ink3">
          <span style={{ color: m.who === 'you' ? 'var(--aq-accent)' : undefined }}>{m.who === 'you' ? t('you') : t('agent')}</span>
          <span>{m.at}</span>
          {st.pinned[m.id] && <Pin size={11} className="aq-accent" aria-label={t('pinned')} />}
          {st.important[m.id] && <Flag size={11} style={{ color: 'var(--aq-important)' }} aria-label={t('important')} />}
          {st.forkLater[m.id] && <span className="aq-chip" style={{ color: 'var(--aq-fork)' }}><GitFork size={10} />{t('fork later')}</span>}
          {tk && <span className="aq-chip">{tk}</span>}
        </div>
        <div className={`${dense ? 'text-12 line-clamp-2' : 'text-13 line-clamp-3'} leading-snug`} style={{ color: 'var(--aq-ink)' }}>{m.text}</div>
        {m.note && (
          <button type="button" className="aq-btn line self-start" onClick={(e) => { e.stopPropagation(); onNote?.(m.note!) }}>
            <FileText size={12} />{noteOf(m.note)?.title}
          </button>
        )}
      </div>
      <div className="absolute right-4 top-4 hidden group-hover:flex group-focus-within:flex gap-1 aq-raise rounded-[6px] p-2 shadow-sm">
        <ActionBtn on={st.pinned[m.id]} label={t('Pin (p)')} onClick={() => togglePin(m.id)}><Pin size={13} /></ActionBtn>
        <ActionBtn on={st.important[m.id]} label={t('Important (i)')} onClick={() => toggleImportant(m.id)}><Flag size={13} /></ActionBtn>
        <ActionBtn on={!!tk} label={t('To a task (t)')} onClick={() => toTask(m.id)}><ListPlus size={13} /></ActionBtn>
        <ActionBtn on={st.forkLater[m.id]} label={t('Fork later (f)')} onClick={() => toggleForkLater(m.id)}><GitFork size={13} /></ActionBtn>
        <ActionBtn label={t('Copy')} onClick={() => { try { void navigator.clipboard?.writeText(m.text) } catch { /* mock */ } flash(t('Message copied')) }}><Copy size={13} /></ActionBtn>
      </div>
    </li>
  )
}

function ActionBtn({ on, label, onClick, children }: { on?: boolean; label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="aq-btn icon" aria-pressed={!!on} title={label} aria-label={label}
      onClick={(e) => { e.stopPropagation(); onClick() }}>{children}</button>
  )
}

/* ---------------------------------------------------------------- pins */

/** Pinned messages: the master message and the few others to come back to, by chat. */
export function Pins({ project, onJump, onNote }: { project?: string; onJump?: (m: Message) => void; onNote?: (id: string) => void }) {
  const st = useAqua()
  const pinned = MESSAGES.filter((m) => st.pinned[m.id] && (!project || sessionOf(m.session)?.project === project))
  const by = SESSIONS.filter((s) => pinned.some((m) => m.session === s.id))
  if (!pinned.length) return <p className="aq-ink3 text-12 p-12 m-0">{t('No pins. Pin a message with p, or the pin on its row.')}</p>
  return (
    <div className="flex flex-col gap-10 p-8 aq-scroll min-h-0">
      {by.map((s) => (
        <section key={s.id} className="flex flex-col gap-4">
          <div className="flex items-center gap-6 aq-label"><ProjectSwatch code={s.project} size={8} />{s.name}</div>
          <ol className="m-0 p-0 list-none flex flex-col gap-2">
            {pinned.filter((m) => m.session === s.id).map((m) => <MessageRow key={m.id} m={m} st={st} onJump={onJump} onNote={onNote} dense />)}
          </ol>
        </section>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------ branches */

const STATUS_INK: Record<Task['status'], string> = { todo: 'var(--aq-ink3)', doing: 'var(--aq-accent)', done: 'var(--aq-up)' }

/**
 * How work branched from a chat: the tasks it spawned (by the board's
 * parent links), the background agents and forks to other chats, and the
 * messages queued to fork later.
 */
export function Branches({ sessionId, onChat }: { sessionId: string; onChat?: (id: string) => void }) {
  const st = useAqua()
  const s = sessionOf(sessionId)!
  const tasks = tasksFrom(sessionId)
  const roots = tasks.filter((x) => !x.parent || !tasks.some((y) => y.id === x.parent))
  const made = Object.entries(st.tasked).filter(([mid]) => MESSAGES.find((m) => m.id === mid)?.session === sessionId).map(([, tk]) => tk)
  const queued = MESSAGES.filter((m) => m.session === sessionId && st.forkLater[m.id])
  const node = (x: Task, depth: number): ReactNode => (
    <Fragment key={x.id}>
      <li className="flex items-center gap-8 min-w-0 py-4" style={{ paddingLeft: 14 + depth * 18 }}>
        <svg width="14" height="14" aria-hidden className="shrink-0 -ml-16"><path d="M1 0 V7 H13" fill="none" stroke="var(--aq-line)" strokeWidth="1.5" /></svg>
        <span className="aq-dot" style={{ background: STATUS_INK[x.status] }} />
        <span className="text-12 truncate" style={{ color: 'var(--aq-ink)' }}>{x.title}</span>
        <span className="aq-chip">{x.id}</span>
        {x.via && <span className="text-10 font-mono aq-ink3 shrink-0">{x.via}</span>}
        {x.chat && x.chat !== sessionId && (
          <button type="button" className="aq-btn shrink-0" onClick={() => onChat?.(x.chat!)}><ArrowUpRight size={12} />{sessionOf(x.chat)?.name}</button>
        )}
      </li>
      {tasks.filter((y) => y.parent === x.id).map((y) => node(y, depth + 1))}
    </Fragment>
  )
  return (
    <div className="flex flex-col gap-8 p-10 aq-scroll min-h-0">
      <div className="flex items-center gap-8"><StateDot s={s} st={st} /><b className="text-13">{s.name}</b><span className="aq-chip">{s.id}</span></div>
      <ol className="m-0 p-0 list-none flex flex-col border-l ml-4 aq-line" aria-label={t('Tasks from this chat')}>
        {roots.map((x) => node(x, 0))}
        {made.map((tk) => (
          <li key={tk} className="flex items-center gap-8 py-4 pl-14 aq-fade">
            <svg width="14" height="14" aria-hidden className="shrink-0 -ml-16"><path d="M1 0 V7 H13" fill="none" stroke="var(--aq-line)" strokeWidth="1.5" /></svg>
            <span className="aq-dot" style={{ background: STATUS_INK.todo }} /><span className="text-12">{t('from a message')}</span><span className="aq-chip">{tk}</span>
          </li>
        ))}
      </ol>
      {queued.length > 0 && (
        <div className="flex flex-col gap-4 mt-4">
          <div className="aq-label flex items-center gap-6" style={{ color: 'var(--aq-fork)' }}><GitFork size={11} />{t('Queued to fork')}</div>
          {queued.map((m) => (
            <div key={m.id} className="aq-raise rounded-[8px] p-8 flex items-start gap-8">
              <span className="text-12 flex-1 line-clamp-2">{m.text}</span>
              <button type="button" className="aq-btn line shrink-0" onClick={() => { toggleForkLater(m.id); flash(t('Handed to a new agent with the chat\'s briefing')) }}>
                <Play size={12} />{t('Hand to an agent')}</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- note */

function inline(text: string): ReactNode {
  return text.split(/(`[^`]+`)/).map((p, i) => (p.startsWith('`') ? <code key={i} className="font-mono text-[0.9em] px-4 rounded-[4px]" style={{ background: 'var(--aq-hover)' }}>{p.slice(1, -1)}</code> : p))
}

/** A note an agent wrote, at reading width: the long text that does not belong in the terminal. */
export function NoteBody({ id, size = 14 }: { id: string; size?: number }) {
  const n = noteOf(id)
  if (!n) return null
  const out: ReactNode[] = []
  const lines = n.body.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i]!
    if (l.startsWith('```')) {
      const code: string[] = []
      for (i++; i < lines.length && !lines[i]!.startsWith('```'); i++) code.push(lines[i]!)
      out.push(<pre key={i} className="font-mono text-12 p-10 rounded-[8px] m-0 overflow-x-auto" style={{ background: 'var(--aq-term-bg)', color: 'var(--aq-term-fg)' }}>{code.join('\n')}</pre>)
    } else if (l.startsWith('# ')) out.push(<h2 key={i} className="m-0 text-20 font-semibold" style={{ color: 'var(--aq-ink)' }}>{l.slice(2)}</h2>)
    else if (l.startsWith('## ')) out.push(<h3 key={i} className="m-0 mt-8 text-11 font-mono uppercase tracking-wide aq-accent">{l.slice(3)}</h3>)
    else if (/^(- |\d+\. )/.test(l)) out.push(<div key={i} className="flex gap-8 pl-4"><span className="aq-ink3 font-mono">{l.startsWith('- ') ? '–' : l.match(/^\d+/)![0]}</span><span>{inline(l.replace(/^(- |\d+\. )/, ''))}</span></div>)
    else if (l.trim()) out.push(<p key={i} className="m-0">{inline(l)}</p>)
  }
  return <article className="flex flex-col gap-8 leading-relaxed" style={{ fontSize: size, color: 'var(--aq-ink2)', maxWidth: 680 }}>{out}</article>
}

export function NoteMeta({ id }: { id: string }) {
  const n = noteOf(id)
  if (!n) return null
  return (
    <div className="flex items-center gap-6 flex-wrap text-11 aq-ink3 font-mono">
      <span>{n.id}</span><span>·</span><span>{sessionOf(n.session)?.name}</span><span>·</span><span>{n.at}</span><span>·</span><span>{tn(n.words, '{n} word', '{n} words')}</span>
    </div>
  )
}

/* -------------------------------------------------------------- editor */

/**
 * A plain editor in the same window: a file the agent just changed opens
 * here with the changed lines marked; a scratch NOTES.md for the operator.
 */
export function Editor({ initial = 'slots', size = 13 }: { initial?: keyof typeof FILES; size?: number }) {
  const [file, setFile] = useState<keyof typeof FILES>(initial)
  const [texts, setTexts] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(FILES).map(([k, f]) => [k, f.text])))
  const dirty = (k: string) => texts[k] !== FILES[k]!.text
  const lines = texts[file]!.split('\n')
  const changed = file === 'slots' ? [4, 5] : []
  return (
    <div className="flex flex-col min-h-0 h-full aq-term" style={{ fontSize: size }}>
      <div className="flex items-end gap-2 px-6 pt-4 shrink-0" role="tablist" aria-label={t('Open files')} style={{ background: 'var(--aq-panel)' }}>
        {Object.entries(FILES).map(([k, f]) => (
          <button key={k} type="button" role="tab" aria-selected={file === k} className="aq-tab" onClick={() => setFile(k)}>
            {f.path.split('/').pop()}{dirty(k) && <span className="aq-dot" style={{ width: 6, height: 6, background: 'var(--aq-ink2)' }} aria-label={t('unsaved')} />}
            {k === 'slots' && <span className="text-10" style={{ color: 'var(--aq-term-claude)' }}>{t('agent')}</span>}
          </button>
        ))}
        <span className="ml-auto text-10 font-mono aq-ink3 pb-6 pr-6 truncate">{FILES[file]!.path}</span>
      </div>
      <div className="flex-1 min-h-0 flex aq-scroll">
        <div className="select-none text-right pr-8 pl-8 pt-8 dim shrink-0" aria-hidden>
          {lines.map((_, i) => <div key={i} style={{ borderLeft: changed.includes(i) ? '2px solid var(--aq-term-ok)' : '2px solid transparent', paddingLeft: 4 }}>{i + 1}</div>)}
        </div>
        <textarea aria-label={FILES[file]!.path} spellCheck={false} value={texts[file]} wrap="off"
          onChange={(e) => setTexts({ ...texts, [file]: e.target.value })}
          onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); FILES[file]!.text = texts[file]!; setTexts({ ...texts }); flash(`${t('Saved')} ${FILES[file]!.path}`) } }}
          className="flex-1 min-w-0 resize-none bg-transparent outline-none border-0 pt-8 font-mono"
          style={{ color: 'inherit', fontSize: 'inherit', lineHeight: 1.5, tabSize: 2 }} rows={lines.length + 2} />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- servers */

/** The project's local servers, from its entry points' ways in: apart from the agent chats. */
export function Servers({ project, onOpen, compact = false }: { project?: string; onOpen?: (id: string) => void; compact?: boolean }) {
  const st = useAqua()
  const list = SERVERS.filter((s) => !project || s.project === project)
  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-2">
      {list.map((s) => {
        const up = st.up[s.id]
        return (
          <li key={s.id} className="aq-row px-8 py-6" onClick={() => onOpen?.(s.id)}>
            <span className={`aq-dot ${up ? 'up' : 'down'}`} aria-label={up ? t('up') : t('down')} />
            {!project && <ProjectSwatch code={s.project} size={8} />}
            <span className="text-12 truncate" style={{ color: 'var(--aq-ink)' }}>{s.name}</span>
            {s.port && <span className="aq-chip">:{s.port}</span>}
            {!compact && <code className="text-11 aq-ink3 truncate min-w-0 flex-1">{s.command}</code>}
            <button type="button" className="aq-btn icon ml-auto shrink-0" title={up ? t('Stop') : t('Start')} aria-label={`${up ? t('Stop') : t('Start')} ${s.name}`}
              onClick={(e) => { e.stopPropagation(); toggleServer(s.id) }}>{up ? <Square size={12} /> : <Play size={12} />}</button>
          </li>
        )
      })}
    </ul>
  )
}

/** A server's own terminal: its log, opaque, with the way in on top. */
export function ServerLog({ id, size = 12 }: { id: string; size?: number }) {
  const st = useAqua()
  const s = serverOf(id)
  if (!s) return null
  const up = st.up[s.id]
  return (
    <div className="aq-term h-full flex flex-col min-h-0" style={{ fontSize: size }}>
      <div className="flex items-center gap-8 px-10 py-6 shrink-0" style={{ borderBottom: '1px solid var(--aq-term-box)' }}>
        <span className={`aq-dot ${up ? 'up' : 'down'}`} />
        <b className="font-semibold">{s.name}</b>
        <span className="dim truncate">{s.folder} $ {s.command}</span>
        {s.port && <span className="link ml-auto" role="button" tabIndex={0} onClick={() => flash(`${t('Opens in the browser:')} http://localhost:${s.port}`)}>localhost:{s.port}</span>}
        <button type="button" className="aq-btn" onClick={() => toggleServer(s.id)}>{up ? t('Stop') : t('Start')}</button>
      </div>
      <div className="flex-1 min-h-0 aq-scroll p-10 flex flex-col justify-end">
        {(up ? s.log : [...s.log.slice(0, 1), t('— stopped —')]).map((l, i) => <div key={i} className="whitespace-pre-wrap">{l}</div>)}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- stats */

/** The day so far: your time at the keyboard matched against the agents' working time; tokens; by project. */
export function Stats({ compact = false }: { compact?: boolean }) {
  const st = useAqua()
  const you = HOURS.reduce((a, h) => a + h.you, 0)
  const agents = HOURS.reduce((a, h) => a + h.agents, 0)
  const tokens = SESSIONS.reduce((a, s) => a + s.tokens, 0)
  const waiting = SESSIONS.filter((s) => s.state === 'waiting' && !st.asleep[s.id]).length
  const max = Math.max(...HOURS.map((h) => Math.max(h.you, h.agents)))
  const hm = (m: number) => `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}`
  const tiles: Array<[string, string, string]> = [
    [t('You, at the keyboard'), hm(you), t('since 08:00')],
    [t('Agents working'), hm(agents), tn(SESSIONS.filter((s) => !st.asleep[s.id]).length, '{n} chat awake', '{n} chats awake')],
    [t('Tokens today'), fmtTokens(tokens), '≈ $41'],
    [t('Waiting on you'), String(waiting), waiting ? t('oldest 12 min') : t('nobody')],
  ]
  return (
    <div className="flex flex-col gap-14 p-12">
      <div className={`grid gap-8 ${compact ? 'grid-cols-2' : 'grid-cols-4'}`}>
        {tiles.map(([k, v, sub]) => (
          <div key={k} className="aq-raise rounded-[10px] p-10 flex flex-col gap-2">
            <span className="aq-label">{k}</span>
            <span className="text-24 font-semibold tabular-nums" style={{ color: 'var(--aq-ink)' }}>{v}</span>
            <span className="text-11 aq-ink3">{sub}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-6">
        <span className="aq-label">{t('By hour: you and the agents')}</span>
        <div className="flex items-end gap-12 h-[96px]" role="img" aria-label={t('By hour: you and the agents')}>
          {HOURS.map((h) => (
            <div key={h.h} className="flex flex-col items-center gap-4 flex-1 h-full justify-end">
              <div className="flex items-end gap-3 w-full justify-center h-full">
                <div style={{ height: `${(h.you / max) * 100}%`, width: 10, background: 'var(--aq-ink2)', borderRadius: 3 }} title={`${t('you')} ${h.you}m`} />
                <div style={{ height: `${(h.agents / max) * 100}%`, width: 10, background: 'var(--aq-accent)', borderRadius: 3 }} title={`${t('agents')} ${h.agents}m`} />
              </div>
              <span className="text-10 font-mono aq-ink3">{h.h}:00</span>
            </div>
          ))}
        </div>
        <div className="flex gap-12 text-11 aq-ink3"><span><span className="aq-dot" style={{ background: 'var(--aq-ink2)' }} /> {t('you')}</span><span><span className="aq-dot" style={{ background: 'var(--aq-accent)' }} /> {t('agent-minutes')}</span></div>
      </div>
      <div className="flex flex-col gap-6">
        <span className="aq-label">{t('By project')}</span>
        {PROJECTS.map((p) => {
          const ss = SESSIONS.filter((s) => s.project === p.code)
          const mins = ss.reduce((a, s) => a + s.today, 0)
          const tok = ss.reduce((a, s) => a + s.tokens, 0)
          return (
            <div key={p.code} className="flex items-center gap-8 text-12">
              <ProjectSwatch code={p.code} />
              <span className="w-[110px] truncate" style={{ color: 'var(--aq-ink)' }}>{p.name}</span>
              <div className="flex-1 h-6 rounded-[3px] overflow-hidden" style={{ background: 'var(--aq-hover)' }}>
                <div style={{ width: `${Math.min(100, (mins / 240) * 100)}%`, height: '100%', background: projectInk(p.code) }} />
              </div>
              <span className="w-[56px] text-right tabular-nums aq-ink2">{hm(mins)}</span>
              <span className="w-[56px] text-right tabular-nums aq-ink3">{fmtTokens(tok)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- palette */

export interface Action { id: string; label: string; group: string; kbd?: string; run: () => void }

function score(q: string, s: string): number {
  if (!q) return 1
  const a = s.toLowerCase()
  const b = q.toLowerCase()
  if (a.includes(b)) return 3 - a.indexOf(b) / 100
  let i = 0
  for (const ch of a) if (ch === b[i]) i++
  return i === b.length ? 1 : 0
}

/** Ctrl+K: every chat, server, note and action, found by a few letters, run with Enter. */
export function Palette({ open, onClose, actions, placeholder }: { open: boolean; onClose: () => void; actions: Action[]; placeholder?: string }) {
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const found = useMemo(() => actions.map((a) => [a, score(q, `${a.label} ${a.group}`)] as const).filter(([, s]) => s > 0).sort((x, y) => y[1] - x[1]).slice(0, 12).map(([a]) => a), [actions, q])
  useEffect(() => { setI(0) }, [q])
  useEffect(() => { if (!open) setQ('') }, [open])
  if (!open) return null
  const run = (a?: Action) => { if (!a) return; onClose(); a.run() }
  return (
    <div className="absolute inset-0 z-[40] flex items-start justify-center pt-[12vh]" role="dialog" aria-label={t('Command palette')}>
      <button type="button" aria-label={t('Close')} className="absolute inset-0 cursor-default" style={{ background: 'oklch(0 0 0 / 0.28)' }} onClick={onClose} />
      <div className="relative aq-glass aq-float rounded-[14px] w-[620px] max-w-[92%] overflow-hidden aq-fade">
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder ?? t('Go to a chat, a server, a note, or run…')}
          aria-label={t('Command')}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setI((n) => Math.min(n + 1, found.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setI((n) => Math.max(n - 1, 0)) }
            else if (e.key === 'Enter') run(found[i])
            else if (e.key === 'Escape') onClose()
          }}
          className="w-full bg-transparent border-0 outline-none px-16 py-14 text-16" style={{ color: 'var(--aq-ink)', borderBottom: '1px solid var(--aq-glass-line)' }} />
        <ul className="m-0 p-6 list-none max-h-[52vh] aq-scroll" role="listbox" aria-label={t('Results')}>
          {found.map((a, n) => (
            <li key={a.id} role="option" aria-selected={n === i} className="aq-row px-10 py-8 text-13" onMouseEnter={() => setI(n)} onClick={() => run(a)}>
              <span className="aq-label w-[72px] shrink-0">{a.group}</span>
              <span className="truncate flex-1" style={{ color: 'var(--aq-ink)' }}>{a.label}</span>
              {a.kbd && <Kbd>{a.kbd}</Kbd>}
            </li>
          ))}
          {!found.length && <li className="p-12 text-12 aq-ink3">{t('Nothing matches.')}</li>}
        </ul>
      </div>
    </div>
  )
}

/** The common entries of every variant's palette; a variant adds its own. */
export function commonActions(go: (id: string) => void, extra: { note?: (id: string) => void; server?: (id: string) => void } = {}): Action[] {
  return [
    ...SESSIONS.map((s) => ({ id: `go-${s.id}`, group: t('chat'), label: `${projectOf(s.project).name} › ${s.name}`, run: () => go(s.id) })),
    ...SERVERS.map((s) => ({ id: `sv-${s.id}`, group: t('server'), label: `${projectOf(s.project).name} › ${s.name}${s.port ? ` :${s.port}` : ''}`, run: () => (extra.server ? extra.server(s.id) : toggleServer(s.id)) })),
    ...NOTES.map((n) => ({ id: `nt-${n.id}`, group: t('note'), label: n.title, run: () => extra.note?.(n.id) })),
    ...TASKS.filter((x) => x.status !== 'done').map((x) => ({ id: `tk-${x.id}`, group: t('task'), label: `${x.title} · ${x.id}`, run: () => go(x.chat ?? x.from) })),
  ]
}

/* -------------------------------------------------------------- keymap */

export function Keymap({ open, onClose, keys }: { open: boolean; onClose: () => void; keys: Array<[string, string]> }) {
  if (!open) return null
  return (
    <div className="absolute inset-0 z-[40] flex items-center justify-center" role="dialog" aria-label={t('Keys')}>
      <button type="button" aria-label={t('Close')} className="absolute inset-0 cursor-default" style={{ background: 'oklch(0 0 0 / 0.3)' }} onClick={onClose} />
      <div className="relative aq-glass aq-float rounded-[14px] p-20 aq-fade w-[640px] max-w-[92%]">
        <div className="flex items-center mb-12"><b className="text-14">{t('Keys')}</b><button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={14} /></button></div>
        <dl className="m-0 grid grid-cols-2 gap-x-24 gap-y-6">
          {keys.map(([k, what]) => (
            <div key={k} className="flex items-center gap-10 text-12">
              <dt className="w-[110px] shrink-0 flex gap-2 flex-wrap">{k.split(' ').map((x) => <Kbd key={x}>{x}</Kbd>)}</dt>
              <dd className="m-0 aq-ink2">{what}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

export const MESSAGE_KEYS: Array<[string, string]> = [
  ['p', t('pin the focused message')], ['i', t('mark it important')], ['t', t('make it a task')], ['f', t('fork it later')], ['m', t('cycle its carry light')],
]

/* ------------------------------------------------------------- restore */

/**
 * After a reboot: one button brings back the servers and every chat that
 * was awake, each resumed by its session id; one whose id is gone fails
 * and offers a fresh start with the topic's briefing.
 */
export function Restore({ className = '' }: { className?: string }) {
  const st = useAqua()
  if (!st.rebooted && !st.restore) return null
  const steps = st.restore
  const done = steps && Object.values(steps).every((x) => x === 'ok' || x === 'fail')
  const failed = steps ? Object.entries(steps).filter(([, x]) => x === 'fail').map(([id]) => id) : []
  return (
    <div className={`aq-glass aq-float rounded-[12px] p-12 flex flex-col gap-8 aq-fade ${className}`} role="status">
      <div className="flex items-center gap-10">
        <RotateCcw size={16} className="aq-accent" />
        <b className="text-13">{steps ? (done ? t('Restored') : t('Restoring…')) : t('The machine restarted. Your layout is kept; nothing runs.')}</b>
        {!steps && <button type="button" className="aq-btn solid ml-auto" onClick={() => restoreAll()}>{t('Restore all')} <Kbd>⏎</Kbd></button>}
        {done && <button type="button" className="aq-btn ml-auto" onClick={closeRestore}>{t('Close')}</button>}
      </div>
      {!steps && <span className="text-12 aq-ink2">{tn(SERVERS.filter((s) => s.up).length, '{n} server', '{n} servers')} · {tn(SESSIONS.filter((s) => !s.asleep).length, '{n} chat that was awake', '{n} chats that were awake')} · {t('sleeping chats stay asleep')}</span>}
      {steps && (
        <ul className="m-0 p-0 list-none grid grid-cols-2 gap-x-16 gap-y-2">
          {Object.entries(steps).map(([id, x]) => {
            const s = sessionOf(id)!
            return (
              <li key={id} className="flex items-center gap-6 text-11 font-mono">
                <span style={{ color: x === 'ok' ? 'var(--aq-up)' : x === 'fail' ? 'var(--aq-down)' : 'var(--aq-ink3)' }}>{x === 'ok' ? '✓' : x === 'fail' ? '✕' : x === 'run' ? '…' : '·'}</span>
                <span className="truncate aq-ink2">{s.name}</span>
              </li>
            )
          })}
        </ul>
      )}
      {done && failed.length > 0 && (
        <span className="text-12" style={{ color: 'var(--aq-down)' }}>{sessionOf(failed[0]!)!.name}: {t('session id gone; start fresh with the topic\'s briefing from the chat\'s view.')}</span>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ detached */

/**
 * Detached windows: what the real app opens as a separate OS window (on a
 * second screen, say) is drawn here as a floating window you can drag.
 * The button on its bar docks it back.
 */
export function Detached({ size = 13 }: { size?: number }) {
  const st = useAqua()
  return <>{st.detached.map((k, i) => <Floating key={k} id={k} index={i} size={size} />)}</>
}

export const detachedTitle = (k: string) => {
  const [kind, id] = k.split(':')
  if (kind === 'term') return sessionOf(id!)?.name ?? k
  if (kind === 'note') return noteOf(id!)?.title ?? k
  if (kind === 'server') return serverOf(id!)?.name ?? k
  if (kind === 'editor') return t('Editor')
  if (kind === 'stats') return t('Stats')
  return k
}

function Floating({ id, index, size }: { id: string; index: number; size: number }) {
  const st = useAqua()
  const [pos, setPos] = useState({ x: 120 + index * 36, y: 90 + index * 30 })
  const drag = useRef<{ dx: number; dy: number } | null>(null)
  const [kind, ref] = id.split(':')
  const s = kind === 'term' ? sessionOf(ref!) : undefined
  const body = kind === 'term' && s ? <Screen session={s} asleep={st.asleep[s.id]} size={size} focused={false} inWindow />
    : kind === 'note' ? <div className="p-16 aq-scroll h-full" style={{ background: 'var(--aq-panel)' }}><NoteMeta id={ref!} /><div className="mt-10"><NoteBody id={ref!} /></div></div>
      : kind === 'server' ? <ServerLog id={ref!} />
        : kind === 'editor' ? <Editor />
          : kind === 'stats' ? <div className="aq-scroll h-full" style={{ background: 'var(--aq-panel)' }}><Stats compact /></div> : null
  return (
    <div className="absolute z-[30] rounded-[10px] overflow-hidden flex flex-col aq-fade aq-float" role="dialog" aria-label={`${t('Detached window')}: ${detachedTitle(id)}`}
      style={{ left: pos.x, top: pos.y, width: 560, height: 380, background: 'var(--aq-panel)' }}>
      <div className="flex items-center gap-8 px-10 h-[30px] shrink-0 cursor-grab select-none aq-glass" style={{ borderWidth: 0, borderBottomWidth: 1 }}
        onPointerDown={(e) => { drag.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y }; (e.target as HTMLElement).setPointerCapture?.(e.pointerId) }}
        onPointerMove={(e) => { if (drag.current) setPos({ x: e.clientX - drag.current.dx, y: e.clientY - drag.current.dy }) }}
        onPointerUp={() => { drag.current = null }}>
        <ExternalLink size={12} className="aq-ink3" />
        <span className="text-12 truncate" style={{ color: 'var(--aq-ink)' }}>{detachedTitle(id)}</span>
        <span className="text-10 aq-ink3 font-mono">{t('own window')}</span>
        <button type="button" className="aq-btn ml-auto" onClick={() => dock(id)} onPointerDown={(e) => e.stopPropagation()}><Minimize2 size={12} />{t('Dock back')}</button>
      </div>
      <div className="flex-1 min-h-0">{body}</div>
    </div>
  )
}

/* --------------------------------------------------------------- flash */

const FLASH_VISIBLE_MS = 2600

export function Flash() {
  const st = useAqua()
  const [shown, setShown] = useState<number | null>(null)
  useEffect(() => {
    if (!st.flash) return
    setShown(st.flash.n)
    const h = setTimeout(() => setShown(null), FLASH_VISIBLE_MS)
    return () => clearTimeout(h)
  }, [st.flash])
  if (!st.flash || shown !== st.flash.n) return null
  return (
    <div className="absolute bottom-48 left-1/2 -translate-x-1/2 z-[50] aq-glass rounded-[999px] px-14 py-6 text-12 shadow-lg aq-fade" role="status"
      style={{ color: 'var(--aq-ink)' }}>{st.flash.text}</div>
  )
}

/* ------------------------------------------------------------ titlebar */

/** The app window's own bar (Tauri, no system frame): a title in the middle and the three controls. */
export function WindowControls() {
  return (
    <div className="flex items-center gap-6 shrink-0" aria-hidden>
      {['oklch(0.70 0.17 25)', 'oklch(0.82 0.15 85)', 'oklch(0.75 0.15 150)'].map((c) => <span key={c} className="inline-block rounded-full" style={{ width: 11, height: 11, background: c }} />)}
    </div>
  )
}

export function sessionsWaiting(st: AquaState) { return SESSIONS.filter((s) => s.state === 'waiting' && !st.asleep[s.id]) }
export function nextWaiting(st: AquaState, from: string) {
  const w = sessionsWaiting(st)
  if (!w.length) return undefined
  const i = w.findIndex((s) => s.id === from)
  return w[(i + 1) % w.length]!.id
}

