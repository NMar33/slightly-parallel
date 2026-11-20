/**
 * The commands in an agent's reply, to copy or paste them from the terminal
 * (tk_29b870f1, the operator: «хорошо бы иметь возможность копировать
 * команды, как и ссылки»).
 *
 * Claude Code draws markdown: a fenced block loses its fence and a code span
 * its backticks, so the screen alone cannot tell a command from prose. The
 * commands are read from the RECORDED reply (the agent's markdown) and then
 * found on the screen in the rows of that reply, by the same letters-and-
 * digits key the message menu matches with (match.ts):
 *
 * - a fenced block (``` or ~~~) with no language or a shell's (sh, bash,
 *   console …) is one command, kept whole: its lines, the fence and the
 *   language gone, the common indentation gone; a block with no language
 *   counts only when its first line reads like a command; one in another
 *   language (ts, json …) is code, not a command;
 * - a code span counts only when it reads like a command: a known program
 *   (or ./x, sudo, a script with arguments, VAR=1 before them) and at least
 *   one argument. `README.md`, `true`, `tk_…`, a web address are not.
 * - a `$ ` or `! ` before the command is the prompt, not the command: it
 *   goes when every line has it.
 *
 * Where no reply is matched (a shell, a narration, an unrecorded chat), a
 * row that starts with `$ ` or `! ` and then a program is a command.
 */

import { blocksOf, messageAt, type Record } from './match'

export interface Command {
  /** What «Copy the command» copies: no prompt, no fence, lines joined with \n. */
  text: string
  kind: 'block' | 'inline' | 'line'
}

/* ------------------------------------------------------------ the markdown */

/** Languages a fence names for a shell session. A fence with no language is judged by its first line. */
const SHELL_LANGS = new Set(['sh', 'bash', 'shell', 'zsh', 'fish', 'console', 'shellsession', 'shell-session', 'terminal', 'ksh', 'dash',
  'powershell', 'ps1', 'pwsh', 'cmd', 'bat', 'batch'])
const PLAIN_LANGS = new Set(['', 'text', 'txt', 'plain', 'plaintext'])

/** Programs a code span may start with to be a command. Conservative: what an agent tells the operator to run. */
const PROGRAMS = new Set(`sudo doas cd ls ll cat less more head tail echo printf grep egrep rg ag find fd sed awk tr sort uniq wc cut xargs tee
  cp mv rm rmdir mkdir touch ln chmod chown chgrp stat du df free top htop ps kill killall pkill pgrep lsof watch time timeout env export unset
  source alias which whereis type file diff patch tar zip unzip gzip gunzip xz curl wget ssh scp rsync sftp ping dig nslookup host nc netstat ss ip
  git gh hub svn npm npx pnpm pnpx yarn bun bunx deno node nvm corepack tsc vite vitest jest eslint prettier playwright
  python python3 python2 py pip pip3 pipx uv uvx poetry pytest ruff mypy black flake8 django-admin
  cargo rustc rustup go gofmt make cmake ninja gcc g++ clang java javac mvn gradle dotnet ruby gem bundle rails php composer perl
  docker docker-compose podman kubectl helm terraform ansible vagrant
  systemctl journalctl service sysctl apt apt-get dpkg snap flatpak brew port dnf yum pacman zypper apk nix
  tmux screen bash sh zsh fish exec nohup xdg-open open code subl vim nvim nano emacs
  ffmpeg ffprobe convert magick jq yq sqlite3 psql mysql redis-cli mongosh
  claude codex opencode cursor ollama sp sp.py`.split(/\s+/).filter(Boolean))

const PROMPT = /^[$!] (?=\S)/

/** Words of prose that follow a program's name in a sentence ("make sure", "cat is", "find out"), never its argument here. */
const PROSE = new Set(`a an the is are was were be been it its this that these those to of for and or but not no so as at by from with into onto
  out up sure about if when then than there here which who what why how you your we our they them he she his her my me i
  и в на не что это как с по к о из за от для`.split(/\s+/).filter(Boolean))

/** Leading spaces (tabs count as such) every non-empty line has, gone. */
export function dedent(lines: string[]): string[] {
  const ind = lines.filter((l) => l.trim()).map((l) => /^[ \t]*/.exec(l)![0].length)
  const n = ind.length ? Math.min(...ind) : 0
  return lines.map((l) => l.slice(Math.min(n, /^[ \t]*/.exec(l)![0].length)))
}

/** The `$ ` or `! ` before each line, gone when every non-empty line has one (a single line: when it has one). */
export function stripPrompt(lines: string[]): string[] {
  const full = lines.filter((l) => l.trim())
  if (!full.length || !full.every((l) => PROMPT.test(l))) return lines
  return lines.map((l) => l.replace(PROMPT, ''))
}

/** A command's text as it is copied: empty lines at its ends gone, trailing spaces gone. */
function tidy(lines: string[]): string {
  const out = stripPrompt(dedent(lines.map((l) => l.replace(/\s+$/, ''))))
  while (out.length && !out[0]!.trim()) out.shift()
  while (out.length && !out[out.length - 1]!.trim()) out.pop()
  return out.join('\n')
}

/** The first word of a line: a program, a ./script, a script with an extension, after any VAR=value. */
function firstWord(s: string): { word: string; rest: string } | null {
  let t = s.trim().replace(PROMPT, '')
  // VAR=value before the program.
  for (let m = /^[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|"[^"]*"|\S*)\s+/.exec(t); m; m = /^[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|"[^"]*"|\S*)\s+/.exec(t)) t = t.slice(m[0].length)
  const m = /^(\S+)(.*)$/s.exec(t)
  return m ? { word: m[1]!, rest: m[2]!.trim() } : null
}

/** A program, as the first word of a command line. */
function isProgram(w: string): 'known' | 'script' | null {
  if (PROGRAMS.has(w)) return 'known'
  // ./run.sh, ../x, ~/bin/x, /usr/bin/x: a path run as a program.
  if (/^(\.{1,2}|~)?\/[\w./+-]*[\w+-]$/.test(w) && /^(\.|~)/.test(w)) return 'script'
  // scripts/release-ready.sh, backend/.venv/bin/python, sp.py: a script by its extension or a venv's binary.
  if (/^[\w.+-]+(\/[\w.+-]+)*\.(sh|py|mjs|cjs|js|ts|rb|pl|ps1|bat|cmd)$/.test(w) || /(^|\/)\.?venv\/bin\/[\w.-]+$/.test(w)) return 'script'
  return null
}

/**
 * A code span or a line that reads like a shell command: a program and at
 * least one argument (`./run.sh` and `cd ..` too). A single word, a path, a
 * file name, an id, a web address are not.
 */
export function looksLikeCommand(s: string): boolean {
  const line = s.trim()
  if (!line || line.includes('\n') || /^https?:\/\//i.test(line)) return false
  const f = firstWord(line)
  if (!f) return false
  const kind = isProgram(f.word)
  if (!kind) return false
  // `./run.sh` alone runs it; `git` or `true` alone says nothing.
  if (!f.rest) return kind === 'script' && /^(\.{1,2}|~)\//.test(f.word)
  // "cat is …", "make sure", "find out": a word of prose after the program's name.
  if (PROSE.has(f.rest.split(/\s+/)[0]!.toLowerCase())) return false
  // An argument starts like one (a flag, a name, a path, a quote, a variable, a pipe).
  return /^([-\w./~$'"`(<>|&;=:@%+,*?[\]{}\\]|\P{ASCII})/u.test(f.rest)
}

/** Every command in a reply's markdown, in the reply's order. */
export function commandsOf(md: string): Command[] {
  const out: Command[] = []
  const lines = md.replace(/\r\n?/g, '\n').split('\n')
  for (let i = 0; i < lines.length; i++) {
    const open = /^(\s*)(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/.exec(lines[i]!)
    if (open) {
      const fence = open[2]!
      const lang = open[3]!.toLowerCase().replace(/^\{?\.?/, '').replace(/[}\s].*$/, '')
      const body: string[] = []
      let j = i + 1
      for (; j < lines.length; j++) {
        const close = /^\s*(`{3,}|~{3,})\s*$/.exec(lines[j]!)
        if (close && close[1]![0] === fence[0] && close[1]!.length >= fence.length) break
        body.push(lines[j]!)
      }
      i = j
      const text = tidy(body)
      if (!text) continue
      const shell = SHELL_LANGS.has(lang)
      const plain = PLAIN_LANGS.has(lang)
      if (shell || (plain && looksLikeCommand(text.split('\n')[0]!))) out.push({ text, kind: 'block' })
      continue
    }
    // Code spans of a prose line: `…` or ``…`` (one line each).
    for (const m of lines[i]!.matchAll(/(`+)([^`]|[^`].*?[^`])\1(?!`)/g)) {
      const inner = m[2]!.trim()
      if (looksLikeCommand(inner)) out.push({ text: tidy([inner]), kind: 'inline' })
    }
  }
  return out
}

/** What «Copy for Claude Code» copies: `! ` and the command (Claude Code runs it from its prompt). One line only. */
export function forClaudeCode(c: Command): string | null {
  return c.text.includes('\n') ? null : `! ${c.text}`
}

/* ------------------------------------------------------------ on the screen */

/** Where a command stands: rows (indices into the rows given) and the characters of its first and last row. */
export interface CmdSpan {
  cmd: Command
  row: number
  col: number
  endRow: number
  /** One past the command's last character in `endRow`. */
  endCol: number
}

const isWord = (c: string | undefined) => !!c && /[\p{L}\p{N}]/u.test(c)

/** A text's key, character by character, with where each key character came from (match.keyOf, kept positional). */
function keyed(s: string): { key: string; at: number[] } {
  let key = ''
  const at: number[] = []
  let i = 0
  for (const ch of s) {
    const k = ch.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '')
    for (let x = 0; x < k.length; x++) at.push(i)
    key += k
    i += ch.length
  }
  return { key, at }
}

/** A command's key shorter than this says too little to be found by. */
const KEY_MIN = 4

/**
 * The commands of a reply placed in the rows `from..to` that show it: each
 * found by its key, the last command at the last place it stands, the one
 * before it before that (narration above the reply may name the same
 * words), and only where it starts and ends at a word's edge.
 */
export function placeCommands(rows: string[], from: number, to: number, cmds: Command[]): CmdSpan[] {
  let key = ''
  const where: Array<{ row: number; col: number }> = []
  for (let r = from; r <= to; r++) {
    const k = keyed(rows[r] ?? '')
    key += k.key
    for (const c of k.at) where.push({ row: r, col: c })
  }
  const out: CmdSpan[] = []
  let limit = key.length
  for (let i = cmds.length - 1; i >= 0; i--) {
    const ck = keyed(cmds[i]!.text).key
    if (ck.length < KEY_MIN) continue
    let at = key.lastIndexOf(ck, limit - ck.length)
    while (at >= 0) {
      const a = where[at]!, b = where[at + ck.length - 1]!
      const before = (rows[a.row] ?? '').slice(0, a.col)
      const lastCh = String.fromCodePoint((rows[b.row] ?? '').codePointAt(b.col) ?? 32)
      const endCol = b.col + lastCh.length
      const after = (rows[b.row] ?? '')[endCol]
      if (!isWord([...before].at(-1)) && !isWord(after)) {
        // The command's own text from its start: a prompt or punctuation before the key's first letter ("! echo", "./run").
        let col = a.col
        const lead = cmds[i]!.text.slice(0, cmds[i]!.text.search(/[\p{L}\p{N}]/u))
        if (lead && before.endsWith(lead)) col -= lead.length
        out.push({ cmd: cmds[i]!, row: a.row, col, endRow: b.row, endCol })
        limit = at
        break
      }
      at = at > 0 ? key.lastIndexOf(ck, at - 1) : -1
    }
  }
  return out.reverse()
}

/** A row that starts with `$ ` or `! ` and a program: a command shown with its prompt (the fallback). */
const LINE = /^(\s*)([$!]) (\S.*)$/

export function promptLine(row: string): Command | null {
  const m = LINE.exec(row)
  if (!m) return null
  const rest = m[3]!.replace(/\s+$/, '')
  const f = firstWord(rest)
  // `! [rejected] main -> main`: git's, not a command.
  if (!f || !/^[\w.~/-]/.test(f.word)) return null
  if (!isProgram(f.word) && !/^[\w.-]+$/.test(f.word)) return null
  return { text: rest, kind: 'line' }
}

/**
 * The commands in `rows`: those of each reply the rows show (matched in the
 * record by match.messageAt, by its own text), and the `$ ` / `! ` rows
 * outside such replies. `wrapped[i]`: row i continues row i−1 (xterm's
 * wrapping), so a long `$ ` line keeps its rows. `skip`: the row being typed
 * on (the prompt), never a command.
 */
export function commandSpans(rows: string[], rec: Record | null, opts: { wrapped?: boolean[]; skip?: number; from?: number; to?: number } = {}): CmdSpan[] {
  const out: CmdSpan[] = []
  const inReply = new Set<number>()
  const lo = opts.from ?? 0, hi = opts.to ?? rows.length - 1
  if (rec) {
    for (const b of blocksOf(rows)) {
      if (b.kind !== 'agent' || b.end < lo || b.start > hi) continue
      const f = messageAt(rows, b.start, rec)
      if (!f || f.side !== 'reply' || f.how !== 'text') continue
      const text = rec.byN.get(f.n)?.agent ?? ''
      const cmds = commandsOf(text)
      for (let r = b.start; r <= b.end; r++) inReply.add(r)
      if (cmds.length) out.push(...placeCommands(rows, b.start, b.end, cmds))
    }
  }
  for (let r = lo; r <= hi; r++) {
    if (inReply.has(r) || r === opts.skip || opts.wrapped?.[r]) continue
    const c = promptLine(rows[r] ?? '')
    if (!c) continue
    let end = r
    let text = c.text
    while (opts.wrapped?.[end + 1] && end + 1 < rows.length && end + 1 !== opts.skip) { end += 1; text += rows[end]!.replace(/\s+$/, '') }
    out.push({ cmd: { text, kind: 'line' }, row: r, col: rows[r]!.indexOf(rows[r]!.trim()[0]!), endRow: end, endCol: rows[end]!.replace(/\s+$/, '').length })
  }
  return out.sort((a, b) => a.row - b.row || a.col - b.col)
}

/** The command at row `row` (and character `col`, when known): the one under it, else the only one on the row. */
export function commandAt(spans: CmdSpan[], row: number, col: number | null): CmdSpan | null {
  const on = spans.filter((s) => row >= s.row && row <= s.endRow)
  if (!on.length) return null
  if (col == null) return on[0]!
  const hit = on.find((s) => (row > s.row || col >= s.col) && (row < s.endRow || col < s.endCol))
  if (hit) return hit
  // A block is its rows; an inline command on a row of prose: the row, when it holds just one.
  return on.find((s) => s.cmd.kind !== 'inline') ?? (on.length === 1 ? on[0]! : null)
}
