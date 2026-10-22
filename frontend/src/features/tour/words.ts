/**
 * Words on a canvas: wrapping and fitting, with nothing drawn.
 *
 * Shared by the scene and the opening and closing cards, which are drawn
 * in their own file. Every caller measures with the font it has already
 * set on the context; `fitSize` is the one that sets it.
 */

/** Greedy wrap. Returns the lines; the caller owns the leading. */
export function wrap(g: CanvasRenderingContext2D, text: string, max: number): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let line = ''
  for (const w of words) {
    const next = line ? `${line} ${w}` : w
    if (g.measureText(next).width > max && line) {
      lines.push(line)
      line = w
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

/** Wrap into at most `n` lines; the last ends in an ellipsis when words were left over. */
export function lines(g: CanvasRenderingContext2D, text: string, max: number, n: number): string[] {
  const all = wrap(g, text, max)
  if (all.length <= n) return all
  const out = all.slice(0, n)
  let last = `${out[n - 1]}…`
  while (g.measureText(last).width > max && /\s/.test(last)) last = last.replace(/\s+\S+…$/, '…')
  out[n - 1] = last
  return out
}

/** The largest size from `hi` down to `lo` at which the text wraps into `n` lines. */
export function fitSize(
  g: CanvasRenderingContext2D, text: string, max: number, n: number,
  hi: number, lo: number, weight: number, face: string,
): number {
  for (let s = hi; s > lo; s *= 0.93) {
    g.font = `${weight} ${s}px ${face}`
    if (wrap(g, text, max).length <= n) return s
  }
  g.font = `${weight} ${lo}px ${face}`
  return lo
}
