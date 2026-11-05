import { describe, expect, it } from 'vitest'

import { cardLife, countOf, docColor, docOrder, hostOf, markdownOf, versionDiffs, wordDiff, type Card, type Doc } from './data'

const card: Card = {
  id: 'pu_1', project: 'alpha', agent_id: 'cc-1', session_id: 's1', source_turn: 3, at: '2026-11-01T10:00:00',
  message: 'Capture now reads stdin', text: 'Capture reads stdin now.',
  versions: [
    { n: 2, at: '2026-11-02T10:00:00', text: 'Capture reads stdin now.', note: '' },
    { n: 1, at: '2026-11-01T12:00:00', text: 'Capture reads stdin', note: 'grammar' },
  ],
  tasks: [], cores: [], commits: [], images: [],
  placements: [
    { doc_id: 'pd_b', doc_name: 'Post', version_n: 1, item_id: 'pi_3', text: 'Capture reads stdin now.', changed: false },
    { doc_id: 'pd_a', doc_name: 'Release', version_n: 2, item_id: 'pi_2', text: 'Reads stdin.', changed: true },
    { doc_id: 'pd_a', doc_name: 'Release', version_n: 1, item_id: 'pi_1', text: 'Capture reads stdin', changed: true },
  ],
  archived_at: '',
}

const doc = (over: Partial<Doc>): Doc => ({ id: 'pd_a', project: 'alpha', name: 'Release', created_at: '2026-11-01T09:00:00', archived_at: '', current: 1, versions: [], ...over })

describe('cardLife', () => {
  it('runs original → edits in order → placements per document (tab order) and version', () => {
    const life = cardLife(card, ['pd_a', 'pd_b'])
    expect(life.map((n) => n.kind === 'placed' ? n.label : n.key)).toEqual(['o', 'u1', 'u2', 'Release v1', 'Release v2', 'Post v1'])
  })

  it('grows a placement from the version whose text it carries, else from the newest', () => {
    const life = cardLife(card, ['pd_a', 'pd_b'])
    const placed = life.filter((n) => n.kind === 'placed')
    expect(placed.map((n) => n.kind === 'placed' && n.from)).toEqual([1, 2, 2])
  })

  it('is the original alone for a card never edited or placed', () => {
    const life = cardLife({ ...card, versions: [], placements: [] })
    expect(life).toHaveLength(1)
    expect(life[0]!.kind).toBe('original')
  })
})

describe('docOrder', () => {
  it('leaves archived documents out and sorts the rest oldest first', () => {
    const docs = [
      doc({ id: 'pd_c', created_at: '2026-11-03T00:00:00' }),
      doc({ id: 'pd_x', created_at: '2026-10-01T00:00:00', archived_at: '2026-11-02T00:00:00' }),
      doc({ id: 'pd_a', created_at: '2026-11-01T00:00:00' }),
    ]
    expect(docOrder(docs).map((d) => d.id)).toEqual(['pd_a', 'pd_c'])
  })

  it('gives each place in the order a token colour, wrapping round', () => {
    expect(docColor(0)).toBe('var(--brand)')
    expect(docColor(1)).toBe('var(--brand-lean)')
    expect(docColor(8)).toBe(docColor(0))
  })
})

describe('markdownOf and versionDiffs', () => {
  const d = doc({
    current: 2,
    versions: [
      { n: 1, at: '2026-11-01T09:00:00', actor: 'operator', note: '', items: [
        { id: 'i1', card_id: 'pu_1', text: 'One.', position: 1, changed: false },
        { id: 'i2', card_id: 'pu_2', text: 'Two.', position: 2, changed: false },
      ] },
      { n: 2, at: '2026-11-02T09:00:00', actor: 'operator', note: 'tighter', items: [
        { id: 'i4', card_id: 'pu_3', text: 'Three.', position: 1, changed: false },
        { id: 'i3', card_id: 'pu_1', text: 'One, shorter.', position: 2, changed: true },
      ] },
    ],
  })

  it('writes the name as the title and one paragraph per item, in order', () => {
    expect(markdownOf(d)).toBe('# Release\n\nThree.\n\nOne, shorter.\n')
    expect(markdownOf(d, 1)).toBe('# Release\n\nOne.\n\nTwo.\n')
  })

  it('marks what came in, changed and left in each version', () => {
    const [v1, v2] = versionDiffs(d)
    expect(v1!.rows.map((r) => r.mark)).toEqual(['new', 'new'])
    expect(v2!.rows.map((r) => [r.item.card_id, r.mark])).toEqual([['pu_3', 'new'], ['pu_1', 'changed']])
    expect(v2!.left.map((it) => it.card_id)).toEqual(['pu_2'])
  })
})

describe('wordDiff', () => {
  it('marks the words added and removed, keeping the rest', () => {
    const parts = wordDiff('Capture now reads stdin', 'Capture reads stdin on every tool')
    expect(parts).toEqual([
      { op: 'same', text: 'Capture ' },
      { op: 'del', text: 'now ' },
      { op: 'same', text: 'reads stdin ' },
      { op: 'add', text: 'on every tool' },
    ])
    expect(parts.filter((p) => p.op === 'del').map((p) => p.text.trim())).toEqual(['now'])
    expect(parts.filter((p) => p.op === 'add').map((p) => p.text.trim())).toEqual(['on every tool'])
    // read back, the kept and added parts are the new text
    expect(parts.filter((p) => p.op !== 'del').map((p) => p.text).join('').replace(/\s+/g, ' ').trim()).toBe('Capture reads stdin on every tool')
  })

  it('is all kept for the same text, and all new from nothing', () => {
    expect(wordDiff('one two', 'one two')).toEqual([{ op: 'same', text: 'one two' }])
    expect(wordDiff('', 'one two')).toEqual([{ op: 'add', text: 'one two' }])
  })

  it('counts words and characters, and names a link by its host', () => {
    expect(countOf(' two words ')).toEqual({ words: 2, chars: 11 })
    expect(countOf('')).toEqual({ words: 0, chars: 0 })
    expect(hostOf('https://www.example.com/a/b')).toBe('example.com')
    expect(hostOf('not a url')).toBe('not a url')
  })
})
