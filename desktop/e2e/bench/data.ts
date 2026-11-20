/**
 * The bench's output: coloured lines like a working terminal prints them —
 * a passed test, a diff (- and +), `ls -l`, a line in a 256-colour, a log
 * line — in a fixed cycle, from a seeded random source, so every run and
 * every system prints the same bytes. The same mix as the engine comparison
 * of 2026-11-16 (notes/2611-16-terminal-engines.md): 20 MB is about 280 000
 * lines.
 *
 * `makeData` is self-contained (no imports, no closures): the speed bench
 * also runs it inside the page, by its source text, to write straight into
 * the page's terminal.
 */
export function makeData(bytes: number, eol: string): string {
  let s = 0x5eed1234
  const rnd = () => {
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  const W = ['export', 'index', 'client', 'failed', 'const', 'delete', 'config', 'test', 'main', 'session', 'function', 'passed',
    'error', 'async', 'render', 'await', 'parser', 'module', 'server', 'fetch', 'utils', 'running', 'import', 'update', 'create',
    'build', 'src', 'lib', 'status', 'terminal', 'warning', 'return']
  const w = () => W[Math.floor(rnd() * W.length)]
  const n = (k: number) => Math.floor(rnd() * k)
  const words = (lo: number, hi: number) => Array.from({ length: lo + n(hi - lo + 1) }, w).join(' ')
  const pad = (v: number, k: number) => String(v).padStart(k, '0')
  const E = '\x1b['
  const out: string[] = []
  let size = 0
  for (let i = 0; size < bytes; i++) {
    let l: string
    switch (i % 6) {
      case 0: l = `${E}32m✓${E}0m ${w()}/${w()}.test.ts ${E}2m(${n(900) + 10} ms)${E}0m`; break
      case 1: l = `${E}31m-    return ${w()}.${w()}(${n(999)}) && ${w()} <= ${w()}.end${E}0m`; break
      case 2: l = `${E}32m+    return ${w()}.${w()}(${n(999)}) && ${w()} < ${w()}.end${E}0m`; break
      case 3: l = `-rw-r--r-- 1 user user ${String(n(99000) + 1000).padStart(6)} Nov 16 12:${pad(n(60), 2)} ${E}1;34m${w()}${E}0m/${w()}_${i}.py`; break
      case 4: l = `${E}38;5;${16 + n(216)}m${words(8, 14)}${E}0m`; break
      default: l = `[${pad(i, 7)}] ${words(3, 14)} — ${rnd().toFixed(6)}`
    }
    out.push(l)
    // Bytes, not characters: ✓ and — are three bytes each in UTF-8.
    size += l.length + eol.length + (i % 6 === 0 || i % 6 === 5 ? 2 : 0)
  }
  return out.join(eol) + eol
}
