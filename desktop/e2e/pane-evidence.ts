import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'
import type { APIRequestContext, Page, TestInfo } from '@playwright/test'

const MAX_RECORDS = 400

// Runs in the renderer. Observe real input and layout without changing how the
// application handles it. Sample only around actions that can close the pane.
function observeLayout() {
  const records: object[] = []
  Object.defineProperty(window, '__spPaneEvidence', { value: records, configurable: true })
  const put = (record: object) => {
    records.push({ at: performance.timeOrigin + performance.now(), ...record })
    if (records.length > 400) records.shift()
  }
  const size = (element: Element | null) => {
    const rect = element?.getBoundingClientRect()
    return rect && [rect.x, rect.y, rect.width, rect.height]
  }
  const focus = () => document.activeElement?.closest('.aqua-screen') ? 'left'
    : document.activeElement?.closest('.aqua-right-pane') ? 'right'
      : document.activeElement?.getAttribute('aria-label') ?? document.activeElement?.tagName
  let until = 0
  let scheduled = false
  let previous = ''
  const sample = () => {
    const frame = {
      kind: 'layout', focus: focus(), window: [innerWidth, innerHeight, outerWidth, outerHeight],
      pixelRatio: devicePixelRatio,
      inspector: size(document.querySelector('aside[aria-label="Right sidebar"]')),
      panes: [...document.querySelectorAll('.aqua-screen, .aqua-right-pane')].map((pane) => {
        const grid = pane.querySelector<HTMLElement>('[data-cols][data-rows]')
        const rows = [...pane.querySelectorAll('.xterm-rows > div')]
        return {
          side: pane.classList.contains('aqua-screen') ? 'left' : 'right',
          host: size(pane), screen: size(pane.querySelector('.xterm-screen')),
          grid: [grid?.dataset.cols, grid?.dataset.rows],
          lines: rows.map((row) => row.textContent?.trimEnd()).filter(Boolean).slice(-8),
        }
      }),
    }
    const signature = JSON.stringify(frame)
    if (signature !== previous) put(frame)
    previous = signature
    scheduled = performance.now() < until
    if (scheduled) requestAnimationFrame(sample)
  }
  const watch = () => {
    until = performance.now() + 500
    if (scheduled) return
    scheduled = true
    requestAnimationFrame(sample)
  }
  window.addEventListener('resize', () => { put({ kind: 'resize' }); watch() })
  window.addEventListener('focusin', () => { put({ kind: 'focus', target: focus() }); watch() }, true)
  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.code !== 'BracketRight') return
    put({ kind: 'key', key: event.key, alt: event.altKey, target: focus() })
    watch()
  }, true)
  window.addEventListener('mousedown', (event) => {
    const target = (event.target as Element | null)?.closest('button, .xterm-screen')
    put({ kind: 'mouse', button: event.button, x: event.clientX, y: event.clientY,
      hit: target?.getAttribute('aria-label') ?? target?.className, focus: focus() })
    watch()
  }, true)
}

const run = promisify(execFile)
const tapPane = `import shlex, sys
from pathlib import Path
from backend.termlib import PREFIX, tmux
root, target, output = sys.argv[1:]
command = ["pipe-pane", "-t", PREFIX + target]
if output:
    command += ["-O", "cat > " + shlex.quote(output)]
r = tmux(Path(root), *command, timeout=3)
if r.returncode:
    sys.exit(r.stderr or r.returncode)
`

async function pipeShellOutput(shell: { id: string; backend: string }, testInfo: TestInfo) {
  if (shell.backend !== 'tmux' || !testInfo.file.endsWith('tab-split.spec.ts')) return async () => ''
  const cwd = path.resolve(__dirname, '..', '..', 'backend')
  const python = path.join(cwd, '.venv', 'bin', 'python')
  const root = path.join(process.env.SP_DESKTOP_E2E_ROOT!, 'data')
  const output = path.join(process.env.SP_DESKTOP_E2E_ROOT!, `pane-${shell.id}.log`)
  const pipe = (file: string) => run(python, ['-c', tapPane, root, shell.id, file],
    { cwd, env: { ...process.env, TMUX_TMPDIR: process.env.SP_DESKTOP_E2E_TMUX }, timeout: 3500 })
  try { await pipe(output) } catch (error) { return async () => String(error) }
  return async () => {
    try {
      await pipe('')
      return String(await readFile(output, 'utf8')).slice(-16000)
    } catch (error) {
      return String(error)
    }
  }
}

export async function recordPaneEvidence(page: Page, api: APIRequestContext,
                                         shell: { id: string; backend: string }, testInfo: TestInfo) {
  if (process.env.SP_E2E_PANE_EVIDENCE !== '1') return async () => {}
  // CDP watches the socket writer and reader without wrapping WebSocket.
  // Keep only socket paths and frames from these disposable shell tests.
  const closePipe = await pipeShellOutput(shell, testInfo)
  const network = await page.context().newCDPSession(page)
  const events: object[] = []
  const paths = new Map<string, string>()
  const put = (event: object) => {
    events.push({ at: Date.now(), ...event })
    if (events.length > MAX_RECORDS) events.shift()
  }
  network.on('Network.webSocketCreated', ({ requestId, url }) => {
    const pathname = new URL(url).pathname
    paths.set(requestId, pathname)
    put({ kind: 'socket', requestId, pathname })
  })
  for (const [event, direction] of [
    ['Network.webSocketFrameSent', 'send'], ['Network.webSocketFrameReceived', 'receive'],
  ] as const) {
    network.on(event, ({ requestId, response }) => {
      const pathname = paths.get(requestId)
      if (pathname && !pathname.startsWith('/ws/terminal/')) return
      const content = response.opcode === 2
        ? Buffer.from(response.payloadData, 'base64').toString('utf8') : response.payloadData
      put({ kind: 'frame', requestId, pathname, direction, data: content.slice(-800) })
    })
  }
  await network.send('Network.enable')
  await page.addInitScript(observeLayout)
  await page.evaluate(observeLayout)

  return async () => {
    const [layout, pane, shellOutput] = await Promise.allSettled([
      page.evaluate(() => Reflect.get(window, '__spPaneEvidence') as object[]),
      shell.backend === 'tmux'
        ? api.post(`/api/terminal/sessions/${shell.id}/capture`, {
          data: { mode: 'screen' }, timeout: 3000,
        }).then(async (response) => response.ok() ? (await response.json()).text : `HTTP ${response.status()}`)
        : Promise.resolve('This session has no tmux pane.'),
      closePipe(),
    ])
    await testInfo.attach('pane evidence', {
      body: JSON.stringify({ browser: layout.status === 'fulfilled' ? layout.value : String(layout.reason),
        socket: events, pane: pane.status === 'fulfilled' ? pane.value : String(pane.reason),
        shellOutput: shellOutput.status === 'fulfilled' ? shellOutput.value : String(shellOutput.reason) }, null, 2),
      contentType: 'application/json',
    })
    await network.detach().catch(() => {})
  }
}
