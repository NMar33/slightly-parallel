/**
 * The copy icon of a command in the terminal (tk_29b870f1): while the
 * pointer is over a command's rows, a small icon at the right end of its
 * first row; a click copies the command and says «Скопировано». Which rows
 * are a command comes from commands.ts (the reply's markdown, found on the
 * screen; else a `$ ` / `! ` row). The right-click items are the message
 * menu's (MessageMenu.tsx), from the same scan.
 *
 * The icon is drawn inside xterm's screen element and placed by its line in
 * the buffer (rowAnchor.ts), so it moves with the text in a smooth scroll.
 * Nothing is drawn at rest: only under the pointer. The copied text is not
 * logged anywhere.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { IDisposable, Terminal } from 'xterm'
import { Check, Copy } from 'lucide-react'

import { writeClipboard } from '../../../lib/useCopy'
import { t } from '../../../i18n/scope/msgmenu'
import { commandAt, commandSpans, type Command } from './commands'
import { lineCells } from './cells'
import type { Record } from './match'
import { rowTop, useView } from './rowAnchor'

/** A command on the screen, by its lines in the buffer. */
export interface AbsSpan { cmd: Command; line: number; endLine: number; col: number; endCol: number }

/** How many rows above the view a scan reads, to find the start of the reply a command is in. */
const ABOVE = 400
/** And below it: a command that runs on past the bottom row. */
const BELOW = 60

/**
 * The commands a terminal shows, read again only when its text, its view or
 * the record changed. One scanner serves every terminal of a window.
 */
export class CommandScanner {
  private memo = new WeakMap<Terminal, { key: string; rec: Record | null; spans: AbsSpan[]; dirty: boolean; sub: IDisposable | undefined }>()
  constructor(private record: () => Record | null) {}

  spans(term: Terminal): AbsSpan[] {
    const b = term.buffer.active
    const key = `${b.type}|${b.viewportY}|${b.length}|${term.rows}|${term.cols}`
    const rec = this.record()
    const m = this.memo.get(term)
    if (m && !m.dirty && m.key === key && m.rec === rec) return m.spans
    const from = Math.max(0, b.viewportY - ABOVE)
    const to = Math.min(b.length - 1, b.viewportY + term.rows - 1 + BELOW)
    const rows: string[] = []
    const wrapped: boolean[] = []
    for (let i = from; i <= to; i++) {
      const l = b.getLine(i)
      rows.push(l?.translateToString(true) ?? '')
      wrapped.push(!!l?.isWrapped)
    }
    // The top row cut out of its block (tmux shows only its screen): read as the agent's text, so the
    // reply it belongs to is still found by its words. "  " → "● " keeps every column where it was.
    if (rows.length && /^ {2}\S/.test(rows[0]!)) rows[0] = `● ${rows[0]!.slice(2)}`
    const cursor = b.baseY + b.cursorY - from
    const spans = commandSpans(rows, rec, { wrapped, skip: cursor }).map((s) => ({ cmd: s.cmd, line: s.row + from, endLine: s.endRow + from, col: s.col, endCol: s.endCol }))
    if (!m) {
      // New output marks the scan stale (fakes in tests have no such event: their text never changes).
      const mm = { key, rec, spans, dirty: false, sub: term.onWriteParsed?.(() => { mm.dirty = true }) }
      this.memo.set(term, mm)
    } else Object.assign(m, { key, rec, spans, dirty: false })
    return spans
  }

  /** The command under a point of `term`'s screen: by its row, and by its column for a command inside a line of prose. */
  at(term: Terminal, clientX: number, clientY: number): AbsSpan | null {
    const p = pointOf(term, clientX, clientY)
    if (!p) return null
    const spans = this.spans(term)
    const line = term.buffer.active.getLine(p.line)
    const col = line ? lineCells(line).cells.findIndex((c) => c === p.col) : -1
    const hit = commandAt(spans.map((s) => ({ cmd: s.cmd, row: s.line, endRow: s.endLine, col: s.col, endCol: s.endCol })), p.line, col < 0 ? null : col)
    return hit ? spans.find((s) => s.line === hit.row && s.col === hit.col) ?? null : null
  }

  /** Any command on the row under a point (the icon shows for a command's rows, whatever the column). */
  onRow(term: Terminal, clientY: number): AbsSpan | null {
    const p = pointOf(term, 0, clientY)
    if (!p) return null
    return this.spans(term).find((s) => p.line >= s.line && p.line <= s.endLine) ?? null
  }
}

/** The buffer line and cell under a point of the screen (the screen's rectangle includes the smooth scroll's shift). */
export function pointOf(term: Terminal, clientX: number, clientY: number): { line: number; col: number } | null {
  const scr = term.element?.querySelector('.xterm-screen')
  if (!scr || !term.rows) return null
  const r = scr.getBoundingClientRect()
  if (r.height <= 0) return null
  const row = Math.floor(((clientY - r.top) / r.height) * term.rows)
  if (row < 0 || row >= term.rows) return null
  return { line: term.buffer.active.viewportY + row, col: Math.floor(((clientX - r.left) / r.width) * term.cols) }
}

/** What the layer tells the icon: the pointer moved over a terminal (null: it left). */
export type HoverFeed = (term: Terminal, e: { clientX: number; clientY: number } | null) => void

export function CommandCopy({ scanner, feed, say }: {
  scanner: CommandScanner
  /** Where the layer sends the pointer's moves over each terminal. */
  feed: React.MutableRefObject<HoverFeed | null>
  say: (s: string) => void
}) {
  const [hover, setHover] = useState<{ term: Terminal; span: AbsSpan } | null>(null)
  const [copied, setCopied] = useState('')
  const last = useRef<{ term: Terminal; x: number; y: number } | null>(null)
  const view = useView(hover?.term)

  const look = useCallback(() => {
    const l = last.current
    const span = l ? scanner.onRow(l.term, l.y) : null
    setHover((o) => (span && l ? (o && o.term === l.term && o.span.line === span.line && o.span.col === span.col && o.span.cmd.text === span.cmd.text ? o : { term: l.term, span }) : null))
  }, [scanner])

  useEffect(() => {
    feed.current = (term, e) => {
      last.current = e ? { term, x: e.clientX, y: e.clientY } : null
      look()
    }
    return () => { feed.current = null }
  }, [feed, look])

  // The text moved under a pointer that stood still (a scroll): what is under it now.
  useEffect(() => { if (last.current) look() }, [view?.viewportY, look])
  useEffect(() => { if (!copied) return; const id = window.setTimeout(() => setCopied(''), 1200); return () => window.clearTimeout(id) }, [copied])

  const host = hover?.term.element?.querySelector('.xterm-screen') as HTMLElement | null | undefined
  if (!hover || !host || !view) return null
  const { span } = hover
  // Its first row; when that is above the view, the first row of it on the screen.
  const top = rowTop(Math.max(span.line, view.viewportY), view)
  if (top == null || span.endLine < view.viewportY) return null
  const done = copied === span.cmd.text
  return createPortal(
    <button type="button" className={`mm-cmd lab-mark${done ? ' on' : ''}`} aria-label={t('Copy the command')} title={t('Copy the command')}
      data-line={span.line}
      // The chip's own height (15 px) in the middle of the row.
      style={{ position: 'absolute', right: 4, top: top + Math.max(0, (view.cell - 15) / 2), zIndex: 7, cursor: 'pointer', pointerEvents: 'auto' }}
      onClick={() => {
        const text = span.cmd.text
        void writeClipboard(text).then((ok) => {
          if (!ok) { say(t('The browser did not allow copying')); return }
          setCopied(text)
          say(t('Command copied'))
        })
      }}>
      {done ? <><Check size={11} />{t('Copied')}</> : <Copy size={11} />}
    </button>,
    host,
  )
}
