import { describe, expect, it } from 'vitest'

import { commandAt, commandSpans, commandsOf, dedent, forClaudeCode, looksLikeCommand, placeCommands, promptLine, stripPrompt } from './commands'
import { Record } from './match'

const texts = (md: string) => commandsOf(md).map((c) => c.text)

describe('the commands of a reply, from its markdown', () => {
  it('a fenced block with a shell language, without one, with ~~~; the fence and the language gone', () => {
    expect(texts('Run:\n\n```bash\nnpm ci\n```\n')).toEqual(['npm ci'])
    expect(texts('Run:\n```\ngit status\n```')).toEqual(['git status'])
    expect(texts('~~~sh\nmake test\n~~~')).toEqual(['make test'])
    expect(texts('```console\n$ ls -la\n```')).toEqual(['ls -la'])
  })

  it('the operator\'s example: `! ` before it is the prompt, not the command', () => {
    const md = "Поставь лимит:\n\n```\n! echo 'fs.inotify.max_user_instances=1024' | sudo tee /etc/sysctl.d/60-inotify.conf && sudo sysctl --system\n```"
    const [c] = commandsOf(md)
    expect(c!.text).toBe("echo 'fs.inotify.max_user_instances=1024' | sudo tee /etc/sysctl.d/60-inotify.conf && sudo sysctl --system")
    expect(forClaudeCode(c!)).toBe(`! ${c!.text}`)
  })

  it('a multi-line block is one command, kept whole: line breaks kept, the common indentation gone, its inner indentation kept', () => {
    const md = [
      '1. Then:',
      '',
      '   ```bash',
      '   cd frontend',
      '   for f in a b; do',
      '     echo "$f" \\',
      '       | tr a-z A-Z',
      '   done',
      '   ```',
    ].join('\n')
    const [c] = commandsOf(md)
    expect(c!.text).toBe('cd frontend\nfor f in a b; do\n  echo "$f" \\\n    | tr a-z A-Z\ndone')
    expect(c!.kind).toBe('block')
    // Several lines: never with `! ` (Claude Code runs one line from its prompt).
    expect(forClaudeCode(c!)).toBeNull()
  })

  it('a prompt is stripped only when every line has one', () => {
    expect(stripPrompt(['$ a', '$ b'])).toEqual(['a', 'b'])
    expect(stripPrompt(['$ a', 'output'])).toEqual(['$ a', 'output'])
    expect(stripPrompt(['! a'])).toEqual(['a'])
    expect(dedent(['    a', '      b', '', '    c'])).toEqual(['a', '  b', '', 'c'])
  })

  it('a block in another language is code, not a command; a plain block counts when its first line reads like one', () => {
    expect(texts('```ts\nconst x = 1\n```')).toEqual([])
    expect(texts('```json\n{"a": 1}\n```')).toEqual([])
    expect(texts('```\n┌──┐\n│ a │\n```')).toEqual([])
    expect(texts('```text\npython3 -m http.server 8000\n```')).toEqual(['python3 -m http.server 8000'])
  })

  it('inline code: a command counts; a path, a file, a single word, an id, an address do not', () => {
    const md = 'Run `git status`, then `./run.sh`, `sudo sysctl --system` and `FOO=1 npm test`. '
      + 'Not `README.md`, `true`, `git`, `tk_29b870f1`, `https://example.com/x`, `frontend/src/app.ts`, `--force`, `ls`, `make sure`.'
    expect(texts(md)).toEqual(['git status', './run.sh', 'sudo sysctl --system', 'FOO=1 npm test'])
    expect(commandsOf(md).every((c) => c.kind === 'inline')).toBe(true)
  })

  it('a command with quotes, pipes, &&, $VAR, backslashes and Cyrillic is copied as written', () => {
    const cmd = `grep -rn "привет мир" . | sed 's/\\\\/\\//g' && echo "$HOME" > /tmp/вывод.txt`
    expect(texts('```sh\n' + cmd + '\n```')).toEqual([cmd])
    expect(texts('Run `' + 'echo "$PATH" | tr : \\\\n' + '`.')).toEqual(['echo "$PATH" | tr : \\\\n'])
  })

  it('looksLikeCommand: conservative', () => {
    for (const yes of ['cd ..', 'npm run build', 'python3 -m pytest -q', 'scripts/release-ready.sh main', 'backend/.venv/bin/python -m x', '~/bin/tool --x', 'sp.py restart'])
      expect(looksLikeCommand(yes), yes).toBe(true)
    for (const no of ['true', 'npm', 'docs/audit/index.md', 'cat is here', 'find out why', 'git\nstatus', 'a | b', 'Record', "'url' | 'path'"])
      expect(looksLikeCommand(no), no).toBe(false)
  })
})

describe('the commands on the screen', () => {
  // A reply as Claude Code draws it: no fences, no backticks, its own indentation and wrapping.
  const md = "Поставь лимит inotify:\n\n```\n! echo 'fs.inotify.max_user_instances=1024' | sudo tee /etc/sysctl.d/60-inotify.conf && sudo sysctl --system\n```\n\nПотом `git status` и:\n\n```bash\ncd frontend\nnpx vitest run\n```\n\nФайл `README.md` не трогай."
  const rows = [
    '❯ почему падает vite',
    '',
    '● Поставь лимит inotify:',
    '',
    "    ! echo 'fs.inotify.max_user_instances=1024' | sudo tee",
    '    /etc/sysctl.d/60-inotify.conf && sudo sysctl --system',
    '',
    '  Потом git status и:',
    '',
    '    cd frontend',
    '    npx vitest run',
    '',
    '  Файл README.md не трогай.',
    '',
    '✻ Worked for 3s',
  ]
  const rec = new Record([{ n: 4, sid: 's', user: 'почему падает vite', agent: md }])

  it('each command at its rows: a wrapped one over two, the inline one inside its row, the block whole', () => {
    const spans = commandSpans(rows, rec)
    expect(spans.map((s) => [s.cmd.kind, s.row, s.endRow])).toEqual([['block', 4, 5], ['inline', 7, 7], ['block', 9, 10]])
    expect(spans[1]!.col).toBe(rows[7]!.indexOf('git status'))
    expect(spans[1]!.endCol).toBe(rows[7]!.indexOf('git status') + 'git status'.length)
    // The block starts where its command does, after the `! ` it is shown with.
    expect(spans[0]!.col).toBe(rows[4]!.indexOf('echo'))
    expect(spans[2]!.cmd.text).toBe('cd frontend\nnpx vitest run')
    // README.md is not a command, so nothing stands on its row.
    expect(commandAt(spans, 12, null)).toBeNull()
  })

  it('the command at a click: the block by its rows, the inline one by its columns (or the only one on the row)', () => {
    const spans = commandSpans(rows, rec)
    expect(commandAt(spans, 5, 0)!.cmd.kind).toBe('block')
    expect(commandAt(spans, 7, rows[7]!.indexOf('status'))!.cmd.text).toBe('git status')
    expect(commandAt(spans, 7, 0)!.cmd.text).toBe('git status')
    expect(commandAt(spans, 9, null)!.cmd.text).toBe('cd frontend\nnpx vitest run')
  })

  it('the last place a command stands is the reply\'s: narration above it with the same words is not', () => {
    const r = ['● git status first', '  then:', '    git status']
    const s = placeCommands(r, 0, 2, [{ text: 'git status', kind: 'block' }])
    expect(s.map((x) => x.row)).toEqual([2])
    // Inside a longer word it is not found: "legit statuses".
    expect(placeCommands(['  legit statuses'], 0, 0, [{ text: 'git status', kind: 'inline' }])).toEqual([])
  })

  it('a reply not in the record: the `$ ` and `! ` rows are commands, wrapped rows joined; git\'s `! [rejected]` and an empty prompt are not', () => {
    const r = ['$ echo one two', '  output', '! npm run lint -- --fix', ' ! [rejected]        main -> main (fetch first)', '$ ', '$ python3 -c "print(1)" && ech', 'o done']
    const wrapped = [false, false, false, false, false, false, true]
    const spans = commandSpans(r, null, { wrapped })
    expect(spans.map((s) => [s.row, s.endRow, s.cmd.text])).toEqual([
      [0, 0, 'echo one two'], [2, 2, 'npm run lint -- --fix'], [5, 6, 'python3 -c "print(1)" && echo done']])
    expect(promptLine('! [rejected] x')).toBeNull()
    // The row being typed on is never one.
    expect(commandSpans(['$ ls -la'], null, { skip: 0 })).toEqual([])
  })

  it('rows of a matched reply are not read as `$ ` rows; elsewhere they are', () => {
    const r2 = [...rows.slice(0, 13), '  $ not-a-command-here x', '', '$ ls -la']
    const rec2 = new Record([{ n: 4, sid: 's', user: 'почему падает vite', agent: md + '\n\n$ not-a-command-here x' }])
    const spans = commandSpans(r2, rec2)
    expect(spans.some((s) => s.row === 13)).toBe(false)
    expect(spans.find((s) => s.row === 15)!.cmd.text).toBe('ls -la')
  })
})
