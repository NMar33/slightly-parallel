/**
 * The native window around SP Aqua, when there is one: the app's shell
 * (desktop/, Electron) hands the page `window.spWindow`. Inside it the title
 * row moves the window, the sidebars grow the window outward and the
 * close and minimise buttons work; in an ordinary browser there is no
 * bridge, the sidebars grow inside the page and a detach is a new tab.
 */

type Handler = {
  postMessage: (msg: unknown) => void
  restoreOffer?: () => Promise<number>
  saveDraft?: (name: string, text: string) => Promise<boolean>
}

export type BridgeOp =
  | { op: 'drag' }
  | { op: 'close' }
  | { op: 'minimize' }
  | { op: 'fullscreen' }
  | { op: 'grow'; left: number; right: number }
  | { op: 'detach'; url: string }
  | { op: 'title'; text: string }
  /** A page outside the window (http/https), in the browser. */
  | { op: 'open'; url: string }
  /** The answer to restoreOffer: open the windows of last time, or not. */
  | { op: 'restore'; open: boolean }

function handler(): Handler | null {
  if (typeof window === 'undefined') return null
  const h = (window as unknown as { spWindow?: Handler }).spWindow
  return h && typeof h.postMessage === 'function' ? h : null
}

/** Inside the app's own window. */
export const isNative = () => handler() !== null

/** Tell the window; false when there is no window to tell. */
export function post(msg: BridgeOp): boolean {
  const h = handler()
  if (!h) return false
  try { h.postMessage(msg); return true } catch { return false }
}


/** Let the native Save As dialog choose the destination. Undefined on the web or an older desktop shell. */
export function saveNativeDraft(name: string, text: string): Promise<boolean> | undefined {
  return handler()?.saveDraft?.(name, text)
}

/** Another window on this address: the app's own, or a browser tab. */
export function openWindow(url: string) {
  if (!post({ op: 'detach', url })) window.open(url, '_blank', 'noopener')
}

/** How many windows of last time wait for the operator's answer (Settings ›
 *  Terminal › On start: ask). 0 outside the app, in a window that is not the
 *  main one, or when nothing waits. */
export async function restoreOffer(): Promise<number> {
  const h = handler()
  if (!h || typeof h.restoreOffer !== 'function') return 0
  try { const n = await h.restoreOffer(); return typeof n === 'number' && n > 0 ? n : 0 } catch { return 0 }
}
