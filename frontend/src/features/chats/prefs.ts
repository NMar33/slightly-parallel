import { persistPref, readPref } from '../../lib/uiPrefs'

/**
 * What the chats page remembers between visits.
 *
 * The reader used to carry these as loose buttons in its own header — text
 * size, markdown, order. They are settings, not tools, so they moved under
 * one gear, in the same strip the task window opens. The reader still owns
 * them on the agent page, where there is no gear; the chats page hands them
 * down and hides its buttons.
 *
 * The four the reader also keeps are written to the reader's own keys as
 * well, so a size set here is the size the agent page opens with. Usage goes
 * both ways: the reader's switch writes it back here (storeUsagePref).
 */

/** How the width is split between the list of chats and the chat. */
type PaneWidth = 'narrow' | 'even' | 'wide'

/** Reading sizes in px — the same three the reader offers. */
type TextSize = 12 | 14 | 16

export interface ChatsPrefs {
  /** The list of chats against the chat itself. */
  width: PaneWidth
  /** Text size in the list of chats. */
  list: TextSize
  /** Text size in the chat. */
  chat: TextSize
  /** Oldest first, or newest first. */
  order: 'oldest' | 'newest'
  /** Render markdown, or show the raw text as it was sent. */
  md: boolean
  /** Show the commits and files a turn made. */
  work: boolean
  /** Show a turn's tokens on its meta row. On by default: the viewer is
   *  where one looks on purpose. Tokens are recorded either way. */
  usage: boolean
}

const CHATS_PREFS_KEY = 'sp-chats'

const DEFAULT_CHATS_PREFS: ChatsPrefs = {
  width: 'even', list: 12, chat: 12, order: 'oldest', md: true, work: true, usage: true,
}

/** The reader's own keys, kept in step so both surfaces read alike. */
const READER_KEYS = { size: 'sp-chat-size', md: 'sp-chat-md', order: 'sp-chat-order', usage: 'sp-chat-usage' }

function size(v: unknown, fallback: TextSize): TextSize {
  const n = Number(v)
  return n === 12 || n === 14 || n === 16 ? n : fallback
}

export function readChatsPrefs(): ChatsPrefs {
  let raw: unknown
  try { raw = JSON.parse(readPref(CHATS_PREFS_KEY) ?? 'null') } catch { raw = null }
  const d = DEFAULT_CHATS_PREFS
  if (!raw || typeof raw !== 'object') return readerFallback(d)
  const p = raw as Partial<ChatsPrefs>
  return {
    width: p.width === 'narrow' || p.width === 'wide' ? p.width : d.width,
    list: size(p.list, d.list),
    chat: size(p.chat, d.chat),
    order: p.order === 'newest' ? 'newest' : 'oldest',
    md: p.md !== false,
    work: p.work !== false,
    // One truth for both surfaces: the reader's key, which the agent page's
    // switch writes too; the saved field only when that key was never set.
    usage: usageFrom(readPref(READER_KEYS.usage), p.usage),
  }
}

function usageFrom(reader: string | null, saved: unknown): boolean {
  if (reader === 'on') return true
  if (reader === 'off') return false
  return saved !== false
}

/**
 * The agent page's reader changed "usage": the chats page's saved prefs
 * follow, so the two never disagree (the reader's key is written by the caller).
 */
export function storeUsagePref(on: boolean): void {
  persistPref(READER_KEYS.usage, on ? 'on' : 'off')
  let raw: unknown
  try { raw = JSON.parse(readPref(CHATS_PREFS_KEY) ?? 'null') } catch { raw = null }
  if (raw && typeof raw === 'object') persistPref(CHATS_PREFS_KEY, JSON.stringify({ ...(raw as object), usage: on }))
}

/** The key the usage pref lives under, for listeners of `sp:pref`. */
export const USAGE_PREF_KEY = READER_KEYS.usage

/** First visit: start from whatever the reader was already set to. */
function readerFallback(d: ChatsPrefs): ChatsPrefs {
  return {
    ...d,
    chat: size(readPref(READER_KEYS.size), d.chat),
    md: readPref(READER_KEYS.md) !== 'off',
    order: readPref(READER_KEYS.order) === 'reverse' ? 'newest' : 'oldest',
    usage: readPref(READER_KEYS.usage) !== 'off',
  }
}

/** readPref and persistPref never throw: a browser with no storage still reads chats. */
export function storeChatsPrefs(p: ChatsPrefs): void {
  persistPref(CHATS_PREFS_KEY, JSON.stringify(p))
  persistPref(READER_KEYS.size, String(p.chat))
  persistPref(READER_KEYS.md, p.md ? 'on' : 'off')
  persistPref(READER_KEYS.order, p.order === 'newest' ? 'reverse' : 'normal')
  persistPref(READER_KEYS.usage, p.usage ? 'on' : 'off')
}

/** The grid the two panes sit in. Narrow is a rail to pick from; even
 *  splits the room; wide is for reading the list itself. */
export function paneColumns(width: PaneWidth): string {
  if (width === 'narrow') return 'minmax(0, 240px) minmax(0, 1fr)'
  if (width === 'wide') return 'minmax(0, 2fr) minmax(0, 1fr)'
  return 'minmax(0, 1fr) minmax(0, 1fr)'
}
