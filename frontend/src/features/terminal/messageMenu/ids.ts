/**
 * Slightly Parallel's records in a terminal row: a task (tk_), a note (nt_),
 * a decision (dc_), an entry point (ep_), a Publish card (pu_), a core
 * (cr_), a skill (sk_), a chat (its agent id: cc-, codex-, oc-, cursor-),
 * and a git commit (its hash). They underline on hover and a click opens
 * their menu or card (MessageMenu.tsx, IdCards.tsx).
 *
 * A commit hash is only a candidate here: the layer asks the server whether
 * it is a commit of the terminal's project before it underlines it.
 */

export interface FoundId { id: string; kind: IdKind; start: number; length: number }

const KIND = {
  tk: 'task', nt: 'note', dc: 'decision', ep: 'entrypoint', pu: 'publish', cr: 'core', sk: 'skill',
  rl: 'rule', vs: 'vision', pb: 'problem', msg: 'message',
} as const
type Prefix = keyof typeof KIND
export type IdKind = (typeof KIND)[Prefix] | 'agent' | 'commit'

// Eight hex digits, not part of a longer word: tk_a9306fb1, (tk_a9306fb1), tk_a9306fb1.
const ID = new RegExp(String.raw`(?<![\p{L}\p{N}_])(${Object.keys(KIND).join('|')})_[0-9a-f]{8}(?![\p{L}\p{N}_])`, 'gu')

// A chat's agent id (backend hookshared.session_key): Claude Code, Codex and
// Cursor take eight hex digits of the session; OpenCode eight letters or
// digits of its own (oc-y0q3vy8m), with a digit among them here, so a word
// such as oc-assigned is never one. Not part of a longer word or name.
const AGENT = /(?<![\p{L}\p{N}_.-])(?:(?:cc|codex|cursor)-[0-9a-f]{8}|oc-(?=[a-z]{0,7}[0-9])[0-9a-z]{8})(?![\p{L}\p{N}_-])/gu

// A run of 7–40 hex digits standing alone.
const HEX = /(?<![\p{L}\p{N}_])[0-9a-f]{7,40}(?![\p{L}\p{N}_])/gu

/** What may stand right before a hash: the row's start, a space, an opening bracket or quote, a comma, or `..` of a range. */
function openOk(text: string, at: number): boolean {
  if (at === 0) return true
  const c = text[at - 1]!
  if (/\s/u.test(c) || '([{<\'"`,'.includes(c)) return true
  return c === '.' && text[at - 2] === '.' && /[0-9a-f]/.test(text[at - 3] ?? '')
}

/** What may stand right after one: the row's end, a space, a closing bracket or quote, `,;:`, an end of sentence, or `..` of a range. */
function closeOk(text: string, end: number): boolean {
  if (end >= text.length) return true
  const c = text[end]!
  if (/\s/u.test(c) || ')]}>\'"`,;:'.includes(c)) return true
  const next = text[end + 1]
  if ('.!?'.includes(c) && (next === undefined || /\s/u.test(next))) return true
  return c === '.' && next === '.' && /[0-9a-f]/.test(text[end + 2] ?? '')
}

/**
 * A hash a commit may have: 7–40 hex digits with a letter and a digit among
 * them (no number, no word like "deadbeef" or "decade"), standing alone —
 * never a part of a word, of an id (tk_…), of a UUID (its dashes), of a
 * version (1.2.3), of a path or a URL (a slash, `=`, `#`, a dot before it).
 */
export function hashCandidates(text: string): FoundId[] {
  const out: FoundId[] = []
  for (const m of text.matchAll(HEX)) {
    const s = m[0]
    const at = m.index!
    if (!/[a-f]/.test(s) || !/[0-9]/.test(s)) continue
    if (!openOk(text, at) || !closeOk(text, at + s.length)) continue
    out.push({ id: s, kind: 'commit', start: at, length: s.length })
  }
  return out
}

/** Every record named in a row, in the row's order; commit hashes as candidates still to check. */
export function findIds(text: string): FoundId[] {
  const out: FoundId[] = []
  for (const m of text.matchAll(ID)) out.push({ id: m[0], kind: KIND[m[1] as Prefix], start: m.index!, length: m[0].length })
  for (const m of text.matchAll(AGENT)) out.push({ id: m[0], kind: 'agent', start: m.index!, length: m[0].length })
  // A hash inside an id or an agent id found above is theirs.
  const taken = (f: FoundId) => out.some((o) => f.start < o.start + o.length && o.start < f.start + f.length)
  for (const h of hashCandidates(text)) if (!taken(h)) out.push(h)
  return out.sort((a, b) => a.start - b.start)
}
