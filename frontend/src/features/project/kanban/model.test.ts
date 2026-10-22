/**
 * What a copied task says.
 *
 * The reference and the newest round are the instruction; a task that
 * wants evidence carries the ask with it, so the agent collects proof
 * while the work is happening instead of rebuilding it afterwards.
 */

import { describe, it, expect } from 'vitest'

import { columnText, evidenceNote, taskText, type TaskRow } from './model'

const PROMPT = 'Prove the work in 1–3 items, each with a one-line title.'
const ask = (t: TaskRow) => (t.evidence_prompt === 'shots' ? 'Screenshots only.' : PROMPT)

function task(over: Partial<TaskRow> = {}): TaskRow {
  return {
    id: 'tk_d5c553c8',
    title: 'Architecture Page',
    description: 'the first round',
    turns_n: 1,
    turn_last: { n: 1, date: '2609-01', time: '10:00', text: 'the first round' },
    ...over,
  } as TaskRow
}

describe('taskText', () => {
  it('is the reference, the title and the newest round', () => {
    expect(taskText(task())).toBe('tk_d5c553c8 · Architecture Page\nthe first round')
  })

  it('names the round when there is more than one', () => {
    const t = task({ turns_n: 2, turn_last: { n: 2, date: '2609-02', time: '11:17', text: 'the second round' } })
    expect(taskText(t)).toBe('tk_d5c553c8.2 · Architecture Page\nthe second round')
  })

  it('says nothing about evidence when the task wants none', () => {
    expect(taskText(task(), ask)).not.toMatch(/Evidence/)
    expect(evidenceNote(task(), ask)).toBe('')
  })

  it('carries the ask and the operator’s instructions when evidence is required', () => {
    const t = task({ evidence_required: 'yes' })
    expect(taskText(t, ask)).toBe(
      'tk_d5c553c8 · Architecture Page\nthe first round\n\n'
      + 'Evidence required — collect it as you work, then report and attach it.\n'
      + PROMPT,
    )
  })

  it('quotes the task’s own prompt, not only the default', () => {
    const t = task({ evidence_required: 'yes', evidence_prompt: 'shots' })
    expect(taskText(t, ask)).toMatch(/Screenshots only\.$/)
  })

  it('still says evidence is wanted before the prompts have loaded', () => {
    const t = task({ evidence_required: 'yes' })
    expect(taskText(t)).toMatch(/Evidence required — collect it as you work/)
    expect(taskText(t)).not.toMatch(/Prove the work/)
  })

  it('the column copy carries it too', () => {
    const t = task({ evidence_required: 'yes' })
    const col = columnText([task(), t], ask)
    expect(col.match(/Evidence required/g)).toHaveLength(1)
    expect(col.startsWith('1. tk_d5c553c8 · Architecture Page')).toBe(true)
  })
})
