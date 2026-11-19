/**
 * Which recorded chat message a row of the terminal belongs to
 * (tk_a9306fb1): the right-click menu on a message in the real terminal.
 *
 * The terminal holds text, not messages. Claude Code prints the chat into
 * the normal screen and wraps it itself:
 *
 *   ❯ the operator's message            (older versions: "> ")
 *     its next lines, indented
 *   ● the agent's text                  (older versions: "⏺ ")
 *   ● Bash(…)  /  ⎿ tool output, indented
 *   ✻ Worked for 42s · done             (a status line)
 *   ──────── / ❯ draft / ────────       (the input box: never a message)
 *
 * Codex draws the same parts with its own marks (tk_86712550):
 *
 *   › the operator's message            (its next lines indented)
 *   • the agent's text, • Ran …, • Edited …, └ output, indented
 *     Worked for 6s • 7:44 PM            (a status line, indented)
 *   › draft                              (its input box, no rules around:
 *                                         never in the record, so never found)
 *
 * Slightly Parallel records each turn: the operator's message whole and the
 * agent's final answer (its last message; what it said between tool calls
 * is not recorded). So a row is matched in two ways:
 *
 * - by text: the rows of the block around the click, reduced to letters and
 *   digits (markdown, box lines, wrapping and indents gone), are looked up
 *   in the recorded messages of the same side. A message that holds more of
 *   the block's text wins; the clicked row counts twice. A short block
 *   ("статус") counts only when a whole message is exactly that.
 * - by turn: anything printed after the operator's message n and before the
 *   next one is the agent's reply in turn n. A click in the agent's
 *   narration, a tool call or a status line walks up to the nearest
 *   operator message and takes its turn; an operator message that is not in
 *   the record (a slash command) stops the walk: nothing is guessed.
 *
 * The same words in two turns ("статус" twice): the operator's messages are
 * in turn order on the screen, so the nearest message above or below that
 * matched only one turn says which; failing that, the most recent turn.
 */

export type Side = '' | 'reply'

/** One recorded turn: its number in the chat, its session, the two texts. */
export interface CapturedTurn { n: number; sid: string; user: string; agent: string }

export interface Found {
  n: number
  side: Side
  sid: string
  /** text: the block's own text was found; turn: the operator's message above gave the turn. */
  how: 'text' | 'turn'
}

export type RowKind = 'user' | 'agent' | 'status' | 'input' | 'other' | 'cont'

const USER = /^(❯|>|›)(\s|$)/
const AGENT = /^(●|⏺|•)(\s|$)/
/** Claude Code's "› Message from …" (another session's message): a status line, not the operator's. */
const PEER = /^› Message from /
// Spinner and status glyphs Claude Code starts a line with, and "› Message from …".
const STATUS = /^[✻✶✳✢✽✺·*›⎿]\s/
const RULE = /^[─━]+$/
/** A row of Claude Code's own under a block: a tool's output, "Interrupted". */
const UI = /^\s*⎿/

/** Letters and digits only, lower case: what is left of a text whatever the terminal did to it. */
export function keyOf(s: string): string {
  return s.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '')
}

/** The agent's text as Claude Code shows it: links by their words. */
function shownReply(s: string): string {
  return s.replace(/!?\[([^\]]*)\]\([^)\s]*\)/g, '$1')
}

export function rowKind(row: string, prev?: string): RowKind {
  if (!row.trim() || /^\s/.test(row)) return 'cont'
  if (PEER.test(row)) return 'status'
  if (USER.test(row)) return prev !== undefined && RULE.test(prev.trim()) ? 'input' : 'user'
  if (AGENT.test(row)) return 'agent'
  if (STATUS.test(row)) return 'status'
  return 'other'
}

/** A row's words without the block's marker. */
const content = (row: string) => row.replace(/^(❯|>|›|●|⏺|•)\s?/, '')

export interface Block { start: number; end: number; kind: Exclude<RowKind, 'cont'> }

/** The rows cut into blocks: a block starts at an unindented row and holds the indented and empty rows after it. */
export function blocksOf(rows: string[]): Block[] {
  const out: Block[] = []
  for (let i = 0; i < rows.length; i++) {
    const k = rowKind(rows[i]!, i > 0 ? rows[i - 1] : undefined)
    if (k === 'cont') {
      if (!out.length) out.push({ start: i, end: i, kind: 'other' })
      else out[out.length - 1]!.end = i
      continue
    }
    out.push({ start: i, end: i, kind: k })
  }
  return out
}

/* ------------------------------------------------------------ the record */

/** One side of every turn as one long key, to search once instead of once per turn. */
class SideIndex {
  readonly all: string
  private readonly starts: number[] = []
  private readonly turns: CapturedTurn[] = []
  readonly whole = new Map<string, CapturedTurn[]>()

  constructor(turns: CapturedTurn[], side: Side) {
    const parts: string[] = []
    let at = 0
    for (const t of turns) {
      const text = side === 'reply' ? shownReply(t.agent) : t.user
      const k = keyOf(text)
      if (!k) continue
      this.starts.push(at)
      this.turns.push(t)
      parts.push(k)
      at += k.length + 1
      const same = this.whole.get(k)
      if (same) same.push(t)
      else this.whole.set(k, [t])
    }
    // A separator no key holds: a row never matches across two messages.
    this.all = parts.join('\u0000')
  }

  /** Every turn whose text holds `k`. */
  holding(k: string): CapturedTurn[] {
    const out = new Set<CapturedTurn>()
    let i = this.all.indexOf(k)
    while (i >= 0) {
      out.add(this.turnAt(i))
      i = this.all.indexOf(k, i + 1)
    }
    return [...out]
  }

  private turnAt(pos: number): CapturedTurn {
    let lo = 0, hi = this.starts.length - 1
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1
      if (this.starts[mid]! <= pos) lo = mid
      else hi = mid - 1
    }
    return this.turns[lo]!
  }
}

export class Record {
  readonly user: SideIndex
  readonly reply: SideIndex
  readonly byN = new Map<number, CapturedTurn>()
  constructor(readonly turns: CapturedTurn[]) {
    this.user = new SideIndex(turns, '')
    this.reply = new SideIndex(turns, 'reply')
    for (const t of turns) this.byN.set(t.n, t)
  }
}

/** A row shorter than this (in letters and digits) says too little on its own. */
const ROW_MIN = 4
/** A block counts as found with this much of its text found, or when a whole message is exactly the block. */
const ENOUGH = 12

type Scores = Map<CapturedTurn, number>

/** How much of the block's text each recorded message holds. */
function score(rows: string[], b: Block, idx: SideIndex, focus: number | null): { scores: Scores; found: Scores; exact: CapturedTurn[] } {
  // `scores` ranks (the clicked row counts twice); `found` is how much text was found, for the threshold.
  const scores: Scores = new Map()
  const found: Scores = new Map()
  const add = (ts: CapturedTurn[], w: number, n: number) => {
    for (const t of ts) { scores.set(t, (scores.get(t) ?? 0) + w); found.set(t, (found.get(t) ?? 0) + n) }
  }
  const whole: string[] = []
  for (let i = b.start; i <= b.end; i++) {
    // "⎿ Interrupted", a tool's output: Claude Code's, never a recorded text.
    if (UI.test(rows[i]!)) continue
    const text = content(rows[i]!)
    const k = keyOf(text)
    if (k) whole.push(k)
    if (k.length < ROW_MIN) continue
    const w = k.length * (i === focus ? 2 : 1)
    const hit = idx.holding(k)
    if (hit.length) { add(hit, w, k.length); continue }
    // A row Claude Code drew differently in one place (a link, a table cell
    // wrapped): its two halves, each long enough to say something.
    if (k.length >= 24) {
      const words = text.trim().split(/\s+/)
      const mid = Math.ceil(words.length / 2)
      for (const half of [words.slice(0, mid).join(' '), words.slice(mid).join(' ')]) {
        const hk = keyOf(half)
        if (hk.length >= 10) add(idx.holding(hk), Math.floor(w / 2), hk.length)
      }
    }
  }
  return { scores, found, exact: idx.whole.get(whole.join('')) ?? [] }
}

/** The turns that best hold the block, best first (several only on a tie). */
function candidates(rows: string[], b: Block, idx: SideIndex, focus: number | null): CapturedTurn[] {
  const { scores, found, exact } = score(rows, b, idx, focus)
  if (exact.length) return exact
  let best = 0
  for (const v of scores.values()) best = Math.max(best, v)
  return [...scores.entries()].filter(([t, v]) => v === best && (found.get(t) ?? 0) >= ENOUGH).map(([t]) => t)
}

/** Several turns hold the operator's block: its neighbours that match one turn each say which. */
function settle(rows: string[], blocks: Block[], bi: number, rec: Record, tied: CapturedTurn[]): CapturedTurn {
  const newest = () => tied.reduce((a, b) => (b.n > a.n ? b : a))
  if (tied.length === 1) return tied[0]!
  const near = (dir: -1 | 1): number | null => {
    let k = 0
    for (let j = bi + dir; j >= 0 && j < blocks.length; j += dir) {
      if (blocks[j]!.kind !== 'user') continue
      k += 1
      const c = candidates(rows, blocks[j]!, rec.user, null)
      if (c.length === 1) return c[0]!.n - dir * k
      if (k > 40) break
    }
    return null
  }
  const expect = near(-1) ?? near(1)
  if (expect == null) return newest()
  return tied.reduce((a, b) => {
    const da = Math.abs(a.n - expect), db = Math.abs(b.n - expect)
    return db < da || (db === da && b.n > a.n) ? b : a
  })
}

/** The operator's message block `bi`, as a turn, or null when it is not in the record. */
function userTurn(rows: string[], blocks: Block[], bi: number, rec: Record, focus: number | null): CapturedTurn | null {
  const c = candidates(rows, blocks[bi]!, rec.user, focus)
  return c.length ? settle(rows, blocks, bi, rec, c) : null
}

/**
 * The operator's message block `bi` as a turn, and whether only its first
 * row is the message. Codex, scrolled up, pins the prompt of the turn on
 * view to the screen's top row while the turn's output scrolls under it
 * (tk_86712550): the output's indented rows join the prompt's block, and
 * the block as a whole is no message. Its first row alone, when that is
 * one, is the message; the rows under it are that turn's.
 */
function userTurnOrHead(rows: string[], blocks: Block[], bi: number, rec: Record, focus: number | null): { t: CapturedTurn; head: boolean } | null {
  const b = blocks[bi]!
  const head = (): CapturedTurn | null => {
    if (b.end === b.start) return null
    const c = candidates(rows, { start: b.start, end: b.start, kind: 'user' }, rec.user, null)
    return c.length ? settle(rows, blocks, bi, rec, c) : null
  }
  // On the screen's top row it is the pinned prompt first: the output glued
  // under it may hold words of another message (one that quoted a reply).
  const pinned = b.start === 0 ? head() : null
  if (pinned) return { t: pinned, head: true }
  const t = userTurn(rows, blocks, bi, rec, focus)
  if (t) return { t, head: false }
  const h = b.start === 0 ? null : head()
  return h ? { t: h, head: true } : null
}

/** How far up a click in the agent's output walks to find the operator's message. */
const WALK = 400

/**
 * The recorded message row `at` of `rows` belongs to, or null.
 */
export function messageAt(rows: string[], at: number, rec: Record): Found | null {
  if (at < 0 || at >= rows.length || !rec.turns.length) return null
  const blocks = blocksOf(rows)
  const bi = blocks.findIndex((b) => at >= b.start && at <= b.end)
  if (bi < 0) return null
  const b = blocks[bi]!
  if (b.kind === 'input' || b.kind === 'other') return null
  if (b.kind === 'user') {
    const got = userTurnOrHead(rows, blocks, bi, rec, at)
    if (!got) return null
    const { t, head } = got
    return head && at > b.start ? { n: t.n, side: 'reply', sid: t.sid, how: 'turn' } : { n: t.n, side: '', sid: t.sid, how: 'text' }
  }
  // The agent's side: its text where it was recorded, the turn above in any case.
  const own = b.kind === 'agent' ? candidates(rows, b, rec.reply, at) : []
  let above: CapturedTurn | null | undefined
  for (let j = bi - 1; j >= 0 && b.start - blocks[j]!.end < WALK; j--) {
    const k = blocks[j]!.kind
    if (k === 'other' || k === 'input') break
    if (k !== 'user') continue
    above = userTurnOrHead(rows, blocks, j, rec, null)?.t
    break
  }
  // The operator's message above decides: the record keeps only the agent's
  // last message of a turn, and a line of its narration can read like
  // another turn's answer ("Ждут твоего ответа:").
  if (above) return { n: above.n, side: 'reply', sid: above.sid, how: own.includes(above) ? 'text' : 'turn' }
  if (own.length) {
    const t = own.reduce((a, c) => (c.n > a.n ? c : a))
    return { n: t.n, side: 'reply', sid: t.sid, how: 'text' }
  }
  return null
}

/** The text of the block around row `at`, as shown: the fallback "copy the line" copies the row itself. */
export function blockText(rows: string[], at: number): string {
  const b = blocksOf(rows).find((x) => at >= x.start && at <= x.end)
  if (!b) return rows[at] ?? ''
  const out = rows.slice(b.start, b.end + 1).map((r, i) => (i === 0 ? content(r) : r.replace(/^ {2}/, '')))
  while (out.length && !out[out.length - 1]!.trim()) out.pop()
  return out.join('\n')
}
