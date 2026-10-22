import { describe, expect, it } from 'vitest'
import { hitHref, kindWord, type SearchHit } from './searchHits'

const hit = (kind: string, id: string): SearchHit =>
  ({ kind, id, title: 't', project: 'p', date: '2609-21', snippet: 's', where: 'title' })

describe('search hits', () => {
  it('sends each kind to its page', () => {
    expect(hitHref(hit('scan', 'sn_1'))).toBe('/scans#scan=sn_1')
    expect(hitHref(hit('chat', 'cc-1'))).toBe('/agent/cc-1#sec=chats')
    expect(hitHref({ ...hit('turn', 'cc-2#4.user'), agent_id: 'cc-2' })).toBe('/agent/cc-2#sec=chats')
    expect(hitHref(hit('unknown', 'x_1'))).toContain('/search?q=')
  })
  it('names a kind as the pages do', () => {
    expect(kindWord('architecture')).toBe('Architecture')
    expect(kindWord('gizmo')).toBe('gizmo')
  })
})
