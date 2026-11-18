/**
 * Where something drawn on a row of the terminal stands: the pin marks on a
 * message (MessageMenu.BlockMarks) and the copy icon of a command
 * (CommandCopy.tsx). Both are put inside xterm's `.xterm-screen`, so the
 * smooth scrolling's pixel shift (scrollLayer.ts: a CSS translate of that
 * element) moves them with the text. What is left is the whole row: the
 * layer moves xterm by `scrollToLine`, a row at a time, while the pixels go
 * on. A mark placed by the row it had on the screen half a second ago stays
 * there while its text moves up a row, then jumps back (tk_49c10a34: «при
 * прокрутке метка «закреплено» отстаёт от строки сообщения»).
 *
 * So a mark keeps its line in the buffer (absolute), and its top is worked
 * out from xterm's own row at the moment xterm moves (`onScroll`, which
 * fires inside `scrollToLine`, in the same frame as the shift): on the
 * screen it stands at `line × rowH − pos`, exactly where its text is. The
 * new top is rendered at once (flushSync), not in React's next task: that
 * would come after the frame is painted, a row off for one frame.
 */

import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import type { Terminal } from 'xterm'

export interface View { viewportY: number; rows: number; cell: number }

/** The top of buffer line `abs` inside `.xterm-screen` (before the shift), or null when it is off the screen. */
export function rowTop(abs: number, v: View): number | null {
  const r = abs - v.viewportY
  return r >= 0 && r < v.rows ? r * v.cell : null
}

/** The view of a terminal as it stands now: its first row in the buffer, its rows, a row's height in pixels. */
export function viewOf(t: Terminal): View {
  const host = t.element?.querySelector('.xterm-screen') as HTMLElement | null
  return { viewportY: t.buffer.active.viewportY, rows: t.rows, cell: host && t.rows ? host.clientHeight / t.rows : 0 }
}

const same = (a: View | null, b: View) => !!a && a.viewportY === b.viewportY && a.rows === b.rows && a.cell === b.cell

/** The view of `term`, again each time xterm moves its rows (a scroll, a resize, a buffer switch), rendered in the same frame. */
export function useView(term: Terminal | null | undefined): View | null {
  const [v, setV] = useState<View | null>(() => (term ? viewOf(term) : null))
  useEffect(() => {
    if (!term) { setV(null); return }
    const set = (n: View) => setV((o) => (same(o, n) ? o : n))
    const upd = () => {
      const n = viewOf(term)
      // From inside React's own work (an effect that scrolled), the state is set the ordinary way.
      try { flushSync(() => set(n)) } catch { set(n) }
    }
    set(viewOf(term))
    const subs = [term.onScroll(upd), term.onResize(upd), term.buffer.onBufferChange(upd), term.onRender(upd)]
    return () => { for (const s of subs) s.dispose() }
  }, [term])
  return v
}
