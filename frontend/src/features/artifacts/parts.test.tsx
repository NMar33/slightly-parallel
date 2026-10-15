import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Artifact, Preview } from './data'
import { KindPreview } from './parts'

function art(preview: Preview, exists = true): Artifact {
  return {
    row: {
      id: 'ar_t', created_date: '2609-18', created_time: '10:00', project: 'alpha', agent_id: 'cc-1', l1: 'x',
      source: 'captured', session_id: null, source_turn: 1, versions_n: 0, tags: null,
      name: 'thing', kind: preview.kind, description: 'd', status: 'active', path: '/r/projects/alpha/artifacts/thing',
      files_n: 1, bytes: 10, updated_at: null,
    },
    kept: null,
    folder: { path: '/r/projects/alpha/artifacts/thing', exists, files: [{ path: 'a.txt', bytes: 3, is_text: true }],
      manifest: { meta: {}, body: '' }, preview },
  }
}

describe('KindPreview', () => {
  it('draws a dataset as fields and a sample, and names a read error plainly', () => {
    render(<KindPreview a={art({ kind: 'dataset', missing: false, tables: [
      { file: 'rows.jsonl', fields: ['before', 'chosen'], rows: 2, sample: [{ before: 'a', chosen: 'b' }], error: 'line 3: Expecting value' },
    ] })} />)
    expect(screen.getByText('rows.jsonl')).toBeTruthy()
    expect(screen.getByText('before')).toBeTruthy()
    expect(screen.getByText('b')).toBeTruthy()
    expect(screen.getByText(/Read stopped at line 3/)).toBeTruthy()
  })

  it('renders a document', () => {
    render(<KindPreview a={art({ kind: 'document', missing: false, document: { file: 'notes.md', text: '# Title\n\nBody here.', truncated: true } })} />)
    expect(screen.getByText('Body here.')).toBeTruthy()
    expect(screen.getByText(/The text is cut here/)).toBeTruthy()
  })

  it('frames a page from the file route with a way to open it', () => {
    const { container } = render(<KindPreview a={art({ kind: 'page', missing: false, entry: 'index.html', pages: ['index.html'] })} />)
    const frame = container.querySelector('iframe')
    expect(frame?.getAttribute('src')).toBe('/api/artifacts/ar_t/files/index.html')
    expect(frame?.getAttribute('sandbox')).toBe('')
    expect(screen.getByText('Open in a tab').getAttribute('href')).toBe('/api/artifacts/ar_t/files/index.html')
  })

  it('shows an app as its run line and tree', () => {
    render(<KindPreview a={art({ kind: 'app', missing: false, run: 'node capture.mjs',
      tree: [{ path: 'lib', dir: true, depth: 0 }, { path: 'lib/shot.mjs', dir: false, depth: 1, bytes: 1020 }] })} />)
    expect(screen.getByText('node capture.mjs')).toBeTruthy()
    expect(screen.getByText('shot.mjs')).toBeTruthy()
  })

  it('says when the folder is gone, with the path', () => {
    render(<KindPreview a={art({ kind: 'other', missing: true }, false)} />)
    expect(screen.getByText(/The folder is gone/).textContent).toContain('/r/projects/alpha/artifacts/thing')
  })
})
