/**
 * The message menu of the terminal window (tk_a9306fb1, tk_91fe214d,
 * tk_a69a8c7a, tk_5df68bcf): variant b «list» of the mockup
 * (`/aqua?v=k&msgmenu=b`), on the real terminal.
 *
 * - A right click on a message — the operator's or the agent's reply —
 *   opens a compact list: pin; carry after compaction (word for word / as
 *   a summary); hand over later; branch into a new window; make a task;
 *   copy. Which message a row is comes from match.ts, against the chat's
 *   record. A row that is no recorded message gets Copy only, and says so.
 *   «Меню терминала…» (or Shift + right click) is the screen's own menu.
 * - Ids are links: tk_… opens the task's menu (its card, its column, copy
 *   the id); nt_… opens the note right here, read and acted on in place
 *   (Esc closes); a decision, a Publish card, a core, a skill, an entry
 *   point, a chat's agent id and a commit hash open their card
 *   (IdCards.tsx, tk_b3edbd84). A hash is underlined only once the server
 *   says it is a commit of the terminal's project (records.CommitCheck).
 * - What an action did stays on the message as a small mark at the right
 *   end of its first row; a line at the bottom of the window says what
 *   happened (the window's own `say`).
 *
 * The page takes the right click before xterm, so tmux never shows its own
 * pane menu under ours; a left click on an id is the page's too. The rest
 * of the mouse is the terminal's (selecting, tmux, a program's mouse).
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { Terminal } from 'xterm'
import { AlignLeft, ChevronsDownUp, ChevronsUpDown, ClipboardPaste, Clock, Copy, ExternalLink, GitBranch, Globe, Layers, Link2, ListPlus, Pin, PinOff, Quote, SquareTerminal, X } from 'lucide-react'

import '../../notes/render/notes.css'
import { writeClipboard } from '../../../lib/useCopy'
import { msgTarget, type MsgRef } from '../../../lib/pins'
import { useAquaActions } from '../../aqua/app/api'
import { openWindow, post } from '../../aqua/app/bridge'
import { detachUrl } from '../../aqua/app/model'
import { toNote, useNotesFeed, type WireNote } from '../../notes/page/data'
import { ServerNoteEnv } from '../../notes/page/ServerEnv'
import { NoteRead } from '../../notes/render/reader'
import { getJson } from '../../../lib/getJson'
import { useQuery } from '@tanstack/react-query'
import { t, tn } from '../../../i18n/scope/msgmenu'
import type { ScreenApi, ScreenHooks } from '../Screen'
import { findIds, type FoundId, type IdKind } from './ids'
import { AgentCard, CommitCard, CoreCard, DecisionCard, EntryCard, PublishCard, SkillCard, type CardProps } from './IdCards'
import { lineCells } from './cells'
import { copyId, place, useFirstFocus } from './pop'
import { CommitCheck, pageAddress } from './records'
import { linkAt, type TermLink } from './links'
import { blocksOf, messageAt, type Found } from './match'
import { commandAt, commandSpans, forClaudeCode, type Command } from './commands'
import { CommandCopy, CommandScanner, type HoverFeed } from './CommandCopy'
import { rowTop, useView } from './rowAnchor'
import { foldSaid, messageRange, spansOf, type Span } from '../fold'
import { foldViewOf } from '../reader'
import { firstLine, marksOf, refOf, useChatRecord, useKept, useMessageActions, useTask, type CarryLevel, type MessageMarks } from './data'

const COLUMNS = ['todo', 'doing', 'done'] as const

type Open =
  | { kind: 'msg'; x: number; y: number; cx: number; cy: number; state: 'reading' | 'done'; found: Found | null; line: string; link: TermLink | null; cmd: Command | null
      /** The message's rows as fold.ts names them (collapse, expand), and the rows read: «collapse all replies» reads them again. */
      span?: Span | null; rows?: string[] }
  | { kind: 'id'; x: number; y: number; id: FoundId; card?: boolean }

/** What the layer hands the screen: its hooks, and where to put the screen's actions. */
export interface LayerSlot { hooks: ScreenHooks; bind: (api: ScreenApi | null) => void }

export { lineCells }

export function MessageLayer({ agentId, project, say, refocus, goTo, children }: {
  /** The chat in this terminal ("" — a shell: the right click stays the screen's). */
  agentId: string
  project: string
  /** A line at the bottom of the window: what an action did. */
  say: (text: string) => void
  /** The keyboard back to the terminal. */
  refocus: () => void
  /** Show a terminal of this window (a chat's card: «Go to its tab»); else it opens in a window of its own. */
  goTo?: (sid: string) => void
  children: (slot: LayerSlot) => ReactNode
}) {
  const root = useRef<HTMLDivElement>(null)
  const api = useRef<ScreenApi | null>(null)
  const terms = useRef(new Set<Terminal>())
  const [open, setOpen] = useState<Open | null>(null)
  const { record } = useChatRecord(agentId)
  const recordRef = useRef(record)
  recordRef.current = record
  const agentRef = useRef(agentId)
  agentRef.current = agentId
  const seq = useRef(0)
  // Which hashes printed here are commits of the project: asked once each, kept for the terminal's life.
  const check = useMemo(() => new CommitCheck(project), [project])
  const checkRef = useRef(check)
  checkRef.current = check
  // The commands each terminal shows (commands.ts), for the copy icon and the right click.
  const scanner = useMemo(() => new CommandScanner(() => recordRef.current), [])
  const feed = useRef<HoverFeed | null>(null)

  const at = (e: { clientX: number; clientY: number }) => {
    const r = root.current?.getBoundingClientRect()
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
  }

  const openId = useCallback((id: FoundId, e: { clientX: number; clientY: number }) => {
    const p = at(e)
    setOpen({ kind: 'id', id, x: p.x, y: p.y + 10, card: id.kind === 'note' })
  }, [])

  /** An id named inside a card: its own card or menu, where the card was. */
  const openRef = useCallback((id: string, kind: IdKind) => {
    setOpen((o) => ({ kind: 'id', id: { id, kind, start: 0, length: id.length }, x: o?.x ?? 40, y: o?.y ?? 40, card: kind === 'note' }))
  }, [])

  /** The id under a pointer, in whichever xterm it is over. */
  /** The row under a pointer, in whichever xterm it is over: its text, the cell of each character, the cell pointed at. */
  const rowAt = useCallback((e: MouseEvent): { text: string; cells: number[]; col: number } | null => {
    const host = (e.target as Element | null)?.closest?.('.xterm')
    const term = [...terms.current].find((x) => x.element === host)
    const scr = host?.querySelector('.xterm-screen')
    if (!term || !scr || !term.rows) return null
    const r = scr.getBoundingClientRect()
    const col = Math.floor(((e.clientX - r.left) / r.width) * term.cols)
    const row = Math.floor(((e.clientY - r.top) / r.height) * term.rows)
    const line = term.buffer.active.getLine(term.buffer.active.viewportY + row)
    if (!line) return null
    return { ...lineCells(line), col }
  }, [])
  const idAt = useCallback((e: MouseEvent): FoundId | null => {
    const got = rowAt(e)
    if (!got) return null
    const { text, cells, col } = got
    return findIds(text).find((f) => col >= cells[f.start]! && col <= cells[f.start + f.length - 1]!
      && (f.kind !== 'commit' || checkRef.current.known(f.id) === true)) ?? null
  }, [rowAt])
  /** The link under a right click: an id, a web address, a path the editor opens. */
  const termLinkAt = useCallback((e: MouseEvent): TermLink | null => {
    const got = rowAt(e)
    if (!got) return null
    const i = got.cells.findIndex((c) => c === got.col)
    if (i < 0) return null
    return linkAt(got.text, i, { commitOk: (sha) => checkRef.current.known(sha) === true, paths: !!api.current?.editor?.() })
  }, [rowAt])

  /** The command under a pointer: on the copy icon, the icon's; else by row and column. */
  const cmdAt = useCallback((e: MouseEvent): Command | null => {
    const el = e.target as Element | null
    const term = [...terms.current].find((x) => x.element === el?.closest?.('.xterm'))
    if (!term) return null
    return (el?.closest?.('.mm-cmd') ? scanner.onRow(term, e.clientY) : scanner.at(term, e.clientX, e.clientY))?.cmd ?? null
  }, [scanner])

  const taken = useRef(false)
  const hooks = useMemo<ScreenHooks>(() => ({
    terminal: (term, kind) => {
      for (const x of terms.current) if (!x.element?.isConnected) terms.current.delete(x)
      terms.current.add(term)
      void kind
      // The pointer over the terminal: the copy icon of the command under it.
      term.element?.addEventListener('mousemove', (e) => feed.current?.(term, e))
      term.element?.addEventListener('mouseleave', () => feed.current?.(term, null))
      term.registerLinkProvider({
        provideLinks(y, callback) {
          const line = term.buffer.active.getLine(y - 1)
          if (!line) { callback(undefined); return }
          const { text, cells } = lineCells(line)
          const found = findIds(text)
          const links = (fs: FoundId[]) => (fs.length ? fs.map((f) => ({
            range: { start: { x: cells[f.start]! + 1, y }, end: { x: cells[f.start + f.length - 1]! + 1, y } },
            text: f.id,
            decorations: { underline: true, pointerCursor: true },
            activate: (ev: MouseEvent) => openId(f, ev),
          })) : undefined)
          const sure = found.filter((f) => f.kind !== 'commit')
          const hashes = found.filter((f) => f.kind === 'commit')
          if (!hashes.length) { callback(links(sure)); return }
          // A hash is a link only when it is a commit of this project (the server says so, once per hash).
          const c = checkRef.current
          void Promise.all(hashes.map((f) => c.check(f.id))).then((ok) => callback(links([...sure, ...hashes.filter((_, i) => ok[i])].sort((a, b) => a.start - b.start))))
        },
      })
    },
    mouse: (e) => {
      // The copy icon is the page's: xterm (and tmux) never see a press on it.
      if ((e.target as Element | null)?.closest?.('.mm-cmd')) {
        if (e.type === 'mousedown') taken.current = true
        else taken.current = false
        return true
      }
      // The right button is the page's when the menu applies: tmux would show its own pane menu.
      if (e.button === 2 && !e.shiftKey && (agentRef.current || termLinkAt(e) || cmdAt(e))) return true
      if (e.button !== 0 || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return false
      if (e.type === 'mouseup') { const was = taken.current; taken.current = false; return was }
      const id = idAt(e)
      if (!id) return false
      taken.current = true
      openId(id, e)
      return true
    },
    contextMenu: (e) => {
      if (e.shiftKey) return false
      // A link under the pointer comes first: copy it, open it — then the message's items.
      const link = termLinkAt(e)
      // A command under the pointer, as the screen shows it (the icon's scan).
      const cmd = cmdAt(e)
      if (!agentRef.current && !link && !cmd) return false
      const p = at(e)
      const n = ++seq.current
      setOpen({ kind: 'msg', x: p.x, y: p.y, cx: e.clientX, cy: e.clientY, state: agentRef.current ? 'reading' : 'done', found: null, line: '', link, cmd })
      if (!agentRef.current) return true
      void (api.current?.rowsAt(e.clientX, e.clientY) ?? Promise.resolve(null)).then((rows) => {
        if (n !== seq.current) return
        const rec = recordRef.current
        const found = rows && rec ? messageAt(rows.rows, rows.at, rec) : null
        // The command on the clicked row, read in the whole history (a tmux pane's from tmux) when the screen's scan had none.
        const more = rows ? commandAt(commandSpans(rows.rows, rec, { from: rows.at, to: rows.at }), rows.at, null)?.cmd ?? null : null
        const span = rows ? messageRange(rows.rows.map((text) => ({ text })), rows.at) : null
        setOpen((o) => (o?.kind === 'msg' && n === seq.current ? { ...o, state: 'done', found, line: rows ? rows.rows[rows.at] ?? '' : '', cmd: o.cmd ?? more, span, rows: rows?.rows } : o))
      }, () => setOpen((o) => (o?.kind === 'msg' && n === seq.current ? { ...o, state: 'done' } : o)))
      return true
    },
  }), [openId, idAt, termLinkAt, cmdAt])

  const bind = useCallback((a: ScreenApi | null) => { api.current = a }, [])
  const slot = useMemo(() => ({ hooks, bind }), [hooks, bind])

  const close = useCallback(() => { seq.current += 1; setOpen(null); refocus() }, [refocus])

  // Escape or a click outside closes what is open.
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close() } }
    const down = (e: PointerEvent) => { if (!(e.target as HTMLElement).closest?.('.mm-pop')) close() }
    window.addEventListener('keydown', key, true)
    window.addEventListener('pointerdown', down, true)
    return () => { window.removeEventListener('keydown', key, true); window.removeEventListener('pointerdown', down, true) }
  }, [open, close])

  const w = root.current?.clientWidth ?? 1000
  const h = root.current?.clientHeight ?? 600
  return (
    <div ref={root} className="relative w-full h-full min-h-0">
      {children(slot)}
      {agentId && <BlockMarks terms={terms} agentId={agentId} record={record} />}
      <CommandCopy scanner={scanner} feed={feed} say={say} />
      {open?.kind === 'msg' && (
        <MsgMenu key={`${open.x}:${open.y}`} open={open} w={w} h={h} agentId={agentId} project={project} record={record} api={api} say={say} close={close}
          onId={(id) => openId(id, { clientX: open.cx, clientY: open.cy })} />
      )}
      {open?.kind === 'id' && open.id.kind === 'task' && (open.card
        ? <TaskCard key={open.id.id} open={open} w={w} h={h} say={say} close={close} />
        : <TaskMenu key={open.id.id} open={open} w={w} h={h} say={say} close={close} onCard={() => setOpen({ ...open, card: true })} />)}
      {open?.kind === 'id' && open.id.kind === 'note' && <NoteCard key={open.id.id} id={open.id.id} close={close} />}
      {open?.kind === 'id' && open.id.kind !== 'task' && open.id.kind !== 'note' && <RecordCardOf key={`card:${open.id.id}`} kind={open.id.kind}
        p={{ id: open.id.id, x: open.x, y: open.y, w, h, project, say, close, onId: openRef }} goTo={goTo} />}
    </div>
  )
}

/** The card of a record that has one (IdCards.tsx); a task and a note have their own above. */
function RecordCardOf({ kind, p, goTo }: { kind: IdKind; p: CardProps; goTo?: (sid: string) => void }) {
  switch (kind) {
    case 'decision': return <DecisionCard {...p} />
    case 'publish': return <PublishCard {...p} />
    case 'core': return <CoreCard {...p} />
    case 'skill': return <SkillCard {...p} />
    case 'entrypoint': return <EntryCard {...p} />
    case 'agent': return <AgentCard {...p} goTo={goTo} />
    case 'commit': return <CommitCard {...p} />
    default: return null
  }
}

/* ------------------------------------------------------------ the message list */

function MsgMenu({ open, w, h, agentId, project, record, api, say, close, onId }: {
  open: Extract<Open, { kind: 'msg' }>; w: number; h: number; agentId: string; project: string
  record: ReturnType<typeof useChatRecord>['record']; api: React.RefObject<ScreenApi | null>
  say: (s: string) => void; close: () => void; onId: (id: FoundId) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const actions = useMessageActions(agentId, project)
  const aqua = useAquaActions()
  const kept = useKept()
  const f = open.found
  const turn = f ? record?.byN.get(f.n) : undefined
  const text = f ? (f.side === 'reply' ? turn?.agent : turn?.user) ?? '' : ''
  const ref: MsgRef | null = f ? refOf(agentId, project, f, text) : null
  const target = f ? msgTarget(agentId, f.n, f.side) : ''
  const m: MessageMarks | null = f ? marksOf(actions.marks.of, kept, target) : null
  useFirstFocus(box, open.state)
  const run = (fn: () => void | Promise<void>) => () => {
    close()
    void Promise.resolve().then(fn).catch((e: unknown) => say(t('Could not do it: {error}', { error: e instanceof Error ? e.message : String(e) })))
  }
  const copy = run(async () => {
    const sel = api.current?.selection() ?? ''
    if (!sel && await api.current?.copyTmuxSelection?.()) return
    const what = sel || text || open.line.trim()
    if (!(await writeClipboard(what))) { say(t('The browser did not allow copying')); return }
    say(sel ? t('Selection copied') : text ? t('Message copied') : t('Line copied'))
  })
  const title = !agentId ? (open.link ? t('Link') : t('Command'))
    : open.state === 'reading' ? t('Looking for the message…')
      : !f ? t('Message not found in the chat record')
        : `${f.side === 'reply' ? t('Agent\'s reply') : t('Your message')} · ${f.n}`
  const link = open.link
  const copyLink = run(async () => {
    say(await writeClipboard(link!.text) ? t('Link copied') : t('The browser did not allow copying'))
  })
  const copyPage = run(async () => {
    const id = link!.kind === 'id' ? link!.id : null
    const path = id ? await pageAddress(id.kind, id.id) : ''
    if (!path) return
    say(await writeClipboard(`${window.location.origin}${path}`) ? t('Page address copied') : t('The browser did not allow copying'))
  })
  const openLink = run(() => {
    if (link!.kind === 'url') { if (!post({ op: 'open', url: link!.text })) window.open(link!.text, '_blank', 'noopener') }
    else if (link!.kind === 'path') api.current?.openPath?.(link!.path)
    else onId(link!.id)
  })
  const linkRows = link ? 2 + (link.kind === 'id' && link.id.kind !== 'commit' ? 1 : 0) : 0
  const cmd = open.cmd
  const claude = cmd ? forClaudeCode(cmd) : null
  // A line break pasted where the shell did not ask for bracketed paste would run the lines: not offered then.
  const pasteOk = !!cmd && !!api.current?.paste && (!cmd.text.includes('\n') || !!api.current.bracketed?.())
  const cmdRows = cmd ? 2 + (claude ? 1 : 0) : 0
  const copyCmd = (what: string, said: string) => run(async () => {
    say(await writeClipboard(what) ? said : t('The browser did not allow copying'))
  })
  const pasteCmd = run(() => {
    api.current?.paste?.(cmd!.text)
    say(t('Pasted into the terminal: Enter runs it'))
  })
  const row = (key: string, icon: ReactNode, label: string, onClick: () => void, on = false, title?: string) => (
    <button key={key} type="button" role="menuitem" className="lab-list-row" data-on={on || undefined} title={title} onClick={onClick}>{icon}{label}</button>
  )
  // Collapsing (fold.ts): the message under the click, every reply read, all of them back.
  const fold = api.current?.fold
  const span = open.span ?? null
  const folded = !!span && !!fold?.has(span.id)
  const foldCount = fold?.count() ?? 0
  const foldRows = fold && span ? 2 + (foldCount ? 1 : 0) : fold && foldCount ? 1 : 0
  const toggleFold = run(async () => {
    const got = await fold!.set([span!.id], !folded)
    say(folded ? foldSaid.open() : foldSaid[got]())
  })
  const foldAll = run(async () => {
    const ids = spansOf((open.rows ?? []).map((text) => ({ text }))).filter((s) => s.side === 'reply').map((s) => s.id)
    const got = await fold!.set(ids, true)
    say(got === 'off' ? foldSaid.off() : tn(ids.length, '{n} reply collapsed', '{n} replies collapsed'))
  })
  const unfoldAll = run(async () => {
    await fold!.clear()
    say(t('All messages expanded'))
  })
  const carry = (level: CarryLevel) => run(() => {
    actions.carry(ref!, m!.carry, level)
    say(m!.carry === level ? t('Not carried after compaction') : level === 'carry' ? t('After compaction: word for word') : t('After compaction: as a summary'))
  })
  return (
    <div ref={box} className="mm-pop lab-menu lab-list" role="menu" aria-label={title} data-found={f ? 'yes' : open.state === 'reading' ? 'reading' : 'no'}
      style={place(open.x, open.y, 256, (f ? 262 : agentId ? 118 : 60) + foldRows * 28 + (link ? linkRows * 28 + 30 : 0) + (cmd ? cmdRows * 28 + 30 : 0), w, h)}>
      {link && (
        <>
          <div className="lab-list-head"><span className="truncate font-mono" title={link.text}>{link.text}</span></div>
          {row('link-copy', <Link2 size={15} />, t('Copy the link'), copyLink)}
          {link.kind === 'id' && link.id.kind !== 'commit' && row('link-page', <Globe size={15} />, t('Copy the page address'), copyPage)}
          {row('link-open', <ExternalLink size={15} />, t('Open'), openLink)}
          <div className="h-px my-3" style={{ background: 'var(--aq-term-frame, rgba(255,255,255,0.1))' }} />
        </>
      )}
      {cmd && (
        <>
          <div className="lab-list-head"><span className="truncate font-mono" title={cmd.text}>{cmd.text.split('\n')[0]}{cmd.text.includes('\n') ? ' …' : ''}</span></div>
          {row('cmd-copy', <Copy size={15} />, t('Copy the command'), copyCmd(cmd.text, t('Command copied')))}
          {claude && row('cmd-claude', <SquareTerminal size={15} />, t('Copy for Claude Code'), copyCmd(claude, t('Copied for Claude Code')))}
          <button type="button" role="menuitem" className="lab-list-row" disabled={!pasteOk} aria-disabled={!pasteOk || undefined}
            title={pasteOk ? undefined : t('A pasted line break would run the lines here')} onClick={pasteOk ? pasteCmd : undefined}>
            <ClipboardPaste size={15} />{t('Paste into the terminal')}
          </button>
          <div className="h-px my-3" style={{ background: 'var(--aq-term-frame, rgba(255,255,255,0.1))' }} />
        </>
      )}
      {agentId && <div className="lab-list-head"><span className="truncate" title={f ? firstLine(text) : undefined}>{title}</span></div>}
      {f && m && ref && (
        <>
          {row('pin', m.pinned ? <PinOff size={15} /> : <Pin size={15} />, m.pinned ? t('Unpin') : t('Pin'), run(() => {
            actions.pin(ref, !m.pinned)
            say(m.pinned ? t('Message unpinned') : t('Message pinned'))
          }), m.pinned)}
          <div className="flex flex-col">
            <div className="lab-list-row static"><Layers size={15} /><span>{t('Carry after compaction')}</span></div>
            <div className="flex gap-6 pl-[31px] pb-4">
              <button type="button" role="menuitemradio" aria-checked={m.carry === 'carry'} aria-label={`${t('Carry after compaction')}: ${t('word for word')}`}
                className="lab-pill whitespace-nowrap inline-flex items-center gap-4" data-on={m.carry === 'carry' || undefined} onClick={carry('carry')}><Quote size={11} />{t('word for word')}</button>
              <button type="button" role="menuitemradio" aria-checked={m.carry === 'brief'} aria-label={`${t('Carry after compaction')}: ${t('as a summary')}`}
                className="lab-pill whitespace-nowrap inline-flex items-center gap-4" data-on={m.carry === 'brief' || undefined} onClick={carry('brief')}><AlignLeft size={11} />{t('as a summary')}</button>
            </div>
          </div>
          {row('later', <Clock size={15} />, t('Hand over later'), run(() => {
            actions.later(ref, !m.later)
            say(m.later ? t('Not handed over later') : t('Will be handed over later'))
          }), m.later)}
          {row('branch', <GitBranch size={15} />, t('Branch into a new window'), run(async () => {
            const why = await actions.branch(ref, {
              open: async (command, label) => {
                const s = await aqua.open({ kind: 'shell', project, label: t('branch: {name}', { name: label.slice(0, 40) }), command, role: 'chat' })
                if (!s) return false
                openWindow(detachUrl('chat', s.id))
                return true
              },
            })
            say(why === 'no-command' ? t('The branch did not start: this chat has no session or folder recorded')
              : why === 'no-terminal' ? t('The branch did not start: the terminal did not open')
                : t('Branch opened in a new window'))
          }), m.branched)}
          {row('task', <ListPlus size={15} />, m.task ? t('Task {id}', { id: m.task }) : t('Make a task'), run(async () => {
            const got = await actions.makeTask(ref, text, t('From the chat: {target}', { target }))
            say(got.existing ? t('Already a task: {id}', { id: got.id })
              : got.title ? t('Task made in todo: {id} · {title}', { id: got.id, title: got.title })
                : t('Task made in todo: {id}', { id: got.id }))
          }), !!m.task)}
        </>
      )}
      {agentId && fold && span && row('fold', folded ? <ChevronsUpDown size={15} /> : <ChevronsDownUp size={15} />, folded ? t('Expand') : t('Collapse to one line'), toggleFold, folded,
        t('Shown as one line in the history, when you scroll up; the live screen at the bottom stays as the program drew it'))}
      {agentId && fold && span && row('fold-all', <ChevronsDownUp size={15} />, t('Collapse all replies'), foldAll)}
      {agentId && fold && foldCount > 0 && row('unfold-all', <ChevronsUpDown size={15} />, t('Expand all'), unfoldAll)}
      {agentId && row('copy', <Copy size={15} />, t('Copy'), copy)}
      <div className="h-px my-3" style={{ background: 'var(--aq-term-frame, rgba(255,255,255,0.1))' }} />
      {row('own', <SquareTerminal size={15} />, t('Terminal menu…'), () => { close(); api.current?.ownMenu(open.cx, open.cy) })}
    </div>
  )
}

/* ------------------------------------------------------------ a task id */

function TaskMenu({ open, w, h, say, close, onCard }: {
  open: Extract<Open, { kind: 'id' }>; w: number; h: number; say: (s: string) => void; close: () => void; onCard: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const id = open.id.id
  const q = useTask(id, true)
  const actions = useMessageActions('', '')
  const status = q.data?.metadata.status ?? ''
  useFirstFocus(box)
  return (
    <div ref={box} className="mm-pop lab-menu lab-list" role="menu" aria-label={id} style={place(open.x, open.y, 256, 150, w, h)}>
      <div className="lab-list-head">
        <span className="font-mono">{id}</span>
        <span className="truncate lab-list-sub">{q.isLoading ? t('Reading the task…') : q.isError ? t('No such task') : q.data?.metadata.title}</span>
      </div>
      <button type="button" role="menuitem" className="lab-list-row" onClick={onCard}><ExternalLink size={15} />{t('Open the task')}</button>
      <Columns id={id} status={status} disabled={!q.data} onMove={(c) => {
        close()
        void actions.moveTask(id, c).then(() => say(`${id} → ${c}`), (e: Error) => say(t('Could not do it: {error}', { error: e.message })))
      }} />
      <button type="button" role="menuitem" className="lab-list-row" onClick={() => { close(); void copyId(id, say) }}><Copy size={15} />{t('Copy the id')}</button>
    </div>
  )
}

function Columns({ id, status, disabled, onMove }: { id: string; status: string; disabled: boolean; onMove: (c: string) => void }) {
  return (
    <div className="lab-list-row static" role="radiogroup" aria-label={`${t('Column')} ${id}`}>
      <span className="lab-list-label">{t('Column')}</span>
      {COLUMNS.map((c) => (
        <button key={c} type="button" role="menuitemradio" aria-checked={status === c} disabled={disabled} className="lab-pill" data-column={c} data-on={status === c || undefined}
          onClick={() => { if (status !== c) onMove(c) }}>{c}</button>
      ))}
    </div>
  )
}

/** "Open the task": a small card in place of the menu; the column changes in it and it stays. */
function TaskCard({ open, w, h, say, close }: { open: Extract<Open, { kind: 'id' }>; w: number; h: number; say: (s: string) => void; close: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const id = open.id.id
  const q = useTask(id, true)
  const actions = useMessageActions('', '')
  const d = q.data
  const status = d?.metadata.status ?? ''
  const desc = (d?.description ?? '').trim()
  useFirstFocus(box)
  return (
    <div ref={box} className="mm-pop lab-menu lab-list lab-card" role="dialog" aria-label={`${t('Task')} ${id}`} style={place(open.x, open.y, 320, 220, w, h)}>
      <div className="lab-list-head">
        <span className="font-mono">{id}</span>
        {d && <span className="aq-chip">{d.metadata.project}</span>}
        <button type="button" className="lab-edge-btn icon ml-auto" aria-label={t('Close')} onClick={close}><X size={12} /></button>
      </div>
      <div className="px-10 pb-6 flex flex-col gap-4">
        <b className="text-13 leading-snug" style={{ color: 'var(--aq-term-fg)' }}>{q.isLoading ? t('Reading the task…') : q.isError ? t('No such task') : d?.metadata.title}</b>
        {desc && <p className="m-0 text-11 leading-snug whitespace-pre-wrap line-clamp-5" style={{ color: 'var(--aq-term-dim)' }}>{desc}</p>}
        {status && !COLUMNS.includes(status as typeof COLUMNS[number]) && <span className="text-11" style={{ color: 'var(--aq-term-dim)' }}>{t('Now in {column}', { column: status })}</span>}
      </div>
      <Columns id={id} status={status} disabled={!d} onMove={(c) => {
        void actions.moveTask(id, c).then(() => say(`${id} → ${c}`), (e: Error) => say(t('Could not do it: {error}', { error: e.message })))
      }} />
      <button type="button" className="lab-list-row" onClick={() => { void copyId(id, say) }}><Copy size={15} />{t('Copy the id')}</button>
    </div>
  )
}

/* ------------------------------------------------------------ a note, read in place */

function NoteCard({ id, close }: { id: string; close: () => void }) {
  const feed = useNotesFeed({})
  const inFeed = feed.data?.notes.find((n) => n.id === id)
  // An archived note is not in the feed: read on its own.
  const alone = useQuery({
    queryKey: ['notes', 'one', id],
    queryFn: ({ signal }) => getJson<WireNote>(`/api/notes/${encodeURIComponent(id)}/full`, signal),
    enabled: !!feed.data && !inFeed,
    retry: false,
  })
  const wire = inFeed ?? alone.data
  const note = useMemo(() => (wire ? toNote(wire) : null), [wire])
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { box.current?.focus() }, [])
  const failed = feed.isError || alone.isError
  return (
    <div className="mm-pop absolute inset-0 z-30 flex items-start justify-center p-16" style={{ background: 'color-mix(in srgb, var(--term-ground) 55%, transparent)' }}
      onPointerDown={(e) => { if (e.target === e.currentTarget) close() }}>
      <div ref={box} tabIndex={-1} role="dialog" aria-label={`${t('Note')} ${id}`}
        className="relative w-full max-w-[760px] max-h-full flex flex-col rounded-card border border-border-default shadow-lg outline-none"
        style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
        <div className="shrink-0 flex items-center gap-8 px-14 h-[34px] text-12" style={{ borderBottom: '1px solid var(--border-default)' }}>
          <span className="font-mono text-tertiary">{id}</span>
          <span className="text-11 text-tertiary">{t('Esc closes')}</span>
          <button type="button" className="ml-auto inline-flex items-center justify-center w-[24px] h-[24px] rounded-input hover:bg-hover" aria-label={t('Close')} onClick={close}><X size={13} /></button>
        </div>
        <div className="flex-1 min-h-0 overflow-auto px-20 py-16">
          {note ? (
            <ServerNoteEnv feed={feed.data} extraNote={inFeed ? undefined : alone.data}>
              <NoteRead note={note} size="mid" />
            </ServerNoteEnv>
          ) : (
            <p className="m-0 text-13 text-tertiary">{failed ? t('The note could not be read.') : t('Reading the note…')}</p>
          )}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ marks on the blocks */

interface Shown { line: number; target: string; m: MessageMarks }

/**
 * What an action did, at the right end of the message's first row on the
 * screen: drawn inside xterm's screen element, so it moves with the text
 * (the smooth scrolling moves that element). Which messages are on the
 * screen is read again twice a second; where each mark stands follows
 * xterm's rows at once (rowAnchor.ts: by its line in the buffer, not by the
 * row it had at the last read, tk_49c10a34).
 */
function BlockMarks({ terms, agentId, record }: { terms: React.RefObject<Set<Terminal>>; agentId: string; record: ReturnType<typeof useChatRecord>['record'] }) {
  const actions = useMessageActions(agentId, '')
  const kept = useKept()
  const of = actions.marks.of
  const any = actions.marks.all.some((x) => x.agent_id === agentId)
    || Object.keys(kept.tasked).some((k) => k.startsWith(`${agentId}#`)) || Object.keys(kept.branched).some((k) => k.startsWith(`${agentId}#`))
  const [shown, setShown] = useState<{ host: HTMLElement; term: Terminal; items: Shown[] } | null>(null)
  const view = useView(shown?.term)
  useEffect(() => {
    if (!any || !record) { setShown(null); return }
    const tick = () => {
      const live = [...(terms.current ?? [])].filter((x) => x.element?.isConnected)
      // The reader, when it is in front; else the live terminal.
      const term = live.find((x) => x.element?.closest('.sp-reader') && (x.element.closest('.sp-reader') as HTMLElement).style.visibility !== 'hidden')
        ?? live.find((x) => !x.element?.closest('.sp-reader'))
      const host = term?.element?.querySelector('.xterm-screen') as HTMLElement | null
      if (!term || !host || !term.rows) { setShown(null); return }
      const b = term.buffer.active
      // A reader with collapsed messages (fold.ts): its source rows, each mark on the row its text is on now (a label for a collapsed one).
      const fv = foldViewOf(term)
      const toView = (src: number) => (fv ? fv.map.toView(src) : src)
      const top = fv ? fv.map.toSrc(b.viewportY) : b.viewportY
      const end = fv ? Math.min(fv.src.length, fv.map.toSrc(b.viewportY + term.rows)) : b.viewportY + term.rows
      const from = Math.max(0, top - 300)
      const rows: string[] = []
      for (let i = from; i < end; i++) rows.push(fv ? fv.src[i]?.text ?? '' : b.getLine(i)?.translateToString(true) ?? '')
      const items: Shown[] = []
      const seen = new Set<string>()
      for (const blk of blocksOf(rows)) {
        const line = toView(blk.start + from)
        const r = line - b.viewportY
        // A screen's worth above too: a scroll brings them in before the next read.
        if (r < -term.rows || r >= term.rows || (blk.kind !== 'user' && blk.kind !== 'agent')) continue
        const f = messageAt(rows, blk.start, record)
        if (!f) continue
        const target = msgTarget(agentId, f.n, f.side)
        if (seen.has(target)) continue
        seen.add(target)
        const m = marksOf(of, kept, target)
        if (m.pinned || m.carry || m.later || m.branched || m.task) items.push({ line, target, m })
      }
      setShown({ host, term, items })
    }
    tick()
    const id = window.setInterval(tick, 500)
    // The reader made again (a message collapsed or expanded): the marks move with their text now, not at the next read.
    window.addEventListener('sp-reader-swap', tick)
    return () => { window.clearInterval(id); window.removeEventListener('sp-reader-swap', tick) }
  }, [any, record, agentId, of, kept, terms])
  if (!shown || !shown.items.length || !view) return null
  return createPortal(
    <>
      {shown.items.map(({ line, target, m }) => {
        const top = rowTop(line, view)
        return top != null && (
        <span key={target} className="mm-marks" aria-label={t('Marks')} data-target={target} data-line={line}
          style={{ position: 'absolute', right: 4, top, height: view.cell, display: 'flex', alignItems: 'center', gap: 4, zIndex: 6, pointerEvents: 'none' }}>
          {m.pinned && <span className="lab-mark on"><Pin size={10} />{t('pinned')}</span>}
          {m.carry && <span className="lab-mark"><Layers size={10} />{m.carry === 'carry' ? t('word for word') : t('as a summary')}</span>}
          {m.later && <span className="lab-mark"><Clock size={10} />{t('later')}</span>}
          {m.branched && <span className="lab-mark"><GitBranch size={10} />{t('branch')}</span>}
          {m.task && <span className="lab-mark task">{m.task}</span>}
        </span>
        )
      })}
    </>,
    shown.host,
  )
}
