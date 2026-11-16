import { describe, expect, it } from 'vitest'

import { isTypingElement, isTypingTarget, letter } from './typing'

function make(html: string): HTMLElement {
  const host = document.createElement('div')
  host.innerHTML = html
  document.body.appendChild(host)
  return host.firstElementChild as HTMLElement
}

describe('isTypingTarget', () => {
  it('counts inputs, textareas, selects and contenteditable as typing', () => {
    expect(isTypingElement(make('<input />'))).toBe(true)
    expect(isTypingElement(make('<textarea></textarea>'))).toBe(true)
    expect(isTypingElement(make('<select><option>a</option></select>'))).toBe(true)
    expect(isTypingElement(make('<div contenteditable="true"></div>'))).toBe(true)
    const inner = make('<div contenteditable="true"><p><b>x</b></p></div>').querySelector('b')
    expect(isTypingElement(inner)).toBe(true)
  })

  it('does not count buttons, links, the body or nothing', () => {
    expect(isTypingElement(make('<button>b</button>'))).toBe(false)
    expect(isTypingElement(make('<a href="/x">a</a>'))).toBe(false)
    expect(isTypingElement(document.body)).toBe(false)
    expect(isTypingElement(null)).toBe(false)
    expect(isTypingElement(window)).toBe(false)
  })

  it('reads the event target', () => {
    const input = make('<input />')
    const e = new KeyboardEvent('keydown', { key: '1' })
    Object.defineProperty(e, 'target', { value: input })
    expect(isTypingTarget(e)).toBe(true)
  })
})

describe('letter', () => {
  it('is the Latin letter typed, else the place on the board', () => {
    expect(letter({ key: 's', code: 'KeyS' })).toBe('s')
    expect(letter({ key: 'S', code: 'KeyS' })).toBe('s')
    // Cyrillic: Ctrl+S arrives as ы, t as е.
    expect(letter({ key: 'ы', code: 'KeyS' })).toBe('s')
    expect(letter({ key: 'е', code: 'KeyT' })).toBe('t')
    // Dvorak: the character wins; the key labelled S on QWERTY types o.
    expect(letter({ key: 'o', code: 'KeyS' })).toBe('o')
    // Not a letter: the key as it is.
    expect(letter({ key: 'Enter', code: 'Enter' })).toBe('Enter')
    expect(letter({ key: '`', code: 'Backquote' })).toBe('`')
    expect(letter({ key: 'ArrowLeft', code: 'ArrowLeft' })).toBe('ArrowLeft')
  })
})
