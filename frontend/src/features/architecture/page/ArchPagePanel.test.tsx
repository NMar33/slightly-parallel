import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ArchPagePanel } from './ArchPagePanel'
import { segments, standingWord, type ArchPageAnswer } from './data'

vi.mock('../../../lib/useAgentNames', () => ({ useAgentNames: () => (id: string) => (id === 'cc-a' ? 'photo-work' : id) }))

const FACTS = {
  today: '2026-09-21', folder: '/p/photos', files: 1204, standing: 'paused — last file change 2026-08-29, 3 weeks before today',
  top_level: [{ name: 'src', files: 40, mb: 0.4, last_change: '2026-08-29' }, { name: 'old', files: 9, mb: 1.2, last_change: '2026-03-02' }],
  git: { commits: 88, last_commit: '2026-08-29 Read dates from video', remote: ['origin git@x:y.git (fetch)'], uncommitted_files: 2,
         recent_commit_subjects: ['2026-08-29 Read dates from video'] },
  nested_repositories: [], build_and_ci_files: ['Makefile'],
}

const BODY = [
  'What a person can run today.',
  '',
  '1. **Rename photos by date** — `rename.py` · where: `rename.py` · seen: ran it on 3 files · made by: person',
  '   · checked by: automated tests',
  '2. Dry-run report. Where: `report.py`.',
  '- A plain note with no evidence.',
].join('\n')

const ANSWER: ArchPageAnswer = {
  project: 'photos', word_budget: 900, facts: FACTS,
  versions: [{ n: 1, at: '2026-09-20T10:00:00', agent_id: 'cc-a', note: 'first', words: 300 },
             { n: 2, at: '2026-09-21T09:30:00', agent_id: 'cc-a', note: 'recounted', words: 320 }],
  page: {
    n: 2, at: '2026-09-21T09:30:00', agent_id: 'cc-a', note: 'recounted', words: 320, text: BODY,
    counts: { claims: 2, with_path: 2, missing: 1, changed_since: 1 },
    sections: [{
      title: 'What it does or has produced', body: BODY,
      claims: [
        { text: 'Rename photos by date — `rename.py`', where: '`rename.py`', seen: 'ran it on 3 files', made_by: 'person',
          checked_by: 'automated tests', path: 'rename.py', path_found: true, changed_since: '2026-09-21' },
        { text: 'Dry-run report', where: '`report.py`', path: 'report.py', path_found: false },
      ],
    }],
  },
}

function mount(answer: ArchPageAnswer) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(String(url))
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => answer, text: async () => '' }
  }))
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ArchPagePanel projectCode="photos" />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('ArchPagePanel', () => {
  it('shows each claim with its evidence and the marks the server gave it', async () => {
    mount(ANSWER)
    expect(await screen.findByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('photo-work')).toBeInTheDocument()
    expect(screen.getByText('2 claims')).toBeInTheDocument()
    expect(screen.getByText('1 not found')).toBeInTheDocument()
    expect(screen.getByText('1 changed since')).toBeInTheDocument()
    expect(document.querySelectorAll('[data-claim]')).toHaveLength(2)
    expect(screen.getByText('ran it on 3 files')).toBeInTheDocument()
    expect(screen.getByText('automated tests')).toBeInTheDocument()
    expect(screen.getByText('not found')).toBeInTheDocument()
    expect(screen.getByText('changed 2026-09-21')).toBeInTheDocument()
    // Prose and a list item with no evidence stay prose.
    expect(screen.getByText('What a person can run today.')).toBeInTheDocument()
    expect(screen.getByText('A plain note with no evidence.')).toBeInTheDocument()
    // The computed band says it is computed, and colours only the standing word.
    expect(screen.getByLabelText('Computed by Slightly Parallel')).toBeInTheDocument()
    expect(document.querySelector('[data-standing="paused"]')).not.toBeNull()
  })

  it('asks for an older version and marks it read only', async () => {
    const calls = mount(ANSWER)
    const select = await screen.findByLabelText('Version')
    fireEvent.change(select, { target: { value: '1' } })
    await waitFor(() => expect(calls.some((u) => u.includes('version=1'))).toBe(true))
  })

  it('shows the computed band with no page written yet', async () => {
    mount({ ...ANSWER, page: null, versions: [] })
    expect(await screen.findByText('No architecture page yet.')).toBeInTheDocument()
    expect(screen.getAllByText('#page').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Computed by Slightly Parallel')).toBeInTheDocument()
  })
})

describe('segments', () => {
  it('keeps the written order and drops nothing', () => {
    const parts = segments(ANSWER.page!.sections[0])
    expect(parts.map((p) => p.kind)).toEqual(['md', 'claim', 'claim', 'md'])
    const orphan = segments({ title: 't', body: 'Only prose.', claims: [{ text: 'A claim the body lost' }] })
    expect(orphan.map((p) => p.kind)).toEqual(['md', 'claim'])
  })
  it('reads the first word of the standing', () => {
    expect(standingWord('dormant — last file change 2026-03-01')).toBe('dormant')
    expect(standingWord(undefined)).toBe('')
  })
})
