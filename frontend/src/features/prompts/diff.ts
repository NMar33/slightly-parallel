/** A line diff (LCS) — enough to show what a version changed. */

type DiffLine = { type: 'same' | 'add' | 'del'; text: string }

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const n = a.length
  const m = b.length
  // LCS table; the files are a few hundred lines, so n·m is fine.
  const dp: Uint16Array[] = []
  for (let i = 0; i <= n; i++) dp.push(new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ type: 'same', text: a[i] }); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: 'del', text: a[i] }); i++ }
    else { out.push({ type: 'add', text: b[j] }); j++ }
  }
  while (i < n) out.push({ type: 'del', text: a[i++] })
  while (j < m) out.push({ type: 'add', text: b[j++] })
  return out
}

/** Only the changed lines with a little context, as hunks. */
export function hunks(diff: DiffLine[], context = 2): DiffLine[][] {
  const keep = new Array<boolean>(diff.length).fill(false)
  diff.forEach((d, i) => {
    if (d.type === 'same') return
    for (let k = Math.max(0, i - context); k <= Math.min(diff.length - 1, i + context); k++) keep[k] = true
  })
  const out: DiffLine[][] = []
  let cur: DiffLine[] = []
  keep.forEach((k, i) => {
    if (k) cur.push(diff[i])
    else if (cur.length) { out.push(cur); cur = [] }
  })
  if (cur.length) out.push(cur)
  return out
}

export function diffStats(diff: DiffLine[]): { add: number; del: number } {
  return diff.reduce((s, d) => ({ add: s.add + (d.type === 'add' ? 1 : 0), del: s.del + (d.type === 'del' ? 1 : 0) }), { add: 0, del: 0 })
}
