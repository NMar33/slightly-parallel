import { describe, expect, it } from 'vitest'

import { crumbsOf, decodeSegment } from './crumbs'

describe('crumbsOf', () => {
  it('shows a project code as typed and does not link the bare /project', () => {
    const c = crumbsOf('/project/my-app')
    expect(c.map((x) => x.to)).toEqual(['/', null, '/project/my-app'])
    expect(c[2]!.label).toBe('my-app')
  })

  it('shows agent and prompt ids verbatim, not capitalised', () => {
    expect(crumbsOf('/agent/cc-abc123').at(-1)!.label).toBe('cc-abc123')
    expect(crumbsOf('/prompts/pm_1').at(-1)!.label).toBe('pm_1')
    expect(crumbsOf('/agent/cc-abc123')[1]!.to).toBe('/agent')
  })

  it('survives a malformed escape in the path', () => {
    expect(() => crumbsOf('/project/%E0%A4%A')).not.toThrow()
    expect(decodeSegment('%E0%A4%A')).toBe('%E0%A4%A')
    expect(decodeSegment('a%20b')).toBe('a b')
  })
})
