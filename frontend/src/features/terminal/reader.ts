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

import type { Terminal } from 'xterm'
import type { SearchAddon } from 'xterm-addon-search'
import { postJson } from '../../lib/getJson'
import { attachSmoothLayer, type SmoothLayer } from './scrollLayer'

export interface HistoryRows {
  text: string
  history: number
  rows: number
  cols: number
  above: number
  complete: boolean
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
  dispose: () => void
}

type Make = { Terminal: typeof Terminal; Search: new () => SearchAddon }

export const fetchRows = (sid: string, rows: number) =>
  postJson<HistoryRows>(`/api/terminal/sessions/${encodeURIComponent(sid)}/capture`, { mode: 'history', rows })

/** Build a reader over `host` from `got` (hidden until written). */
export async function buildReader(make: Make, host: HTMLElement, live: Terminal, got: HistoryRows): Promise<Reader> {
  const el = document.createElement('div')
  el.className = 'sp-reader'
  // Laid over the live xterm exactly: the same box, the same padding.
  const cs = getComputedStyle(host)
  Object.assign(el.style, {
    position: 'absolute', left: '0', top: '0', right: '0', bottom: '0', zIndex: '5',
    paddingLeft: cs.paddingLeft, paddingTop: cs.paddingTop, paddingRight: cs.paddingRight,
    background: (live.options.theme?.background as string) || '#000', visibility: 'hidden',
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
  // The cursor stays the live terminal's.
  const body = '\x1b[?25l' + got.text.split('\n').join('\r\n')
  await new Promise<void>((res) => term.write(body, res))
  term.scrollToBottom()
  const layer = attachSmoothLayer(term)
  return {
    term, layer, search, history: got.history, above: got.above, el,
    dispose: () => { layer.dispose(); try { term.dispose() } catch { /* fine */ } el.remove() },
  }
}

/** The keys that stay with the reader: copying, finding, paging, lone modifiers. */
export function readerKeeps(e: KeyboardEvent, mac: boolean): 'keep' | 'page-up' | 'page-down' | 'close' | 'live' {
  if (['Shift', 'Control', 'Alt', 'Meta', 'CapsLock'].includes(e.key)) return 'keep'
  const mod = mac ? e.metaKey : e.ctrlKey
  const k = e.key.toLowerCase()
  if (mod && (k === 'c' || k === 'a')) return 'keep'
  if (e.ctrlKey && e.shiftKey && (k === 'c' || k === 'f')) return 'keep'
  if (e.key === 'PageUp') return 'page-up'
  if (e.key === 'PageDown') return 'page-down'
  if (e.key === 'Escape') return 'close'
  return 'live'
}
