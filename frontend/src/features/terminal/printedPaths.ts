/**
 * Paths a terminal printed — `src/app.ts:42`, `./a/b.py:10:5`, `~/x/y.md`,
 * `/abs/file.go` — found in one line of text, so each can become a link
 * that opens the file at that line.
 *
 * What counts: something with a folder in it (`a/b.ts`), or a bare file
 * name WITH a line (`app.ts:12`). A bare `README.md` or a version like
 * `v1.2` is left alone, and so is anything inside a URL (the web-links
 * addon owns those). The server decides whether the file exists.
 */

export interface PrintedPath {
  /** The matched text, as printed (with its :line:col). */
  text: string
  path: string
  line: number
  col: number
  /** 0-based index in the line where the match starts, and its length. */
  start: number
  length: number
}

// A path: optional ~/ ./ ../ or /, folders, then a name with a letter-led
// extension; then optional :line and :col.
const PATH = /(?:~\/|\.{1,2}\/|\/)?(?:[\w.@+-]+\/)*[\w@+-][\w.@+-]*\.[A-Za-z][A-Za-z0-9]{0,7}(?::(\d+)(?::(\d+))?)?/g

const URL_RE = /[a-z][\w+.-]*:\/\/\S+/gi

export function findPaths(text: string): PrintedPath[] {
  const out: PrintedPath[] = []
  // Inside a URL (https://host/a/b.js): the web-links addon's, not ours.
  const urls = [...text.matchAll(URL_RE)].map((u) => [u.index ?? 0, (u.index ?? 0) + u[0].length] as const)
  for (const m of text.matchAll(PATH)) {
    const whole = m[0]
    const at = m.index ?? 0
    if (urls.some(([a, b]) => at < b && at + whole.length > a)) continue
    const line = m[1] ? Number(m[1]) : 0
    const col = m[2] ? Number(m[2]) : 0
    const path = whole.replace(/(?::\d+){1,2}$/, '')
    const foldered = path.includes('/')
    if (!foldered && !line) continue
    out.push({ text: whole, path, line, col, start: at, length: whole.length })
  }
  return out
}
