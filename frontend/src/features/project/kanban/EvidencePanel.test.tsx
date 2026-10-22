import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

// Agent names come from the snapshot; these tests render with no query client.
vi.mock('../../../lib/useAgentNames', () => ({ useAgentNames: () => (id: string | null | undefined) => String(id ?? '') }))

import { EvidencePanel } from './EvidencePanel'

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const NOTE = {
  id: 'tev_note', kind: 'text', title: 'What I ran',
  body: 'pytest: **34 passed**', agent_id: 'cc-abc12345', created_at: '2026-09-18T16:52:00',
}
const SHOT = {
  id: 'tev_shot', kind: 'image', title: 'The panel', body: 'task_evidence/tk_1/tev_shot.png',
  agent_id: 'cc-abc12345', created_at: '2026-09-18T16:53:00', url: '/api/tasks/evidence/tev_shot/file',
}
const FILES = {
  id: 'tev_files', kind: 'files', title: 'Touched', body: '',
  agent_id: 'cc-abc12345', created_at: '2026-09-18T16:54:00',
  start_here: 'kanban/evidenceItems.tsx:FilesTable',
  paths: [{
    path: 'kanban/evidenceItems.tsx', action: 'created', lines_add: 300, lines_del: 0,
    importance: 5, blast_radius: 3, test_coverage: 'covered', security_surface: false,
    why: 'The new kinds live here.', in_git: true,
  }],
}

function mount(evidence: unknown[], extra: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).endsWith('/evidence')) {
      return json(200, { task_id: 'tk_1', evidence, work: null, missing: [], ...extra })
    }
    return json(200, { default_id: 'default', prompts: [] })
  }))
  // The panel reads the evidence prompts through react-query now.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <EvidencePanel taskId="tk_1" promptId="" onPickPrompt={() => {}} />
    </QueryClientProvider>,
  )
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
})

describe('the evidence panel', () => {
  it('still renders a note as markdown and a screenshot as a thumbnail', async () => {
    mount([NOTE, SHOT])
    await waitFor(() => expect(screen.getByText('What I ran')).toBeInTheDocument())
    expect(screen.getByText('34 passed').tagName).toBe('STRONG')
    const img = screen.getByAltText('The panel') as HTMLImageElement
    expect(img.getAttribute('src')).toBe('/api/tasks/evidence/tev_shot/file')
    // No files or changes posted, so no summary line.
    expect(screen.queryByText(/1 file ·/)).not.toBeInTheDocument()
  })

  it('counts every item on the summary line', async () => {
    mount([NOTE, SHOT])
    await waitFor(() => expect(screen.getByText(/2 items from cc-abc12345/)).toBeInTheDocument())
  })

  it('keeps the proof first, with the files and changes folded under it', async () => {
    mount([FILES, NOTE])
    await waitFor(() => expect(screen.getByText(/1 file · \+300 −0/)).toBeInTheDocument())
    const fold = screen.getByText('Touched and done').closest('details')!
    expect(fold).not.toHaveAttribute('open')
    // The operator's proof is above the fold that holds the account of the work.
    const note = screen.getByText(NOTE.title)
    expect(note.compareDocumentPosition(fold) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(fold).toContainElement(screen.getByText('kanban/evidenceItems.tsx:FilesTable'))
  })

  it('lists what git saw and nobody claimed', async () => {
    mount([FILES], {
      work: { files: [{ path: 'left/out.ts', lines_add: 7, lines_del: 1 }], commits: 1, add: 7, del: 1 },
      missing: [{ path: 'left/out.ts', lines_add: 7, lines_del: 1, committed: true }],
    })
    await waitFor(() =>
      expect(screen.getByText("Git saw 1 more file with large changes")).toBeInTheDocument(),
    )
  })

  it('says so plainly when an agent has posted nothing', async () => {
    mount([])
    await waitFor(() => expect(screen.getByText(/Nothing posted by an agent yet/)).toBeInTheDocument())
  })
})
