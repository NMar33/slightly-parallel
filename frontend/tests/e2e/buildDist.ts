import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

/**
 * The backend serves frontend/dist, so the suite tests whatever was built
 * last. A run once tested a five-day-old build for a whole session. Here the
 * build is redone whenever a file under src/ (or index.html, the Vite config)
 * is newer than dist/index.html — a run always tests the code on disk.
 *
 * Playwright starts the webServer before globalSetup, and the server mounts
 * dist/ once, when it starts: on a fresh export of a commit (no dist/ yet)
 * every page of that run was {"detail":"Not Found"}. So both configs
 * (frontend/ and desktop/e2e, and the bench through it) call this in the
 * runner, before the server starts.
 *
 * global-setup.ts keeps the same check of its own: it is an ES module, and
 * one importing this file fails when desktop/e2e's CommonJS config has
 * already loaded it ("does not provide an export named"). No import.meta
 * here for the same reason.
 */
function newest(dir: string): number {
  let t = 0
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    t = Math.max(t, e.isDirectory() ? newest(p) : fs.statSync(p).mtimeMs)
  }
  return t
}

/** Build frontend/ (the folder given) when its source is newer than dist/. */
export function buildIfStale(frontend: string): void {
  const built = path.join(frontend, 'dist', 'index.html')
  const builtAt = fs.existsSync(built) ? fs.statSync(built).mtimeMs : 0
  const source = Math.max(newest(path.join(frontend, 'src')),
    ...['index.html', 'vite.config.ts'].map((f) => fs.statSync(path.join(frontend, f)).mtimeMs))
  if (source <= builtAt) return
  if (process.env.SP_E2E_NO_BUILD === '1') {
    throw new Error(`SP_E2E_NO_BUILD requires a current build in ${built}`)
  }
  execSync('npm run build', { cwd: frontend, stdio: 'inherit' })
}
