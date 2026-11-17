import { execFileSync, spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

/**
 * Before the suite, after the frontend's own setup (playwright.config.ts:
 * frontend/dist rebuilt when its source is newer), on a Linux laptop: a display
 * of the suite's own that nobody sees, so no test window comes up on the
 * operator's screen and no key typed there lands in one.
 *
 * The display is GNOME Shell without a screen: `gnome-shell --headless
 * --wayland --virtual-monitor`, in a D-Bus session of its own. Its graphics
 * are the machine's real ones (GPU compositing is on, so the speed guard
 * measures what the operator gets). Each run has its own display name; the
 * teardown stops that gnome-shell by its pid — never by name, the operator's
 * desktop is a gnome-shell too.
 *
 * SP_E2E_VISIBLE=1: the real screen instead (to watch a test). Without
 * gnome-shell (CI) the display is whatever the run was given (xvfb-run);
 * SP_E2E_HEADLESS=1 is Chromium's headless Ozone, no display at all.
 */
export default async function globalSetup(): Promise<void> {
  if (process.platform !== 'linux' || process.env.SP_E2E_VISIBLE === '1' || process.env.SP_E2E_HEADLESS === '1') return
  const shell = which('gnome-shell')
  const dbus = which('dbus-run-session')
  const runtime = process.env.XDG_RUNTIME_DIR
  if (!shell || !dbus || !runtime) return
  const name = `sp-e2e-${process.pid}`
  const sock = path.join(runtime, name)
  const runner = spawn(dbus, ['--', shell, '--headless', '--wayland', '--no-x11', `--wayland-display=${name}`, '--virtual-monitor', '1600x1000'], {
    stdio: 'ignore',
    env: { ...process.env, WAYLAND_DISPLAY: '', DISPLAY: '' },
  })
  const stop = () => stopDisplay(runner.pid, name)
  process.once('exit', stop)
  const deadline = Date.now() + 30_000
  while (!fs.existsSync(sock)) {
    if (runner.exitCode !== null || Date.now() > deadline) {
      stop()
      throw new Error(`the hidden display ${name} did not come up (gnome-shell --headless); SP_E2E_VISIBLE=1 runs on the screen`)
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  process.env.SP_E2E_WAYLAND = name
  process.env.SP_E2E_DISPLAY_PID = String(runner.pid)
}

function which(cmd: string): string {
  try { return execFileSync('which', [cmd], { encoding: 'utf-8' }).trim() } catch { return '' }
}

/** Every process under `pid`, from /proc (Linux). */
function descendants(pid: number): number[] {
  const out: number[] = []
  const walk = (p: number) => {
    let kids: number[] = []
    try {
      for (const t of fs.readdirSync(`/proc/${p}/task`)) {
        kids = kids.concat(fs.readFileSync(`/proc/${p}/task/${t}/children`, 'utf-8').split(/\s+/).filter(Boolean).map(Number))
      }
    } catch { /* gone */ }
    for (const k of kids) { out.push(k); walk(k) }
  }
  walk(pid)
  return out
}

const cmdline = (pid: number) => { try { return fs.readFileSync(`/proc/${pid}/cmdline`, 'utf-8').split('\0') } catch { return [] } }

/** Stop the display this run started: its gnome-shell (a child of our
 *  dbus-run-session with our display name: killing dbus-run-session alone
 *  leaves it running), then the rest of that session, then its socket. */
export function stopDisplay(pidOf: number | string | undefined, name: string): void {
  const pid = Number(pidOf)
  if (!pid) return
  const tree = descendants(pid)
  const shells = tree.filter((p) => cmdline(p).includes(`--wayland-display=${name}`))
  for (const p of [...shells, ...tree.filter((p) => !shells.includes(p)), pid]) {
    try { process.kill(p, 'SIGTERM') } catch { /* already gone */ }
  }
  const until = Date.now() + 3000
  while (Date.now() < until && shells.some((p) => fs.existsSync(`/proc/${p}`))) { /* wait a moment */ execFileSync('sleep', ['0.1']) }
  for (const p of shells) { try { process.kill(p, 'SIGKILL') } catch { /* gone */ } }
  const runtime = process.env.XDG_RUNTIME_DIR
  if (runtime) for (const f of [name, `${name}.lock`]) { try { fs.rmSync(path.join(runtime, f), { force: true }) } catch { /* gone */ } }
}
