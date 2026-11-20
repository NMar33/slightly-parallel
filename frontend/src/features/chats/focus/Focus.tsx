/**
 * Focus — one chat, full screen, nothing else: the map look (Nav.tsx),
 * chosen from six experiments on 2026-09-25. The chat list on the left
 * with its filter, one reading column as wide as you set it, the whole
 * chat drawn small down the right edge, one chat or all, and the agent's
 * terminal beside it (T).
 */

import { MapFocus, type ChatFocusProps } from './Map'

export function ChatFocus(props: ChatFocusProps) {
  return <MapFocus {...props} />
}
