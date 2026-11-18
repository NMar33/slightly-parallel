import { describe, expect, it } from 'vitest'

import { findUrls, linkAt } from './links'

const no = { commitOk: () => false, paths: true }

describe('the link under a right click', () => {
  it('a web address as printed, without the sentence\'s punctuation or a bracket it never opened', () => {
    expect(findUrls('see https://example.com/a?b=1#c. and (http://x.io/y) or https://en.wikipedia.org/wiki/Foo_(bar), done').map((u) => u.text))
      .toEqual(['https://example.com/a?b=1#c', 'http://x.io/y', 'https://en.wikipedia.org/wiki/Foo_(bar)'])
    expect(findUrls('https:// alone, ftp://x.io')).toEqual([])
  })

  it('an id, then an address, then a path the editor opens; nothing between them', () => {
    const row = 'tk_a9306fb1 at http://127.0.0.1:8123/kanban?task=tk_a9306fb1 in src/app.ts:42 47feacd0'
    expect(linkAt(row, 3, no)).toMatchObject({ kind: 'id', text: 'tk_a9306fb1' })
    expect(linkAt(row, row.indexOf('127'), no)).toMatchObject({ kind: 'url', text: 'http://127.0.0.1:8123/kanban?task=tk_a9306fb1' })
    // The id inside the address is the address's.
    expect(linkAt(row, row.lastIndexOf('tk_') + 2, no)).toMatchObject({ kind: 'url' })
    expect(linkAt(row, row.indexOf('app.ts'), no)).toMatchObject({ kind: 'path', text: 'src/app.ts:42' })
    expect(linkAt(row, row.indexOf('app.ts'), { ...no, paths: false })).toBeNull()
    expect(linkAt(row, row.indexOf(' at '), no)).toBeNull()
    // A hash is a link only when it is a commit.
    expect(linkAt(row, row.indexOf('47fe'), no)).toBeNull()
    expect(linkAt(row, row.indexOf('47fe'), { ...no, commitOk: (s) => s === '47feacd0' })).toMatchObject({ kind: 'id', text: '47feacd0' })
  })
})
