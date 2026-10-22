/**
 * Focus — one chat, full screen, nothing else: the map look (Nav.tsx),
 * chosen from six experiments on 2026-09-25. The chat list on the left
 * with its filter, one reading column as wide as you set it, the whole
 * chat drawn small down the right edge, one chat or all, and the agent's
 * terminal beside it (T).
 */

import type { ReactNode } from 'react'

import type { Row } from '../data'
import { MapFocus } from './Map'

interface FocusProps {
  session: Row
  /** The chats the page lists, newest first — [ and ] walk them. */
  sessions: Row[]
  /** Every chat of the project: the map filters it itself. */
  pool?: Row[]
  /** The agent the page has picked. */
  agent?: string
  onPick: (id: string) => void
  onClose: () => void
  onOpenTask?: (id: string) => void
  /** The ★ on a turn, drawn by the host. */
  star?: (turn: number, text: string) => ReactNode
}

export function ChatFocus(props: FocusProps) {
  return <MapFocus {...props} />
}
