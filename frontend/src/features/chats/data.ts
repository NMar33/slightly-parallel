import type { ProfileSession } from '../agents/profile'
import { mentionLabel, mentionWho, type MentionAgent } from '../project/mentions'
import type { LensRow } from '../../lib/api'
import { safeParseMs } from '../../utils/dateUtils'
import type { AgentLine } from './AgentPanel'
import { groupKey, groupName, isGroupKey } from '../../lib/groups'

import { t, tn } from '../../i18n/scope/views'
/**
 * What a chat is on the chats page, and the few numbers read off it.
 *
 * The page at /chats and the workbench the project tab and the prompt
 * comparison still render are the same rows with different chrome, so the
 * row lives here rather than in either of them.
 */
export type Row = ProfileSession & {
  agent_id: string
  project: string
  produced: Record<string, number>
  /** What marked the chat: the saved prompt it came from, a kept message. */
  marks: Record<string, number>
  tasks: number
  matches: number
  git: { commits: number; files: number; add: number; del: number }
  /** Who the chat is with, and where it ran — the name and the resume. */
  agent: MentionAgent | null
}

export function toSession(r: LensRow): Row {
  return {
    id: r.id,
    created_date: String(r.created_date ?? ''),
    start_time: String(r.start_time ?? ''),
    end_time: String(r.end_time ?? ''),
    duration_min: Number(r.duration_min ?? 0),
    turns_n: Number(r.turns_n ?? 0),
    chat_end_line: Number(r.chat_end_line ?? 0),
    // A pasted block's wrapper tag is the capture's, not the person's words.
    l1: String(r.l1 ?? '').replace(/<\/?pasted_content[^>]*>/g, ' ').replace(/\s+/g, ' ').trim(),
    agent_id: String(r.agent_id ?? ''),
    project: String(r.project ?? ''),
    produced: (r.produced as Record<string, number> | undefined) ?? {},
    marks: (r.marks as Record<string, number> | undefined) ?? {},
    tasks: Number(r.tasks ?? 0),
    matches: Number(r.matches ?? 0),
    git: (r.git as Row['git'] | undefined) ?? { commits: 0, files: 0, add: 0, del: 0 },
    agent: (r.agent as MentionAgent | null | undefined) ?? null,
  }
}

/** One kind of entry with its count, in the interface language; an unknown kind stays as the server names it. */
function producedWord(kind: string, n: number): string {
  switch (kind) {
    case 'scans': return tn(n, '{n} scan', '{n} scans')
    case 'decisions': return tn(n, '{n} decision', '{n} decisions')
    case 'standups': return tn(n, '{n} standup', '{n} standups')
    case 'files': return tn(n, '{n} file entry', '{n} file entries')
    case 'visions': return tn(n, '{n} vision', '{n} visions')
    case 'entrypoints': return tn(n, '{n} entry point', '{n} entry points')
    case 'problems': return tn(n, '{n} problem', '{n} problems')
    case 'rules': return tn(n, '{n} rule', '{n} rules')
    case 'skills': return tn(n, '{n} skill', '{n} skills')
    case 'artifacts': return tn(n, '{n} artifact', '{n} artifacts')
    case 'architecture': return tn(n, '{n} architecture entry', '{n} architecture entries')
    default: return `${n} ${n === 1 ? kind.replace(/s$/, '') : kind}`
  }
}

/** "2 scans · 1 decision · 3 tasks" — what came out of a chat, in a breath. */
export function producedWords(s: Row): string[] {
  const out: string[] = []
  // Git first: it is the part nobody had to write down.
  if (s.git.commits) out.push(`${tn(s.git.commits, '{n} commit', '{n} commits')} · ${tn(s.git.files, '{n} file', '{n} files')} · +${s.git.add} −${s.git.del}`)
  out.push(...Object.entries(s.produced).map(([k, n]) => producedWord(k, n)))
  if (s.tasks) out.push(tn(s.tasks, '{n} task', '{n} tasks'))
  return out
}

const HOUR = 36e5

/** Start and end of a chat as ms, from Slightly Parallel's YYMM-DD and HH:MM. */
function span(s: Row): [number, number] | null {
  const day = safeParseMs(s.created_date)
  if (day == null) return null
  const at = (hhmm: string) => {
    const [h, m] = hhmm.split(':').map(Number)
    return day + (h || 0) * HOUR + (m || 0) * 6e4
  }
  const a = at(s.start_time)
  const b = at(s.end_time)
  return [a, b < a ? b + 24 * HOUR : b]
}

/** The rhythm between two chats, newer above older: nothing, a night, N days. */
export function gapLabel(newer: Row, older: Row): string | null {
  const a = span(older)
  const b = span(newer)
  if (!a || !b) return null
  const hours = (b[0] - a[1]) / HOUR
  if (hours < 6) return null
  const days = Math.round(hours / 24)
  if (days >= 2) return tn(days, '{n} day', '{n} days')
  return newer.created_date !== older.created_date ? t('a night') : t('{n} h', { n: Math.round(hours) })
}

/** The agents of these chats, the one that said most first. */
function agentOnly(rows: Row[]): AgentLine[] {
  const by = new Map<string, AgentLine>()
  for (const s of rows) {
    if (!s.agent_id) continue
    const a = by.get(s.agent_id) ?? {
      id: s.agent_id, label: mentionLabel(s), title: mentionWho(s),
      project: s.project, chats: 0, turns: 0, last: '',
    }
    a.chats += 1
    a.turns += s.turns_n
    if (s.created_date > a.last) a.last = s.created_date
    by.set(s.agent_id, a)
  }
  return [...by.values()].sort((a, b) => b.turns - a.turns || a.label.localeCompare(b.label))
}

/** The agents of these chats, the one that said most first — and before
 *  them the groups they belong to, each standing for all its members. */
export function agentLines(rows: Row[]): AgentLine[] {
  const agents = agentOnly(rows)
  const groups = new Map<string, AgentLine>()
  for (const s of rows) {
    const g = s.agent?.agent_group || ''
    if (!g) continue
    const line = groups.get(g) ?? {
      id: groupKey(g), label: g, title: t('group {g}', { g }), project: s.project,
      chats: 0, turns: 0, last: '', group: 0,
    }
    line.chats += 1
    line.turns += s.turns_n
    if (s.created_date > line.last) line.last = s.created_date
    groups.set(g, line)
  }
  for (const line of groups.values()) {
    line.group = agents.filter((a) => rows.some((s) => s.agent_id === a.id && s.agent?.agent_group === line.label)).length
  }
  return [...[...groups.values()].sort((a, b) => b.turns - a.turns), ...agents]
}

/** A chat belongs to the pick: the agent itself, or a member of the group. */
export function ofAgent(s: Row, pick: string): boolean {
  if (!pick) return true
  return isGroupKey(pick) ? s.agent?.agent_group === groupName(pick) : s.agent_id === pick
}
