import { describe, expect, it } from 'vitest'

import { unsafe } from './safety'

describe('the page check before a query is sent', () => {
  it('lets reading through', () => {
    expect(unsafe("SELECT * FROM messages WHERE commands like '%delete%'")).toBe('')
    expect(unsafe("SELECT 1 -- drop the rest")).toBe('')
    expect(unsafe('SELECT count(*) AS created FROM tasks')).toBe('')
  })
  it('stops what would change something, and says why', () => {
    expect(unsafe('DELETE FROM tasks')).toMatch(/DELETE/)
    expect(unsafe('SELECT 1; DROP TABLE tasks')).toMatch(/Two statements/)
    expect(unsafe("SELECT 1 WHERE x IN (SELECT 1) OR 1=1 UNION SELECT 2; ATTACH 'x'")).toMatch(/Two statements/)
    expect(unsafe("COPY tasks TO 'x.csv'")).toMatch(/COPY/)
  })
})
