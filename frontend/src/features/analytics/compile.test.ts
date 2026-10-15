import { describe, expect, it } from 'vitest'

import { EXAMPLE_GROUPS, parsePipeline, toSql } from './compile'

const TABLES = ['messages', 'chats', 'tasks', 'task_events']

describe('the pipeline', () => {
  it('reads every example without an error', () => {
    for (const g of EXAMPLE_GROUPS) for (const e of g.items) expect(parsePipeline(e.line, TABLES).error, e.line).toBe('')
  })
  it('compiles to one grouped query', () => {
    const { spec } = parsePipeline('messages | last 30d | where words > 5 | by agent_name | count, sum answer_words | top 10', TABLES)
    expect(toSql(spec!)).toBe(
      'SELECT agent_name, count(*) AS count, sum(answer_words) AS sum_answer_words\nFROM messages\n'
      + 'WHERE sent_at >= current_date - 30\n  AND words > 5\nGROUP BY 1\nORDER BY count DESC\nLIMIT 10')
  })
  it('uses a table\'s own day column and buckets the others', () => {
    expect(toSql(parsePipeline('messages | by day | count', TABLES).spec!)).toContain('SELECT day, count(*)')
    expect(toSql(parsePipeline('tasks | by week | count', TABLES).spec!)).toContain("date_trunc('week', created) AS week")
  })
  it('says what it does not understand', () => {
    expect(parsePipeline('people | count', TABLES).error).toMatch(/Start with a table/)
    expect(parsePipeline('messages | explode', TABLES).error).toMatch(/not a step/)
  })
})

describe('on a project page', () => {
  it('reads that project\'s rows only, under the table\'s own name', () => {
    const sql = toSql(parsePipeline('messages | by day | count', TABLES).spec!, "o'brien")
    expect(sql).toContain("FROM (SELECT * FROM messages WHERE project = 'o''brien') AS messages")
    expect(toSql(parsePipeline('task_events | count', TABLES).spec!, 'p')).toContain('task_id IN (SELECT id FROM tasks WHERE project = \'p\')')
  })
})
