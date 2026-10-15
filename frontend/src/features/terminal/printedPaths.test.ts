import { describe, expect, it } from 'vitest'

import { findPaths } from './printedPaths'

const paths = (s: string) => findPaths(s).map((p) => [p.path, p.line, p.col])

describe('paths a terminal printed', () => {
  it('finds foldered paths, with or without a line and column', () => {
    expect(paths('error in src/app.ts:42:7 — see ./lib/x.py:3 and ~/notes/todo.md')).toEqual([
      ['src/app.ts', 42, 7], ['./lib/x.py', 3, 0], ['~/notes/todo.md', 0, 0],
    ])
    expect(paths('/home/user/proj/main.go:10')).toEqual([['/home/user/proj/main.go', 10, 0]])
  })
  it('takes a bare file name only when it carries a line', () => {
    expect(paths('Edited app.tsx:12 and README.md')).toEqual([['app.tsx', 12, 0]])
  })
  it('leaves versions, numbers and URLs alone', () => {
    expect(paths('v1.2 costs 3.14 at https://example.com/a/b.js:3')).toEqual([])
  })
  it('stops at the punctuation around a path', () => {
    expect(paths('(src/a.ts:5), "b/c.md".')).toEqual([['src/a.ts', 5, 0], ['b/c.md', 0, 0]])
  })
  it('reports where the match sits, for the link underline', () => {
    const [p] = findPaths('at src/x.ts:9')
    expect([p!.start, p!.length, p!.text]).toEqual([3, 10, 'src/x.ts:9'])
  })
})
