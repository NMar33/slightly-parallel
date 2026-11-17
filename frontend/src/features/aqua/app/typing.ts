/**
 * Typing ticks: how many keys the operator pressed in each terminal, sent
 * to the server (`POST /api/terminal/typing {sid, keys}`) at most once
 * every 15 seconds while they type — a count, never the text. The first
 * key after a quiet spell goes at once; the keys after it wait for the
 * window to pass. A server without the route (404) ends the ticks for good.
 */

export type Send = (sid: string, keys: number) => Promise<'ok' | 'gone'> | 'ok' | 'gone'

export const TYPING_EVERY_MS = 15_000

export class TypingBatcher {
  private counts = new Map<string, number>()
  private last = -Infinity
  private timer: ReturnType<typeof setTimeout> | null = null
  private off = false

  constructor(
    private send: Send,
    private every = TYPING_EVERY_MS,
    private now: () => number = () => Date.now(),
  ) {}

  /** One input event in this terminal (a key, or one paste). */
  tick(sid: string, n = 1) {
    if (this.off || !sid || n <= 0) return
    this.counts.set(sid, (this.counts.get(sid) ?? 0) + n)
    if (this.timer) return
    const wait = Math.max(0, this.last + this.every - this.now())
    if (wait === 0) { void this.flush(); return }
    this.timer = setTimeout(() => { this.timer = null; void this.flush() }, wait)
  }

  /** Send what is counted now (also when the page goes away). */
  async flush() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null }
    if (this.off || this.counts.size === 0) return
    const batch = [...this.counts.entries()]
    this.counts.clear()
    this.last = this.now()
    for (const [sid, keys] of batch) {
      try {
        if ((await this.send(sid, keys)) === 'gone') { this.stop(); return }
      } catch { /* a missed tick is a lost count, nothing more */ }
    }
  }

  /** Counted but not yet sent, for a terminal (tests, and the stats). */
  pending(sid: string) { return this.counts.get(sid) ?? 0 }

  get stopped() { return this.off }

  stop() {
    this.off = true
    this.counts.clear()
    if (this.timer) { clearTimeout(this.timer); this.timer = null }
  }
}
