import { describe, expect, it } from 'vitest'

import { blockText, blocksOf, keyOf, messageAt, Record, rowKind, type CapturedTurn } from './match'

/*
 * Rows shaped like Claude Code's output in a tmux pane (read from the
 * operator's panes, read only, 2026-11-18; the words here are made up):
 * the operator's message after "❯ " with its next lines indented, the
 * agent's text and tool calls after "● ", tool output after "⎿", status
 * lines after "✻", a slash command the record does not keep, and the input
 * box between two rules. Markdown is drawn: no ** and no backticks.
 */
const SCREEN = [
  '╭──────────────────────────────╮',
  '│ ✻ Welcome to Claude Code      │',
  '╰──────────────────────────────╯',
  '',
  '❯ почини падение теста входа на macOS: имя хоста длинное и строка',
  '  переносится на вторую',
  '',
  '● Read(desktop/e2e/terminals.spec.ts)',
  '  ⎿  Read 134 lines',
  '',
  '● Тест считал строки в склеенном тексте, а длинное имя хоста',
  '  переносило команду на вторую строку. Теперь он ждёт строку',
  '  целиком и печатает экран при падении.',
  '',
  '  - terminals.spec.ts: ожидание строки, а не счёт строк',
  '',
  '  Ждут твоего ответа: 1, 2.',
  '',
  '✻ Worked for 42s · done 9:24 PM',
  '',
  '❯ статус',
  '',
  '● Смотрю CI, это займёт минуту.',
  '',
  '● Bash(gh run view 44057213382)',
  '  ⎿  in_progress',
  '',
  '● Всё зелёное: 41 passed на трёх системах.',
  '',
  '  Ждут твоего ответа: 1, 2.',
  '',
  '❯ /compact',
  '  ⎿  Compacted (ctrl+o to see full summary)',
  '',
  '● Продолжаю после сжатия: что-то, чего нет в записи.',
  '',
  '❯ статус',
  '',
  '● Опять статус: на macOS красный, остальные зелёные.',
  '',
  '  Ждут твоего ответа: 1, 2.',
  '',
  '──────────────────────────────────────────',
  '❯ черновик в поле ввода',
  '──────────────────────────────────────────',
  '  ? for shortcuts',
]

const TURNS: CapturedTurn[] = [
  { n: 7, sid: 's1', user: 'почини падение теста входа на macOS: имя хоста длинное и строка переносится на вторую',
    agent: 'Тест считал строки в склеенном тексте, а длинное имя хоста переносило команду на вторую строку. Теперь он ждёт **строку целиком** и печатает экран при падении.\n\n- `terminals.spec.ts`: ожидание строки, а не счёт строк\n\nЖдут твоего ответа: 1, 2.' },
  { n: 8, sid: 's1', user: 'статус', agent: 'Всё зелёное: 41 passed на трёх системах.\n\nЖдут твоего ответа: 1, 2.' },
  { n: 9, sid: 's2', user: 'статус', agent: 'Опять статус: на macOS красный, остальные зелёные.\n\nЖдут твоего ответа: 1, 2.' },
]
const rec = new Record(TURNS)
const row = (text: string, from = 0) => { const i = SCREEN.indexOf(text, from); expect(i, text).toBeGreaterThanOrEqual(0); return i }

describe('the rows of a Claude Code chat', () => {
  it('knows each kind of row: the input box is not a message', () => {
    expect(rowKind('❯ статус', '')).toBe('user')
    expect(rowKind('> статус', '')).toBe('user')
    expect(rowKind('● текст')).toBe('agent')
    expect(rowKind('⏺ текст')).toBe('agent')
    expect(rowKind('✻ Worked for 42s')).toBe('status')
    expect(rowKind('  продолжение')).toBe('cont')
    expect(rowKind('❯ черновик', '──────')).toBe('input')
    // A rule that wrapped onto a row of its own is still the box's edge.
    expect(rowKind('❯ черновик', '─')).toBe('input')
    expect(rowKind('nick@host:~$ ls')).toBe('other')
  })

  it('cuts the rows into blocks that hold their indented and empty rows', () => {
    const b = blocksOf(SCREEN)
    const first = b.find((x) => x.kind === 'user')!
    expect([first.start, first.end]).toEqual([row('❯ почини падение теста входа на macOS: имя хоста длинное и строка'), row('● Read(desktop/e2e/terminals.spec.ts)') - 1])
  })

  it('reduces a text to its letters and digits', () => {
    expect(keyOf('**Строку** `целиком`, ‑ 41 passed │')).toBe('строкуцеликом41passed')
  })
})

describe('a click matched to a recorded message', () => {
  it('the operator\'s message, on its first row and on its wrapped row', () => {
    expect(messageAt(SCREEN, row('❯ почини падение теста входа на macOS: имя хоста длинное и строка'), rec)).toEqual({ n: 7, side: '', sid: 's1', how: 'text' })
    expect(messageAt(SCREEN, row('  переносится на вторую'), rec)).toEqual({ n: 7, side: '', sid: 's1', how: 'text' })
  })

  it('a wrapped reply drawn without its markdown is found by its text', () => {
    expect(messageAt(SCREEN, row('  переносило команду на вторую строку. Теперь он ждёт строку'), rec)).toEqual({ n: 7, side: 'reply', sid: 's1', how: 'text' })
    expect(messageAt(SCREEN, row('  - terminals.spec.ts: ожидание строки, а не счёт строк'), rec)?.n).toBe(7)
  })

  it('a tool call, its output, the narration and the status line are the reply of the message above', () => {
    expect(messageAt(SCREEN, row('● Read(desktop/e2e/terminals.spec.ts)'), rec)).toEqual({ n: 7, side: 'reply', sid: 's1', how: 'turn' })
    expect(messageAt(SCREEN, row('  ⎿  Read 134 lines'), rec)?.n).toBe(7)
    expect(messageAt(SCREEN, row('✻ Worked for 42s · done 9:24 PM'), rec)).toEqual({ n: 7, side: 'reply', sid: 's1', how: 'turn' })
    expect(messageAt(SCREEN, row('● Смотрю CI, это займёт минуту.'), rec)).toEqual({ n: 8, side: 'reply', sid: 's1', how: 'turn' })
  })

  it('the same words in two turns: the order on the screen says which', () => {
    const first = row('❯ статус')
    const second = row('❯ статус', first + 1)
    expect(messageAt(SCREEN, first, rec)?.n).toBe(8)
    expect(messageAt(SCREEN, second, rec)).toEqual({ n: 9, side: '', sid: 's2', how: 'text' })
  })

  it('a line present in three replies belongs to the turn it was printed in', () => {
    const lines = SCREEN.map((r, i) => (r === '  Ждут твоего ответа: 1, 2.' ? i : -1)).filter((i) => i >= 0)
    expect(lines.map((i) => messageAt(SCREEN, i, rec)?.n)).toEqual([7, 8, 9])
  })

  it('without the operator\'s message on the screen, the reply\'s own text, the most recent turn on a tie', () => {
    const tail = SCREEN.slice(row('● Опять статус: на macOS красный, остальные зелёные.'))
    expect(messageAt(tail, 0, rec)).toEqual({ n: 9, side: 'reply', sid: 's2', how: 'text' })
    const shared = ['● Ждут твоего ответа: 1, 2.']
    expect(messageAt(shared, 0, rec)?.n).toBe(9)
  })

  it('nothing is guessed: a slash command, what follows it, the input box, the banner, a shell line', () => {
    expect(messageAt(SCREEN, row('❯ /compact'), rec)).toBeNull()
    expect(messageAt(SCREEN, row('● Продолжаю после сжатия: что-то, чего нет в записи.'), rec)).toBeNull()
    expect(messageAt(SCREEN, row('❯ черновик в поле ввода'), rec)).toBeNull()
    expect(messageAt(SCREEN, 1, rec)).toBeNull()
    expect(messageAt(['nick@host:~$ ls', 'a.txt'], 1, rec)).toBeNull()
    expect(messageAt(SCREEN, 0, new Record([]))).toBeNull()
  })

  it('an old Claude Code (">" and "⏺") reads the same', () => {
    const old = SCREEN.map((r) => r.replace(/^❯ /, '> ').replace(/^● /, '⏺ '))
    expect(messageAt(old, row('● Read(desktop/e2e/terminals.spec.ts)'), rec)?.n).toBe(7)
    expect(messageAt(old, row('❯ статус'), rec)?.n).toBe(8)
  })

  it('a short message counts only when a whole recorded message is exactly it', () => {
    const r = new Record([{ n: 1, sid: 's', user: 'статус. что по сабагентам?', agent: '' }])
    expect(messageAt(['❯ статус'], 0, r)).toBeNull()
    expect(messageAt(['❯ статус. что по сабагентам?'], 0, r)?.n).toBe(1)
  })

  it('Claude Code\'s own rows under a message do not count for it ("Interrupted")', () => {
    const r = new Record([
      { n: 3, sid: 's', user: 'Interrupted · What should Claude do instead? пример из вставки длиннее строки', agent: '' },
      { n: 4, sid: 's', user: 'делай tk_bba7c02c', agent: '' },
    ])
    expect(messageAt(['❯ делай tk_bba7c02c', '  ⎿  Interrupted · What should Claude do instead?'], 0, r)?.n).toBe(4)
  })

  it('copies the block as shown when no message is found', () => {
    expect(blockText(SCREEN, row('  переносится на вторую'))).toBe('почини падение теста входа на macOS: имя хоста длинное и строка\nпереносится на вторую')
  })
})
