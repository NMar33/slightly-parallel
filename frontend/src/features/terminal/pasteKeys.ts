import { letter } from '../../lib/typing'

/**
 * Who pastes when a paste key is pressed in the terminal. One of them only:
 * the operator's command once reached the shell twice, glued, because the
 * page pasted on Ctrl+Shift+V and Chromium pasted again from its own "paste
 * as plain text" on xterm's textarea.
 *
 * - 'native': the browser's own paste. Its `paste` event reaches xterm's
 *   textarea and xterm sends the text once. Ctrl+Shift+V and Shift+Insert
 *   on Linux and Windows, Cmd+V on macOS (Electron's default Edit menu).
 *   The page only keeps the key from xterm.
 * - 'page': the browser has no paste for this key (Ctrl+Shift+V on macOS):
 *   the page cancels the key and pastes from the clipboard itself.
 * - null: not a paste key. Ctrl+V is the shell's ^V on Linux and macOS, as
 *   in GNOME Terminal and Terminal.app (Claude Code takes it as "paste an
 *   image"); on Windows PowerShell's line editor pastes on ^V itself.
 */
export type PasteBy = 'native' | 'page' | null

export function pasteKey(e: { key: string; code?: string; ctrlKey: boolean; shiftKey: boolean; altKey: boolean; metaKey: boolean }, mac: boolean): PasteBy {
  if (e.altKey) return null
  if (e.shiftKey && !e.ctrlKey && !e.metaKey && e.key === 'Insert') return mac ? null : 'native'
  if (letter(e) !== 'v') return null
  if (mac && e.metaKey && !e.ctrlKey && !e.shiftKey) return 'native'
  if (e.ctrlKey && e.shiftKey && !e.metaKey) return mac ? 'page' : 'native'
  return null
}

/** The paste key named in the terminal's menu and messages. */
export const pasteKeyName = (mac: boolean) => (mac ? 'Cmd+V' : 'Ctrl+Shift+V')

export const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
