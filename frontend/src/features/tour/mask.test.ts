/**
 * The capture's mask (scripts/tour_mask.mjs): the paths of this computer,
 * rewritten in the words and the fields of a page right before a picture.
 */

import { describe, it, expect, beforeEach } from 'vitest'

import { maskPage } from '../../../scripts/tour_mask.mjs'

const MASK = [
  { from: '/tmp/slightly-parallel-tour-world-8123/work/example/shopfront', to: '~/code/shopfront' },
  { from: '/tmp/slightly-parallel-tour-world-8123/work', to: '~/.slightly-parallel' },
  { from: '/home/ann/src/slightly-parallel', to: '~/code/slightly-parallel' },
  { from: '/home/ann', to: '~' },
]

describe('the capture mask', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('rewrites the text of the page and the values of its fields, longest path first', () => {
    document.body.innerHTML = `
      <p id="a">cd /tmp/slightly-parallel-tour-world-8123/work/example/shopfront &amp;&amp; ls /home/ann/notes</p>
      <code id="b">/home/ann/src/slightly-parallel/backend · /tmp/slightly-parallel-tour-world-8123/work/projects</code>
      <input id="c" value="/home/ann/src/slightly-parallel/AGENTS.md">
      <textarea id="d">/tmp/slightly-parallel-tour-world-8123/work</textarea>`
    expect(maskPage(MASK)).toBe(4)
    expect(document.getElementById('a')?.textContent).toBe('cd ~/code/shopfront && ls ~/notes')
    expect(document.getElementById('b')?.textContent).toBe('~/code/slightly-parallel/backend · ~/.slightly-parallel/projects')
    expect((document.getElementById('c') as HTMLInputElement).value).toBe('~/code/slightly-parallel/AGENTS.md')
    expect((document.getElementById('d') as HTMLTextAreaElement).value).toBe('~/.slightly-parallel')
  })

  it('leaves attributes, scripts and styles alone, and a page without paths as it is', () => {
    document.body.innerHTML = `
      <a id="a" href="/files?path=/home/ann/x" title="/home/ann/x">open</a>
      <script>var p = "/home/ann"</script><style>/* /home/ann */</style>`
    const before = document.body.innerHTML
    expect(maskPage(MASK)).toBe(0)
    expect(document.body.innerHTML).toBe(before)
    expect(maskPage([])).toBe(0)
  })
})
