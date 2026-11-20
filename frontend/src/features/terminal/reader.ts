/**
 * The reader: a tmux terminal's history, scrolled by pixels in the page.
 *
 * In tmux mode the page's xterm has no history (tmux keeps it and draws the
 * screen on xterm's alternate screen), and the wheel used to go to tmux's
 * copy mode: five lines a step, two frames late. The reader instead takes
 * the pane's rows from tmux (`capture-pane -e`: colours kept, wrapped lines
 * as they show) into a second, read-only xterm of the same size, laid
 * exactly over the live one, and scrolls it with the smooth layer. Its last
 * rows are the live screen, so opening it does not show.
 *
 * - It is a snapshot: the agent goes on writing underneath (the "↓ newest"
 *   pill counts it); back at the bottom, or any key, and the live terminal
 *   is in front again.
 * - Selection, Ctrl+C / Ctrl+Shift+C and find work in it (it is an xterm).
 * - The last 2000 rows come at once (about 50 ms); a longer history follows
 *   in the background in a second reader, swapped in at the same distance
 *   from the bottom.
 */

import type { IBufferCell, IBufferLine, Terminal } from 'xterm'
import type { SearchAddon } from 'xterm-addon-search'
import { postJson } from '../../lib/getJson'
import { THEME } from './palette'
import { attachSmoothLayer, disposeTerminal, type SmoothLayer } from './scrollLayer'
import { keepSelectionLocal } from './explicitClipboard'
import { FoldMap, foldLines, foldsOf, stripAnsi, tmuxRows, type Fold, type SrcRow } from './fold'

export interface HistoryRows {
  text: string
  history: number
  rows: number
  cols: number
  above: number
  complete: boolean
  /** A plain terminal's rows (plainRows): which ones go on the row above (soft wrap). */
  wrapped?: boolean[]
}

export const FIRST_ROWS = 2000

export interface Reader {
  term: Terminal
  layer: SmoothLayer
  search: SearchAddon
  /** The pane's history above its screen when the rows were taken. */
  history: number
  /** History rows the reader holds above the screen. */
  above: number
  el: HTMLElement
  /** What it was made from (made again from it when a message is collapsed or expanded). */
  got: HistoryRows
  /** The rows of `got` as text, and the collapsed messages among them (fold.ts). */
  src: SrcRow[]
  folds: Fold[]
  map: FoldMap
  dispose: () => void
}

/** A reader's rows as text and its map of collapsed messages, by its xterm (the message menu's marks read it). */
const views = new WeakMap<Terminal, { src: SrcRow[]; map: FoldMap }>()
export const foldViewOf = (t: Terminal) => views.get(t) ?? null

type Make = { Terminal: typeof Terminal; Search: new () => SearchAddon }

export const fetchRows = (sid: string, rows: number) =>
  postJson<HistoryRows>(`/api/terminal/sessions/${encodeURIComponent(sid)}/capture`, { mode: 'history', rows })

/** Which messages to collapse: the ids, and the rows at the bottom never collapsed (the live screen). */
export interface FoldOpts { has: (id: string) => boolean; tail: number }

/** Build a reader over `host` from `got` (hidden until written), the messages `fold` names collapsed. */
export async function buildReader(make: Make, host: HTMLElement, live: Terminal, got: HistoryRows, fold?: FoldOpts): Promise<Reader> {
  const el = document.createElement('div')
  el.className = 'sp-reader'
  // Laid over the live xterm exactly: the same box, the same padding.
  const cs = getComputedStyle(host)
  Object.assign(el.style, {
    position: 'absolute', left: '0', top: '0', right: '0', bottom: '0', zIndex: '5',
    paddingLeft: cs.paddingLeft, paddingTop: cs.paddingTop, paddingRight: cs.paddingRight,
    background: (live.options.theme?.background as string) || THEME.background, visibility: 'hidden',
  })
  host.appendChild(el)
  const cols = got.cols > 0 ? got.cols : live.cols
  const term = new make.Terminal({
    cols, rows: live.rows,
    theme: live.options.theme, fontFamily: live.options.fontFamily, fontSize: live.options.fontSize,
    lineHeight: live.options.lineHeight, scrollback: got.above + live.rows + 10,
    cursorBlink: false, disableStdin: true, allowProposedApi: true, rightClickSelectsWord: false,
  })
  const search = new make.Search()
  term.loadAddon(search)
  term.open(el)
  keepSelectionLocal(term)
  const lines = got.text.split('\n')
  const src: SrcRow[] = got.wrapped
    ? lines.map((l, i) => ({ text: stripAnsi(l), wrapped: got.wrapped![i] || undefined }))
    : tmuxRows(lines.map(stripAnsi), cols)
  const folds = fold ? foldsOf(src, fold.has, fold.tail) : []
  const map = new FoldMap(src.length, folds)
  // The cursor stays the live terminal's.
  const body = '\x1b[?25l' + foldLines(lines, folds, cols).join('\r\n')
  await new Promise<void>((res) => term.write(body, res))
  term.scrollToBottom()
  const layer = attachSmoothLayer(term)
  views.set(term, { src, map })
  return {
    term, layer, search, history: got.history, above: got.above, el, got, src, folds, map,
    dispose: () => { layer.dispose(); disposeTerminal(term); el.remove() },
  }
}

/** Where a reader stands: the source row at its top and the pixels into it. */
export function topOf(r: Reader): { src: number; frac: number } {
  const { pos, rowH } = r.layer.where()
  if (rowH <= 0) return { src: 0, frac: 0 }
  const line = Math.floor(pos / rowH + 1e-6)
  return { src: r.map.toSrc(line), frac: Math.max(0, pos - line * rowH) }
}

/**
 * Put a reader's top at source row `src`, `frac` pixels into it. A row now
 * collapsed: its label stands where the row stood (the text after a
 * message that ended on the top row does not move).
 */
export function placeAt(r: Reader, src: number, frac: number): void {
  const { rowH } = r.layer.where()
  r.layer.setPos(r.map.toView(src) * rowH + frac)
}

/* ------------------------------------------------------------ a plain terminal's rows */

const hex6 = (n: number) => [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(';')

function colourParams(c: IBufferCell, fg: boolean): string {
  const pal = fg ? c.isFgPalette() : c.isBgPalette()
  const rgb = fg ? c.isFgRGB() : c.isBgRGB()
  const v = fg ? c.getFgColor() : c.getBgColor()
  if (pal) return v < 8 ? String((fg ? 30 : 40) + v) : v < 16 ? String((fg ? 90 : 100) + v - 8) : `${fg ? 38 : 48};5;${v}`
  if (rgb) return `${fg ? 38 : 48};2;${hex6(v)}`
  return ''
}

/** One buffer line as text with its colours (SGR), each line starting from a reset. */
export function lineSgr(line: IBufferLine, cols: number): string {
  let out = '\x1b[0m'
  let cur = ''
  let cell: IBufferCell | undefined
  // Trailing blank cells in the default look are left out.
  let last = -1
  for (let x = 0; x < cols; x++) {
    cell = line.getCell(x, cell)
    if (!cell) break
    if (cell.getChars() || !cell.isAttributeDefault()) last = x
  }
  for (let x = 0; x <= last; x++) {
    cell = line.getCell(x, cell)
    if (!cell) break
    if (cell.getWidth() === 0) continue
    const p: string[] = []
    if (cell.isBold()) p.push('1')
    if (cell.isDim()) p.push('2')
    if (cell.isItalic()) p.push('3')
    if (cell.isUnderline()) p.push('4')
    if (cell.isBlink()) p.push('5')
    if (cell.isInverse()) p.push('7')
    if (cell.isInvisible()) p.push('8')
    if (cell.isStrikethrough()) p.push('9')
    const fg = colourParams(cell, true), bg = colourParams(cell, false)
    if (fg) p.push(fg)
    if (bg) p.push(bg)
    const key = p.join(';')
    if (key !== cur) { out += `\x1b[0${key ? `;${key}` : ''}m`; cur = key }
    out += cell.getChars() || ' '
  }
  return out + (cur ? '\x1b[0m' : '')
}

/** A plain terminal's whole buffer (its history and its screen) as a reader is made from. */
export function plainRows(t: Terminal): HistoryRows {
  const b = t.buffer.normal
  const lines: string[] = []
  const wrapped: boolean[] = []
  for (let i = 0; i < b.length; i++) {
    const l = b.getLine(i)
    lines.push(l ? lineSgr(l, t.cols) : '')
    wrapped.push(!!l?.isWrapped)
  }
  return { text: lines.join('\n'), history: b.baseY, rows: t.rows, cols: t.cols, above: b.baseY, complete: true, wrapped }
}

/** The keys that stay with the reader: copying, finding, paging, lone modifiers. */
export function readerKeeps(e: KeyboardEvent, mac: boolean, selected = false): 'keep' | 'page-up' | 'page-down' | 'close' | 'live' {
  if (['Shift', 'Control', 'Alt', 'Meta', 'CapsLock'].includes(e.key)) return 'keep'
  const mod = mac ? e.metaKey : e.ctrlKey
  const k = e.key.toLowerCase()
  if (mod && (k === 'a' || (k === 'c' && (mac || selected)))) return 'keep'
  if (e.ctrlKey && e.shiftKey && (k === 'c' || k === 'f')) return 'keep'
  if (e.key === 'PageUp') return 'page-up'
  if (e.key === 'PageDown') return 'page-down'
  if (e.key === 'Escape') return 'close'
  return 'live'
}
