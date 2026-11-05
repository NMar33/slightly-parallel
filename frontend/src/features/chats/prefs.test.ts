import { afterEach, describe, expect, it } from 'vitest'

import { readChatsPrefs, storeChatsPrefs, storeUsagePref } from './prefs'

afterEach(() => localStorage.clear())

describe('the chats page prefs: usage on a turn', () => {
  it('shows usage by default: the viewer is where one looks on purpose', () => {
    expect(readChatsPrefs().usage).toBe(true)
  })

  it('keeps "hide" between visits, and tells the agent page reader too', () => {
    storeChatsPrefs({ ...readChatsPrefs(), usage: false })
    expect(readChatsPrefs().usage).toBe(false)
    expect(localStorage.getItem('sp-chat-usage')).toBe('off')
  })

  it('starts a first visit from the reader\'s own switch', () => {
    localStorage.setItem('sp-chat-usage', 'off')
    expect(readChatsPrefs().usage).toBe(false)
  })

  it('reads older saved prefs without the field as shown', () => {
    localStorage.setItem('sp-chats', JSON.stringify({ width: 'even', list: 12, chat: 12, order: 'oldest', md: true, work: true }))
    expect(readChatsPrefs().usage).toBe(true)
  })

  it('follows the agent page reader\'s switch after the chats page saved its own', () => {
    storeChatsPrefs({ ...readChatsPrefs(), usage: true })
    storeUsagePref(false)
    expect(readChatsPrefs().usage).toBe(false)
    expect(JSON.parse(localStorage.getItem('sp-chats')!).usage).toBe(false)
    storeUsagePref(true)
    expect(readChatsPrefs().usage).toBe(true)
  })

  it('reads the reader\'s key over a saved field that disagrees', () => {
    localStorage.setItem('sp-chats', JSON.stringify({ width: 'even', list: 12, chat: 12, order: 'oldest', md: true, work: true, usage: true }))
    localStorage.setItem('sp-chat-usage', 'off')
    expect(readChatsPrefs().usage).toBe(false)
  })
})
