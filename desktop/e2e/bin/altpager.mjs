// A full-screen pager on the alternate screen, the way vim, less or htop
// sit there: no history of its own in the terminal, the view moved a line
// per arrow key (or wheel report, when it asks for the mouse). Runs on
// every system the suite does (node is there), unlike less.
//
//   node altpager.mjs <file> [--mouse]
//
// --mouse: asks for SGR mouse reports (as vim with `mouse=a` does) and
// scrolls a line per wheel report; without it the terminal turns the wheel
// into arrow keys. q quits and leaves the alternate screen.
import fs from 'node:fs'

const file = process.argv[2]
const mouse = process.argv.includes('--mouse')
const lines = fs.readFileSync(file, 'utf-8').split(/\r?\n/).filter((l, i, a) => i < a.length - 1 || l)
const out = process.stdout
let top = Math.max(0, lines.length - (out.rows || 24))

const draw = () => {
  const rows = out.rows || 24
  top = Math.max(0, Math.min(top, lines.length - rows))
  let s = '\x1b[H'
  for (let r = 0; r < rows; r++) s += `\x1b[2K${(lines[top + r] ?? '').slice(0, (out.columns || 80) - 1)}${r < rows - 1 ? '\r\n' : ''}`
  out.write(s)
}

out.write('\x1b[?1049h\x1b[?25l' + (mouse ? '\x1b[?1000h\x1b[?1006h' : ''))
if (process.stdin.isTTY) process.stdin.setRawMode(true)
process.stdin.resume()
draw()
out.on('resize', draw)

const quit = () => {
  out.write((mouse ? '\x1b[?1006l\x1b[?1000l' : '') + '\x1b[?25h\x1b[?1049l')
  process.exit(0)
}

process.stdin.on('data', (buf) => {
  const s = buf.toString('latin1')
  if (s.includes('q') && !s.includes('\x1b[<')) return quit()
  // Arrow keys (normal and application cursor mode) and SGR wheel reports.
  const up = (s.match(/\x1b[[O]A/g) ?? []).length + (s.match(/\x1b\[<64;\d+;\d+M/g) ?? []).length
  const down = (s.match(/\x1b[[O]B/g) ?? []).length + (s.match(/\x1b\[<65;\d+;\d+M/g) ?? []).length
  if (up || down) { top += down - up; draw() }
})
