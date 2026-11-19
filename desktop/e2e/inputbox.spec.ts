import fs from 'node:fs'
import path from 'node:path'
import type { ElectronApplication, Page } from '@playwright/test'
import { test, expect, KEEP_PLAIN, PROJECT, WINDOWS, expectLine, fullSize, lines } from './fixtures'

/**
 * The input box an agent draws, in a terminal its program started in before
 * the window attached (tk_11bd239e).
 *
 * Codex asks the terminal for its text and ground colours (OSC 10/11) once,
 * as it starts, and draws its input box as a band in a shade of the ground;
 * told nothing, it draws no band at all. An agent's terminal starts its
 * command as the session is born, before any window is attached, and tmux
 * answered those questions only from an attached window: Codex in the
 * window had no input box, where Claude Code (which draws its box with two
 * rules and asks nothing) had one. Now tmux knows the scheme's colours from
 * the session's birth (termlib.window_style).
 *
 * No real agent runs here: `codexish.py` does what Codex does at its start
 * (asks, reads the answers raw, draws the band in a shade of the ground it
 * was told) and `claudeish.py` draws Claude Code's box. The terminal opens
 * through the route with the script as its command, then the window shows it.
 */

const CODEXISH = String.raw`
import os, re, select, signal, sys, termios, time, tty
fd = os.open('/dev/tty', os.O_RDWR)
old = termios.tcgetattr(fd)
tty.setraw(fd)
# The device attributes last: every terminal answers them, so their answer ends the wait.
os.write(fd, b'\x1b]10;?\x1b\\\x1b]11;?\x1b\\\x1b[c')
got, end = b'', time.time() + 1.0
while time.time() < end and not got.endswith(b'c'):
    r, _, _ = select.select([fd], [], [], 0.05)
    if r:
        got += os.read(fd, 1000)
termios.tcsetattr(fd, termios.TCSADRAIN, old)
m = re.search(rb'\x1b\]11;rgb:([0-9a-f]+)/([0-9a-f]+)/([0-9a-f]+)', got)
if m:
    bg = [int(x[:2], 16) for x in m.groups()]
    light = sum(bg) / 3 > 128
    shade = [round(c + ((0 if light else 255) - c) * 0.12) for c in bg]
    band, told = '\x1b[48;2;%d;%d;%dm' % tuple(shade), 'told shade=%d,%d,%d' % tuple(shade)
else:
    band, told = '', 'told nothing'

def draw(*_):
    # As Codex does: the whole screen again at the terminal's new size.
    cols = os.get_terminal_size().columns
    out = '\x1b[H\x1b[2J' + 'codexish header\r\n' + told + '\r\n'
    for text in ('', '\u203a Ask Codex to do anything', ''):
        out += band + text.ljust(cols - 1) + '\x1b[0m\r\n'
    sys.stdout.write(out)
    sys.stdout.flush()

signal.signal(signal.SIGWINCH, draw)
draw()
while True:
    time.sleep(600)
`

const CLAUDEISH = String.raw`
import os, signal, sys, time

def draw(*_):
    cols = os.get_terminal_size().columns
    rule = '\x1b[38;5;244m' + '\u2500' * (cols - 1) + '\x1b[39m'
    sys.stdout.write('\x1b[H\x1b[2J\u25cf claudeish answer\r\n\r\n' + rule + '\r\n\u276f draft\r\n' + rule + '\r\n')
    sys.stdout.flush()

signal.signal(signal.SIGWINCH, draw)
draw()
while True:
    time.sleep(600)
`

const strip = (page: Page) => page.getByRole('tablist', { name: 'Chats' })

/** The backgrounds the window draws on the row holding `text`, and on an empty row. */
const rowGrounds = (page: Page, text: string) => page.evaluate((t) => {
  const rows = [...document.querySelectorAll('.aqua-screen .xterm-rows > div')] as HTMLElement[]
  const grounds = (r: HTMLElement | undefined) => [...new Set([...(r?.querySelectorAll('span') ?? [])].map((s) => getComputedStyle(s).backgroundColor))]
  const viewport = document.querySelector('.aqua-screen .xterm-viewport') as HTMLElement | null
  return {
    row: grounds(rows.find((r) => (r.textContent ?? '').includes(t))),
    empty: grounds(rows[rows.length - 1]),
    ground: viewport ? getComputedStyle(viewport).backgroundColor : '',
  }
}, text)

/** Open a terminal running `script` through the route, then show it in the window. */
async function agentTab(app: ElectronApplication, page: Page, api: import('@playwright/test').APIRequestContext, dir: string, name: string, script: string) {
  fs.writeFileSync(path.join(dir, `${name}.py`), script)
  const r = await api.post('/api/terminal/sessions', { data: { kind: 'shell', project: PROJECT, label: name, role: 'shell', command: `python3 ${name}.py` } })
  expect(r.ok(), await r.text()).toBeTruthy()
  await page.reload()
  await fullSize(app, page)
  const tab = strip(page).getByRole('tab', { name: new RegExp(`^${name}`) })
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
}

test.describe('an agent\'s input box (tk_11bd239e)', () => {
  test.skip(WINDOWS, 'a Unix tty and python3')
  // A plain terminal is a pty the server holds: before the window attaches,
  // nobody answers the questions there; tmux is the Linux and macOS default.
  test.skip(KEEP_PLAIN, 'tmux only: a plain terminal has no tmux to answer before the window attaches')

  test('a Codex-shaped program started before the window attaches is told the ground and draws its box', async ({ win, server }) => {
    const { page } = win
    await agentTab(win.app, page, server.api, server.dir, 'codexish', CODEXISH)
    // What the terminal shows, when the line does not come (docs/testing.md §1).
    await expectLine(page, /^told /).catch(async (e) => { throw new Error(`${e}\n${(await lines(page)).join('\n')}`) })
    const told = (await lines(page)).find((l) => l.startsWith('told '))!
    expect(told, 'the program was told the ground before any window attached').toMatch(/^told shade=\d+,\d+,\d+$/)
    const shade = `rgb(${told.slice('told shade='.length).split(',').join(', ')})`
    const got = await rowGrounds(page, 'Ask Codex to do anything')
    // The input box is a band in the shade on the prompt's row (its last cell, past the band, is the ground).
    expect(got.row, JSON.stringify(got)).toContain(shade)
    expect(got.row.every((c) => c === shade || c === got.ground), JSON.stringify(got)).toBe(true)
    expect(got.empty.every((c) => c === got.ground || c === 'rgba(0, 0, 0, 0)'), JSON.stringify(got)).toBe(true)
  })

  test('a Claude-Code-shaped box draws on the ground as before', async ({ win, server }) => {
    const { page } = win
    await agentTab(win.app, page, server.api, server.dir, 'claudeish', CLAUDEISH)
    await expectLine(page, /^❯ draft$/).catch(async (e) => { throw new Error(`${e}\n${(await lines(page)).join('\n')}`) })
    const got = await rowGrounds(page, 'draft')
    // tmux paints the pane in the scheme's ground: exactly the window's own, so nothing shows.
    for (const c of [...got.row, ...got.empty]) expect([got.ground, 'rgba(0, 0, 0, 0)'], JSON.stringify(got)).toContain(c)
  })
})
