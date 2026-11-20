import { describe, expect, it } from 'vitest'

import { InputMarker, isTerminalReply } from './operatorInput'

// What xterm sent through the socket when the timer's e2e test clicked once
// in a tmux terminal (logged on the server, 2026-11-18): none of it typing.
const SEEN_ON_A_CLICK = [
  '\x1b[?1;2c', '\x1b[>0;276;0c',
  '\x1b]10;rgb:e6e6/e8e8/ebeb\x1b\\', '\x1b]11;rgb:0e0e/1010/1313\x1b\\',
  '\x1b[I', '\x1b[O', '\x1b[<0;65;17M', '\x1b[<0;65;17m',
]

describe('isTerminalReply', () => {
  it.each(SEEN_ON_A_CLICK)('a report or reply is not typing: %j', (data) => {
    expect(isTerminalReply(data)).toBe(true)
  })

  it.each([
    '\x1b[12;40R', '\x1b[?12;40;1R', '\x1b[0n', '\x1b[?2004;2$y', '\x1b[8;34;128t',
    '\x1b[?0u', '\x1bP1$r0m\x1b\\', '\x1b]4;1;rgb:ffff/0000/0000\x07', '\x1b[64;10;5M', '\x1b[M !!',
    '\x1b[<0;1;1M\x1b[<0;1;1m\x1b[<64;3;3M',  // several in one message
  ])('also %j', (data) => {
    expect(isTerminalReply(data)).toBe(true)
  })

  it.each([
    'a', 'ls\r', '\r', '\x7f', '\x03', '\x1b', '\x1b[A', '\x1bOP', '\x1b[15~', '\x1b[200~pasted\x1b[201~',
    'привет', '\x1b[I' + 'x', 'x' + '\x1b[<0;1;1M', '',
  ])('a key or a paste is typing: %j', (data) => {
    expect(isTerminalReply(data)).toBe(false)
  })
})

describe('InputMarker', () => {
  it('a report is not typed, a key and a paste are', () => {
    const m = new InputMarker()
    for (const d of SEEN_ON_A_CLICK) expect(m.typed(d)).toBe(false)
    m.key()
    expect(m.typed('a')).toBe(true)
    expect(m.typed('\x1b[200~text\x1b[201~')).toBe(true)
  })

  it('a key that looks like a report is typed: Ctrl+F3 is ESC[1;5R', () => {
    const m = new InputMarker()
    expect(m.typed('\x1b[1;5R')).toBe(false)
    m.key()
    expect(m.typed('\x1b[1;5R')).toBe(true)
    // Only the data right after the key: the next report is a report again.
    expect(m.typed('\x1b[1;5R')).toBe(false)
  })

  it('a key that sent nothing does not mark a later report', async () => {
    const m = new InputMarker()
    m.key()
    await Promise.resolve()
    expect(m.typed('\x1b[<0;1;1M')).toBe(false)
  })
})
