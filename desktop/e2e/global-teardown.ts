import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { stopDisplay } from './global-setup'
import { tmuxSockets } from './sockets'

/**
 * After the suite: the hidden display stops (global-setup.ts), the
 * sandbox's tmux server stops (its sockets are in its own
 * TMUX_TMPDIR, nowhere else) and the copy goes. Playwright stops the
 * web server itself; each Electron window is closed by its own test.
 */
export default function globalTeardown(): void {
  const root = process.env.SP_DESKTOP_E2E_ROOT
  const tmux = process.env.SP_DESKTOP_E2E_TMUX
  if (process.env.SP_E2E_WAYLAND) stopDisplay(process.env.SP_E2E_DISPLAY_PID, process.env.SP_E2E_WAYLAND)
  if (!root || !path.basename(root).startsWith('sp-desktop-e2e-')) return
  for (const sock of tmux ? tmuxSockets(tmux) : []) {
    try { execFileSync('tmux', ['-S', sock, 'kill-server'], { stdio: 'ignore', timeout: 5000 }) } catch { /* none running */ }
  }
  if (process.env.SP_DESKTOP_E2E_KEEP) return
  for (const dir of [root, tmux]) {
    try { if (dir) fs.rmSync(dir, { recursive: true, force: true }) } catch { /* the OS cleans tmp */ }
  }
}
