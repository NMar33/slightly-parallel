/**
 * Notes (tk_3e544086): the shape of a note and the parser for its light
 * markup, shared by the Notes page, the task window and the design round.
 * The server parses the same way (backend notelib.py: the same item ids,
 * the same hash), so a tick it keeps is the tick drawn here.
 *
 * The file stays readable markdown. What Slightly Parallel adds:
 *
 *   tk_xxxxxxxx ep_ dc_ pu_   live chips (title, status)
 *   ```copy Title             a block with a copy button
 *   - [ ] / - [x]             a checklist the operator ticks (the server keeps it)
 *   ```gallery                images with captions that step like a shot series
 *   :::fold Title … :::       a folded section
 *   ```choice Question        numbered options answered by a button
 *   ```mermaid                a diagram
 */

export type NoteKind = 'context' | 'paste' | 'review' | 'plan' | 'report' | 'actions'
export const KINDS: NoteKind[] = ['context', 'paste', 'review', 'plan', 'report', 'actions']

export interface NoteSource {
  id: string
  project: string
  kind: NoteKind
  /** The task the note was written for. */
  task: string
  /** The chat that wrote it. */
  chat: string
  entrypoint?: string
  publish?: string
  created: string
  updated: string
  versions: number
  /** The markdown, its first line the title (`# …`). */
  body: string
  /** A newer note that takes this one's place. */
  replacedBy?: string
  /** Older notes this one takes the place of. */
  replaces?: string[]
  /** Pictures kept with the note, by id (`ni_…`). */
  images?: Array<{ id: string; caption: string; src: string; width?: number; height?: number }>
  archivedAt?: string
}

export interface CheckItem { id: string; text: string; done: boolean }
export interface Shot { src: string; caption: string }

export type Block =
  | { type: 'md'; text: string }
  | { type: 'copy'; id: string; title: string; text: string }
  | { type: 'check'; items: CheckItem[] }
  | { type: 'gallery'; id: string; shots: Shot[] }
  | { type: 'choice'; id: string; question: string; options: string[] }
  | { type: 'mermaid'; src: string }
  | { type: 'fold'; title: string; blocks: Block[] }

export interface Section { id: string; title: string; blocks: Block[] }

export interface Note extends NoteSource {
  title: string
  sections: Section[]
  /** Every id the text names, in order, without repeats. */
  refs: string[]
  words: number
  /** The first paragraph, plain. */
  lead: string
}

/** A short stable hash: a tick or an answer is kept by its text, so it survives a new version that leaves the item as it was. */
export function hashOf(s: string): string {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return (h >>> 0).toString(16).padStart(8, '0')
}

export const ID_RE = /\b(?:tk|ep|dc|pu|nt)_[0-9a-f]{8}\b/g

const CHECK = /^\s*- \[( |x|X)\] (.*)$/

function parseBlocks(lines: string[], noteId: string): Block[] {
  const out: Block[] = []
  let md: string[] = []
  const flush = () => {
    const text = md.join('\n').trim()
    if (text) out.push({ type: 'md', text })
    md = []
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!
    const fence = line.match(/^```(copy|gallery|choice|mermaid)\b ?(.*)$/)
    if (fence) {
      flush()
      const inner: string[] = []
      i++
      while (i < lines.length && !lines[i]!.startsWith('```')) inner.push(lines[i++]!)
      const kind = fence[1]!
      const head = (fence[2] ?? '').trim()
      if (kind === 'copy') out.push({ type: 'copy', id: `${noteId}:c:${hashOf(head + inner.join('\n'))}`, title: head, text: inner.join('\n') })
      else if (kind === 'mermaid') out.push({ type: 'mermaid', src: inner.join('\n') })
      else if (kind === 'gallery') {
        const shots = inner.map((l) => l.match(/^!\[(.*)\]\((.*)\)\s*$/)).filter((m): m is RegExpMatchArray => !!m)
          .map((m) => ({ caption: m[1]!, src: m[2]! }))
        out.push({ type: 'gallery', id: `${noteId}:g:${hashOf(shots.map((s) => s.src).join())}`, shots })
      } else {
        const options = inner.map((l) => l.match(/^\s*\d+\.\s+(.*)$/)?.[1]).filter((o): o is string => !!o)
        out.push({ type: 'choice', id: `${noteId}:q:${hashOf(head + options.join('|'))}`, question: head, options })
      }
      continue
    }
    const fold = line.match(/^:::fold\s+(.*)$/)
    if (fold) {
      flush()
      const inner: string[] = []
      i++
      while (i < lines.length && lines[i]!.trim() !== ':::') inner.push(lines[i++]!)
      out.push({ type: 'fold', title: fold[1]!.trim(), blocks: parseBlocks(inner, noteId) })
      continue
    }
    if (CHECK.test(line)) {
      flush()
      const items: CheckItem[] = []
      while (i < lines.length && CHECK.test(lines[i]!)) {
        const m = lines[i]!.match(CHECK)!
        items.push({ id: `${noteId}:k:${hashOf(m[2]!)}`, text: m[2]!, done: m[1] !== ' ' })
        i++
      }
      i--
      out.push({ type: 'check', items })
      continue
    }
    md.push(line)
  }
  flush()
  return out
}

/** Split the body into its title and its `## ` sections (the lines before the first heading are the opening section, untitled). */
export function parseNote(src: NoteSource): Note {
  const lines = src.body.replace(/\r\n/g, '\n').split('\n')
  let title = src.id
  if (lines[0]?.startsWith('# ')) title = lines.shift()!.slice(2).trim()
  const sections: Section[] = []
  let cur: { title: string; lines: string[] } = { title: '', lines: [] }
  const close = () => {
    const blocks = parseBlocks(cur.lines, src.id)
    if (blocks.length || cur.title) sections.push({ id: `s${sections.length}`, title: cur.title, blocks })
  }
  for (const line of lines) {
    if (line.startsWith('## ')) { close(); cur = { title: line.slice(3).trim(), lines: [] }; continue }
    cur.lines.push(line)
  }
  close()
  const refs = [...new Set(src.body.match(ID_RE) ?? [])]
  const words = src.body.split(/\s+/).filter(Boolean).length
  const firstMd = sections[0]?.blocks.find((b): b is Extract<Block, { type: 'md' }> => b.type === 'md')
  const lead = (firstMd?.text.split(/\n\n/)[0] ?? '').replace(/[`*]/g, '').replace(/\n/g, ' ')
  return { ...src, title, sections, refs, words, lead }
}

/** Every block of a note, folds opened, with the section it sits in. */
export function allBlocks(note: Note): Array<{ block: Block; section: Section }> {
  const out: Array<{ block: Block; section: Section }> = []
  const walk = (blocks: Block[], section: Section) => {
    for (const b of blocks) {
      if (b.type === 'fold') walk(b.blocks, section)
      else out.push({ block: b, section })
    }
  }
  for (const s of note.sections) walk(s.blocks, s)
  return out
}

/** What a section holds besides text, for the outline: "12 to tick", "a choice". */
export function blocksOf(blocks: Block[]): Block[] {
  return blocks.flatMap((b) => (b.type === 'fold' ? blocksOf(b.blocks) : [b]))
}

/** "16 Nov" from an ISO stamp. */
export const dayKey = (at: string) => at.slice(0, 10)
