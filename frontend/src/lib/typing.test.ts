import { describe, expect, it } from 'vitest'

import { isTypingElement, isTypingTarget } from './typing'

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
