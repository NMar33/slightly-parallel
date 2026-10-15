/**
 * A standup cut into the sections focus mode reads one at a time: the day
 * (numbers, summary, story), what needs you, what went wrong, what moved,
 * the decisions, the tasks and agents of the day, what was created, what
 * may be forgotten, and the rest. A section with nothing in it is left out.
 *
 * The standup has no field for what needs you: it is the "Needs an answer"
 * lines of its detail, and the detail without them is "More".
 */
import type { DayRecord, Standup } from '../data'

export type SectionKind =
  | 'day' | 'needs' | 'wrong' | 'moved' | 'decisions' | 'tasks' | 'agents' | 'created' | 'forgotten' | 'more'

export interface Section { kind: SectionKind; count: number }

const NEEDS = /\*\*Needs an answer:\*\*\s*([\s\S]*?)(?=\*\*[A-Z][^*\n]{0,40}:\*\*|$)/g

/** An answer that says there is nothing: "none left open", "nothing". */
const EMPTY = /^(none|nothing|no\b|—|-)/i

/** The questions the detail says wait for the operator, and the detail without them. */
export function needsOf(detail: string): { needs: string[]; rest: string } {
  const needs: string[] = []
  const rest = (detail ?? '').replace(NEEDS, (_, body: string) => {
    const text = body.trim().replace(/\s+$/, '')
    if (text && !EMPTY.test(text)) needs.push(text)
    return ''
  })
  return { needs, rest: rest.replace(/\n{3,}/g, '\n\n').trim() }
}

/** A markdown list as its items; text that is not a list is one item. */
export function bulletsOf(md: string): string[] {
  const text = (md ?? '').trim()
  if (!text) return []
  const lines = text.split('\n')
  if (!lines.some((l) => /^\s*[-*]\s+/.test(l))) return [text]
  const out: string[] = []
  for (const l of lines) {
    const m = /^\s*[-*]\s+(.*)$/.exec(l)
    if (m) out.push(m[1]!.trim())
    else if (l.trim() && out.length) out[out.length - 1] += ` ${l.trim()}`
    else if (l.trim()) out.push(l.trim())
  }
  return out.filter(Boolean)
}

/** The story's paragraphs, a heading line dropped. */
export function paragraphsOf(story: string): string[] {
  return (story ?? '').split(/\n\s*\n/).map((p) => p.trim()).filter((p) => p && !/^#+\s/.test(p))
}

/** The sections of one standup, in reading order, the empty ones left out. */
export function sectionsOf(s: Standup, rec?: DayRecord): Section[] {
  const { needs, rest } = needsOf(s.detail)
  const all: Section[] = [
    { kind: 'day', count: 1 },
    { kind: 'needs', count: needs.length },
    { kind: 'wrong', count: bulletsOf(s.deviation).length },
    { kind: 'moved', count: s.movement.length },
    { kind: 'decisions', count: s.decisions.length },
    { kind: 'tasks', count: rec?.tasks.length ?? 0 },
    { kind: 'agents', count: rec?.agents.length ?? 0 },
    { kind: 'created', count: rec?.created.length ?? 0 },
    { kind: 'forgotten', count: s.forgotten.length },
    { kind: 'more', count: rest ? 1 : 0 },
  ]
  return all.filter((x) => x.count > 0)
}

/** The colour a section is drawn in on the map, as a CSS colour. */
export const MAP_TONE: Record<SectionKind, string> = {
  day: 'color-mix(in srgb, var(--status-amber) 55%, transparent)',
  needs: 'color-mix(in srgb, var(--status-purple) 35%, transparent)',
  wrong: 'color-mix(in srgb, var(--status-amber) 30%, transparent)',
  moved: 'color-mix(in srgb, var(--brand) 30%, transparent)',
  decisions: 'color-mix(in srgb, var(--status-purple) 25%, transparent)',
  tasks: 'var(--border-strong)',
  agents: 'var(--border-strong)',
  created: 'var(--border-strong)',
  forgotten: 'var(--border-default)',
  more: 'var(--border-default)',
}
