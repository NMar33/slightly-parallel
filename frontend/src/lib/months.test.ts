import { afterEach, describe, expect, it } from 'vitest'

import { setLangForTests } from '../i18n'
import { dayMonth, monthLabel } from './months'

afterEach(() => { setLangForTests('en') })

describe('month labels', () => {
  it('write the short month as "Sep" in English, day first', () => {
    const d = new Date(2026, 8, 14)
    expect(monthLabel(d)).toBe('Sep')
    expect(dayMonth(d)).toBe('14 Sep')
  })

  it('leave Russian to Intl', () => {
    setLangForTests('ru')
    const d = new Date(2026, 8, 14)
    expect(monthLabel(d)).toBe(d.toLocaleDateString('ru-RU', { month: 'short' }))
    expect(dayMonth(d)).toBe(d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }))
  })
})
