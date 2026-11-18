/**
 * Output in ANSI colours, added after each chat's script in the J lab so a
 * colour scheme shows on what a terminal really prints: `ls` colours, a test
 * run with passes and a failure, `git status` and a diff stat, a log with
 * yellow hashes. Mock text; the codes are real SGR codes.
 */

import type { Session } from '../../mock'
import type { ScreenLine } from '../../term'

const E = '\x1b['
const c = (code: string, s: string) => `${E}${code}m${s}${E}0m`

const DIR: Record<string, string> = { harbor: 'src/booking', kelp: 'src/watch', lumen: 'src/search', otter: 'src/sync' }

const cache = new Map<string, ScreenLine[]>()

export function showcase(s: Session): ScreenLine[] {
  const hit = cache.get(s.id)
  if (hit) return hit
  const dir = DIR[s.project] ?? 'src'
  const lines: ScreenLine[] = [
    { k: 'you', text: `run the whole suite, then show me ${dir} and what changed` },
    { k: 'tool', name: 'Bash', arg: `ls -la ${dir}` },
    { k: 'ansi', text: `  drwxr-xr-x  4 dev dev  4096 Nov 18 10:41 ${c('1;34', 'drag')}` },
    { k: 'ansi', text: `  -rwxr-xr-x  1 dev dev   812 Nov 18 09:02 ${c('1;32', 'seed.sh')}` },
    { k: 'ansi', text: `  lrwxrwxrwx  1 dev dev    14 Nov 17 18:20 ${c('1;36', 'current')} -> v2` },
    { k: 'ansi', text: `  -rw-r--r--  1 dev dev 40960 Nov 16 12:00 ${c('1;31', 'fixtures.tar.gz')}` },
    { k: 'tool', name: 'Bash', arg: 'npm test' },
    { k: 'ansi', text: `  ${c('32', '✓')} ${dir}/slots.test.ts ${c('2', '(15 tests)')} ${c('33', '1.9s')}` },
    { k: 'ansi', text: `  ${c('31', '✗')} ${dir}/month.test.ts ${c('2', '>')} back-to-back bookings share a cell` },
    { k: 'ansi', text: `    ${c('31', 'AssertionError: expected 2 to be 1')}` },
    { k: 'ansi', text: `  Tests  ${c('1;31', '1 failed')} | ${c('1;32', '41 passed')} | ${c('35', '1 skipped')} ${c('2', '(43)')}` },
    { k: 'tool', name: 'Bash', arg: 'git status --short && git diff --stat && git log --oneline -1' },
    { k: 'ansi', text: `  ${c('32', 'M')}  ${dir}/slots.ts    ${c('31', 'M')} ${dir}/MonthGrid.tsx` },
    { k: 'ansi', text: `   ${dir}/MonthGrid.tsx | 6 ${c('32', '++++')}${c('31', '--')}` },
    { k: 'ansi', text: `  ${c('33', '8cd792a')} (${c('1;36', 'HEAD -> ')}${c('1;32', 'main')}) Touching slots no longer overlap` },
    { k: 'say', text: `One test fails in the month view: two bookings that touch still share a cell. The task is ${s.task}; the agenda view is tk_93d0a5f7.` },
  ]
  cache.set(s.id, lines)
  return lines
}
