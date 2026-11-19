/**
 * A message collapsed to one line in the terminal's history (tk_a2bb64a1):
 * «▸ A · 48 строк · first line».
 *
 * The live terminal is drawn by the program in it and stays as it is. The
 * history the page shows when scrolled up is the page's own (reader.ts: a
 * read-only xterm written from tmux's capture, or from a plain terminal's
 * buffer), so its rows can be left out: each collapsed message's rows are
 * written as one label row. Its last screen of rows (the live screen) is
 * never collapsed, so the reader still opens and closes without a jump.
 *
 * - A message is the operator's (❯ and its indented rows) or the agent's
 *   reply: every row printed after the operator's message up to the next
 *   one — narration, tool calls, output, the answer, «✻ Worked for …».
 * - Its id comes from its text (letters and digits only: wrapping, indents
 *   and the window's width do not change it), not from a row number, which
 *   changes as the history grows: the operator's words, and the reply's
 *   first block (a reply still being written keeps its id as it grows).
 *   The same question with the same first answer twice is one id: both
 *   collapse together.
 * - FoldMap maps the source rows (the capture) to the rows on view and back:
 *   the scroll position, marks and right clicks keep to their text.
 *
 * Pure: unit-tested in fold.test.ts. Kept per terminal in foldStore.ts.
 */

import { keyOf, rowKind, type RowKind } from './messageMenu/match'
import { t, tn } from '../../i18n/scope/msgmenu'

export type FoldSide = 'user' | 'reply'

/** One row of the history as text; `wrapped`: it goes on the row above (xterm's soft wrap). */
export interface SrcRow { text: string; wrapped?: boolean }

/** A message's rows in the source, both ends included. */
export interface Span { id: string; side: FoldSide; start: number; end: number }

/** A collapsed message: its span and the line its label shows. */
export interface Fold extends Span { first: string }

interface Seg { start: number; end: number; kind: Exclude<RowKind, 'cont'> }

/** The rows cut into blocks, as match.blocksOf does; a soft-wrapped row goes on its block. */
function segments(rows: SrcRow[]): Seg[] {
  const out: Seg[] = []
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]!
    const k = r.wrapped && out.length ? 'cont' : rowKind(r.text, i > 0 ? rows[i - 1]!.text : undefined)
    if (k === 'cont') {
      if (!out.length) out.push({ start: i, end: i, kind: 'other' })
      else out[out.length - 1]!.end = i
      continue
    }
    out.push({ start: i, end: i, kind: k })
  }
  return out
}

/** The block's last row with text (its empty rows after stay where they are). */
function lastFilled(rows: SrcRow[], s: Seg): number {
  let e = s.end
  while (e > s.start && !rows[e]!.text.trim()) e--
  return e
}

/** FNV-1a, 32 bits, base 36: short and stable. */
export function hashOf(s: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(36)
}

const keyOfRows = (rows: SrcRow[], a: number, b: number) => keyOf(rows.slice(a, b + 1).map((r) => r.text).join(' '))

/**
 * Every message in the rows: the operator's and the reply after it.
 * The reply's id has the operator's words and its own first block (it may
 * still be growing at the bottom); the operator's has a few of the reply's
 * words too, so two «статус» with different answers are two messages.
 */
export function spansOf(rows: SrcRow[]): Span[] {
  const segs = segments(rows)
  const out: Span[] = []
  for (let i = 0; i < segs.length; i++) {
    const s = segs[i]!
    if (s.kind !== 'user') continue
    const uEnd = lastFilled(rows, s)
    const uk = keyOfRows(rows, s.start, uEnd)
    let j = i + 1
    while (j < segs.length && (segs[j]!.kind === 'agent' || segs[j]!.kind === 'status')) j++
    // The reply's first block: whole once it is in the history (Claude Code prints a block when it is done).
    const rk = j > i + 1 ? keyOfRows(rows, segs[i + 1]!.start, segs[i + 1]!.end).slice(0, 200) : ''
    out.push({ id: `u${hashOf(`${uk}\u0000${rk.slice(0, 40)}`)}`, side: 'user', start: s.start, end: uEnd })
    if (j > i + 1) out.push({ id: `r${hashOf(`${uk}\u0000${rk}`)}`, side: 'reply', start: segs[i + 1]!.start, end: lastFilled(rows, segs[j - 1]!) })
    i = j - 1
  }
  return out
}

const side = (ui: number, bi: number): FoldSide => (ui === bi ? 'user' : 'reply')

/** The message row `at` belongs to (the operator's, or the reply its turn printed), or null. */
export function messageRange(rows: SrcRow[], at: number): Span | null {
  if (at < 0 || at >= rows.length) return null
  const segs = segments(rows)
  const bi = segs.findIndex((s) => at >= s.start && at <= s.end)
  if (bi < 0) return null
  const k = segs[bi]!.kind
  if (k !== 'user' && k !== 'agent' && k !== 'status') return null
  // The operator's message the row is in, or the one above the reply it is in.
  let ui = bi
  while (ui >= 0 && segs[ui]!.kind !== 'user') {
    if (segs[ui]!.kind !== 'agent' && segs[ui]!.kind !== 'status') return null
    ui--
  }
  if (ui < 0) return null
  const start = side(ui, bi) === 'user' ? segs[ui]!.start : segs[ui + 1]!.start
  return spansOf(rows).find((s) => s.side === side(ui, bi) && s.start === start) ?? null
}

/** The first row of a span that says something, its marker gone. */
export function firstWords(rows: SrcRow[], s: Span): string {
  for (let i = s.start; i <= s.end; i++) {
    const w = rows[i]!.text.replace(/^[\s❯>●⏺⎿✻✶✳✢✽✺·*›]+/u, '').trim()
    if (/[\p{L}\p{N}]/u.test(w)) return w.replace(/\s+/g, ' ')
  }
  return ''
}

/**
 * The collapsed messages of the rows: the ones `has` names, never in the
 * last `tail` rows (the live screen), none inside another.
 */
export function foldsOf(rows: SrcRow[], has: (id: string) => boolean, tail: number): Fold[] {
  const limit = rows.length - Math.max(0, tail)
  const out: Fold[] = []
  const picked = spansOf(rows).filter((s) => has(s.id) && s.end < limit).sort((a, b) => a.start - b.start || b.end - a.end)
  for (const s of picked) {
    const last = out[out.length - 1]
    if (last && s.start <= last.end) continue
    out.push({ ...s, first: firstWords(rows, s) })
  }
  return out
}

/** Source rows ⇄ rows on view, with each fold one row. */
export class FoldMap {
  readonly length: number
  constructor(readonly total: number, readonly folds: Fold[]) {
    this.length = total - folds.reduce((n, f) => n + (f.end - f.start), 0)
  }

  /** The view row of source row `src` (a folded row: its label's). */
  toView(src: number): number {
    let shift = 0
    for (const f of this.folds) {
      if (src > f.end) { shift += f.end - f.start; continue }
      if (src >= f.start) return f.start - shift
      break
    }
    return src - shift
  }

  /** The source row of view row `view` (a label: its message's first row). */
  toSrc(view: number): number {
    let shift = 0
    for (const f of this.folds) {
      const at = f.start - shift
      if (view < at) break
      if (view === at) return f.start
      shift += f.end - f.start
    }
    return view + shift
  }

  /** The fold whose label is view row `view`, or null. */
  foldAt(view: number): Fold | null {
    let shift = 0
    for (const f of this.folds) {
      const at = f.start - shift
      if (view < at) return null
      if (view === at) return f
      shift += f.end - f.start
    }
    return null
  }
}

/** How many columns a character takes: wide (CJK, emoji) ones two. */
function widthOf(ch: string): number {
  const c = ch.codePointAt(0) ?? 0
  return c >= 0x1100 && (c <= 0x115f || (c >= 0x2e80 && c <= 0xa4cf) || (c >= 0xac00 && c <= 0xd7a3) || (c >= 0xf900 && c <= 0xfaff)
    || (c >= 0xfe30 && c <= 0xfe4f) || (c >= 0xff00 && c <= 0xff60) || (c >= 0xffe0 && c <= 0xffe6) || (c >= 0x1f300 && c <= 0x1faff) || (c >= 0x20000 && c <= 0x3fffd)) ? 2 : 1
}

const textWidth = (s: string) => { let w = 0; for (const ch of s) w += widthOf(ch); return w }

/**
 * tmux's rows (capture-pane without -J) say nothing of soft wraps: a line
 * longer than the pane (tmux reflows the history when the window narrows)
 * goes on at column 0 of the next row, where it would read as a block of its
 * own. A row after a full one is taken for its continuation, unless it starts
 * a message.
 */
export function tmuxRows(lines: string[], cols: number): SrcRow[] {
  return lines.map((text, i) => ({
    text,
    wrapped: i > 0 && cols > 0 && textWidth(lines[i - 1]!) >= cols - 1 && !/^(❯|>|›|●|⏺|•)(\s|$)/.test(text) && !!text.trim() ? true : undefined,
  }))
}

/** `s` cut to `cols` columns, an ellipsis where it was cut. */
export function fitTo(s: string, cols: number): string {
  let w = 0
  let out = ''
  const chars = [...s]
  for (let i = 0; i < chars.length; i++) {
    const cw = widthOf(chars[i]!)
    if (w + cw > cols - (i < chars.length - 1 ? 1 : 0)) return `${out}…`
    out += chars[i]
    w += cw
  }
  return out
}

/** The label's words: «A · 48 строк · first line», cut to `cols` with room for «▸ ». */
export function labelText(f: Pick<Fold, 'side' | 'start' | 'end' | 'first'>, cols: number): string {
  const who = f.side === 'user' ? t('You') : 'A'
  const n = f.end - f.start + 1
  const head = `▸ ${who} · ${tn(n, '{n} line', '{n} lines')}`
  return fitTo(f.first ? `${head} · ${f.first}` : head, Math.max(8, cols))
}

/** The label row as the reader writes it: quiet (dim), the marker a little brighter. */
export function labelRow(f: Fold, cols: number): string {
  const text = labelText(f, cols)
  return `\x1b[0m▸\x1b[2m${text.slice(1)}\x1b[0m`
}

/* ------------------------------------------------------------ the text */

const ESC = '\u001b', BEL = '\u0007'
export const ANSI = new RegExp(`${ESC}\\[[0-9;?]*[ -/]*[@-~]|${ESC}\\][^${BEL}${ESC}]*(?:${BEL}|${ESC}\\\\)|${ESC}[()][0-9A-B]`, 'g')
const SGR = new RegExp(`${ESC}\\[([0-9;:]*)m`, 'g')

export const stripAnsi = (s: string) => s.replace(ANSI, '')

/**
 * The colours in force after `line`, given those before (`state`: the SGR
 * sequences since the last reset). tmux's capture writes only the changes,
 * and they carry from one row to the next: a row after a fold is written
 * with what the rows left out had set.
 */
export function sgrAfter(line: string, state: string): string {
  let s = state
  for (const m of line.matchAll(SGR)) {
    const p = m[1] ?? ''
    if (p === '' || p === '0' || p.startsWith('0;')) s = m[0]
    else s += m[0]
  }
  return s.length > 600 ? s.slice(-600) : s
}

/** The source lines (with their colours) as the reader writes them: each fold one label row. */
export function foldLines(lines: string[], folds: Fold[], cols: number): string[] {
  if (!folds.length) return lines
  const out: string[] = []
  let state = ''
  let fi = 0
  let carry = ''
  for (let i = 0; i < lines.length; i++) {
    const f = folds[fi]
    const line = lines[i]!
    if (f && i >= f.start && i <= f.end) {
      state = sgrAfter(line, state)
      if (i === f.end) {
        out.push(labelRow(f, cols))
        fi++
        // The row after goes on in the colours the left-out rows set.
        carry = `\x1b[0m${state}`
      }
      continue
    }
    state = sgrAfter(line, state)
    out.push(carry + line)
    carry = ''
  }
  return out
}

/** The source rows wrapped ones joined (as the message menu reads them), and the joined row source row `at` is in. */
export function joinedRows(rows: SrcRow[], at: number): { rows: string[]; at: number } {
  const out: string[] = []
  let got = 0
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]!
    if (r.wrapped && out.length) out[out.length - 1] += r.text
    else out.push(r.text)
    if (i === at) got = out.length - 1
  }
  return { rows: out, at: got }
}

/** What the menu says after a collapse, an expand. */
export const foldSaid = {
  shown: () => t('Collapsed to one line'),
  later: () => t('Collapsed: it shows as one line in the history, once it is above the live screen'),
  off: () => t('Collapsing needs smooth scrolling (Settings › Terminal)'),
  open: () => t('Expanded'),
}
