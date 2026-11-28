'use strict'
/** What the window works out without Electron: sizes, addresses, growth. */

const { host: defaultHost, port: defaultPort } = require('../backend/backend/server_defaults.json')
const DEFAULT_SERVER_URL = `http://${defaultHost}:${defaultPort}`

const MIN_W = 420
const MIN_H = 240

/** "1000x640" → [1000, 640], never under the minimum. */
function sizeOf(text) {
  const m = /^(\d+)x(\d+)$/i.exec(String(text || ''))
  if (!m) return [1000, 640]
  return [Math.max(MIN_W, Number(m[1])), Math.max(MIN_H, Number(m[2]))]
}

function webUrl(value, base) {
  try {
    const url = new URL(value, base)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url : null
  } catch { return null }
}

function sameSite(base, url) {
  const a = webUrl(base)
  const b = webUrl(url)
  return a !== null && b !== null && a.origin === b.origin
}

/** The address a window may open: a path of the app, or a full address of
 *  the same server. Anything else is not a page of ours. */
function pageUrl(base, pathOrUrl) {
  const v = String(pathOrUrl || '')
  const home = webUrl(base)
  if (!home || v.startsWith('//') || v.startsWith('/\\')) return null
  const target = v.startsWith('/') ? webUrl(v, home) : webUrl(v)
  return target?.origin === home.origin ? target.href : null
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
  const out = { url: env.SP_URL || DEFAULT_SERVER_URL, path: '/term', size: '1000x640', check: false, inspect: false }
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

/* ------------------------------------------------ windows after a restart */

/** Settings › Terminal › On start (backend/backend/app_settings.py). */
const RESTORE_KEY = 'terminal.restore_windows'
const RESTORE_CHOICES = ['restore', 'ask', 'main']

/** The setting out of the server's /api/settings answer; the default when
 *  the answer has none or the server did not answer. */
function restoreChoice(payload) {
  const groups = payload && Array.isArray(payload.groups) ? payload.groups : []
  for (const g of groups) {
    for (const s of (g && Array.isArray(g.settings) ? g.settings : [])) {
      if (s && s.key === RESTORE_KEY && RESTORE_CHOICES.includes(s.value)) return s.value
    }
  }
  return 'restore'
}

/** Linux draws the window through Wayland: the command line names it, or
 *  Electron's automatic choice (ozone-platform-hint auto) finds a Wayland
 *  display. There a window cannot place itself; the desktop does. */
function isWayland(platform, argv, env, ozone = '') {
  if (platform !== 'linux') return false
  const named = ozone || (argv.find((a) => a.startsWith('--ozone-platform=')) || '').slice('--ozone-platform='.length)
  if (named) return named === 'wayland'
  return !!env.WAYLAND_DISPLAY
}

/** What is kept of one window: its address, its size, and where the platform
 *  lets a window stand, its place and display. `bounds` is the window's
 *  normal (not maximised) rectangle. */
function windowRecord(url, bounds, { wayland = false, display = null } = {}) {
  const rec = { url, width: Math.round(bounds.width), height: Math.round(bounds.height) }
  if (!wayland) {
    rec.x = Math.round(bounds.x); rec.y = Math.round(bounds.y)
    if (display !== null && display !== undefined) rec.display = display
  }
  return rec
}

/** The file's text: the windows to bring back. */
function savedText(windows) {
  return JSON.stringify({ version: 1, windows }, null, 1) + '\n'
}

/** The windows a saved file names that may open now: pages of this server
 *  (`base`), sizes kept in range, places only where both numbers are. A file
 *  that cannot be read names none. */
function readSaved(text, base) {
  let data
  try { data = JSON.parse(String(text || '')) } catch { return [] }
  const list = data && Array.isArray(data.windows) ? data.windows : []
  const out = []
  for (const w of list) {
    if (!w || typeof w !== 'object') continue
    const url = pageUrl(base, w.url)
    if (!url) continue
    const rec = { url, width: num(w.width, MIN_W, 8000, 900), height: num(w.height, MIN_H, 8000, 600) }
    if (typeof w.x === 'number' && typeof w.y === 'number' && Number.isFinite(w.x) && Number.isFinite(w.y)) {
      rec.x = Math.round(w.x); rec.y = Math.round(w.y)
      if (w.display !== undefined) rec.display = w.display
    }
    out.push(rec)
  }
  return out
}

/** A saved place is kept only when the window's title row would be on a
 *  display there now: at least 80 × 24 px of its top 40 px inside one
 *  display's work area. Otherwise the window opens where the system puts it. */
function onScreen(rec, displays) {
  if (typeof rec.x !== 'number' || typeof rec.y !== 'number') return rec
  const row = { x: rec.x, y: rec.y, width: rec.width, height: Math.min(40, rec.height) }
  const seen = (displays || []).some((d) => {
    const a = d.workArea || d.bounds
    if (!a) return false
    const w = Math.min(row.x + row.width, a.x + a.width) - Math.max(row.x, a.x)
    const h = Math.min(row.y + row.height, a.y + a.height) - Math.max(row.y, a.y)
    return w >= 80 && h >= 24
  })
  if (seen) return rec
  const { x: _x, y: _y, display: _d, ...rest } = rec
  return rest
}

/** At start, with the windows saved last time: restore opens them, ask
 *  holds them for the operator's answer, main lets them go. */
function startPlan(choice, saved) {
  const list = saved || []
  if (!list.length || choice === 'main') return { open: [], ask: [] }
  if (choice === 'ask') return { open: [], ask: list }
  return { open: list, ask: [] }
}

module.exports = {
  MIN_W, MIN_H, sizeOf, webUrl, sameSite, pageUrl, grown, num, parseArgs,
  RESTORE_KEY, RESTORE_CHOICES, restoreChoice, isWayland, windowRecord, savedText, readSaved, onScreen, startPlan,
}
