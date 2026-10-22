import { absolutePath, useFolder } from '../../../lib/paths'
import { Trash2 } from 'lucide-react'

import { CopyButton } from '../../../components/CopyButton'
import { Button } from '../../../components/primitives'
import { formatStamp } from '../../../utils/dateUtils'
import { AgentName } from '../../../components/AgentName'
import { t } from '../../../i18n/scope/project'

/**
 * Evidence items — what an agent posts besides a note and a screenshot:
 * the files it touched, and what landed.
 *
 * The words are the ones Slightly Parallel already uses. A file carries the file
 * entry's own judgment — action, importance, blast radius, test coverage,
 * why. A change carries the architecture vocabulary — feature, endpoint,
 * module, tests, debt — in its eight groups. Same language in a new place,
 * so there is nothing new to learn and nothing to keep in step by hand.
 *
 * Git knows which files the task's turns really touched. A file the agent
 * claimed that git never saw is marked, quietly: it is information, not an
 * error — the agent may have touched something outside the repository.
 */

type EvidenceAction = 'created' | 'modified' | 'deleted' | 'renamed'

export type EvidencePath = {
  path: string
  action: EvidenceAction
  lines_add: number
  lines_del: number
  /** 1–5. */
  importance: number
  /** 1–10. */
  blast_radius: number
  test_coverage: 'covered' | 'partial' | 'untested'
  security_surface: boolean
  why: string
  /** False when git did not see this file in the task's turns. */
  in_git: boolean
}

export type EvidenceChange = {
  op: 'add' | 'change' | 'remove'
  type: string
  group: string
  name: string
  path: string[]
  note: string
}

export type EvidenceItem = {
  id: string
  kind: string
  title: string
  body: string
  agent_id: string
  created_at: string
  url?: string
  /** files items: where to start reading. */
  start_here?: string
  paths?: EvidencePath[]
  changes?: EvidenceChange[]
}

/** One file git saw. `committed` is false while it is only in the working
 *  tree, which on this laptop may belong to another session (taskwork.py). */
export type WorkFile = {
  path: string
  lines_add: number
  lines_del: number
  committed?: boolean
}

/** The architecture groups, in the order the form asks for them. */
const GROUP_ORDER = [
  'does', 'owes', 'runs', 'stores', 'talks', t('built with'), 'faces', 'holds',
]

const OP_MARK: Record<string, string> = { add: '+', change: '~', remove: '−' }
const OP_WORD: Record<string, string> = { add: 'added', change: 'changed', remove: 'removed' }

/** Types whose plural is not the type plus an s. */
const PLURAL: Record<string, string> = {
  fix: 'fixes',
  debt: 'debt',
  'action-needed': 'action-needed',
  files: 'files',
  tests: 'tests',
}

function plural(type: string, n: number): string {
  if (n === 1) return type
  return PLURAL[type] ?? `${type}s`
}

/** Most important first, then by path, so the eye starts at the top. */
export function sortPaths(paths: EvidencePath[]): EvidencePath[] {
  return [...paths].sort(
    (a, b) => (b.importance ?? 0) - (a.importance ?? 0) || a.path.localeCompare(b.path),
  )
}

/** "11 files · +605 −75 · 3 features · 1 endpoint" — the post in one line. */
export function summarise(items: EvidenceItem[]): string {
  const paths = new Map<string, EvidencePath>()
  for (const it of items) {
    if (it.kind !== 'files') continue
    for (const p of it.paths ?? []) if (!paths.has(p.path)) paths.set(p.path, p)
  }
  const counts = new Map<string, number>()
  for (const it of items) {
    if (it.kind !== 'change') continue
    for (const c of it.changes ?? []) counts.set(c.type, (counts.get(c.type) ?? 0) + 1)
  }
  const parts: string[] = []
  if (paths.size > 0) {
    const add = [...paths.values()].reduce((n, p) => n + (p.lines_add ?? 0), 0)
    const del = [...paths.values()].reduce((n, p) => n + (p.lines_del ?? 0), 0)
    parts.push(`${paths.size} ${paths.size === 1 ? 'file' : 'files'}`)
    if (add || del) parts.push(`+${add} −${del}`)
  }
  for (const [type, n] of [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))) {
    parts.push(`${n} ${plural(type, n)}`)
  }
  return parts.join(' · ')
}

/** Where to start reading, and a way to take it with you. */
function StartHere({ pointer }: { pointer: string }) {
  const full = absolutePath(useFolder(), pointer)
  if (!pointer.trim()) return null
  return (
    <div className="flex items-center gap-8 min-w-0">
      <span className="text-10 uppercase tracking-wide font-mono text-tertiary shrink-0">{t('Open this first')}</span>
      <code className="text-12 font-mono text-primary truncate min-w-0" title={full}>{pointer}</code>
      <CopyButton
        text={full}
        title={full}
        ariaLabel={t('Copy the reference')}
        label={t('Copy')}
        size={10}
        className="shrink-0 inline-flex items-center gap-3 h-20 px-6 rounded-input border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-brand"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// The card every item wears
// ---------------------------------------------------------------------------

export function ItemCard({
  item, onRemove, children,
}: {
  item: EvidenceItem
  onRemove: () => void
  children: React.ReactNode
}) {
  return (
    <div className="rounded-input border border-border-subtle bg-elevated px-10 py-8 flex flex-col gap-3">
      <div className="flex items-baseline gap-8 text-10 font-mono text-tertiary">
        <span className="text-12 font-sans font-medium text-primary normal-case">{item.title || 'note'}</span>
        <span className="ml-auto shrink-0"><AgentName id={item.agent_id} /> · {formatStamp(item.created_at)}</span>
        <Button
          variant="danger-text"
          size="bare"
          onClick={onRemove}
          title={t('Remove this evidence item')}
          aria-label={`Remove ${item.title || 'this note'}`}
          className="shrink-0"
        >
          <Trash2 size={10} aria-hidden />
        </Button>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

function Importance({ n }: { n: number }) {
  const v = Math.max(0, Math.min(5, Math.round(n || 0)))
  const label = `Importance ${v} of 5`
  return (
    <span className="inline-flex items-center gap-2" title={label} aria-label={label} role="img">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} aria-hidden className={`w-4 h-4 rounded-pill ${i <= v ? 'bg-brand' : 'bg-border-subtle'}`} />
      ))}
    </span>
  )
}

function Lines({ add, del: removed }: { add: number; del: number }) {
  if (!add && !removed) return <span className="text-tertiary">—</span>
  return (
    <span className="tabular-nums whitespace-nowrap">
      <span className="text-status-green">+{add ?? 0}</span>{' '}
      <span className="text-error">−{removed ?? 0}</span>
    </span>
  )
}

function FilesTable({ paths }: { paths: EvidencePath[] }) {
  const rows = sortPaths(paths)
  if (rows.length === 0) return null
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-11 font-mono border-collapse">
        <thead>
          <tr className="text-10 text-tertiary">
            <th scope="col" className="text-left font-normal py-3 pr-8">{t('file')}</th>
            <th scope="col" className="text-left font-normal py-3 pr-8">{t('what')}</th>
            <th scope="col" className="text-left font-normal py-3 pr-8">{t('lines')}</th>
            <th scope="col" className="text-left font-normal py-3 pr-8">{t('weight')}</th>
            <th scope="col" className="text-left font-normal py-3">{t('tests')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <Row key={p.path} p={p} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Row({ p }: { p: EvidencePath }) {
  return (
    <>
      <tr className="border-t border-border-subtle align-baseline">
        <td className="py-3 pr-8 max-w-[320px]">
          <span className="flex items-baseline gap-6 min-w-0">
            <span className="text-primary truncate" title={p.path}>{p.path}</span>
            {p.security_surface && (
              <span className="text-10 text-status-amber shrink-0" title={t('Touches the security surface')}>{t('security')}</span>
            )}
            {p.in_git === false && (
              <span
                className="text-10 text-tertiary shrink-0"
                title={t('Git did not record this file during the task.')}
              >
                {t('not in git')}
              </span>
            )}
          </span>
        </td>
        <td className="py-3 pr-8 text-secondary whitespace-nowrap">{p.action}</td>
        <td className="py-3 pr-8"><Lines add={p.lines_add} del={p.lines_del} /></td>
        <td className="py-3 pr-8">
          <span className="inline-flex items-center gap-6">
            <Importance n={p.importance} />
            {p.blast_radius > 0 && (
              <span className="text-10 text-tertiary tabular-nums" title={`Blast radius ${p.blast_radius} of 10`}>
                {p.blast_radius}/10
              </span>
            )}
          </span>
        </td>
        <td className={`py-3 whitespace-nowrap ${p.test_coverage === 'untested' ? 'text-status-amber' : 'text-tertiary'}`}>
          {p.test_coverage || '—'}
        </td>
      </tr>
      {p.why?.trim() && (
        <tr className="align-baseline">
          <td colSpan={5} className="pb-4 pl-12 text-11 font-sans text-secondary leading-relaxed">
            {p.why}
          </td>
        </tr>
      )}
    </>
  )
}

export function FilesItem({ item, onRemove }: { item: EvidenceItem; onRemove: () => void }) {
  return (
    <ItemCard item={item} onRemove={onRemove}>
      <div className="flex flex-col gap-6">
        {item.start_here && <StartHere pointer={item.start_here} />}
        <FilesTable paths={item.paths ?? []} />
      </div>
    </ItemCard>
  )
}

// ---------------------------------------------------------------------------
// What landed
// ---------------------------------------------------------------------------

/** The changes by their architecture group, in the form's own order. */
export function groupChanges(changes: EvidenceChange[]): { group: string; changes: EvidenceChange[] }[] {
  const by = new Map<string, EvidenceChange[]>()
  for (const c of changes) {
    const g = c.group || 'does'
    const list = by.get(g)
    if (list) list.push(c)
    else by.set(g, [c])
  }
  return [...by.entries()]
    .sort((a, b) => {
      const ai = GROUP_ORDER.indexOf(a[0])
      const bi = GROUP_ORDER.indexOf(b[0])
      return (ai < 0 ? GROUP_ORDER.length : ai) - (bi < 0 ? GROUP_ORDER.length : bi) || a[0].localeCompare(b[0])
    })
    .map(([group, list]) => ({ group, changes: list }))
}

export function ChangeItem({ item, onRemove }: { item: EvidenceItem; onRemove: () => void }) {
  const groups = groupChanges(item.changes ?? [])
  return (
    <ItemCard item={item} onRemove={onRemove}>
      <div className="flex flex-col gap-8">
        {groups.map((g) => (
          <section key={g.group} aria-label={g.group} className="flex flex-col gap-3">
            <div className="text-10 uppercase tracking-wide font-mono text-tertiary">{g.group}</div>
            {g.changes.map((c, i) => (
              <div key={`${c.type}-${c.name}-${i}`} className="flex flex-col gap-2 pl-8">
                <div className="flex items-baseline gap-6 flex-wrap min-w-0">
                  <span
                    className="text-12 font-mono text-tertiary shrink-0"
                    title={OP_WORD[c.op] ?? c.op}
                    aria-label={OP_WORD[c.op] ?? c.op}
                  >
                    {OP_MARK[c.op] ?? '~'}
                  </span>
                  <span className="inline-flex items-center h-20 px-6 rounded-pill border border-border-subtle text-10 font-mono text-tertiary shrink-0">
                    {c.type}
                  </span>
                  <span className="text-12 text-primary">{c.name}</span>
                  {c.note?.trim() && <span className="text-12 text-secondary">{c.note}</span>}
                </div>
                {(c.path ?? []).length > 0 && (
                  <div className="flex flex-col gap-1 pl-16">
                    {(c.path ?? []).map((path) => (
                      <code key={path} className="text-10 font-mono text-tertiary truncate" title={path}>{path}</code>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </section>
        ))}
      </div>
    </ItemCard>
  )
}

// ---------------------------------------------------------------------------
// What git saw and nobody claimed
// ---------------------------------------------------------------------------

const MISSING_SHOWN = 5

/** `missing` carries the whole file record, so the counts come with it. */
export function MissingFiles({ missing }: { missing: WorkFile[] }) {
  if (missing.length === 0) return null
  return (
    <details className="flex flex-col gap-4">
      <summary className="text-10 uppercase tracking-wide font-mono text-tertiary cursor-pointer hover:text-brand">
        {t('Git saw')} {missing.length} {t('more')} {missing.length === 1 ? 'file' : 'files'} {t('with large changes')}
      </summary>
      <div className="mt-4 flex flex-col gap-2 pl-12">
        {/* The server sends them largest first; five is enough to judge. */}
        {missing.slice(0, MISSING_SHOWN).map((f) => (
          <div key={f.path} className="flex items-baseline gap-8 text-11 font-mono min-w-0">
            <span className="text-secondary truncate" title={f.path}>{f.path}</span>
            <span className="ml-auto shrink-0">
              <Lines add={f.lines_add ?? 0} del={f.lines_del ?? 0} />
            </span>
          </div>
        ))}
        {missing.length > MISSING_SHOWN && (
          <div className="text-11 font-mono text-tertiary">
            {missing.length - MISSING_SHOWN} {t('more with smaller changes.')}
          </div>
        )}
      </div>
    </details>
  )
}
