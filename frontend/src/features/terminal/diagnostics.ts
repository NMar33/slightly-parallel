import type { Terminal } from 'xterm'

import type { Reader } from './reader'
import type { SmoothLayer } from './scrollLayer'

/** Both the displayed window and the live screen, even far back in history. */
function bufferSnapshot(term: Terminal) {
  const b = term.buffer.active
  const indexes = new Set<number>()
  for (const start of [b.viewportY, b.baseY]) {
    const end = Math.min(b.length, start + term.rows)
    for (let i = start; i < end; i++) indexes.add(i)
  }
  const rowsByIndex = [...indexes].sort((a, b) => a - b).map((index) => {
    const line = b.getLine(index)
    return { index, text: line?.translateToString(false) ?? '', wrapped: !!line?.isWrapped }
  })
  return {
    rows: term.rows, cols: term.cols, type: b.type, length: b.length, baseY: b.baseY,
    viewportY: b.viewportY, cursorX: b.cursorX, cursorY: b.cursorY,
    mouseTrackingMode: term.modes.mouseTrackingMode,
    rowsByIndex,
  }
}

function domRows(term: Terminal) {
  return Array.from(term.element?.querySelector('.xterm-rows')?.children ?? [], (row) => row.textContent ?? '')
}

function layerSnapshot(term: Terminal, layer: SmoothLayer | null) {
  const screen = term.element?.querySelector<HTMLElement>('.xterm-screen')
  const ghost = screen?.querySelector<HTMLElement>('.sp-ghost-row')
  return {
    ...layer?.where(),
    transform: screen?.style.transform ?? '',
    clipPath: screen?.style.clipPath ?? '',
    partialRow: ghost?.style.display === 'block' ? ghost.textContent : null,
  }
}

/** Record both xterms and their DOM in the same browser task, without moving them. */
export function terminalSnapshot(live: Terminal, layer: SmoothLayer | null, reader: Reader | null, smooth: boolean) {
  return {
    capturedAt: new Date().toISOString(),
    xterm: { live: bufferSnapshot(live), reader: reader ? bufferSnapshot(reader.term) : null },
    dom: { live: domRows(live), reader: reader ? domRows(reader.term) : null },
    scrollLayer: {
      smooth,
      live: layerSnapshot(live, layer),
      reader: reader ? { ...layerSnapshot(reader.term, reader.layer), visibility: reader.el.style.visibility } : null,
    },
  }
}
