import { describe, expect, it } from 'vitest'
import { entryText, labelOf } from './entryText'

describe('entryText', () => {
  it('reads the named text, and names win over the slots', () => {
    const t = entryText({
      text: { decision: 'Chose Redis', why: 'Workers share counters.', alternatives: ['LRU — rejected: undercounts'], excerpt: 'user: two workers' },
      l2: 'stale', l3: ['stale'], l4: 'stale',
    })
    expect(t.line).toBe('Chose Redis')
    expect(t.text).toBe('Workers share counters.')
    expect(t.list).toEqual(['LRU — rejected: undercounts'])
    expect(t.long).toBe('user: two workers')
    expect(t.byName.why).toBe('Workers share counters.')
    expect(t.parts.list).toEqual({ name: 'alternatives', label: 'Alternatives' })
  })

  it('falls back to the slots when the answer has no named text', () => {
    const t = entryText({ l2: 'a paragraph', l3: ['one', 'two'], l4: 'long' })
    expect([t.text, t.list, t.long]).toEqual(['a paragraph', ['one', 'two'], 'long'])
    expect(t.parts.text.label).toBe('Summary')
    expect(entryText(null).list).toEqual([])
  })

  it('keeps the list a list, and places a lone string after it as the long part', () => {
    const t = entryText({ text: { title: 'A task', points: [], detail: 'the long part' } })
    expect(t.list).toEqual([])
    expect(t.text).toBe('')
    expect(t.long).toBe('the long part')
  })

  it('labels a name for a reader', () => {
    expect(labelOf('per_file')).toBe('Per file')
    expect(labelOf('why')).toBe('Why')
  })
})
