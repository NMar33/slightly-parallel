import { beforeEach, describe, expect, it } from 'vitest'

import { FOCUS_DRAFT_KEY, readFocusDraft, requestBody, writeFocusDraft } from './release'

describe('the release request', () => {
  it('sends the brief and the style as text, an emptied box as an empty string', () => {
    const body = requestBody('release', { focus: 'this week', brief: 'Write it', style: '' }, { brief: 'b1', style: 's1' }, 'operator')
    expect(body).toEqual({
      type: 'release', focus: 'this week', actor: 'operator',
      brief_id: 'b1', brief: 'Write it', style_id: 's1', style: '',
    })
    expect(Object.keys(body)).toContain('style')
  })

  it('sends the focus whole, however long', () => {
    const focus = 'x'.repeat(12_000)
    expect(requestBody('post', { focus, brief: 'b', style: 's' }, {}, 'operator').focus).toHaveLength(12_000)
  })
})

describe('the focus draft', () => {
  beforeEach(() => localStorage.clear())

  it('is kept per task and gone once written empty', () => {
    writeFocusDraft('tk_1', 'my notes')
    expect(readFocusDraft('tk_1')).toBe('my notes')
    expect(readFocusDraft('tk_2')).toBe('')
    writeFocusDraft('tk_1', '')
    expect(localStorage.getItem(FOCUS_DRAFT_KEY('tk_1'))).toBeNull()
  })
})
