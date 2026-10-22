import { useQuery } from '@tanstack/react-query'
import { getJson } from '../../../lib/getJson'

/** One item of the page that carries its evidence, as the server parsed and checked it. */
export interface Claim {
  text: string
  where?: string
  seen?: string
  made_by?: string
  checked_by?: string
  path?: string
  path_found?: boolean
  changed_since?: string
}

export interface PageSection { title: string; body: string; claims: Claim[] }

export interface PageVersion { n: number; at: string; agent_id: string; note: string; words: number }

export interface ArchPage extends PageVersion {
  text: string
  sections: PageSection[]
  counts: { claims: number; with_path: number; missing: number; changed_since: number }
}

interface RepoFacts {
  commits: number
  first_commit?: string
  last_commit: string
  remote: string[]
  tags?: string[]
  uncommitted_files?: number
  recent_commit_subjects?: string[]
}

export interface Facts {
  today?: string
  folder?: string
  files?: number
  standing?: string
  file_types?: [string, number][]
  top_level?: { name: string; files: number; mb: number; last_change: string }[]
  newest_files?: { path: string; changed: string }[]
  git?: RepoFacts | null
  nested_repositories?: ({ path: string } & RepoFacts)[]
  build_and_ci_files?: string[]
  note?: string
}

export interface ArchPageAnswer {
  project: string
  word_budget: number
  page: ArchPage | null
  versions: PageVersion[]
  facts: Facts
}

export function useArchPage(project: string, version?: number) {
  return useQuery({
    queryKey: ['architecture-page', project, version ?? 'current'],
    queryFn: ({ signal }) =>
      getJson<ArchPageAnswer>(
        `/api/architecture/page?project=${encodeURIComponent(project)}${version ? `&version=${version}` : ''}`,
        signal,
      ),
    enabled: !!project,
  })
}

/** A piece of a section, in the order it was written: prose, or one claim. */
type Segment = { kind: 'md'; text: string } | { kind: 'claim'; claim: Claim }

const LIST_ITEM = /^\s*(?:[-*]|\d+\.)\s+/
const norm = (s: string) => s.replace(/[*`]/g, '').replace(/\s+/g, ' ').trim().toLowerCase()

/**
 * A section's body with its claims lifted out, order kept. The server gives
 * the claims in the order of the list items they came from, so each list
 * item is matched against the next claim still waiting; an item that is not
 * a claim stays prose. Nothing is dropped: an unmatched claim is shown last.
 */
export function segments(section: PageSection): Segment[] {
  const out: Segment[] = []
  const waiting = [...section.claims]
  let prose: string[] = []
  let item: string[] | null = null
  const flushProse = () => {
    const text = prose.join('\n').trim()
    if (text) out.push({ kind: 'md', text })
    prose = []
  }
  const flushItem = () => {
    if (!item) return
    const body = norm(item.join(' ').replace(LIST_ITEM, ''))
    const next = waiting[0]
    const head = next ? norm(next.text).slice(0, 40) : ''
    const path = next?.where ? norm(next.where) : ''
    const isClaim = !!next && (head ? body.startsWith(head) : !!path && body.includes(path))
    if (isClaim) {
      flushProse()
      out.push({ kind: 'claim', claim: waiting.shift()! })
    } else {
      prose.push(...item)
    }
    item = null
  }
  for (const line of section.body.split('\n')) {
    if (LIST_ITEM.test(line)) {
      flushItem()
      item = [line]
    } else if (item && line.trim()) {
      item.push(line.trim())
    } else {
      flushItem()
      prose.push(line)
    }
  }
  flushItem()
  flushProse()
  for (const claim of waiting) out.push({ kind: 'claim', claim })
  return out
}

/** active · paused · dormant · empty — the first word of the computed standing. */
export function standingWord(standing?: string): string {
  return (standing ?? '').trim().split(/\s/)[0] || ''
}
