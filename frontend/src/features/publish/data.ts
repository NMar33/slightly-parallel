import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../lib/getJson'
import { OPERATOR_ACTOR } from '../project/types'

/**
 * Publish: the cards the operator kept with #publish in a chat, and the
 * documents he makes from them (docs/publish.md, routers/publish.py). The
 * wire shapes, the reads, the operator's writes, and the pure helpers the
 * page draws with. Every route is under /api/publishing; /api/publish is
 * the kept entity's own list and is not read here.
 */

export const API = '/api/publishing'

export interface CardVersion { n: number; at: string; text: string; note: string }
export interface CardTask { id: string; title: string; status: string }
export interface CardCore { id: string; name: string; type: string }
export interface CardCommit { sha: string; subject: string; at: string }
/** An image of the card: from the tasks' evidence, from a story, or attached
 *  to the card itself (then with its id and who attached it). */
export interface CardImage { url: string; label: string; from?: 'evidence' | 'story' | 'attached' | string; id?: string; by?: string }
export interface CardLink { url: string; label: string; id?: string; by?: string }
/** A file the card's tasks changed: lines added and removed. */
export interface CardFile { path: string; add: number; del: number }
export interface Placement { doc_id: string; doc_name: string; version_n: number; item_id: string; text: string; changed: boolean }

export interface Card {
  id: string
  project: string
  agent_id: string
  session_id: string
  source_turn: number | string
  at: string
  /** The message as typed, the #publish tag taken out. */
  message: string
  /** The current text: the last edit, else the message. */
  text: string
  versions: CardVersion[]
  tasks: CardTask[]
  cores: CardCore[]
  commits: CardCommit[]
  images: CardImage[]
  /** Optional on the wire until every server carries them. */
  links?: CardLink[]
  files?: CardFile[]
  placements: Placement[]
  archived_at: string
}

export interface CardHistoryEvent {
  at: string
  what: 'kept' | 'edited' | 'placed' | 'edited in' | 'removed from' | string
  doc_id: string
  doc_name: string
  version_n: number | null
  text: string
}
export interface CardDetail extends Card { history: CardHistoryEvent[] }

export interface DocItem { id: string; card_id: string; text: string; position: number; changed: boolean }
export interface DocVersion { n: number; at: string; actor: string; note: string; items: DocItem[] }
export interface Doc {
  id: string
  project: string
  name: string
  created_at: string
  archived_at: string
  /** The latest version number. */
  current: number
  versions: DocVersion[]
}

export interface PublishBoard { project: string; cards: Card[]; docs: Doc[] }

export const publishKey = (project: string) => ['publish', project] as const
export const cardKey = (id: string) => ['publish-card', id] as const

export function usePublish(project: string) {
  return useQuery({
    queryKey: publishKey(project),
    queryFn: ({ signal }) => getJson<PublishBoard>(`${API}?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project,
  })
}

export function useCard(id: string) {
  return useQuery({
    queryKey: cardKey(id),
    queryFn: ({ signal }) => getJson<CardDetail>(`${API}/cards/${encodeURIComponent(id)}`, signal),
    enabled: !!id,
  })
}

/** The operator's writes; each refreshes the board (and the open card's history). */
export function usePublishWrites(project: string) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: publishKey(project) })
    void qc.invalidateQueries({ queryKey: ['publish-card'] })
  }
  const op = { actor: OPERATOR_ACTOR }
  const enc = encodeURIComponent
  return {
    cardText: useMutation({
      mutationFn: (input: { id: string; text: string; note?: string }) =>
        postJson<{ card: Card }>(`${API}/cards/${enc(input.id)}/text`, { ...op, text: input.text, ...(input.note ? { note: input.note } : {}) }),
      onSuccess: refresh,
    }),
    newCard: useMutation({
      mutationFn: (input: { text: string }) => postJson<{ card: Card; existing: boolean }>(`${API}/cards`, { ...op, project, text: input.text }),
      onSuccess: refresh,
    }),
    newDoc: useMutation({
      mutationFn: (input: { name: string }) => postJson<{ doc: Doc; existing: boolean }>(`${API}/docs`, { ...op, project, name: input.name }),
      onSuccess: refresh,
    }),
    updateDoc: useMutation({
      mutationFn: (input: { id: string; name?: string; archived?: boolean }) => {
        const { id, ...rest } = input
        return postJson<{ doc: Doc }>(`${API}/docs/${enc(id)}/update`, { ...op, ...rest })
      },
      onSuccess: refresh,
    }),
    newVersion: useMutation({
      mutationFn: (input: { id: string; note?: string }) =>
        postJson<{ doc: Doc }>(`${API}/docs/${enc(input.id)}/versions`, { ...op, ...(input.note ? { note: input.note } : {}) }),
      onSuccess: refresh,
    }),
    place: useMutation({
      mutationFn: (input: { docId: string; card_id: string; text?: string; before?: string }) => {
        const { docId, ...rest } = input
        return postJson<{ item: DocItem; existing: boolean }>(`${API}/docs/${enc(docId)}/items`, { ...op, ...rest })
      },
      onSuccess: refresh,
    }),
    updateItem: useMutation({
      mutationFn: (input: { id: string; text?: string; before?: string }) => {
        const { id, ...rest } = input
        return postJson<{ item: DocItem }>(`${API}/items/${enc(id)}/update`, { ...op, ...rest })
      },
      onSuccess: refresh,
    }),
    attach: useMutation({
      mutationFn: (input: { id: string; images?: Array<{ title: string; ext: string; data_base64: string }>; links?: Array<{ title: string; url: string }> }) => {
        const { id, ...rest } = input
        return postJson<{ attached: Array<{ id: string; kind: string; title: string; existing: boolean }>; card: Card }>(`${API}/cards/${enc(id)}/attach`, { ...op, ...rest })
      },
      onSuccess: refresh,
    }),
    removeAttachment: useMutation({
      mutationFn: (id: string) => postJson<{ removed: boolean }>(`${API}/attachments/${enc(id)}/remove`, op),
      onSuccess: refresh,
    }),
    removeItem: useMutation({
      mutationFn: (id: string) => postJson<{ removed: boolean }>(`${API}/items/${enc(id)}/remove`, op),
      onSuccess: refresh,
    }),
  }
}

export const markdownUrl = (docId: string, n?: number) =>
  `${API}/docs/${encodeURIComponent(docId)}/markdown${n ? `?n=${n}` : ''}`

// ---------------------------------------------------------------- helpers

/** The documents in tab order: the ones not archived, oldest first. */
export function docOrder(docs: Doc[]): Doc[] {
  return docs
    .filter((d) => !d.archived_at)
    .slice()
    .sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
}

/**
 * A document's colour: its place in the tab order over a small palette of
 * tokens. Never a hex: the skins and the dark theme redefine these.
 */
export const DOC_COLORS = [
  'var(--brand)', 'var(--brand-lean)', 'var(--status-info)', 'var(--status-purple)',
  'var(--core-store)', 'var(--core-experiment)', 'var(--core-workflow)', 'var(--core-feature)',
] as const
export const docColor = (index: number): string => DOC_COLORS[((index % DOC_COLORS.length) + DOC_COLORS.length) % DOC_COLORS.length]!

export type LifeNode =
  | { kind: 'original'; key: string; n: 0; at: string; text: string; label: string }
  | { kind: 'edit'; key: string; n: number; at: string; text: string; note: string; label: string }
  | { kind: 'placed'; key: string; doc_id: string; doc_name: string; version_n: number; item_id: string; text: string; changed: boolean; label: string; from: number }

/**
 * A card's life, in order: the message as typed, the operator's edits
 * (U1, U2 …), then each placement grouped per document (in `order`, the
 * tab order, when given) and by version. `from` on a placement is the
 * spine node it grew from: the version whose text it carries, else the
 * newest one (its text was changed inside the document).
 */
export function cardLife(card: Pick<Card, 'at' | 'message' | 'versions' | 'placements'>, order?: string[]): LifeNode[] {
  const spine: LifeNode[] = [{ kind: 'original', key: 'o', n: 0, at: card.at, text: card.message, label: 'original' }]
  const versions = [...card.versions].sort((a, b) => a.n - b.n)
  for (const v of versions) spine.push({ kind: 'edit', key: `u${v.n}`, n: v.n, at: v.at, text: v.text, note: v.note ?? '', label: `U${v.n}` })
  const rank = (id: string) => {
    const i = order ? order.indexOf(id) : -1
    return i === -1 ? Number.MAX_SAFE_INTEGER : i
  }
  const placements = [...card.placements].sort((a, b) =>
    rank(a.doc_id) - rank(b.doc_id) || (a.doc_name < b.doc_name ? -1 : a.doc_name > b.doc_name ? 1 : 0) || a.version_n - b.version_n)
  const last = spine.length - 1
  const placed: LifeNode[] = placements.map((p) => {
    let from = last
    for (let i = last; i >= 0; i--) if (spine[i]!.text === p.text) { from = i; break }
    return {
      kind: 'placed', key: `p${p.item_id || `${p.doc_id}-${p.version_n}`}`, doc_id: p.doc_id, doc_name: p.doc_name,
      version_n: p.version_n, item_id: p.item_id, text: p.text, changed: p.changed, label: `${p.doc_name} v${p.version_n}`, from,
    }
  })
  return [...spine, ...placed]
}

/** A version's items in their order. */
export function itemsOf(doc: Doc, n?: number): DocItem[] {
  const v = doc.versions.find((x) => x.n === (n ?? doc.current)) ?? doc.versions[doc.versions.length - 1]
  return v ? [...v.items].sort((a, b) => a.position - b.position) : []
}

/** A version as markdown, the way the server answers it: the name as the title, one paragraph per item. */
export function markdownOf(doc: Doc, n?: number): string {
  const paras = itemsOf(doc, n).map((it) => it.text.trim()).filter(Boolean)
  return [`# ${doc.name}`, ...paras].join('\n\n') + '\n'
}

export type DiffMark = 'new' | 'changed' | 'same'
export interface VersionDiff { n: number; note: string; at: string; rows: Array<{ item: DocItem; mark: DiffMark }>; left: DocItem[] }

/**
 * Each version against the one before it, by card: what came in, what
 * changed its text, what stayed, and what left. Version 1 is all new.
 */
export function versionDiffs(doc: Doc): VersionDiff[] {
  const versions = [...doc.versions].sort((a, b) => a.n - b.n)
  const out: VersionDiff[] = []
  let prev: Map<string, DocItem> = new Map()
  for (const v of versions) {
    const items = [...v.items].sort((a, b) => a.position - b.position)
    const here = new Map(items.map((it) => [it.card_id, it]))
    const rows = items.map((item) => {
      const before = prev.get(item.card_id)
      const mark: DiffMark = !before ? 'new' : before.text !== item.text ? 'changed' : 'same'
      return { item, mark }
    })
    const left = [...prev.values()].filter((it) => !here.has(it.card_id))
    out.push({ n: v.n, note: v.note, at: v.at, rows, left })
    prev = here
  }
  return out
}

export type DiffPart = { op: 'same' | 'add' | 'del'; text: string }

/**
 * A word diff of `before` → `after`: runs of words kept, added and removed,
 * the spaces riding with the word before them. The common head and tail are
 * cut first (an edit is usually in one place), then the middle is diffed by
 * longest common subsequence; a middle too large for that is shown as
 * removed and added whole.
 */
export function wordDiff(before: string, after: string): DiffPart[] {
  const tok = (s: string) => s.match(/\S+\s*|\s+/g) ?? []
  const a = tok(before)
  const b = tok(after)
  const same = (x: string, y: string) => x.trim() === y.trim()
  let head = 0
  while (head < a.length && head < b.length && same(a[head]!, b[head]!)) head++
  let tail = 0
  while (tail < a.length - head && tail < b.length - head && same(a[a.length - 1 - tail]!, b[b.length - 1 - tail]!)) tail++
  const am = a.slice(head, a.length - tail)
  const bm = b.slice(head, b.length - tail)
  const mid: DiffPart[] = []
  if (am.length * bm.length > 250_000) {
    for (const x of am) mid.push({ op: 'del', text: x })
    for (const y of bm) mid.push({ op: 'add', text: y })
  } else {
    const n = am.length
    const m = bm.length
    const L: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
      L[i]![j] = same(am[i]!, bm[j]!) ? L[i + 1]![j + 1]! + 1 : Math.max(L[i + 1]![j]!, L[i]![j + 1]!)
    }
    let i = 0
    let j = 0
    while (i < n && j < m) {
      if (same(am[i]!, bm[j]!)) { mid.push({ op: 'same', text: bm[j]! }); i++; j++ }
      else if (L[i + 1]![j]! >= L[i]![j + 1]!) { mid.push({ op: 'del', text: am[i]! }); i++ }
      else { mid.push({ op: 'add', text: bm[j]! }); j++ }
    }
    while (i < n) mid.push({ op: 'del', text: am[i++]! })
    while (j < m) mid.push({ op: 'add', text: bm[j++]! })
  }
  const parts = [
    ...b.slice(0, head).map((text) => ({ op: 'same' as const, text })),
    ...mid,
    ...b.slice(b.length - tail).map((text) => ({ op: 'same' as const, text })),
  ]
  // Runs of one kind as one part.
  const out: DiffPart[] = []
  for (const p of parts) {
    const last = out[out.length - 1]
    if (last && last.op === p.op) last.text += p.text
    else out.push({ ...p })
  }
  return out
}

/** Words and characters of a text, for the editor's counter. */
export function countOf(text: string): { words: number; chars: number } {
  const t = text.trim()
  return { words: t ? t.split(/\s+/).length : 0, chars: text.length }
}

/** The host of a link, for its chip; the text itself when it is not a URL. */
export function hostOf(url: string): string {
  try { return new URL(url).host.replace(/^www\./, '') } catch { return url }
}

export interface ImageUpload { title: string; ext: string; data_base64: string }

/** An image file as the attach route takes it: base64, its extension, a title from its name. */
export function fileToUpload(file: File, fallbackTitle: string): Promise<ImageUpload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error('read failed'))
    reader.onload = () => {
      const url = String(reader.result ?? '')
      const data_base64 = url.slice(url.indexOf(',') + 1)
      const dot = file.name.lastIndexOf('.')
      const ext = (dot > 0 ? file.name.slice(dot + 1) : file.type.split('/')[1] ?? 'png').toLowerCase()
      const title = (dot > 0 ? file.name.slice(0, dot) : file.name).trim() || fallbackTitle
      resolve({ title, ext, data_base64 })
    }
    reader.readAsDataURL(file)
  })
}
