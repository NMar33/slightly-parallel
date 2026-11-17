import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { defineConfig } from '@playwright/test'

/**
 * The terminal window's end-to-end suite: the real Electron window of
 * desktop/ against a sandbox server of its own. Run it with `npm run e2e`
 * in desktop/ (e2e/run.mjs lends it the frontend's Playwright).
 *
 * The server is the one the web suite starts (frontend/playwright.config.ts):
 * uvicorn on its own port, on a throwaway copy of fixtures/, SP_SANDBOX=1,
 * a plain /bin/sh for its terminals. Its tmux server is kept apart too:
 * TMUX_TMPDIR is a folder of its own, and global-teardown.ts stops whatever
 * tmux server runs there. Never the operator's server or data root.
 *
 * The specs run one at a time: they share the server's terminals, and each
 * opens real windows on the desktop.
 */

const REPO = path.resolve(__dirname, '..', '..')
const PORT = Number(process.env.SP_DESKTOP_E2E_PORT) || 8131

/** The data root: made by the runner once, handed to the workers by env. */
function dataRoot(): string {
  if (process.env.SP_DESKTOP_E2E_ROOT) return process.env.SP_DESKTOP_E2E_ROOT
  // realpath: macOS's tmp is a symlink, and the server resolves its root.
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sp-desktop-e2e-')))
  // The fixtures without a token of their own: the server makes a fresh one.
  fs.cpSync(path.join(REPO, 'fixtures'), path.join(root, 'data'), {
    recursive: true, filter: (src) => path.basename(src) !== 'operator.token',
  })
  fs.mkdirSync(path.join(root, 'work'))
  // SP_E2E_KEEP=plain: every terminal is a pty the server holds, as on
  // Windows (no tmux there), so most of what Windows does runs here too.
  if (process.env.SP_E2E_KEEP === 'plain') {
    fs.writeFileSync(path.join(root, 'data', 'settings.json'), JSON.stringify({ terminal: { keep: 'plain' } }))
  }
  // tmux's sockets: a short path of their own (macOS's tmp is long, and a
  // socket's path may not pass 104 bytes there).
  const tmux = process.platform === 'win32' ? path.join(root, 'tmux') : fs.mkdtempSync('/tmp/sp-e2e-tmux-')
  fs.mkdirSync(tmux, { recursive: true })
  process.env.SP_DESKTOP_E2E_ROOT = root
  process.env.SP_DESKTOP_E2E_TMUX = tmux
  return root
}

const ROOT = dataRoot()
const PYTHON = process.platform === 'win32'
  ? path.join(REPO, 'backend', '.venv', 'Scripts', 'python.exe')
  : path.join(REPO, 'backend', '.venv', 'bin', 'python')
process.env.SP_DESKTOP_E2E_URL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts$/,
  // The frontend's own (frontend/dist rebuilt when its source is newer),
  // then on Linux a hidden display for the windows (global-setup.ts).
  globalSetup: [path.join(REPO, 'frontend', 'tests', 'e2e', 'global-setup.ts'), './global-setup.ts'],
  globalTeardown: './global-teardown.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  failOnFlakyTests: !!process.env.CI,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  // Traces and screenshots of a failed test stay after the copy is gone.
  outputDir: path.join(__dirname, 'test-results'),
  webServer: {
    command: `"${PYTHON}" -m uvicorn backend.server:app --host 127.0.0.1 --port ${PORT}`,
    cwd: path.join(REPO, 'backend'),
    env: {
      ...process.env as Record<string, string>,
      SP_DATA_ROOT: path.join(ROOT, 'data'),
      SP_BACKUP_ROOT: path.join(ROOT, 'backups'),
      SP_PORT: String(PORT),
      SP_SANDBOX: '1',
      // The window is a terminal: on for this server whatever the settings say.
      SP_ENABLE_TERMINAL: '1',
      // A plain shell, never the operator's interactive bash (its rc may
      // prompt for sudo).
      SHELL: '/bin/sh',
      // Its own tmux sockets, inside the copy: the teardown finds them there.
      TMUX_TMPDIR: process.env.SP_DESKTOP_E2E_TMUX!,
    },
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
