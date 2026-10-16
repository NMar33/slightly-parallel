import { t } from '../../i18n/scope/system'


/**
 * The files panel's shared brain: one read, one set of orderings, one place
 * that explains itself. Every files page differs only in how it draws this.
 *
 * Everything here already exists in /api/files/heatmap and was going unused:
 * per file the counts, the lines, the importance score and the tags; per
 * file *per checkpoint* a sentence the agent wrote about why it changed.
 * That last one is the whole point — 128 of 128 cells carry one.
 */

export type Cell = {
  count: number
  lines_add: number
  lines_del: number
  action?: string
  semantic_score?: number
  tags?: string[]
  why?: string
  /** The checkpoints behind the cell. */
  entry_ids?: string[]
}

export type Entry = {
  id: string
  /** Which project's codebase this checkpoint belongs to. */
  project?: string
  date: string
  time: string
  agent_id: string
  l1: string
  /** What wrote the checkpoint ("scan", or another lens). */
  trigger_lens?: string
  scan_id: string
  session_id: string
  paths_n: number
}

export type FileRow = {
  path: string
  /** What the cells and the matrix hang on: the path, or `project::path`
      when the payload spans every project (the same path in two
      repositories is two files). */
  key?: string
  /** The project the file is from; set when the payload spans every project. */
  project?: string
  total: number
  created: number
  modified: number
  deleted: number
  lines_add: number
  lines_del: number
  semantic_score?: number
  tags?: string[]
}

export type Payload = {
  files: FileRow[]
  dates: string[]
  matrix: Record<string, Cell>
  entries: Entry[]
  cells: Record<string, Cell>
  max: number
}

/** One file, with everything the orderings and the hover need. */
export type Row = FileRow & {
  /** Checkpoints this file appears in, newest first. */
  story: Array<{ entry: Entry; cell: Cell }>
  /** Distinct checkpoints touched — breadth, not volume. */
  breadth: number
  /** Distinct days touched. */
  days: number
  churn: number
  net: number
  /** 0 = oldest checkpoint in the window, 1 = the newest. */
  recency: number
  lastWhy: string
  lastAction: string
  /** Freshness-weighted work, recomputed as the slider moves. */
  heat: number
  /**
   * The same counts, with each checkpoint's contribution decayed by age.
   * Anything counted from events can be asked "and how much of that was
   * recent?" — a judgment score cannot, which is why importance and gone
   * cold are left alone.
   */
  w: { total: number; breadth: number; churn: number; net: number; days: number }
}

/** Orderings the freshness weight has no say over, and why. */
export const WEIGHT_BLIND: Partial<Record<SortKey, string>> = {
  important: t('importance is the agent\'s rating, not a count'),
  cold: t('gone cold already measures age'),
}

export const SORTS = [
  ['heat', t('recent work'), t('Changes weighted by how recent they are; the slider sets the weight')],
  ['worked', t('most worked'), t('Raw number of times the file was touched across every scan')],
  ['breadth', t('in most scans'), t('How many scans changed it')],
  ['churn', t('most churn'), t('Lines added plus lines deleted')],
  ['grown', t('grew most'), t('Net lines gained')],
  ['shrunk', t('shrank most'), t('Net lines lost')],
  ['important', t('importance'), t('The score the agent gave the change')],
  ['cold', t('important but cold'), t('High importance, untouched longest')],
  ['volatile', t('keeps changing'), t('Touched on many days with heavy churn')],
] as const

/** A chosen ordering, or 'original' — the order the board gives. */
export type SortKey = (typeof SORTS)[number][0] | 'original'

export const COUNTS = [10, 20, 30, 0] as const

/**
 * Build the rows. `weight` is the freshness slider: 0 counts all history
 * equally, 10 means only the newest checkpoint really counts. It re-ranks
 * rather than hides, so a slow-moving file never disappears — it just sinks.
 */
export function buildRows(data: Payload, weight: number): Row[] {
  const entries = [...data.entries].sort((a, b) =>
    `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`))
  const n = Math.max(1, entries.length)
  const lambda = (weight / 10) * 0.9        // 0 → flat, 10 → steep decay

  return data.files.map((f) => {
    const story: Row['story'] = []
    let heat = 0
    let newest = -1
    const days = new Set<string>()
    const wDays = new Map<string, number>()
    const w = { total: 0, breadth: 0, churn: 0, net: 0, days: 0 }
    entries.forEach((e, i) => {
      const cell = data.cells[`${f.key ?? f.path}||${e.id}`]
      if (!cell) return
      story.push({ entry: e, cell })
      days.add(e.date)
      newest = Math.max(newest, i)
      const age = (n - 1 - i)
      const decay = Math.exp(-lambda * age)
      heat += (cell.count + (cell.lines_add + cell.lines_del) / 40) * decay
      w.total += cell.count * decay
      w.breadth += decay
      w.churn += (cell.lines_add + cell.lines_del) * decay
      w.net += (cell.lines_add - cell.lines_del) * decay
      wDays.set(e.date, Math.max(wDays.get(e.date) ?? 0, decay))
    })
    w.days = [...wDays.values()].reduce((a, d) => a + d, 0)
    story.reverse()
    return {
      ...f,
      story,
      breadth: story.length,
      days: days.size,
      churn: f.lines_add + f.lines_del,
      net: f.lines_add - f.lines_del,
      w,
      recency: newest < 0 ? 0 : n === 1 ? 1 : newest / (n - 1),
      lastWhy: story[0]?.cell.why ?? '',
      lastAction: story[0]?.cell.action ?? 'modified',
      heat,
    }
  })
}

export const DEFAULTS = { sort: 'original' as SortKey, count: 20, weight: 5 }

export function sortRows(rows: Row[], key: SortKey): Row[] {
  const by = (f: (r: Row) => number) => [...rows].sort((a, b) => f(b) - f(a))
  switch (key) {
    // Untouched: the rows arrive in the order the endpoint gave them, which
    // is the view that existed before any of these orderings did.
    case 'original': return rows
    // Everything counted from events answers to the slider; the two
    // judgment-based orderings deliberately do not.
    case 'heat': return by((r) => r.heat)
    case 'worked': return by((r) => r.w.total)
    case 'breadth': return by((r) => r.w.breadth * 1000 + r.w.total)
    case 'churn': return by((r) => r.w.churn)
    case 'grown': return by((r) => r.w.net)
    case 'shrunk': return by((r) => -r.w.net)
    case 'important': return by((r) => (r.semantic_score ?? 0) * 1000 + r.total)
    case 'cold': return by((r) => (r.semantic_score ?? 0) * (1 - r.recency))
    case 'volatile': return by((r) => r.w.days * Math.sqrt(Math.max(0, r.w.churn)))
    default: return rows
  }
}

export const shortPath = (p: string): string => {
  const bits = p.split('/')
  return bits.length <= 2 ? p : `…/${bits.slice(-2).join('/')}`
}

export const fileName = (p: string): string => p.split('/').pop() ?? p
