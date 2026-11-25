import { describe, expect, it } from 'vitest'

import shared from '../../../testdata/project_codes/table.json'

import { listedIn, projectCodes, projectLists } from './projectCodes'

/**
 * One table for Python, SQL and TypeScript: testdata/project_codes/table.json,
 * which backend/tests/test_project_codes.py loops over too.
 */
interface Case {
  value: string | string[] | null
  codes: string[]
  has: Record<string, boolean>
}

const CASES = (shared as unknown as { cases: Case[] }).cases

describe('the project list table the server shares', () => {
  it('is read from testdata/project_codes/table.json', () => {
    expect(CASES.length).toBeGreaterThan(15)
  })

  for (const c of CASES) {
    it(`reads ${JSON.stringify(c.value)}`, () => {
      expect(projectCodes(c.value)).toEqual(c.codes)
      for (const [code, want] of Object.entries(c.has)) {
        expect([code, projectLists(c.value, code)]).toEqual([code, want])
      }
    })
  }
})

describe('listedIn', () => {
  it('reads projects when the server sent them, else the row’s own project', () => {
    expect(listedIn({ project: 'alpha', projects: 'alpha,beta' }, 'beta')).toBe(true)
    expect(listedIn({ project: 'alpha' }, 'beta')).toBe(false)
    expect(listedIn({ project: 'alpha', projects: '' }, 'alpha')).toBe(true)
  })
})
