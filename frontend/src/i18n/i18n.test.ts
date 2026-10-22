import { afterEach, describe, expect, it, vi } from 'vitest'

import { locale, setLangForTests, t, tn } from '.'

afterEach(() => setLangForTests('en'))

describe('t and tn', () => {
  it('shows the English source, filled, in English', () => {
    expect(t('Language')).toBe('Language')
    expect(tn(1, '{n} task', '{n} tasks')).toBe('1 task')
    expect(tn(3, '{n} task', '{n} tasks')).toBe('3 tasks')
  })

  it('shows the Russian entry in Russian, and English where there is none', () => {
    setLangForTests('ru')
    expect(t('Language')).toBe('Язык')
    expect(t('A text nobody translated, {n}', { n: 2 })).toBe('A text nobody translated, 2')
    expect([1, 2, 5, 21, 22, 25, 11].map((n) => tn(n, '{n} task', '{n} tasks'))).toEqual(
      ['1 задача', '2 задачи', '5 задач', '21 задача', '22 задачи', '25 задач', '11 задач'])
  })
})

describe('watchLanguage', () => {
  it('reloads a tab when another tab picks a different language, and only then', async () => {
    const { watchLanguage, LANG_KEY } = await import('.')
    setLangForTests('en')
    const reload = vi.fn()
    Object.defineProperty(window, 'location', { value: { ...window.location, reload }, writable: true })
    localStorage.setItem(LANG_KEY, 'en')
    watchLanguage()
    window.dispatchEvent(new StorageEvent('storage', { key: LANG_KEY, newValue: 'en' }))
    expect(reload).not.toHaveBeenCalled()
    window.dispatchEvent(new StorageEvent('storage', { key: LANG_KEY, newValue: 'ru' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})

describe('locale', () => {
  it('is one English locale everywhere: day first, as the app writes its dates', () => {
    setLangForTests('en')
    expect(locale()).toBe('en-GB')
    setLangForTests('ru')
    expect(locale()).toBe('ru-RU')
  })
})

describe('setLang', () => {
  it('falls back to English for dates too, and the tab does not reload over the Russian choice', async () => {
    const { setLang, watchLanguage, LANG_KEY } = await import('.')
    setLangForTests('ru')
    const reload = vi.fn()
    Object.defineProperty(window, 'location', { value: { ...window.location, reload }, writable: true })
    localStorage.setItem(LANG_KEY, 'ru')
    setLang('en')
    expect(locale()).toBe('en-GB')
    expect(t('Language')).toBe('Language')
    watchLanguage()
    window.dispatchEvent(new StorageEvent('storage', { key: LANG_KEY, newValue: 'ru' }))
    expect(reload).not.toHaveBeenCalled()
  })
})
