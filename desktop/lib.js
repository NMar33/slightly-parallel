'use strict'
/** What the window works out without Electron: sizes, addresses, growth. */

const MIN_W = 420
const MIN_H = 240

/** "1000x640" → [1000, 640], never under the minimum. */
function sizeOf(text) {
  const m = /^(\d+)x(\d+)$/i.exec(String(text || ''))
  if (!m) return [1000, 640]
  return [Math.max(MIN_W, Number(m[1])), Math.max(MIN_H, Number(m[2]))]
}

function sameSite(base, url) {
  try {
    const a = new URL(base), b = new URL(url)
    return a.protocol === b.protocol && a.hostname === b.hostname && a.port === b.port
  } catch { return false }
}

/** The address a window may open: a path of the app, or a full address of
 *  the same server. Anything else is not a page of ours. */
function pageUrl(base, pathOrUrl) {
  const v = String(pathOrUrl || '')
  if (v.startsWith('/') && !v.startsWith('//')) return base.replace(/\/+$/, '') + v
  return sameSite(base, v) ? v : null
}

/** Where a window stands and how wide it is after growing by `left` and
 *  `right` pixels: the left side moves it, the right side does not. It never
 *  gets narrower than the minimum. */
function grown(x, width, left, right, minW = MIN_W) {
  const w = Math.max(minW, width + left + right)
  const tookLeft = left >= 0 || width + left >= minW ? left : minW - width
  return [x - tookLeft, w]
}

/** A number from a message, kept inside its range; anything else is the default. */
function num(v, lo, hi, dflt = 0) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return dflt
  return Math.round(Math.max(lo, Math.min(hi, v)))
}

/** --url=, --path=, --size=, --check, --inspect out of the command line.
 *  Electron's launcher moves switches ahead of plain words, so a value is
 *  read from `--name=value`; `--name value` is read too when it survives. */
function parseArgs(argv, env = {}) {
  const out = { url: env.SP_URL || 'http://127.0.0.1:8123', path: '/term', size: '1000x640', check: false, inspect: false }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--check') out.check = true
    else if (a === '--inspect') out.inspect = true
    else if ((a === '--url' || a === '--path' || a === '--size') && argv[i + 1] !== undefined) out[a.slice(2)] = argv[++i]
    else if (a.startsWith('--url=') || a.startsWith('--path=') || a.startsWith('--size=')) {
      const k = a.slice(2, a.indexOf('='))
      out[k] = a.slice(a.indexOf('=') + 1)
    }
  }
  out.url = out.url.replace(/\/+$/, '')
  return out
}

module.exports = { MIN_W, MIN_H, sizeOf, sameSite, pageUrl, grown, num, parseArgs }
