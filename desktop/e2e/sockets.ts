import fs from 'node:fs'
import path from 'node:path'

/** The sandbox's tmux sockets: TMUX_TMPDIR/tmux-<uid>/<socket>. */
export function tmuxSockets(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir).flatMap((d) => {
    const sub = path.join(dir, d)
    return fs.statSync(sub).isDirectory() ? fs.readdirSync(sub).map((s) => path.join(sub, s)) : []
  })
}
