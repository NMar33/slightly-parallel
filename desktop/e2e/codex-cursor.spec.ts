import { spawn } from 'node:child_process'
import { once } from 'node:events'
import fs from 'node:fs'
import path from 'node:path'
import { createInterface } from 'node:readline'
import type { Page } from '@playwright/test'
import { test, expect, PROJECT, WINDOWS, fullSize, lines, ready, typeLine } from './fixtures'

const python = path.resolve(__dirname, '../../backend/.venv/bin/python')
const stub = path.resolve(__dirname, '../../scripts/ci/stub_responses.py')
const quote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'"
const input = (page: Page) => page.locator('.aqua-screen .xterm-helper-textarea')
const cursor = (page: Page) => page.locator('.aqua-screen .xterm-rows .xterm-cursor')
async function drawnCursor(page: Page) {
  return cursor(page).evaluateAll((cells) => cells.flatMap((cell) => {
    const parent = cell.parentElement
    const viewport = cell.closest('.xterm')?.querySelector('.xterm-viewport')
    if (!parent || !viewport) return [] // xterm replaced the row between selection and evaluation
    return [{
      row: parent.textContent, cell: cell.textContent, className: cell.className,
      underneath: getComputedStyle(cell.nextElementSibling ?? parent).backgroundColor,
      ground: getComputedStyle(viewport).backgroundColor,
      background: getComputedStyle(cell).backgroundColor,
    }]
  }))
}

function luminance(css: string): number {
  const channels = css.match(/[\d.]+/g)?.slice(0, 3).map((value) => {
    const x = Number(value) / 255
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
  })
  return channels ? channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722 : 0
}

function visibleBlock(c: Awaited<ReturnType<typeof drawnCursor>>[number]): boolean {
  const fg = luminance(c.background)
  const bg = luminance(c.underneath === 'rgba(0, 0, 0, 0)' ? c.ground : c.underneath)
  return c.className.includes('xterm-cursor-block') && (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05) >= 3
}

test('a steady block cursor paints over a cell with a true-color background', async ({ win }) => {
  test.skip(WINDOWS, 'the fixture uses a Unix shell')
  const { page } = win
  await ready(page)
  await typeLine(page, String.raw`printf '\033[?25h\033[2 q\033[48;2;14;16;19mRGB cursor  \033[D'; sleep 20`)
  await expect.poll(() => drawnCursor(page)).toEqual(expect.arrayContaining([
    expect.objectContaining({ row: expect.stringContaining('RGB cursor'), className: expect.stringContaining('xterm-cursor-block') }),
  ]))
  await expect.poll(async () => (await drawnCursor(page)).some((c) => c.row?.includes('RGB cursor') && visibleBlock(c))).toBe(true)
})

test('real Codex shows the insertion cursor, receives input, and keeps focus after switching tabs', async ({ win, shell, server }) => {
  test.skip(WINDOWS || process.env.SP_E2E_REAL_CODEX !== '1', 'opt in with Codex CLI installed on Unix')
  const { page, app } = win
  const selectScheme = async (scheme: string, scope: string) => {
    const response = await server.api.post('/api/settings', {
      data: { values: { 'terminal.scheme': scheme, 'terminal.scheme_scope': scope } },
    })
    expect(response.ok(), await response.text()).toBe(true)
  }
  const configDir = fs.mkdtempSync(path.join(server.dir, 'codex-home-'))
  const log = path.join(configDir, 'requests.jsonl')
  const provider = spawn(python, ['-u', '-c', [
    'import runpy, sys',
    "server = runpy.run_path(sys.argv[1])['serve'](0, sys.argv[2])",
    'print(server.server_port)',
    'server.serve_forever()',
  ].join('\n'), stub, log], { cwd: path.dirname(stub), stdio: ['ignore', 'pipe', 'inherit'] })
  const stream = createInterface({ input: provider.stdout })
  try {
    const port = Number(await Promise.race([
      once(stream, 'line').then(([line]) => line),
      once(provider, 'exit').then(([code]) => { throw new Error(`model stub exited with ${code}`) }),
    ]))
    expect(port).toBeGreaterThan(0)
    fs.writeFileSync(path.join(configDir, 'config.toml'), [
      'model = "stub-model"',
      'model_provider = "stub"',
      'check_for_update_on_startup = false',
      'web_search = "disabled"',
      '[analytics]',
      'enabled = false',
      '[feedback]',
      'enabled = false',
      '[tui]',
      'animations = false',
      'show_tooltips = false',
      '[model_providers.stub]',
      'name = "stub"',
      `base_url = "http://127.0.0.1:${port}/v1"`,
      'wire_api = "responses"',
      `[projects.${JSON.stringify(server.dir)}]`,
      'trust_level = "trusted"',
    ].join('\n') + '\n')
    await selectScheme('catppuccin-latte', 'window')
    const response = await server.api.post('/api/terminal/sessions', {
      data: { kind: 'shell', project: PROJECT, label: 'codex-cursor', command: `env -u OPENAI_API_KEY -u CODEX_API_KEY HOME=${quote(configDir)} CODEX_HOME=${quote(configDir)} codex 'Start the terminal probe.'` },
    })
    expect(response.ok(), await response.text()).toBe(true)
    const { session } = await response.json() as { session: { id: string } }
    const sent: string[] = []
    page.on('websocket', (socket) => {
      if (!new URL(socket.url()).pathname.startsWith('/ws/terminal/')) return
      socket.on('framesent', ({ payload }) => {
        if (typeof payload !== 'string') return
        try {
          const frame = JSON.parse(payload) as { type: string; data?: string }
          if (frame.type === 'input' && frame.data) sent.push(frame.data)
        } catch { /* a control frame */ }
      })
    })
    await page.reload()
    await fullSize(app, page)
    await expect(page.locator('.aq[data-scheme="catppuccin-latte"]')).toHaveCount(1)
    // Codex updates the tab's title after the first turn.
    const codex = page.locator(`[data-tab="${session.id}"]`).getByRole('tab')
    await codex.click()
    await expect(input(page)).toBeFocused()
    try {
      // Codex can already draw the composer while its startup input probes are still active.
      // The response to the initial prompt proves the interactive session has started.
      const replies = () => lines(page).then((rows) => rows.filter((row) => row.includes('Stub reply.')).length)
      await expect.poll(replies, { timeout: 20_000 }).toBe(1)
      await expect.poll(async () => (await drawnCursor(page)).some((c) => c.row?.includes('›') && visibleBlock(c))).toBe(true)
      await expect(input(page)).toBeFocused()
      await page.keyboard.type('cursor probe', { delay: 25 })
      await expect.poll(() => lines(page)).toEqual(expect.arrayContaining([expect.stringContaining('› cursor probe')]))
      await page.keyboard.press('ArrowLeft')
      await expect.poll(async () => (await drawnCursor(page)).some((c) => c.row?.includes('› cursor probe') && c.cell === 'e' && visibleBlock(c))).toBe(true)
      await page.keyboard.insertText('я')
      await app.evaluate(({ clipboard }, text) => clipboard.writeText(text), '123')
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+KeyV' : 'Control+Shift+KeyV')
      const draft = '› cursor probя123e'
      await expect.poll(() => lines(page)).toEqual(expect.arrayContaining([expect.stringContaining(draft)]))
      await page.getByRole('tab', { name: new RegExp(`^${shell.label}`) }).click()
      await codex.click()
      await expect(input(page)).toBeFocused()
      await expect.poll(async () => (await drawnCursor(page)).some((c) => c.row?.includes(draft) && visibleBlock(c))).toBe(true)
      await page.keyboard.press('Enter')
      await expect.poll(replies, { timeout: 20_000 }).toBe(2)
      expect(sent.filter((key) => key.charCodeAt(0) === 13)).toEqual([String.fromCharCode(13)])
      await expect.poll(async () => (await drawnCursor(page)).some((c) => c.row?.includes('›') && visibleBlock(c))).toBe(true)

      const screen = page.locator('.aqua-screen .xterm-screen').filter({ visible: true })
      const prompt = Array.from({ length: 64 }, (_, i) => `scroll-probe-${String(i).padStart(2, '0')}`).join('\n')
      await app.evaluate(({ clipboard }, text) => clipboard.writeText(text), prompt)
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+KeyV' : 'Control+Shift+KeyV')
      await page.keyboard.press('Enter')
      // The echoed lines arrive before the model reply and the idle composer.
      // Take the exact bottom snapshot only once that turn has finished drawing.
      await expect.poll(async () => {
        const rows = await lines(page)
        const end = rows.findIndex((row) => row.includes('scroll-probe-63'))
        return end >= 0 && rows.slice(end + 1).some((row) => row.includes('Stub reply.'))
          && rows.slice(end + 1).some((row) => /Worked for .* • /.test(row))
          && rows.some((row) => row.includes('› Ask Codex to do anything'))
      }).toBe(true)
      const bottom = await lines(page)
      const box = (await screen.boundingBox())!
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.mouse.wheel(0, -900)
      await expect.poll(async () => (await lines(page)).some((row) => row.includes('scroll-probe-10'))).toBe(true)
      await page.mouse.wheel(0, 900)
      await expect.poll(() => lines(page)).toEqual(bottom)
      // A touchpad sends many deltas smaller than a character cell, including
      // diagonal motion. Verify both directions through the real TUI.
      const firstMarker = async () => Math.min(...(await lines(page)).flatMap((row) =>
        Array.from(row.matchAll(/scroll-probe-(\d+)/g), (match) => Number(match[1]))))
      const lastMarker = await firstMarker()
      for (let i = 0; i < 42; i++) await page.mouse.wheel(1, -(2 + i % 5))
      await expect.poll(firstMarker).toBeLessThan(lastMarker)
      for (let i = 0; i < 48; i++) await page.mouse.wheel(-1, 2 + i % 5)
      await expect.poll(() => lines(page)).toEqual(bottom)
    } catch (error) {
      console.log('screen', (await lines(page)).join('\n'), 'cursor', JSON.stringify(await drawnCursor(page)), 'input frames', JSON.stringify(sent))
      await page.screenshot({ path: test.info().outputPath('codex.png') })
      throw error
    }
  } finally {
    stream.close()
    provider.kill()
    await selectScheme('sp-now', 'terminal')
  }
})
