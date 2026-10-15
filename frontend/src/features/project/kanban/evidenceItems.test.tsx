import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

// Agent names come from the snapshot; these tests render with no query client.
vi.mock('../../../lib/useAgentNames', () => ({ useAgentNames: () => (id: string | null | undefined) => String(id ?? '') }))

import {
  ChangeItem, FilesItem, MissingFiles, groupChanges, sortPaths, summarise,
  type EvidenceChange, type EvidenceItem, type EvidencePath,
} from './evidenceItems'

function path(over: Partial<EvidencePath> & { path: string }): EvidencePath {
  return {
    action: 'modified',
    lines_add: 10,
    lines_del: 2,
    importance: 3,
    blast_radius: 4,
    test_coverage: 'covered',
    security_surface: false,
    why: '',
    in_git: true,
    ...over,
  }
}

function item(over: Partial<EvidenceItem>): EvidenceItem {
  return {
    id: 'tev_1',
    kind: 'files',
    title: 'Touched',
    body: '',
    agent_id: 'cc-abc12345',
    created_at: '2026-09-18T16:52:00',
    ...over,
  }
}

const PATHS = [
  path({ path: 'b/low.ts', importance: 1, lines_add: 3, lines_del: 0 }),
  path({ path: 'a/door.tsx', importance: 5, lines_add: 120, lines_del: 8, why: 'The whole change starts here.' }),
  path({ path: 'a/mid.ts', importance: 3, lines_add: 10, lines_del: 2 }),
]

afterEach(cleanup)

describe('the files an agent claims', () => {
  it('puts the most important first, then sorts by path', () => {
    expect(sortPaths(PATHS).map((p) => p.path)).toEqual(['a/door.tsx', 'a/mid.ts', 'b/low.ts'])
  })

  it('renders every path, its lines and its why', () => {
    render(<FilesItem item={item({ paths: PATHS })} onRemove={() => {}} />)
    const rows = screen.getAllByRole('row').slice(1) // past the header
    expect(within(rows[0]!).getByTitle('a/door.tsx')).toBeInTheDocument()
    expect(screen.getByText('The whole change starts here.')).toBeInTheDocument()
    expect(screen.getByText('+120')).toBeInTheDocument()
  })

  it('marks a file git never saw, without shouting', () => {
    render(<FilesItem item={item({ paths: [path({ path: 'x.ts', in_git: false })] })} onRemove={() => {}} />)
    const mark = screen.getByText('not in git')
    expect(mark).toHaveAttribute('title', 'Git did not record this file during the task.')
    expect(mark.className).toContain('text-tertiary')
  })

  it('says how important a file is, for a reader who cannot see the dots', () => {
    render(<FilesItem item={item({ paths: [path({ path: 'x.ts', importance: 4 })] })} onRemove={() => {}} />)
    expect(screen.getByLabelText('Importance 4 of 5')).toBeInTheDocument()
  })
})

describe('open this first', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('shows the pointer and copies it', async () => {
    const pointer = 'features/project/mentions.tsx:MentionRow'
    render(<FilesItem item={item({ paths: PATHS, start_here: pointer })} onRemove={() => {}} />)
    expect(screen.getByText(pointer)).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Copy the reference'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(pointer)
    await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument())
  })

  it('stays out of the way when there is no pointer', () => {
    render(<FilesItem item={item({ paths: PATHS })} onRemove={() => {}} />)
    expect(screen.queryByText('Open this first')).not.toBeInTheDocument()
  })
})

describe('what landed', () => {
  const CHANGES: EvidenceChange[] = [
    { op: 'add', type: 'tests', group: 'holds', name: 'evidenceItems', path: [], note: 'the new kinds' },
    { op: 'add', type: 'feature', group: 'does', name: 'richer evidence', path: ['kanban/EvidencePanel.tsx'], note: 'files and changes' },
    { op: 'change', type: 'endpoint', group: 'talks', name: 'GET /api/tasks/{id}/evidence', path: [], note: 'carries work' },
    { op: 'add', type: 'fix', group: 'does', name: 'kinds no longer read as notes', path: [], note: '' },
  ]

  it('groups the changes in the order the architecture form asks for them', () => {
    expect(groupChanges(CHANGES).map((g) => g.group)).toEqual(['does', 'talks', 'holds'])
    expect(groupChanges(CHANGES)[0]!.changes).toHaveLength(2)
  })

  it('renders each group with its changes and their paths', () => {
    render(<ChangeItem item={item({ kind: 'change', changes: CHANGES })} onRemove={() => {}} />)
    expect(screen.getByRole('region', { name: 'does' })).toBeInTheDocument()
    expect(screen.getByText('richer evidence')).toBeInTheDocument()
    expect(screen.getByText('kanban/EvidencePanel.tsx')).toBeInTheDocument()
    expect(screen.getAllByLabelText('added').length).toBeGreaterThan(0)
  })
})

describe('what git saw and nobody claimed', () => {
  // The server sends whole file records here, not paths — rendering one as
  // a string crashed the task window (found by opening it).
  const missing = [{ path: 'left/out.ts', lines_add: 7, lines_del: 1, committed: true }]

  it('folds, and lists the files with their lines', () => {
    render(<MissingFiles missing={missing} />)
    const fold = screen.getByText("Git saw 1 more file with large changes")
    expect(fold.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByTitle('left/out.ts')).toBeInTheDocument()
    expect(screen.getByText('+7')).toBeInTheDocument()
    expect(screen.getByText('−1')).toBeInTheDocument()
  })

  it('shows the five largest and counts the rest', () => {
    const many = Array.from({ length: 8 }, (_, i) => (
      { path: `f${i}.ts`, lines_add: 100 - i, lines_del: 0, committed: true }
    ))
    render(<MissingFiles missing={many} />)
    expect(screen.getByTitle('f4.ts')).toBeInTheDocument()
    expect(screen.queryByTitle('f5.ts')).not.toBeInTheDocument()
    expect(screen.getByText('3 more with smaller changes.')).toBeInTheDocument()
  })

  it('is absent when the agent claimed everything', () => {
    const { container } = render(<MissingFiles missing={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('the one-line summary', () => {
  it('counts the files, the lines and each kind of change', () => {
    const items = [
      item({ paths: PATHS }),
      item({
        id: 'tev_2', kind: 'change', changes: [
          { op: 'add', type: 'feature', group: 'does', name: 'a', path: [], note: '' },
          { op: 'add', type: 'feature', group: 'does', name: 'b', path: [], note: '' },
          { op: 'add', type: 'endpoint', group: 'talks', name: 'c', path: [], note: '' },
        ],
      }),
    ]
    expect(summarise(items)).toBe('3 files · +133 −10 · 2 features · 1 endpoint')
  })

  it('is empty when there is only a note', () => {
    expect(summarise([item({ kind: 'text', body: 'done' })])).toBe('')
  })
})
