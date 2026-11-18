import { describe, expect, it } from 'vitest'
import { pasteKey, pasteKeyName } from './pasteKeys'

const key = (k: string, mods: Partial<{ ctrl: boolean; shift: boolean; alt: boolean; meta: boolean }> = {}, code?: string) => ({
  key: k, code: code ?? (k.length === 1 ? `Key${k.toUpperCase()}` : k),
  ctrlKey: !!mods.ctrl, shiftKey: !!mods.shift, altKey: !!mods.alt, metaKey: !!mods.meta,
})

describe('pasteKey', () => {
  it('leaves Ctrl+Shift+V to the browser on Linux and Windows: the page must not paste a second time', () => {
    expect(pasteKey(key('V', { ctrl: true, shift: true }), false)).toBe('native')
  })
  it('pastes Ctrl+Shift+V itself on macOS, where the browser has no paste for it', () => {
    expect(pasteKey(key('V', { ctrl: true, shift: true }), true)).toBe('page')
  })
  it('leaves Cmd+V to the browser on macOS', () => {
    expect(pasteKey(key('v', { meta: true }), true)).toBe('native')
  })
  it('leaves Shift+Insert to the browser on Linux and Windows', () => {
    expect(pasteKey(key('Insert', { shift: true }), false)).toBe('native')
    expect(pasteKey(key('Insert', { shift: true }), true)).toBeNull()
  })
  it('keeps Ctrl+V for the shell (^V), and Ctrl+Alt+Shift+V out of it', () => {
    expect(pasteKey(key('v', { ctrl: true }), false)).toBeNull()
    expect(pasteKey(key('v', { ctrl: true }), true)).toBeNull()
    expect(pasteKey(key('V', { ctrl: true, shift: true, alt: true }), false)).toBeNull()
    expect(pasteKey(key('v'), false)).toBeNull()
    expect(pasteKey(key('Insert'), false)).toBeNull()
  })
  it('finds the V by its place on the board under another layout', () => {
    // A Cyrillic layout: V's key types «м».
    expect(pasteKey(key('М', { ctrl: true, shift: true }, 'KeyV'), false)).toBe('native')
  })
  it('names the paste key of the system', () => {
    expect(pasteKeyName(true)).toBe('Cmd+V')
    expect(pasteKeyName(false)).toBe('Ctrl+Shift+V')
  })
})
