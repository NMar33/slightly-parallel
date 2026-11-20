import { beforeEach, describe, expect, it } from 'vitest'

import { setLangForTests } from '../../i18n'
import { FoldMap, fitTo, foldLines, foldsOf, joinedRows, labelText, messageRange, sgrAfter, spansOf, stripAnsi, tmuxRows, type Fold, type SrcRow } from './fold'
import { clearFolds, foldIds, hasFolds, onFolds, resetFoldsForTests, setFolds } from './foldStore'
import { messageAt, Record } from './messageMenu/match'

/* Claude Code's history as a tmux pane shows it (the shape of match.test.ts). */
const CHAT = [
  '╭──────────────────────────────╮',       // 0
  '│ ✻ Welcome to Claude Code      │',      // 1
  '╰──────────────────────────────╯',       // 2
  '',                                       // 3
  '❯ почини падение теста входа на macOS',  // 4  user 1
  '  имя хоста длинное',                    // 5
  '',                                       // 6
  '● Read(desktop/e2e/terminals.spec.ts)',  // 7  reply 1
  '  ⎿  Read 134 lines',                    // 8
  '',                                       // 9
  '● Тест считал строки в склеенном тексте', // 10
  '  и теперь ждёт строку целиком.',        // 11
  '',                                       // 12
  '✻ Worked for 42s',                       // 13
  '',                                       // 14
  '❯ статус',                               // 15 user 2
  '',                                       // 16
  '● Всё зелёное: 41 passed.',              // 17 reply 2
  '',                                       // 18
  '❯ статус',                               // 19 user 3
  '',                                       // 20
  '● На macOS красный, остальные зелёные.', // 21 reply 3
  '',                                       // 22
  '──────────────────────────────',         // 23
  '❯ черновик',                             // 24 input
  '──────────────────────────────',         // 25
]
const rows = (a: string[]): SrcRow[] => a.map((text) => ({ text }))

beforeEach(() => setLangForTests('en'))

describe('the messages in the rows', () => {
  it('cuts the operator\'s messages and the replies, a reply up to the next message', () => {
    const s = spansOf(rows(CHAT))
    expect(s.map((x) => [x.side, x.start, x.end])).toEqual([
      ['user', 4, 5], ['reply', 7, 13],
      ['user', 15, 15], ['reply', 17, 17],
      ['user', 19, 19], ['reply', 21, 21],
    ])
  })

  it('two «статус» with different answers are two messages', () => {
    const s = spansOf(rows(CHAT))
    expect(s[2]!.id).not.toBe(s[4]!.id)
    expect(new Set(s.map((x) => x.id)).size).toBe(6)
  })

  it('a row anywhere in a reply (a tool call, its output, a status line) is the reply; the input box is nothing', () => {
    const r = rows(CHAT)
    const reply = spansOf(r)[1]!
    for (const at of [7, 8, 10, 11, 13]) expect(messageRange(r, at)).toEqual(reply)
    expect(messageRange(r, 5)?.side).toBe('user')
    expect(messageRange(r, 6)?.side).toBe('user')
    expect(messageRange(r, 1)).toBeNull()
    expect(messageRange(r, 24)).toBeNull()
  })

  it('names a message by its text: the same with the rows joined, wrapped or cut elsewhere, and after more history above', () => {
    const r = rows(CHAT)
    const ids = spansOf(r).map((s) => s.id)
    // The same message wrapped by xterm: the second half a soft-wrapped row.
    const wrapped: SrcRow[] = [...r.slice(0, 4), { text: '❯ почини падение теста ' }, { text: 'входа на macOS', wrapped: true }, ...r.slice(5)]
    expect(spansOf(wrapped).map((s) => s.id)).toEqual(ids)
    // Joined back (the message menu reads joined rows).
    expect(spansOf(rows(joinedRows(wrapped, 0).rows)).map((s) => s.id)).toEqual(ids)
    // 100 rows more history above.
    const more = rows([...Array.from({ length: 100 }, (_, i) => `$ line ${i}`), ...CHAT])
    expect(spansOf(more).map((s) => s.id)).toEqual(ids)
  })

  it('tmux: a line the pane wrapped (no flag from tmux) stays in its message, and counts its two rows', () => {
    const cols = 20
    const lines = ['❯ вопрос', '', '● ответ', '  ' + 'w'.repeat(cols - 2), 'www хвост', '  ещё', '', '❯ дальше', '────────────────────', '❯ черновик']
    const src = tmuxRows(lines, cols)
    expect(src.map((r) => !!r.wrapped)).toEqual([false, false, false, false, true, false, false, false, false, false])
    const reply = spansOf(src).find((x) => x.side === 'reply')!
    expect([reply.start, reply.end]).toEqual([2, 5])
    // The same text unwrapped (a wider pane): the same id.
    const wide = tmuxRows(['❯ вопрос', '', '● ответ', '  ' + 'w'.repeat(cols - 2) + 'www хвост', '  ещё', '', '❯ дальше'], 80)
    expect(spansOf(wide).find((x) => x.side === 'reply')!.id).toBe(reply.id)
  })

  it.each([['›', '•'], ['❯', '●'], ['>', '⏺']])('keeps %s and %s separate after a full tmux row', (user, agent) => {
    const cols = 31
    const request = `${user} ${'q'.repeat(cols - 2)}`
    const response = `${agent} ${'r'.repeat(cols - 2)}`
    const nextRequest = `${user} another question`
    const lines = [request, response, nextRequest, `${agent} another answer`, ' '.repeat(2) + 'w'.repeat(cols - 2), 'wrapped tail']
    const src = tmuxRows(lines, cols)

    expect(src.map((r) => !!r.wrapped)).toEqual([false, false, false, false, false, true])
    expect(joinedRows(src, 5)).toEqual({ rows: [...lines.slice(0, 4), lines[4] + lines[5]], at: 4 })
    expect(spansOf(src).map(({ side, start, end }) => [side, start, end])).toEqual([
      ['user', 0, 0], ['reply', 1, 1], ['user', 2, 2], ['reply', 3, 5],
    ])

    const rec = new Record([
      { n: 1, sid: 'test-chat', user: request.slice(2), agent: response.slice(2) },
      { n: 2, sid: 'test-chat', user: 'another question', agent: 'another answer' },
    ])
    const found = src.slice(0, 4).map((_, i) => {
      const joined = joinedRows(src, i)
      const matched = messageAt(joined.rows, joined.at, rec)
      return [matched?.n, matched?.side]
    })
    expect(found).toEqual([[1, ''], [1, 'reply'], [2, ''], [2, 'reply']])
  })

  it('a reply still being written keeps its id once its first words are there', () => {
    const r = rows(CHAT.slice(0, 13))
    const after = rows([...CHAT.slice(0, 13), '  ещё строка', '', '✻ Worked for 50s'])
    expect(spansOf(r)[1]!.id).toBe(spansOf(after)[1]!.id)
  })
})

describe('folds and the map of rows', () => {
  const r = rows(CHAT)
  const s = spansOf(r)

  it('never folds the last screen (the live one)', () => {
    const all = (id: string) => s.some((x) => x.id === id)
    expect(foldsOf(r, all, 0).length).toBe(6)
    // A screen of 8 rows: rows 18.. are live; reply 3 (21) and user 3 (19) stay.
    expect(foldsOf(r, all, 8).map((f) => f.start)).toEqual([4, 7, 15, 17])
  })

  it('maps the rows with adjacent folds, a message partly above, and back', () => {
    const folds = foldsOf(r, (id) => id === s[0]!.id || id === s[1]!.id || id === s[3]!.id, 0)
    expect(folds.map((f) => [f.start, f.end])).toEqual([[4, 5], [7, 13], [17, 17]])
    const m = new FoldMap(r.length, folds)
    // 26 rows − 1 (user 1) − 6 (reply 1) − 0 (reply 2, one row already).
    expect(m.length).toBe(19)
    expect(m.toView(3)).toBe(3)
    expect(m.toView(4)).toBe(4)
    expect(m.toView(5)).toBe(4)
    expect(m.toView(6)).toBe(5)
    expect(m.toView(7)).toBe(6)
    expect(m.toView(13)).toBe(6)
    expect(m.toView(14)).toBe(7)
    expect(m.toView(25)).toBe(18)
    for (let v = 0; v < m.length; v++) expect(m.toView(m.toSrc(v))).toBe(v)
    expect(m.toSrc(4)).toBe(4)
    expect(m.toSrc(6)).toBe(7)
    expect(m.toSrc(7)).toBe(14)
    expect(m.foldAt(6)?.side).toBe('reply')
    expect(m.foldAt(5)).toBeNull()
    expect(m.foldAt(100)).toBeNull()
  })

  it('a fold inside another is dropped, the outer kept', () => {
    const outer: Fold = { id: 'a', side: 'reply', start: 2, end: 9, first: '' }
    const m = new FoldMap(20, [outer])
    expect(m.toView(5)).toBe(2)
    const folds = foldsOf(r, () => true, 0)
    for (let i = 1; i < folds.length; i++) expect(folds[i]!.start).toBeGreaterThan(folds[i - 1]!.end)
  })

  it('writes each fold as one label row and carries the colours the left-out rows set', () => {
    const lines = ['a', '\x1b[31mred starts', 'still red', '\x1b[0mplain', 'b']
    const fold: Fold = { id: 'x', side: 'reply', start: 1, end: 2, first: 'red starts' }
    const out = foldLines(lines, [fold], 80)
    expect(out.length).toBe(4)
    expect(stripAnsi(out[1]!)).toBe('▸ A · 2 lines · red starts')
    // The row after the fold starts from what the rows left out set: red.
    expect(out[2]).toBe('\x1b[0m\x1b[31m\x1b[0mplain')
    expect(sgrAfter('\x1b[1m\x1b[0;32mx\x1b[4m', '\x1b[31m')).toBe('\x1b[0;32m\x1b[4m')
  })
})

describe('the label', () => {
  it('says who, how many rows (wrapped rows count), and the first line that says something', () => {
    const r = rows(CHAT)
    const [u, reply] = foldsOf(r, () => true, 0)
    expect(labelText(u!, 120)).toBe('▸ You · 2 lines · почини падение теста входа на macOS')
    expect(labelText(reply!, 120)).toBe('▸ A · 7 lines · Read(desktop/e2e/terminals.spec.ts)')
    expect(labelText({ side: 'user', start: 0, end: 0, first: '' }, 80)).toBe('▸ You · 1 line')
  })

  it('in Russian', () => {
    setLangForTests('ru')
    expect(labelText({ side: 'reply', start: 0, end: 47, first: 'Готово' }, 80)).toBe('▸ A · 48 строк · Готово')
    expect(labelText({ side: 'user', start: 0, end: 11, first: 'x' }, 80)).toBe('▸ Вы · 12 строк · x')
    expect(labelText({ side: 'user', start: 0, end: 2, first: 'x' }, 80)).toBe('▸ Вы · 3 строки · x')
  })

  it('fits the terminal\'s width, wide characters counted twice', () => {
    expect(fitTo('abcdef', 4)).toBe('abc…')
    expect(fitTo('abcd', 4)).toBe('abcd')
    expect(fitTo('日本語です', 5)).toBe('日本…')
    const l = labelText({ side: 'reply', start: 0, end: 9, first: 'x'.repeat(200) }, 40)
    expect([...l].length).toBe(40)
    expect(l.endsWith('…')).toBe(true)
  })
})

describe('kept per terminal', () => {
  beforeEach(() => { localStorage.clear(); resetFoldsForTests() })

  it('keeps the ids per terminal across a reload, and tells the others', () => {
    const told: string[] = []
    const me = {}
    const off = onFolds((sid, origin) => { if (origin !== me) told.push(sid) })
    setFolds('t1', ['ra', 'ub'], true, me)
    setFolds('t2', ['rc'], true)
    expect(told).toEqual(['t2'])
    resetFoldsForTests()
    expect([...foldIds('t1')]).toEqual(['ra', 'ub'])
    expect(hasFolds('t2')).toBe(true)
    setFolds('t1', ['ra'], false)
    expect([...foldIds('t1')]).toEqual(['ub'])
    clearFolds('t1')
    resetFoldsForTests()
    expect(hasFolds('t1')).toBe(false)
    expect(JSON.parse(localStorage.getItem('sp-term-folds')!)).toEqual({ t2: { ids: ['rc'], at: expect.any(Number) } })
    off()
  })

  it('reads junk as nothing, and drops terminals unused for 60 days', () => {
    localStorage.setItem('sp-term-folds', '[1,2')
    expect(hasFolds('t1')).toBe(false)
    resetFoldsForTests()
    localStorage.setItem('sp-term-folds', JSON.stringify({ old: { ids: ['x'], at: Date.now() - 61 * 24 * 3600 * 1000 }, bad: { ids: 'x' } }))
    expect(hasFolds('old')).toBe(true)
    setFolds('new', ['y'], true)
    expect(Object.keys(JSON.parse(localStorage.getItem('sp-term-folds')!))).toEqual(['new'])
  })
})
