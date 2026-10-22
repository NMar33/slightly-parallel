/**
 * Shots for the tour, taken from the running app.
 *
 * The tour is not a screen recording: every beat is opened in a real
 * browser, given time to load its data, measured, and photographed. A
 * still beat is one frame; an action beat is a burst around a click, so
 * the drawer that opens is the app's own drawer and not an illustration.
 *
 * Reads one JSON job on stdin, writes one JSON result on stdout. Never
 * throws past the top: a beat that fails carries its error and the rest
 * of the tour still gets its pictures.
 */

import { mkdir, readFile, readdir, unlink, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { chromium } from 'playwright'

import { maskPage } from './tour_mask.mjs'

const read = () =>
  new Promise((resolve, reject) => {
    let buf = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (d) => { buf += d })
    process.stdin.on('end', () => {
      try { resolve(JSON.parse(buf)) } catch (e) { reject(e) }
    })
    process.stdin.on('error', reject)
  })

/**
 * Where the subject sits in the viewport, as fractions of it.
 *
 * A selector can match eighty things — every copy button on a board, say.
 * The one worth photographing is the one a viewer's eye would land on: the
 * match nearest the middle of the screen that is wholly inside it. Taking
 * the first match in document order picks whatever is furthest up and left,
 * which on a scrolling board is usually half off the edge.
 */
async function measure(page, selector, view) {
  if (!selector) return null
  try {
    const all = page.locator(selector)
    await all.first().waitFor({ state: 'visible', timeout: 10000 })
    const n = Math.min(await all.count(), 120)
    let best = null
    let bestScore = Infinity
    let fallback = null
    for (let i = 0; i < n; i++) {
      const box = await all.nth(i).boundingBox().catch(() => null)
      if (!box || box.width < 4 || box.height < 4) continue
      if (!fallback) fallback = box
      const inside = box.x >= 0 && box.y >= 0
        && box.x + box.width <= view.width && box.y + box.height <= view.height
      if (!inside) continue
      const dx = box.x + box.width / 2 - view.width / 2
      const dy = box.y + box.height / 2 - view.height / 2
      const score = dx * dx + dy * dy
      if (score < bestScore) { bestScore = score; best = box }
    }
    const box = best || fallback
    if (!box) return null
    return {
      x: box.x / view.width,
      y: box.y / view.height,
      w: box.width / view.width,
      h: box.height / view.height,
    }
  } catch {
    return null
  }
}

/**
 * Scroll the subject into the window when every match of it is outside.
 *
 * A page longer than the window holds some subjects below the fold: the
 * skill's usage table, the one problem that has a rule. Measured where it
 * sits, the subject gets a rect past the bottom of the picture and the film
 * points at nothing. A subject already on screen is left where the page put
 * it, so a page opens as it opens unless the story is further down.
 */
async function bringIntoView(page, selector, view) {
  if (!selector) return
  try {
    const all = page.locator(selector)
    await all.first().waitFor({ state: 'visible', timeout: 10000 })
    // Twice more if need be: the page can still grow above the subject
    // while it settles (a list filling in), and one scroll lands short.
    for (let tries = 0; tries < 3; tries++) {
      const n = Math.min(await all.count(), 120)
      for (let i = 0; i < n; i++) {
        const box = await all.nth(i).boundingBox().catch(() => null)
        if (box && box.y >= 0 && box.y + Math.min(box.height, view.height / 2) <= view.height) return
      }
      await all.first().evaluate((el) => el.scrollIntoView({ block: 'center' }))
      await page.waitForTimeout(400)
    }
  } catch { /* measured where it is; a missing subject is reported there */ }
}

/**
 * Which nav items the page in the last frame hides — under a dialog, say.
 *
 * The rings are drawn on every frame of a beat. A beat that opens the task
 * dialog would ring the Tasks tab through the dialog, a box around a few
 * words of the form. An item the dialog covers is left unringed.
 */
async function covered(page, selectors) {
  const out = []
  for (const sel of selectors) {
    const hidden = await page.locator(sel).first().evaluate((el) => {
      const r = el.getBoundingClientRect()
      const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return !top || !(el === top || el.contains(top) || top.contains(el))
    }).catch(() => false)
    out.push(hidden)
  }
  return out
}

const centre = (box) => ({ x: box.x + box.width / 2, y: box.y + box.height / 2 })

const asFraction = (pt, view, down) => ({
  x: pt.x / view.width, y: pt.y / view.height, down: !!down,
})

/**
 * Perform the beat's manipulation, photographing it as it happens.
 *
 * A tour that only shows still pages teaches where things are, not how they
 * work. The pictures here are of the app actually doing it: the menu that
 * opened, the column that unfolded, the card that moved.
 *
 * The pointer is recorded alongside the frames. It has to be: a browser
 * paints the dragged card and the cursor into a layer screenshots do not
 * capture, so a screenshot of a drag is a screenshot of a board sitting
 * still. These are the real coordinates the mouse was at when each frame
 * was taken — the renderer draws the hand back in, it does not invent it.
 */
async function perform(page, action, shoot, view, navs = []) {
  const n = Math.min(24, Math.max(1, Math.round(action.frames || 6)))
  const gap = Math.max(40, Math.round(action.interval || 110))
  const el = page.locator(action.selector).first()
  await el.waitFor({ state: 'visible', timeout: 6000 })
  const box = await el.boundingBox()
  const pointer = []
  const grab = box && action.kind === 'drag'
    ? { x: box.x / view.width, y: box.y / view.height,
        w: box.width / view.width, h: box.height / view.height }
    : null

  if (action.kind === 'drag') {
    const target = page.locator(action.to).first()
    await target.waitFor({ state: 'visible', timeout: 6000 })
    const from = centre(box)
    const to = centre(await target.boundingBox())
    await page.mouse.move(from.x, from.y)
    await page.mouse.down()
    const steps = Math.max(2, n - 1)
    for (let i = 1; i <= steps; i++) {
      const t = i / steps
      const at = { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t }
      await page.mouse.move(at.x, at.y, { steps: 4 })
      await page.waitForTimeout(gap)
      await shoot(asFraction(at, view, true))
    }
    await page.mouse.up()
    await page.waitForTimeout(gap * 2)
    await shoot(asFraction(to, view, false))
    return { pointer, grab, focus: await measure(page, action.focus || action.selector, view), hidden: await covered(page, navs) }
  }

  let at = centre(box)
  if (action.kind === 'hover') await el.hover()
  else if (action.kind === 'type') await el.fill(String(action.text ?? ''))
  else await el.click({ force: true })
  // What the click opened can sit below the fold (the usage table of the
  // skill just picked): the frames show it, not the page above it.
  if (action.focus) {
    await page.waitForTimeout(gap)
    await bringIntoView(page, action.focus, view)
  }
  // The page can move under the pointer: scrolled to the focus, or laid out
  // again by the click itself — a view pill that changes the line beside it
  // shifts its own row, and the hand was drawn on the pill next door. The
  // pointer stays on what it clicked, measured on the page the frames show.
  await page.waitForTimeout(action.focus ? 0 : gap)
  const moved = await el.boundingBox().catch(() => null)
  if (moved) at = centre(moved)
  for (let i = 1; i <= n; i++) {
    await page.waitForTimeout(gap)
    // `down` on the first frame after the click is what draws the tap ring.
    await shoot(asFraction(at, view, i === 1))
  }
  // Where the callout points once the burst is over — measured now, on the
  // page the last frame shows. After the restore below the view is another
  // one, and the same control sits somewhere else (the changes pill of the
  // architecture tab moves when the page view comes back).
  const focus = await measure(page, action.focus || action.selector, view)
  const hidden = await covered(page, navs)
  // Some beats flip a view the whole app remembers — swim lanes, a folded
  // column. Put it back, or every later beat is photographed in a state one
  // beat chose for it.
  if (action.after) {
    await page.locator(action.after).first().click({ force: true, timeout: 4000 }).catch(() => {})
    // View choices are written back to the server on a debounce; close the
    // page too soon and the restore never leaves the browser, so every later
    // beat is photographed in the state this one flipped it into.
    await page.waitForTimeout(900)
  }
  return { pointer, grab, focus, hidden }
}

async function main() {
  const job = await read()
  const base = String(job.base || 'http://127.0.0.1:5173').replace(/\/$/, '')
  const out = String(job.out || '')
  const view = {
    width: Math.round(job.width || 1440),
    height: Math.round(job.height || 900),
  }
  const scale = Math.min(3, Math.max(1, Math.round(job.scale || 2)))
  // This computer's paths, and what the pictures say instead (tour_mask.mjs).
  const mask = Array.isArray(job.mask) ? job.mask : []
  await mkdir(out, { recursive: true })

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: view,
    deviceScaleFactor: scale,
    ...(job.colorScheme ? { colorScheme: job.colorScheme } : {}),
  })
  // The pages come from the app, their data from the tour's own world
  // (backend/tour_world.py): the example project alone, never the
  // operator's data. Every /api request is answered by that server.
  const api = String(job.api || '').replace(/\/$/, '')
  if (api) {
    await context.route((url) => url.pathname.startsWith('/api/'), async (route) => {
      const req = route.request()
      const u = new URL(req.url())
      try {
        const response = await route.fetch({
          url: api + u.pathname + u.search,
          // What the browser would have sent itself: the world's server
          // hands its operator cookie only to a page of its own, and
          // refuses a write whose Origin is another port's (a dev server
          // on any port but 5173 — the drag of a card was refused there).
          headers: {
            ...req.headers(),
            'sec-fetch-site': 'same-origin',
            ...(req.headers().origin ? { origin: api } : {}),
          },
        })
        await route.fulfill({ response })
      } catch {
        await route.abort().catch(() => {})
      }
    })
  }
  // The app animates on mount; a tour wants the settled page, not the
  // arrival. Motion inside a beat comes from the action, not from CSS.
  // A page's guide ("About this page") is for a first visit, not for a film.
  await context.addInitScript(() => {
    // The board's morning question (which of yesterday's cards to plan
    // for today) would cover the board in every picture of it.
    const d = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    try { localStorage.setItem('sp-today-carry-seen', `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`) } catch { /* no storage */ }
    const css = '*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important;transition-delay:0s!important}'
      + 'section[aria-label="About this page"]{display:none!important}'
    document.addEventListener('DOMContentLoaded', () => {
      const tag = document.createElement('style')
      tag.textContent = css
      document.head.append(tag)
    })
  })

  const shots = []
  for (const beat of job.beats || []) {
    const id = String(beat.id || '')
    const files = []
    const pointer = []
    let rect = null
    const nav = []
    let grab = null
    let error = ''
    // An action that bursts fewer frames than last time would leave the
    // old tail on disk, listed as if it were part of this capture.
    for (const old of await readdir(out).catch(() => [])) {
      if (old.startsWith(`${id}-`) && /^\d+\.png$/.test(old.slice(id.length + 1))) {
        await unlink(path.join(out, old)).catch(() => {})
      }
    }
    const page = await context.newPage()
    try {
      // Not `networkidle`: the dashboard polls, so the network is never
      // idle and every beat would wait out its own timeout. Wait for the
      // document, give the network a short chance to go quiet, then settle.
      await page.goto(base + String(beat.page || '/'), {
        waitUntil: 'load', timeout: 20000,
      })
      await page.waitForLoadState('networkidle', { timeout: 3500 }).catch(() => {})
      if (beat.wait_for) {
        await page.locator(beat.wait_for).first()
          .waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
      }
      await page.waitForTimeout(Math.max(150, beat.settle ?? 700))

      const shoot = async (pt = null) => {
        const name = `${id}-${files.length}.png`
        // Every frame: a burst re-renders what the last frame had masked.
        if (mask.length) await page.evaluate(maskPage, mask).catch(() => {})
        await page.screenshot({ path: path.join(out, name), animations: 'disabled' })
        files.push(name)
        pointer.push(pt)
      }

      await bringIntoView(page, beat.selector, view)
      rect = await measure(page, beat.selector, view)
      if (beat.selector && !rect) error = `element not found: ${beat.selector}`
      // Where this page lives in the navigation — the project in the sidebar
      // and the tab inside it. Measured before anything is clicked, because
      // a beat that opens a panel can cover them.
      for (const sel of beat.nav || []) {
        // Scroll it into its own scroller first: a long project list runs
        // past the bottom of the window, and a highlight nobody can see is
        // the same as no highlight.
        await page.locator(sel).first()
          .scrollIntoViewIfNeeded({ timeout: 2500 }).catch(() => {})
        nav.push(await measure(page, sel, view))
      }
      await page.waitForTimeout(150)
      await shoot()

      const action = beat.action
      if (action && action.selector) {
        const done = await perform(page, action, shoot, view, beat.nav || [])
        grab = done.grab
        done.hidden.forEach((h, i) => { if (h) nav[i] = null })
        // The action's own target is what the callout should point at once
        // the burst is over, unless the beat named something else. A focus
        // the action names wins over the beat's subject: the evidence beat
        // names the card (for the live tour) but the film is about the
        // proof the card opens, and the card itself is folded off screen.
        if (done.focus && (!beat.selector || action.focus)) rect = done.focus
      }
      // A demonstration: each step in turn, its frames after the last.
      for (const step of beat.steps || []) {
        if (!step || !step.selector) continue
        const done = await perform(page, step, shoot, view, beat.nav || [])
        if (done.grab) grab = done.grab
        done.hidden.forEach((h, i) => { if (h) nav[i] = null })
        if (done.focus && (!beat.selector || step.focus)) rect = done.focus
      }
    } catch (e) {
      error = String((e && e.message) || e).split('\n')[0].slice(0, 300)
    } finally {
      await page.close().catch(() => {})
    }
    shots.push({ id, files, pointer, grab, rect, nav, error })
  }

  await browser.close()
  const result = { ok: true, at: new Date().toISOString(), view, scale, shots }
  if (job.manifest) {
    // Re-shooting three beats must not forget the other fourteen: the
    // manifest is the whole photographed set, merged by beat id.
    const file = path.join(out, 'manifest.json')
    let prior = []
    try {
      const old = JSON.parse(await readFile(file, 'utf8'))
      if (Array.isArray(old.shots)) prior = old.shots
    } catch { /* first run */ }
    const merged = new Map(prior.map((s) => [s.id, s]))
    for (const s of shots) merged.set(s.id, s)
    await writeFile(file, JSON.stringify(
      { ...result, shots: [...merged.values()] }, null, 2,
    ))
  }
  process.stdout.write(JSON.stringify(result))
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String((e && e.message) || e) }))
  process.exit(0)
})
