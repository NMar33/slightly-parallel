/**
 * What came out of a chat, and what marked it, as a set of cuts.
 *
 * Three bands over one chat. **Came out** is everything an agent can write
 * during a run — the server counts all fourteen kinds now, so a standup, a
 * skill, an artifact or a press note is no longer invisible on the chat
 * that made it. **Came in** is the other direction: the saved prompt a chat
 * was sent from, and the messages kept out of it as a vision, a skill, a
 * problem or an artifact. **Weight** is turns and minutes. Nothing here
 * touches React or the network, so the counting and the combining are
 * tested on their own.
 *
 * Chips are an "and": a chat must pass every chip that is on. A chip's count
 * is taken over the chats every *other* chip still allows, the rule the
 * search page's facet rail follows, so the number says what the cut would
 * buy before it is made.
 */

import type { Row } from './data'

import { t } from '../../i18n/scope/views'
export type ChipId =
  | 'commits' | 'task' | 'scan' | 'file' | 'vision' | 'entrypoint' | 'problem' | 'decision'
  | 'standup' | 'skill' | 'artifact' | 'rule' | 'architecture'
  | 'prompt' | 'kept' | 'important'
  | 'turns10' | 'hour'

/** The band a chip belongs to, and the order they are read in. */
type Band = 'out' | 'in' | 'weight'

interface Chip {
  id: ChipId
  band: Band
  /** The words on the chip. */
  label: string
  test: (s: Row) => boolean
}

const made = (s: Row, key: string) => (s.produced[key] ?? 0) > 0
const marked = (s: Row, key: string) => (s.marks[key] ?? 0) > 0

export const CHIPS: Chip[] = [
  { id: 'commits', band: 'out', label: t('commits'), test: (s) => s.git.commits > 0 },
  { id: 'task', band: 'out', label: t('a task'), test: (s) => s.tasks > 0 },
  { id: 'scan', band: 'out', label: t('a scan'), test: (s) => made(s, 'scans') },
  { id: 'file', band: 'out', label: t('a file entry'), test: (s) => made(s, 'files') },
  { id: 'standup', band: 'out', label: t('a standup'), test: (s) => made(s, 'standups') },
  { id: 'decision', band: 'out', label: t('a decision'), test: (s) => made(s, 'decisions') },
  { id: 'vision', band: 'out', label: t('a vision'), test: (s) => made(s, 'visions') },
  { id: 'entrypoint', band: 'out', label: t('an entry point'), test: (s) => made(s, 'entrypoints') },
  { id: 'problem', band: 'out', label: t('a problem'), test: (s) => made(s, 'problems') },
  { id: 'rule', band: 'out', label: t('a rule'), test: (s) => made(s, 'rules') },
  { id: 'skill', band: 'out', label: t('a skill'), test: (s) => made(s, 'skills') },
  { id: 'artifact', band: 'out', label: t('an artifact'), test: (s) => made(s, 'artifacts') },
  { id: 'architecture', band: 'out', label: t('architecture'), test: (s) => made(s, 'architecture') },
  { id: 'prompt', band: 'in', label: t('sent from a prompt'), test: (s) => marked(s, 'prompt') },
  { id: 'kept', band: 'in', label: t('a message kept'),
    test: (s) => Object.entries(s.marks).some(([k, n]) => k.startsWith('kept-') && n > 0) },
  { id: 'important', band: 'in', label: t('★ an important message'), test: (s) => marked(s, 'important') },
  { id: 'turns10', band: 'weight', label: t('ten turns or more'), test: (s) => s.turns_n >= 10 },
  { id: 'hour', band: 'weight', label: t('an hour or more'), test: (s) => s.duration_min >= 60 },
]

/** The bands, in the order the panel reads them. */
export const BANDS: Array<[Band, string]> = [
  ['out', t('Came out')], ['in', t('Came in')], ['weight', t('Weight')],
]

const chipOf = (id: ChipId): Chip => CHIPS.find((c) => c.id === id)!

/** Does this chat pass every chip that is on? */
export function keeps(s: Row, picked: ChipId[]): boolean {
  return picked.every((id) => chipOf(id).test(s))
}

export function applyChips(rows: Row[], picked: ChipId[]): Row[] {
  if (picked.length === 0) return rows
  return rows.filter((s) => keeps(s, picked))
}

/** On, off: a second click clears one. */
export function toggleChip(picked: ChipId[], id: ChipId): ChipId[] {
  return picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]
}

interface ChipCount {
  id: ChipId
  label: string
  /** How many chats this chip would leave, with the other chips as they are. */
  count: number
  on: boolean
}

/**
 * Every chip with its count, in the order the set is drawn.
 *
 * A chip that is off counts the chats the other chips allow and it would
 * keep. A chip that is on counts what the whole cut keeps, so its number is
 * the number of chats on the page.
 */
export function chipCounts(rows: Row[], picked: ChipId[]): ChipCount[] {
  return CHIPS.map((c) => {
    const others = picked.filter((id) => id !== c.id)
    const base = applyChips(rows, others)
    return { id: c.id, label: c.label, count: base.filter(c.test).length, on: picked.includes(c.id) }
  })
}
