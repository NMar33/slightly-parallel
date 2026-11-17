'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const { MIN_W, MIN_H, sizeOf, pageUrl, grown, num, parseArgs } = require('./lib')

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
