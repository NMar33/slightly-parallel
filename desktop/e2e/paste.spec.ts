import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { ElectronApplication, Page } from '@playwright/test'
import { tmuxSockets } from './sockets'
import { test, expect, HEADLESS, WINDOWS, echoCalc, expectLine, fullSize, lines, printFile, ready, typeLine } from './fixtures'

/**
 * Pasting into a terminal of the window: every way in sends the text once.
 *
 * Found by the operator: a one-line command pasted into a tab reached the
 * shell twice, glued (`cd "…" && claude -r <id>cd "…" && claude -r <id>`).
 * Two causes, each failed its test here before the fix:
 * - Ctrl+Shift+V: the page pasted from its own key handler, and the browser
 *   pasted again from its native "paste as plain text" on xterm's textarea;
 * - a middle click in a tmux terminal: the browser pasted the selection, and
 *   tmux's default binding pasted its own buffer (a line just copied in the
 *   terminal is in both).
 *
 * Each test puts a line on the system clipboard from the main process
 * (Electron's `clipboard`), pastes it one way, and checks it twice:
 * - what the page sent the server: the text exactly once, and nothing else
 *   but escape sequences (bracketed paste, focus, mouse reports);
 * - what the shell did with it: the pasted command, run, prints its line
 *   exactly once — a doubled paste glues the two copies into one command
 *   that prints something else.
 * Then a typed command still runs (no stuck state). The suite runs in both
 * terminal modes: tmux, and SP_E2E_KEEP=plain (playwright.config.ts).
 */

const MAC = process.platform === 'darwin'
const LINUX = process.platform === 'linux'

async function toClipboard(app: ElectronApplication, text: string, type: 'clipboard' | 'selection' = 'clipboard') {
  await app.evaluate(({ clipboard }, [t, k]) => { clipboard.writeText(t, k as 'clipboard' | 'selection') }, [text, type])
  expect(await app.evaluate(({ clipboard }, k) => clipboard.readText(k as 'clipboard' | 'selection'), type)).toBe(text)
}

function primaryOwner(display: string): string {
  return execFileSync('/usr/bin/python3', ['-c', `
import ctypes as c
import sys
x11 = c.CDLL('libX11.so.6')
x11.XOpenDisplay.argtypes = [c.c_char_p]
x11.XOpenDisplay.restype = c.c_void_p
x11.XGetSelectionOwner.argtypes = [c.c_void_p, c.c_ulong]
x11.XGetSelectionOwner.restype = c.c_ulong
display = x11.XOpenDisplay(sys.argv[1].encode())
if not display:
    raise RuntimeError('Could not open X11 display')
print(x11.XGetSelectionOwner(display, 1))  # XA_PRIMARY
`, display], { encoding: 'utf8' }).trim()
}

/** Every `input` frame the page sends the server from now on. */
async function recordInput(page: Page) {
  await page.evaluate(() => {
    const g = window as unknown as { __sent: string[]; __sendPatched?: boolean }
    g.__sent = []
    if (g.__sendPatched) return
    g.__sendPatched = true
    const send = WebSocket.prototype.send
    WebSocket.prototype.send = function (this: WebSocket, d: Parameters<WebSocket['send']>[0]) {
      if (typeof d === 'string') {
        try { const m = JSON.parse(d) as { type?: string; data?: string }; if (m.type === 'input' && typeof m.data === 'string') g.__sent.push(m.data) } catch { /* not ours */ }
      }
      return send.call(this, d)
    }
  })
}
const sent = (page: Page) => page.evaluate(() => (window as unknown as { __sent: string[] }).__sent.join(''))

/** What a paste of `text` sends: xterm turns line ends into CR. */
const asSent = (text: string) => text.replace(/\r?\n/g, '\r')
/** The input without escape sequences: bracketed-paste marks, focus in/out, mouse reports. */
const bare = (s: string) => s.replace(/\x1b\[[0-9;<>?]*[A-Za-z~]/g, '')
const count = (hay: string, needle: string) => hay.split(needle).length - 1

/** The page sent `text` once, and nothing else but escape sequences. Waits for it, then a little more for a second copy. */
async function sentOnce(page: Page, text: string) {
  const want = asSent(text)
  await expect.poll(async () => count(await sent(page), want), { message: 'the pasted text reached the page\'s socket' }).toBeGreaterThan(0)
  // A second copy comes from a second handler of the same key or click: give it time.
  await page.waitForTimeout(400)
  const got = await sent(page)
  expect(count(got, want), `pasted ${count(got, want)} times: ${JSON.stringify(got.slice(0, 300))}`).toBe(1)
  expect(bare(got)).toBe(want)
}

/** Lines of the terminal that are exactly `text`. */
const linesEqual = async (page: Page, text: string) => (await lines(page)).filter((l) => l.trim() === text).length

/** The pasted command ran once: its one line printed once, and a typed command runs after it. */
async function ranOnce(page: Page, out: string, n: number) {
  await expectLine(page, out)
  await page.waitForTimeout(300)
  expect(await linesEqual(page, out), `"${out}" printed more than once`).toBe(1)
  expect((await lines(page)).some((l) => l.includes(`${out}echo`)), 'two copies glued into one command').toBe(false)
  await typeLine(page, echoCalc(`typed-${n}-`, `${n}+1`))
  await expectLine(page, `typed-${n}-${n + 1}`)
}

const input = (page: Page) => page.getByRole('textbox', { name: 'Terminal input' })

test('a program clipboard request follows the terminal policy', async ({ win, server }) => {
  const { app, page } = win
  const clipboard = () => app.evaluate(({ clipboard: system }) => system.readText())
  const requested = 'text from a terminal program'
  const encoded = Buffer.from(requested).toString('base64')
  const writes = () => page.evaluate(() => (window as Window & { oscWrites?: string[] }).oscWrites)
  const emit = async () => {
    await typeLine(page, WINDOWS
      ? `[Console]::Write([char]27 + ']52;c;${encoded}' + [char]7); Write-Output osc-52-end`
      : `printf '\\033]52;c;%s\\007%s\\n' '${encoded}' osc-52-end`)
    await expectLine(page, 'osc-52-end')
  }
  const configure = async (policy: string) => {
    await page.getByRole('button', { name: 'Window settings' }).click()
    const settings = page.getByRole('complementary', { name: 'Window settings' })
    await settings.getByText('Clipboard', { exact: true }).click()
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/settings') && response.request().method() === 'POST')
    const select = settings.getByLabel('Programs may write to the clipboard (OSC 52)')
    await select.selectOption(policy)
    const result = await saved
    expect(result.ok(), await result.text()).toBe(true)
    await expect(select).toHaveValue(policy)
    await settings.getByRole('button', { name: 'Close window settings' }).click()
  }
  try {
    await ready(page)
    await toClipboard(app, 'operator clipboard')
    await page.evaluate(() => {
      const original = navigator.clipboard.writeText.bind(navigator.clipboard)
      const state = window as Window & { oscWrites?: string[] }
      state.oscWrites = []
      Object.defineProperty(navigator.clipboard, 'writeText', {
        value: (text: string) => { state.oscWrites!.push(text); return original(text) },
      })
    })
    await emit()
    expect(await writes()).toEqual([])
    expect(await clipboard()).toBe('operator clipboard')

    await configure('ask')
    await emit()
    await expect(page.getByText(/wants to copy text/)).toBeVisible()
    expect(await writes()).toEqual([])
    expect(await clipboard()).toBe('operator clipboard')
    await page.getByRole('button', { name: 'Copy', exact: true }).click()
    await expect.poll(clipboard).toBe(requested)
    expect(await writes()).toEqual([requested])

    await configure('allow')
    await toClipboard(app, 'operator clipboard')
    await emit()
    await expect.poll(clipboard).toBe(requested)
    expect(await writes()).toEqual([requested, requested])
    await expect(page.getByText(/copied text/)).toBeVisible()
  } finally {
    await server.api.post('/api/settings', { data: { values: { 'terminal.program_clipboard': 'block' } } })
  }
})

test('a mouse selection writes to the clipboard only on explicit copy', async ({ win }) => {
  test.skip(WINDOWS, 'Unix shell and clipboard shortcut')
  const { app, page } = win
  await ready(page)
  const first = 'Alpha clipboard'
  const second = 'Bravo clipboard'
  await typeLine(page, `printf '%s\\n' '${first}' '${second}'`)
  await expectLine(page, second)
  const clipboard = () => app.evaluate(({ clipboard: system }) => system.readText())
  await page.evaluate(() => {
    const clipboard = navigator.clipboard
    const write = clipboard.writeText.bind(clipboard)
    const state = window as Window & { copyWrites?: string[] }
    state.copyWrites = []
    Object.defineProperty(clipboard, 'writeText', {
      value: (text: string) => { state.copyWrites!.push(text); return write(text) },
    })
  })
  const { start, end } = await page.locator('.aqua-screen .xterm-rows > div').evaluateAll((rows, labels) => {
    const point = (label: string, col: number) => {
      const row = rows.find((el) => el.textContent?.trim() === label)!
      const host = row.closest<HTMLElement>('[data-cols]')!
      const r = row.getBoundingClientRect()
      return { x: r.left + (col + 0.2) * r.width / Number(host.dataset.cols), y: r.top + r.height / 2 }
    }
    return { start: point(labels[0], 0), end: point(labels[1], labels[1].length) }
  }, [first, second] as const)
  const select = async () => {
    await toClipboard(app, 'original clipboard')
    await page.mouse.move(start.x, start.y)
    await page.mouse.down()
    await page.mouse.move(end.x, end.y, { steps: 16 })
    expect(await clipboard()).toBe('original clipboard')
    await page.mouse.up()
    expect(await clipboard()).toBe('original clipboard')
  }
  await select()
  await page.keyboard.press(MAC ? 'Meta+KeyC' : 'Control+Shift+KeyC')
  const selected = first + '\n' + second
  // tmux includes the trailing line break when the mouse ends on the blank
  // cell after the whole line. The browser selection can stop at the text.
  await expect.poll(async () => (await clipboard()).replace(/\n$/, '')).toBe(selected)
  const writes = await page.evaluate(() => (window as Window & { copyWrites?: string[] }).copyWrites ?? [])
  expect(writes.map((text) => text.replace(/\n$/, ''))).toEqual([selected])
  await select()
  await page.keyboard.down('Shift')
  await page.mouse.click(end.x, end.y, { button: 'right' })
  await page.keyboard.up('Shift')
  await page.getByRole('menuitem', { name: /^Copy / }).first().click()
  await expect.poll(async () => (await clipboard()).replace(/\n$/, '')).toBe(selected)
  const afterMenu = await page.evaluate(() => (window as Window & { copyWrites?: string[] }).copyWrites ?? [])
  expect(afterMenu.map((text) => text.replace(/\n$/, ''))).toEqual([selected, selected])
  await typeLine(page, echoCalc('typed-after-copy-', '6*7'))
  await expectLine(page, 'typed-after-copy-42')
  await input(page).focus()
  await recordInput(page)
  await page.keyboard.press('Control+KeyC')
  await expect.poll(async () => bare(await sent(page))).toBe('\x03')
})

test('typing after a mouse drag reaches the shell without copying', async ({ win, shell }) => {
  const { app, page } = win
  const tmux = (command: string, ...args: string[]) => {
    const [socket] = tmuxSockets(process.env.SP_DESKTOP_E2E_TMUX!)
    return execFileSync('tmux', ['-S', socket, command, '-t', `mk-${shell.id}`, ...args], { encoding: 'utf8' }).trim()
  }
  if (shell.backend === 'tmux') {
    // The mouse goes to tmux until the renderer learns that this is a shell.
    await page.route(`**/sessions/${shell.id}/pos`, (route) => route.fulfill({ status: 503 }))
    await page.route(`**/sessions/${shell.id}/capture*`, (route) => route.fulfill({ status: 503 }))
    await page.reload()
  }
  await ready(page)
  const first = 'First selected 42'
  const second = 'Second selected 42'
  await typeLine(page, echoCalc('First selected ', '6*7'))
  await expectLine(page, first)
  await typeLine(page, echoCalc('Second selected ', '6*7'))
  await expectLine(page, second)
  const rows = page.locator('.aqua-screen .xterm-rows > div')
  const start = await rows.getByText(first, { exact: true }).boundingBox()
  const end = await rows.getByText(second, { exact: true }).boundingBox()
  expect(start).not.toBeNull()
  expect(end).not.toBeNull()
  await toClipboard(app, 'clipboard before selection')
  await page.mouse.move(start!.x + 4, start!.y + start!.height / 2)
  await page.mouse.down()
  await page.mouse.move(end!.x + 40, end!.y + end!.height / 2, { steps: 12 })
  await page.mouse.up()
  if (shell.backend === 'tmux') {
    await expect.poll(() => tmux('display-message', '-p', '#{selection_present}')).toBe('1')
  } else {
    await expect(page.locator('.aqua-screen .xterm-selection > div').first()).toBeVisible()
  }
  const command = echoCalc('typed-after-selection-', '6*7')
  await page.keyboard.type(command)
  await page.keyboard.press('Enter')
  await expectLine(page, 'typed-after-selection-42')
  expect(await linesEqual(page, 'typed-after-selection-42')).toBe(1)
  expect(await app.evaluate(({ clipboard }) => clipboard.readText())).toBe('clipboard before selection')
  await expect(page.getByText('Copied', { exact: true })).toHaveCount(0)
})

test('Shift-click extends a selection across scrollback without an automatic copy', async ({ win, server }) => {
  const { app, page } = win
  await ready(page)
  const label = (n: number) => `Select row ${String(n).padStart(3, '0')}`
  const file = path.join(server.dir, 'shift-selection.txt')
  fs.writeFileSync(file, Array.from({ length: 170 }, (_, i) => label(i + 1)).join('\n') + '\n')
  await typeLine(page, printFile(file))
  await expectLine(page, label(170))

  const inventory = () => page.locator('.aqua-screen .xterm-rows > div').evaluateAll((rows) => rows.flatMap((row) => {
    const text = row.textContent?.trim() ?? ''
    if (!/^Select row \d{3}$/.test(text)) return []
    const el = row.closest('.xterm')!
    const area = el.closest('.aqua-screen')!
    if ((el.closest('.sp-reader') !== null) !== !!area.querySelector('.sp-reader[style*="visibility: visible"]')) return []
    const rect = row.getBoundingClientRect()
    const screen = area.getBoundingClientRect()
    const y = rect.y + rect.height / 2
    if (y < screen.top || y > screen.bottom) return []
    return [{ n: Number(text.slice(-3)), x: rect.x + 2, y, charWidth: rect.width / Number(el.closest<HTMLElement>('[data-cols]')!.dataset.cols) }]
  }))
  const clipboard = () => app.evaluate(({ clipboard: system }) => system.readText())
  const x11 = LINUX ? process.env.SP_E2E_X11_DISPLAY : undefined
  await toClipboard(app, 'previous clipboard')
  const primary = x11 ? primaryOwner(x11) : null

  const first = (await inventory()).find((row) => row.n === 164)!
  expect(first).toBeDefined()
  await page.mouse.move(first.x, first.y)
  await page.mouse.down()
  await page.mouse.move(first.x + first.charWidth * 4, first.y, { steps: 8 })
  await page.mouse.up()
  expect(await clipboard()).toBe('previous clipboard')
  if (x11) expect(primaryOwner(x11)).toBe(primary)

  await page.mouse.wheel(0, -1100)
  await expect.poll(async () => (await inventory()).some((row) => row.n < 130)).toBe(true)
  // Wait for the wheel animation to settle before targeting a rendered row.
  const earliest = async () => (await inventory()).find((row) => row.n < 130)
  let previous: Awaited<ReturnType<typeof earliest>>
  await expect.poll(async () => {
    const row = await earliest()
    const settled = !!row && row.n === previous?.n && Math.abs(row.y - previous.y) < 0.01
    previous = row
    return settled
  }).toBe(true)
  const last = previous!
  await page.keyboard.down('Shift')
  await page.mouse.click(last.x, last.y)
  await page.keyboard.up('Shift')
  expect(await clipboard()).toBe('previous clipboard')
  if (x11) expect(primaryOwner(x11)).toBe(primary)

  await page.keyboard.press(MAC ? 'Meta+KeyC' : 'Control+Shift+KeyC')
  const selected = Array.from({ length: 164 - last.n }, (_, i) => label(last.n + i)).join('\n')
  await expect.poll(async () => (await clipboard()).replace(/\r\n/g, '\n')).toBe(selected + '\n')
  if (x11) expect(primaryOwner(x11)).toBe(primary)
})

/** The middle of the terminal, where a click lands on the screen. */
async function middle(page: Page) {
  const b = (await page.locator('.aqua-screen .xterm-screen').boundingBox())!
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
}

/** byShell: the page sends the key (^V) and the shell's line editor pastes (PowerShell on Windows). */
type Way = { name: string; skip?: string; byShell?: boolean; paste: (page: Page, app: ElectronApplication, text: string) => Promise<void> }

const WAYS: Way[] = [
  {
    name: 'Ctrl+Shift+V',
    paste: async (page) => { await input(page).focus(); await page.keyboard.press('Control+Shift+KeyV') },
  },
  {
    // macOS's paste key is Cmd+V. On Windows Ctrl+V reaches PowerShell as ^V
    // and its line editor pastes. On Linux Ctrl+V is the shell's ^V (quote
    // the next key), as in GNOME Terminal: tested below.
    name: MAC ? 'Cmd+V' : 'Ctrl+V',
    byShell: WINDOWS,
    skip: LINUX ? 'on Linux Ctrl+V is ^V for the shell, as in GNOME Terminal (its own test below)' : undefined,
    paste: async (page) => { await input(page).focus(); await page.keyboard.press(MAC ? 'Meta+KeyV' : 'Control+KeyV') },
  },
  {
    name: 'Shift+Insert',
    skip: MAC ? 'macOS has no Insert key' : undefined,
    paste: async (page) => { await input(page).focus(); await page.keyboard.press('Shift+Insert') },
  },
  {
    name: 'the context menu',
    paste: async (page, app) => {
      // Headless Ozone opens the window at 420x240, too low for the menu.
      await fullSize(app, page)
      const m = await middle(page)
      await page.mouse.click(m.x, m.y, { button: 'right' })
      await page.getByRole('menuitem', { name: /^Paste/ }).click()
    },
  },
]

test.describe('paste', () => {
  WAYS.forEach((way, i) => {
    const n = i + 1
    test(`${way.name} pastes a line once`, async ({ win }) => {
      test.skip(!!way.skip, way.skip)
      const { app, page } = win
      await ready(page)
      const text = echoCalc(`pasted-${n}-`, '40+2')
      await toClipboard(app, text)
      await recordInput(page)
      await way.paste(page, app, text)
      if (way.byShell) {
        await expect.poll(() => sent(page)).toContain('\x16')
        await page.waitForTimeout(400)
        expect(bare(await sent(page))).toBe('\x16')
      } else {
        await sentOnce(page, text)
      }
      await page.keyboard.press('Enter')
      await ranOnce(page, `pasted-${n}-42`, n)
    })
  })

  test('a middle click pastes once, also right after a copy in the terminal', async ({ win, shell }) => {
    test.skip(!LINUX, 'the middle-click paste (the primary selection) is Linux only')
    test.skip(HEADLESS, 'Chromium\'s headless Ozone has no primary selection: a middle click pastes nothing there')
    const { app, page } = win
    await ready(page)
    const text = echoCalc('middle-', '40+2')
    // Seed the clipboard, primary selection and tmux buffer with the same
    // text. A middle click must paste one copy from the primary selection.
    await toClipboard(app, text, 'selection')
    await toClipboard(app, text)
    if (shell.backend === 'tmux') {
      for (const s of tmuxSockets(process.env.SP_DESKTOP_E2E_TMUX!)) execFileSync('tmux', ['-S', s, 'set-buffer', text], { stdio: 'ignore' })
    }
    await recordInput(page)
    const m = await middle(page)
    await page.mouse.click(m.x, m.y, { button: 'middle' })
    await sentOnce(page, text)
    await input(page).focus()
    await page.keyboard.press('Enter')
    await ranOnce(page, 'middle-42', 9)
  })

  test('Ctrl+V on Linux is ^V for the shell, not a paste', async ({ win }) => {
    test.skip(!LINUX, 'Linux only: on Windows Ctrl+V pastes, on macOS Cmd+V does (the tests above)')
    const { app, page } = win
    await ready(page)
    await toClipboard(app, echoCalc('never-', '1+1'))
    await recordInput(page)
    await input(page).focus()
    await page.keyboard.press('Control+KeyV')
    await expect.poll(() => sent(page)).toContain('\x16')
    await page.waitForTimeout(400)
    expect(bare(await sent(page))).toBe('\x16')
    // ^V quotes the next key: a Ctrl+U clears the line, then a typed command runs.
    await page.keyboard.press('Control+KeyU')
    await page.keyboard.press('Control+KeyU')
    await typeLine(page, echoCalc('typed-v-', '2+2'))
    await expectLine(page, 'typed-v-4')
  })

  test('three lines paste once, in order', async ({ win, server }) => {
    const { app, page } = win
    await ready(page)
    // Each line appends its name to a file: the screen interleaves the echo
    // of the pasted lines with their output, the file keeps the order.
    const file = path.join(server.dir, 'multi.txt')
    fs.rmSync(file, { force: true })
    const text = ['multi-a', 'multi-b', 'multi-c'].map((x) => `echo ${x} >> '${file}'`).join('\n')
    await toClipboard(app, text)
    await recordInput(page)
    await input(page).focus()
    await page.keyboard.press('Control+Shift+KeyV')
    await sentOnce(page, text)
    // The last line has no line end: it waits for Enter.
    await page.keyboard.press('Enter')
    const read = () => fs.existsSync(file) ? fs.readFileSync(file, 'utf-8').replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean) : []
    await expect.poll(read).toEqual(['multi-a', 'multi-b', 'multi-c'])
    await page.waitForTimeout(300)
    expect(read()).toEqual(['multi-a', 'multi-b', 'multi-c'])
    await typeLine(page, echoCalc('typed-m-', '3+3'))
    await expectLine(page, 'typed-m-6')
  })

  test('a 5 KB line pastes once and whole', async ({ win, server }) => {
    const { app, page } = win
    await ready(page)
    const body = 'long-' + Array.from({ length: 500 }, (_, i) => `${String(i).padStart(3, '0')}abcdef_`).join('').slice(0, 5000)
    const file = path.join(server.dir, 'long.txt')
    fs.rmSync(file, { force: true })
    if (WINDOWS) {
      // PowerShell reads a long line whole: the paste is a command that writes the text.
      const text = `[IO.File]::WriteAllText('${file}', '${body}'); echo "long-$(2+3)"`
      await toClipboard(app, text)
      await recordInput(page)
      await input(page).focus()
      await page.keyboard.press('Control+Shift+KeyV')
      await sentOnce(page, text)
      await page.keyboard.press('Enter')
      await expectLine(page, 'long-5', 20_000)
    } else {
      // A Unix terminal's line editor holds 4 KB (macOS: 1 KB): the shell
      // takes the bytes raw and keeps exactly as many as one copy has.
      // A second copy would be left over for the shell after.
      await typeLine(page, `stty -icanon; head -c ${body.length} > '${file}'; stty icanon; echo long-$((2+3))`)
      await page.waitForTimeout(500)
      await toClipboard(app, body)
      await recordInput(page)
      await input(page).focus()
      await page.keyboard.press('Control+Shift+KeyV')
      await sentOnce(page, body)
      // The pasted text is echoed with no line end: long-5 follows it on its line.
      await expectLine(page, /long-5$/, 20_000)
    }
    await expect.poll(() => fs.existsSync(file) ? fs.readFileSync(file, 'utf-8') : '').toBe(body)
    // Nothing left over: the next typed command runs alone. sh's line editor
    // clears its line on Ctrl+U first. PowerShell's (PSReadLine, Windows
    // mode) has no Ctrl+U: it types a literal ^U into the command, which
    // then fails as `^Uecho`. There the pasted line already ran on Enter,
    // so anything left over would glue to the typed command and break it.
    if (!WINDOWS) await page.keyboard.press('Control+KeyU')
    await typeLine(page, echoCalc('typed-l-', '4+4'))
    await expectLine(page, 'typed-l-8')
  })

  test('a command with spaces, quotes and a folder with a space in its name pastes once', async ({ win, server }) => {
    const { app, page } = win
    await ready(page)
    const dir = path.join(server.dir, 'a folder')
    fs.mkdirSync(dir, { recursive: true })
    // The operator's shape: cd "<path with a space>" && <command with quotes>.
    const text = WINDOWS
      ? `cd "${dir}" && echo "q-'$(2+3)'-$(Split-Path -Leaf $PWD)"`
      : `cd "${dir}" && echo "q-'$((2+3))'-$(basename "$PWD")"`
    await toClipboard(app, text)
    await recordInput(page)
    await input(page).focus()
    await page.keyboard.press('Control+Shift+KeyV')
    await sentOnce(page, text)
    await page.keyboard.press('Enter')
    await ranOnce(page, "q-'5'-a folder", 7)
  })
})
