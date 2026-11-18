/**
 * Which input to a terminal is the operator's: a key or a paste is typing;
 * what xterm sends for itself is not — mouse reports (tmux runs with the
 * mouse on, so a click is two of them), focus in/out, and its answers to a
 * program's questions (device attributes, cursor and status reports, mode
 * reports, window sizes, colours, DCS replies). The socket's input message
 * carries the answer as `typed`, and only typed input beats the timer and
 * counts as keys. The server reads the bytes the same way
 * (termlib.is_terminal_reply) for a message that does not say.
 */

const REPLY = [
  '\\x1b\\[<\\d+;\\d+;\\d+[Mm]', // SGR mouse
  '\\x1b\\[\\d+;\\d+;\\d+M', // urxvt mouse
  '\\x1b\\[M[\\x20-\\u{10ffff}]{3}', // X10 mouse
  '\\x1b\\[[IO]', // focus in / out
  '\\x1b\\[[?>=][\\d;]*c', // device attributes
  '\\x1b\\[\\??\\d+;\\d+(?:;\\d+)?R', // cursor position (a modified F3 looks the same: a key says so)
  '\\x1b\\[\\??\\d*n', // status report
  '\\x1b\\[\\??[\\d;]*\\$y', // mode report
  '\\x1b\\[\\d+(?:;\\d+)*t', // window size
  '\\x1b\\[\\?\\d*u', // keyboard flags
  '\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)', // OSC answer (colours)
  '\\x1bP[^\\x1b]*\\x1b\\\\', // DCS answer
].join('|')
const REPLIES_ONLY = new RegExp(`^(?:${REPLY})+$`, 'u')

/** Only the terminal's own reports and replies, no key in it. */
export function isTerminalReply(data: string): boolean {
  return data.length > 0 && REPLIES_ONLY.test(data)
}

/**
 * Tells xterm's input apart as it comes. xterm fires `onKey` just before the
 * key's `onData`, in the same turn: `key()` there makes the next data typed
 * whatever its bytes (Ctrl+F3 is `ESC[1;5R`, the shape of a cursor report).
 * Any other data is typed unless it is only replies (a paste, IME text).
 */
export class InputMarker {
  private keyed = false

  /** xterm's onKey: the data that follows is a key. */
  key() {
    this.keyed = true
    // A key that sent nothing (stdin off) must not mark the next report.
    queueMicrotask(() => { this.keyed = false })
  }

  /** xterm's onData: is this the operator's input? */
  typed(data: string): boolean {
    const keyed = this.keyed
    this.keyed = false
    return keyed || !isTerminalReply(data)
  }
}
