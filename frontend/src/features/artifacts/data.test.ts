import { describe, expect, it } from 'vitest'

import { firstLoad } from '../visions/data'
import {
  type Artifact, archivedOf, chaptersOf, fileRoute, kindOf, matches, notWritten, notWrittenOf, previewShape, projectsOf, sizeLabel,
} from './data'

function art(over: Partial<Artifact['row']> & { exists?: boolean; kind?: string }): Artifact {
  const { exists = true, ...row } = over
  return {
    row: {
      id: 'ar_x', created_date: '2609-18', created_time: '10:00', project: 'alpha', agent_id: 'cc-1', l1: 'x',
      source: 'captured', session_id: null, source_turn: 1, versions_n: 0, tags: null,
      name: 'thing', kind: 'document', description: 'd', status: 'active', path: '/r/projects/alpha/artifacts/thing',
      files_n: 1, bytes: 10, updated_at: '2026-09-18T10:00:00', ...row,
    } as Artifact['row'],
    kept: null,
    folder: {
      path: '/r/projects/alpha/artifacts/thing', exists, files: [], manifest: { meta: {}, body: '' },
      preview: { kind: (row.kind as never) ?? 'document', missing: !exists },
    },
  }
}

describe('loading', () => {
  it('is loading only while nothing has arrived', () => {
    expect(firstLoad(true, [])).toBe(true)
    expect(firstLoad(false, [{ data: undefined, isError: false }])).toBe(true)
    expect(firstLoad(false, [{ data: undefined, isError: false }, { data: {}, isError: false }])).toBe(false)
    expect(firstLoad(false, [{ data: undefined, isError: true }])).toBe(false)
    expect(firstLoad(false, [])).toBe(false)
  })
})

describe('chapters', () => {
  it('groups by kind in the fixed order and leaves archived and not-written rows out', () => {
    const rows = [
      art({ id: 'a', kind: 'app' }),
      art({ id: 'b', kind: 'dataset' }),
      art({ id: 'c', kind: 'dataset', status: 'archived' }),
      art({ id: 'd', kind: '', name: null, status: 'draft', exists: false }),
      art({ id: 'e', kind: 'weird' as never }),
    ]
    const chapters = chaptersOf(rows)
    expect(chapters.map((c) => c.kind)).toEqual(['dataset', 'app', 'other'])
    expect(chapters[0].items.map((a) => a.row.id)).toEqual(['b'])
    expect(archivedOf(rows).map((a) => a.row.id)).toEqual(['c'])
    expect(notWrittenOf(rows).map((a) => a.row.id)).toEqual(['d'])
    expect(kindOf(rows[4])).toBe('other')
  })

  it('reports a kept message whose folder was never written, and only that', () => {
    expect(notWritten(art({ name: null, status: 'draft', exists: false }))).toBe(true)
    expect(notWritten(art({ name: 'thing', status: 'draft', exists: true }))).toBe(false)
    expect(notWritten(art({ name: 'thing', status: 'active', exists: false }))).toBe(false)
  })

  it('lists projects once, sorted, and matches every word', () => {
    const rows = [art({ id: 'a', project: 'beta' }), art({ id: 'b', project: 'alpha' }), art({ id: 'c', project: 'beta' })]
    expect(projectsOf(rows)).toEqual(['alpha', 'beta'])
    expect(matches(art({ name: 'language-corrections', description: 'every slogan' }), 'slogan language')).toBe(true)
    expect(matches(art({ name: 'language-corrections' }), 'audit')).toBe(false)
  })
})

describe('preview', () => {
  it('picks the part to draw per kind, and says when the folder is gone', () => {
    expect(previewShape(null)).toBe('missing')
    expect(previewShape({ kind: 'dataset', missing: true })).toBe('missing')
    expect(previewShape({ kind: 'dataset', missing: false, tables: [{ file: 'a.csv', fields: ['x'], rows: 1, sample: [] }] })).toBe('tables')
    expect(previewShape({ kind: 'dataset', missing: false, tables: [] })).toBe('empty')
    expect(previewShape({ kind: 'document', missing: false, document: { file: 'ARTIFACT.md', text: 'hi', truncated: false } })).toBe('document')
    expect(previewShape({ kind: 'page', missing: false, entry: 'index.html', pages: ['index.html'] })).toBe('page')
    expect(previewShape({ kind: 'page', missing: false, entry: null, pages: [] })).toBe('empty')
    expect(previewShape({ kind: 'app', missing: false, tree: [], run: '' })).toBe('app')
    expect(previewShape({ kind: 'other', missing: false, tree: [{ path: 'x', dir: false, depth: 0, bytes: 1 }] })).toBe('tree')
  })

  it('serves files from the folder route, path segments encoded', () => {
    expect(fileRoute('ar_x', 'index.html')).toBe('/api/artifacts/ar_x/files/index.html')
    expect(fileRoute('ar_x', 'img/a b.png')).toBe('/api/artifacts/ar_x/files/img/a%20b.png')
  })

  it('prints sizes the page way', () => {
    expect(sizeLabel(12)).toBe('12 B')
    expect(sizeLabel(48_210)).toBe('47 KB')
    expect(sizeLabel(2_400_000)).toBe('2.3 MB')
  })
})
