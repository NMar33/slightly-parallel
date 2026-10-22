import { describe, expect, it } from 'vitest'
import { groupRows, problemsFor } from './data'

describe('the map', () => {
  it('groups rows by kind in reading order and keeps unknown kinds last', () => {
    const groups = groupRows([
      { kind: 'test', name: 'pytest', what: 'x' },
      { kind: 'runtime', name: 'Python', what: 'x' },
      { kind: 'gizmo', name: 'z', what: 'x' },
      { kind: 'runtime', name: 'Node', what: 'x' },
    ])
    expect(groups.map(([k, rows]) => `${k}:${rows.length}`)).toEqual(['runtime:2', 'test:1', 'gizmo:1'])
  })
  it('finds the problems that name a row', () => {
    expect(problemsFor(['“cache”: where `nowhere.db` is not in the project folder', 'the tool template asks for a `module` row'], 'cache')).toHaveLength(1)
  })
})
