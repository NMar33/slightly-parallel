import { describe, expect, it } from 'vitest'
import type { IBufferCell, IBufferLine } from 'xterm'
import { readerKeeps } from './reader'
import { lineDom } from './scrollLayer'

const key = (k: string, mods: Partial<KeyboardEvent> = {}) => ({ key: k, ctrlKey: false, shiftKey: false, altKey: false, metaKey: false, ...mods }) as KeyboardEvent

describe('readerKeeps', () => {
  it('copy, select all, find and lone modifiers stay with the reader', () => {
    expect(readerKeeps(key('c', { ctrlKey: true }), false, true)).toBe('keep')
    expect(readerKeeps(key('C', { ctrlKey: true, shiftKey: true }), false)).toBe('keep')
    expect(readerKeeps(key('F', { ctrlKey: true, shiftKey: true }), false)).toBe('keep')
    expect(readerKeeps(key('c', { metaKey: true }), true)).toBe('keep')
    expect(readerKeeps(key('Shift', { shiftKey: true }), false)).toBe('keep')
  })
  it('paging stays, Esc closes, anything else is the shell\'s', () => {
    expect(readerKeeps(key('PageUp'), false)).toBe('page-up')
    expect(readerKeeps(key('PageDown'), false)).toBe('page-down')
    expect(readerKeeps(key('Escape'), false)).toBe('close')
    expect(readerKeeps(key('a'), false)).toBe('live')
    expect(readerKeeps(key('Enter'), false)).toBe('live')
    expect(readerKeeps(key('c', { ctrlKey: true }), false)).toBe('live')
    // On macOS Ctrl+C is the shell's ^C, not a copy.
    expect(readerKeeps(key('c', { ctrlKey: true }), true)).toBe('live')
  })
})

/** A buffer line of plain cells; `red` columns in palette red, `wide` a two-cell character. */
function fakeLine(text: string, red: number[] = [], wide = -1): IBufferLine {
  const cells: Array<{ ch: string; w: number; fg: number }> = []
  for (let i = 0; i < text.length; i++) {
    if (i === wide) { cells.push({ ch: text[i], w: 2, fg: -1 }, { ch: '', w: 0, fg: -1 }); continue }
    cells.push({ ch: text[i], w: 1, fg: red.includes(i) ? 1 : -1 })
  }
  const cell = (c: { ch: string; w: number; fg: number }) => ({
    getWidth: () => c.w, getChars: () => c.ch, isInverse: () => 0, isBold: () => 0, isItalic: () => 0, isDim: () => 0,
    isUnderline: () => 0, isStrikethrough: () => 0, isInvisible: () => 0,
    isFgPalette: () => c.fg >= 0, getFgColor: () => c.fg, isBgPalette: () => false, getBgColor: () => 0,
    isFgRGB: () => false, isBgRGB: () => false,
  }) as unknown as IBufferCell
  return { getCell: (x: number) => (cells[x] ? cell(cells[x]) : undefined), length: cells.length } as unknown as IBufferLine
}

describe('lineDom (the ghost row)', () => {
  it('draws the line with xterm\'s colour classes, every cell its exact width', () => {
    const row = lineDom(fakeLine('ab cd', [3, 4]), 5, 8, 17)
    expect(row.textContent).toBe('ab cd')
    const spans = [...row.querySelectorAll('span')]
    expect(spans.map((s) => s.textContent)).toEqual(['ab ', 'cd'])
    expect(spans[1].className).toBe('xterm-fg-1')
    expect(spans.map((s) => s.style.width)).toEqual(['24px', '16px'])
    expect(row.style.height).toBe('17px')
  })
  it('a wide character takes two cells and a span of its own', () => {
    const row = lineDom(fakeLine('a界b', [], 1), 4, 8, 17)
    const spans = [...row.querySelectorAll('span')]
    expect(spans.map((s) => [s.textContent, s.style.width])).toEqual([['a', '8px'], ['界', '16px'], ['b', '8px']])
  })
})
