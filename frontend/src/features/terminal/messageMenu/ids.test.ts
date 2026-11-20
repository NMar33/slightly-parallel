import { describe, expect, it } from 'vitest'

import { findIds, hashCandidates } from './ids'

const ids = (row: string) => findIds(row).map((f) => [f.kind, f.id])

describe('ids in a terminal row', () => {
  it('finds tasks, notes, decisions and entry points with where they stand', () => {
    const row = 'Карточка tk_a9306fb1 (заметка nt_0123abcd), решение dc_deadbeef; ep_12345678.'
    const at = (id: string) => row.indexOf(id)
    expect(findIds(row)).toEqual([
      { id: 'tk_a9306fb1', kind: 'task', start: at('tk_'), length: 11 },
      { id: 'nt_0123abcd', kind: 'note', start: at('nt_'), length: 11 },
      { id: 'dc_deadbeef', kind: 'decision', start: at('dc_'), length: 11 },
      { id: 'ep_12345678', kind: 'entrypoint', start: at('ep_'), length: 11 },
    ])
    expect(row.slice(9, 20)).toBe('tk_a9306fb1')
  })

  it('finds a Publish card, a core and a skill', () => {
    expect(ids('карточка pu_1a2b3c4d, ядро cr_00ff00aa и скилл sk_abcdef01')).toEqual([
      ['publish', 'pu_1a2b3c4d'], ['core', 'cr_00ff00aa'], ['skill', 'sk_abcdef01'],
    ])
  })

  it('finds the agent ids of every tool SP records, and nothing that only looks like one', () => {
    expect(ids('чаты cc-676175ea, codex-9f3e21b0, oc-y0q3vy8m и cursor-0a1b2c3d')).toEqual([
      ['agent', 'cc-676175ea'], ['agent', 'codex-9f3e21b0'], ['agent', 'oc-y0q3vy8m'], ['agent', 'cursor-0a1b2c3d'],
    ])
    expect(ids('/chats/cc-676175ea/chat.md')).toEqual([['agent', 'cc-676175ea']])
    // Too long or short, upper case, inside a name, an OpenCode word with no digit.
    expect(ids('cc-676175ea0 cc-676175e xcc-676175ea cc-676175EA my-cc-676175ea oc-assigned codex-zzzzzzzz')).toEqual([])
  })

  it('leaves out what only looks like one', () => {
    expect(findIds('xtk_a9306fb1 tk_a9306fb12 tk_A9306FB1 tk_a9306f nt_al_curl tk_a9306fb1_x')).toEqual([])
  })

  it('reads an id at the very start and end of a row, and in a path or a URL', () => {
    expect(findIds('tk_a9306fb1').map((f) => f.start)).toEqual([0])
    expect(findIds('/tasks/tk_a9306fb1?x=1').map((f) => f.id)).toEqual(['tk_a9306fb1'])
  })
})

describe('a commit hash in a row', () => {
  const hashes = (row: string) => hashCandidates(row).map((f) => f.id)

  it('takes the hashes git and agents print', () => {
    expect(hashes('47feacd0 Terminal window: a menu on a message')).toEqual(['47feacd0'])
    expect(hashes('[master 0bcfdd55] Feature map series')).toEqual(['0bcfdd55'])
    expect(hashes('Committed as 5b1dae58.')).toEqual(['5b1dae58'])
    expect(hashes('commits 47feacd0, 0bcfdd55 and (de702fa1)')).toEqual(['47feacd0', '0bcfdd55', 'de702fa1'])
    expect(hashes('   4cab401f..47feacd0  master -> master')).toEqual(['4cab401f', '47feacd0'])
    expect(hashes('sha: 47feacd0f0e1d2c3b4a5968778695a4b3c2d1e0f')).toEqual(['47feacd0f0e1d2c3b4a5968778695a4b3c2d1e0f'])
  })

  it('never a number, a word, a UUID, a version, a path, a URL or a part of an id', () => {
    expect(hashes('1234567 20261118 deadbeef defaced facade')).toEqual([]) // no letter, or no digit
    expect(hashes('session 676175ea-a3c6-4ae1-adcc-5abf2659566a')).toEqual([]) // a UUID's segments
    expect(hashes('https://github.com/nmar/sp/commit/47feacd0f0e1d2c3b4a5968778695a4b3c2d1e0f')).toEqual([])
    expect(hashes('http://127.0.0.1:8123/api/x?sha=47feacd0#47feacd0')).toEqual([])
    expect(hashes('v1.2.3 1.0.0a1 node@18.3.1 3.12.1abc')).toEqual([])
    expect(hashes('build/a1b2c3d4e5/out.js a1b2c3d4e5.png')).toEqual([])
    expect(hashes('tk_a9306fb1 ag_0badc0de cc-676175ea x47feacd0 47feacd0x 47feacd0_x')).toEqual([])
    expect(hashes('41 passed in 3.2s; a1b2c3 is six')).toEqual([])
  })

  it('an id or an agent id is never read as a hash too', () => {
    expect(ids('dc_0badc0de cc-676175ea 47feacd0')).toEqual([['decision', 'dc_0badc0de'], ['agent', 'cc-676175ea'], ['commit', '47feacd0']])
  })
})
