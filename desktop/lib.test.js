'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const {
  MIN_W, MIN_H, sizeOf, pageUrl, grown, num, parseArgs,
  restoreChoice, isWayland, windowRecord, savedText, readSaved, onScreen, startPlan,
} = require('./lib')

test('growing left moves the window, growing right does not', () => {
  assert.deepEqual(grown(500, 1000, 260, 0), [240, 1260])
  assert.deepEqual(grown(500, 1000, 0, 320), [500, 1320])
  assert.deepEqual(grown(500, 1000, 260, 320), [240, 1580])
  assert.deepEqual(grown(240, 1580, -260, -320), [500, 1000])
})

test('a window never gets narrower than its minimum', () => {
  assert.deepEqual(grown(500, 600, -400, 0), [500 + (600 - MIN_W), MIN_W])
  assert.deepEqual(grown(500, 600, 0, -400), [500, MIN_W])
})

test('a window opens only pages of its own server', () => {
  const base = 'http://127.0.0.1:8123'
  assert.equal(pageUrl(base, '/term?detached=t1'), 'http://127.0.0.1:8123/term?detached=t1')
  assert.equal(pageUrl(base + '/', '/term'), 'http://127.0.0.1:8123/term')
  assert.equal(pageUrl(base, 'http://127.0.0.1:8123/term'), 'http://127.0.0.1:8123/term')
  assert.equal(pageUrl(base, 'http://127.0.0.1:9000/term'), null)
  assert.equal(pageUrl(base, 'https://example.com/'), null)
  assert.equal(pageUrl(base, '//example.com/x'), null)
  assert.equal(pageUrl(base, 'javascript:alert(1)'), null)
  assert.equal(pageUrl(base, 'file:///etc/passwd'), null)
})

test('the size is read and kept above the minimum', () => {
  assert.deepEqual(sizeOf('1200x700'), [1200, 700])
  assert.deepEqual(sizeOf('10x10'), [MIN_W, MIN_H])
  assert.deepEqual(sizeOf('wide'), [1000, 640])
})

test('a number from the page stays inside its range', () => {
  assert.equal(num(260.4, -2000, 2000), 260)
  assert.equal(num(99999, -2000, 2000), 2000)
  assert.equal(num('260', -2000, 2000), 0)
  assert.equal(num(NaN, 0, 10, 5), 5)
})

test('the command line is read', () => {
  const a = parseArgs(['--url=http://127.0.0.1:8141/', '--path=/term?ws=alpha', '--check', '--size', '900x600'])
  assert.deepEqual(a, { url: 'http://127.0.0.1:8141', path: '/term?ws=alpha', size: '900x600', check: true, inspect: false })
  assert.equal(parseArgs([], { SP_URL: 'http://127.0.0.1:9999' }).url, 'http://127.0.0.1:9999')
  // The launcher hoists switches: a bare --url followed by the app folder is not an address.
  assert.equal(parseArgs(['--inspect', '/some/app/folder', '--url=http://127.0.0.1:8123']).url, 'http://127.0.0.1:8123')
})

/* ------------------------------------------------ windows after a restart */

const BASE = 'http://127.0.0.1:8123'
const settings = (value) => ({ groups: [{ name: 'Terminal', settings: [{ key: 'terminal.font_size', value: 13 }, { key: 'terminal.restore_windows', value }] }] })

test('the start setting is read from the server, the default when it says nothing usable', () => {
  assert.equal(restoreChoice(settings('ask')), 'ask')
  assert.equal(restoreChoice(settings('main')), 'main')
  assert.equal(restoreChoice(settings('restore')), 'restore')
  assert.equal(restoreChoice(settings('everything')), 'restore')
  assert.equal(restoreChoice({ groups: [] }), 'restore')
  assert.equal(restoreChoice(null), 'restore')
})

test('restore opens the saved windows, ask holds them, main lets them go', () => {
  const saved = [{ url: BASE + '/term?detached=t1', width: 700, height: 500 }, { url: BASE + '/term?ws=alpha', width: 900, height: 600 }]
  assert.deepEqual(startPlan('restore', saved), { open: saved, ask: [] })
  assert.deepEqual(startPlan('ask', saved), { open: [], ask: saved })
  assert.deepEqual(startPlan('main', saved), { open: [], ask: [] })
  // Nothing saved: nothing to open and nothing to ask.
  assert.deepEqual(startPlan('ask', []), { open: [], ask: [] })
})

test('a window is kept with its address and size, and its place where the platform has one', () => {
  const b = { x: 120.4, y: 80, width: 733, height: 455 }
  assert.deepEqual(windowRecord(BASE + '/term?detached=t1', b, { display: 7 }),
    { url: BASE + '/term?detached=t1', width: 733, height: 455, x: 120, y: 80, display: 7 })
  // Wayland: the desktop places windows, so no place is kept.
  assert.deepEqual(windowRecord(BASE + '/term?ws=alpha', b, { wayland: true, display: 7 }),
    { url: BASE + '/term?ws=alpha', width: 733, height: 455 })
})

test('the saved file is read back, and only pages of this server come out of it', () => {
  const text = savedText([
    { url: BASE + '/term?detached=t1', width: 733, height: 455, x: 10, y: 20, display: 1 },
    { url: BASE + '/term?ws=alpha', width: 10, height: 99999 },
    { url: 'https://example.com/', width: 800, height: 600 },
    { url: 'http://127.0.0.1:9000/term', width: 800, height: 600 },
    { url: BASE + '/term?ws=beta', width: 'wide', height: 600, x: 5 },
    null,
  ])
  assert.deepEqual(readSaved(text, BASE), [
    { url: BASE + '/term?detached=t1', width: 733, height: 455, x: 10, y: 20, display: 1 },
    { url: BASE + '/term?ws=alpha', width: MIN_W, height: 8000 },
    { url: BASE + '/term?ws=beta', width: 900, height: 600 },
  ])
  assert.deepEqual(readSaved('', BASE), [])
  assert.deepEqual(readSaved('{not json', BASE), [])
  assert.deepEqual(readSaved('{"windows": "no"}', BASE), [])
})

test('a saved place off every display now is dropped; the window still opens', () => {
  const displays = [
    { id: 1, workArea: { x: 0, y: 32, width: 1920, height: 1048 } },
    { id: 2, workArea: { x: 1920, y: 0, width: 1280, height: 1024 } },
  ]
  const at = (x, y) => ({ url: BASE + '/term', width: 800, height: 600, x, y, display: 2 })
  assert.deepEqual(onScreen(at(100, 100), displays), at(100, 100))
  assert.deepEqual(onScreen(at(2000, 50), displays), at(2000, 50))
  // The second display is gone: its place is off every display left.
  assert.deepEqual(onScreen(at(2000, 50), displays.slice(0, 1)), { url: BASE + '/term', width: 800, height: 600 })
  // Only a sliver of the title row shows, or the row is above the work area.
  assert.deepEqual(onScreen(at(-760, 100), displays), { url: BASE + '/term', width: 800, height: 600 })
  assert.deepEqual(onScreen(at(100, -30), displays), { url: BASE + '/term', width: 800, height: 600 })
  // A record without a place stays as it is.
  assert.deepEqual(onScreen({ url: BASE + '/term', width: 800, height: 600 }, displays), { url: BASE + '/term', width: 800, height: 600 })
})

test('Wayland is where the command line or the desktop says so, on Linux only', () => {
  assert.equal(isWayland('linux', ['--ozone-platform=wayland'], {}), true)
  assert.equal(isWayland('linux', ['--ozone-platform=x11'], { WAYLAND_DISPLAY: 'wayland-0' }), false)
  assert.equal(isWayland('linux', ['--ozone-platform=headless'], { WAYLAND_DISPLAY: 'wayland-0' }), false)
  assert.equal(isWayland('linux', [], { WAYLAND_DISPLAY: 'wayland-0' }), true)
  assert.equal(isWayland('linux', [], { DISPLAY: ':0' }), false)
  assert.equal(isWayland('linux', [], {}, 'wayland'), true)
  assert.equal(isWayland('darwin', ['--ozone-platform=wayland'], { WAYLAND_DISPLAY: 'x' }), false)
})
