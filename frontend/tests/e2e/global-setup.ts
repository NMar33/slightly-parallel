import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * The backend serves frontend/dist, so the suite tests whatever was built
 * last. A run once tested a five-day-old build for a whole session. Here the
 * build is redone whenever a file under src/ (or index.html, the Vite config)
 * is newer than dist/index.html — a run always tests the code on disk.
 * Skipped when the suite points at a running server (SP_E2E_URL).
 */
const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../..')

function newest(dir: string): number {
  let t = 0
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    t = Math.max(t, e.isDirectory() ? newest(p) : fs.statSync(p).mtimeMs)
  }
  return t
}

export default function globalSetup(): void {
  if (process.env.SP_E2E_URL) return
  const built = path.join(root, 'dist', 'index.html')
  const builtAt = fs.existsSync(built) ? fs.statSync(built).mtimeMs : 0
  const source = Math.max(newest(path.join(root, 'src')),
    ...['index.html', 'vite.config.ts'].map((f) => fs.statSync(path.join(root, f)).mtimeMs))
  if (source > builtAt) execSync('npm run build', { cwd: root, stdio: 'inherit' })
}
