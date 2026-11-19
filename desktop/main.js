'use strict'
/**
 * The terminal window of Slightly Parallel: the page /term of the local
 * server in a window of its own, apart from the browser.
 *
 *   electron . [--url=http://127.0.0.1:8123] [--path=/term] [--size=1000x640]
 *              [--inspect] [--check]
 *
 * The page draws its own title row; the window has no frame. The title row
 * is the window's drag handle (CSS app-region in the page). The page asks
 * the window (preload.js): close, minimize, title {text},
 * grow {left, right}, detach {url, width, height}, open {url}, restore {open}; and it may
 * read what the window's processes use (metrics, for the terminal log).
 *
 * On Linux the window is a native Wayland window where the desktop is
 * Wayland, and an X11 one where it is not. On Wayland a window cannot move
 * itself, so it grows to the right only: a panel opening on the left pushes
 * the terminal. Everywhere else the left panel widens the window to the
 * left and the terminal stays where it was on the screen.
 *
 * --check loads the page in a hidden window, prints what it found as JSON
 * and quits.
 *
 * Windows after a restart, as a browser restores its session: the windows
 * besides the main one (a detached chat or workspace, a page opened in a
 * window of its own) are kept in windows.json in Electron's userData — each
 * one's address, size and, off Wayland, its place and display. The file is
 * written when such a window opens, closes, moves or is resized (the last two
 * debounced), and on quit, so a crash loses nothing. A window the operator
 * closes is gone from it; the app closing (the main window closed, Quit, the
 * session ending) keeps the set. At the next start, after the main window,
 * Settings › Terminal › On start (terminal.restore_windows, read from the
 * server) decides: restore opens them, ask lets the main window's page ask
 * (spWindow.restoreOffer, then op restore {open}), main forgets them.
 */
const fs = require('node:fs')
const path = require('node:path')
const { app, BrowserWindow, dialog, ipcMain, net, powerMonitor, screen, shell } = require('electron')
const {
  MIN_W, MIN_H, sizeOf, sameSite, pageUrl, grown, num, parseArgs,
  restoreChoice, isWayland, windowRecord, savedText, readSaved, onScreen, startPlan,
} = require('./lib')

const args = parseArgs(process.argv.slice(app.isPackaged ? 1 : 2), process.env)
if (process.platform === 'linux') app.commandLine.appendSwitch('ozone-platform-hint', 'auto')

const dragging = new Map() // window id → { timer, dx, dy }
// Only release width the window manager actually granted to a sidebar.
const sidebarGrowth = new WeakMap()

/* ------------------------------------------------ windows after a restart */

let mainWin = null
/** The app is closing: windows closing now stay in the saved set. */
let quitting = false
/** window id → { win, url }: every window besides the main one, in opening order. */
const kept = new Map()
/** Saved windows that have not opened or been dismissed yet. */
let pending = []
let askingToRestore = false
let stateLoaded = false
let decide
/** How many saved windows wait for the operator's answer (0: none, or not asked). */
const decided = new Promise((resolve) => { decide = resolve })
let saveTimer = null
const wayland = () => isWayland(process.platform, process.argv, process.env, app.commandLine.getSwitchValue('ozone-platform'))
const stateFile = () => path.join(app.getPath('userData'), 'windows.json')

function recordOf(entry) {
  const { win } = entry
  const b = win.isDestroyed() ? null : (win.isMaximized() || win.isFullScreen() ? win.getNormalBounds() : win.getBounds())
  if (!b) return null
  const now = win.webContents.getURL()
  const url = now && sameSite(args.url, now) ? now : entry.url
  const way = wayland()
  return windowRecord(url, b, { wayland: way, display: way ? null : screen.getDisplayMatching(b).id })
}

/** Write the set now: the open windows, then those still waiting for an answer. */
function saveNow() {
  clearTimeout(saveTimer)
  saveTimer = null
  if (quitting || !stateLoaded) return
  const windows = [...kept.values()].map(recordOf).filter(Boolean).concat(pending)
  try {
    const file = stateFile()
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file + '.tmp', savedText(windows))
    fs.renameSync(file + '.tmp', file)
  } catch (e) { process.stderr.write(`windows.json not saved: ${e}\n`) }
}

function saveSoon() {
  if (quitting) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(saveNow, 400)
}

/** The app is closing: keep the set as it is now, whatever closes after. */
function closing() {
  if (quitting) return
  saveNow()
  quitting = true
}

/** A window besides the main one: kept while it is open, forgotten when the
 *  operator closes it. */
function keep(win, url) {
  kept.set(win.id, { win, url })
  win.on('move', saveSoon)
  win.on('resize', saveSoon)
  win.webContents.on('did-navigate-in-page', saveSoon)
  win.on('close', () => { if (!quitting) { kept.delete(win.id); saveNow() } })
  win.on('closed', () => kept.delete(win.id))
  if (process.platform === 'win32') win.on('session-end', closing)
  saveNow()
  return win
}

function openSaved() {
  const displays = screen.getAllDisplays()
  while (pending.length) {
    const rec = pending[0]
    const r = wayland() ? { url: rec.url, width: rec.width, height: rec.height } : onScreen(rec, displays)
    const win = openWindow(r.url, r.width, r.height, true, typeof r.x === 'number' ? { x: r.x, y: r.y } : null)
    pending.shift()
    keep(win, r.url)
  }
}

/** Settings › Terminal › On start, from the server; the default when it does not answer. */
async function readChoice() {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), 4000)
  try {
    const r = await net.fetch(args.url + '/api/settings', { signal: ctl.signal })
    return restoreChoice(r.ok ? await r.json() : null)
  } catch { return restoreChoice(null) } finally { clearTimeout(timer) }
}

/** After the main window: the saved windows, as the setting says. */
async function restoreAtStart() {
  // Keep the saved set in every write, including a quit while settings load.
  try { pending = readSaved(fs.readFileSync(stateFile(), 'utf-8'), args.url) } catch { /* no file: nothing saved */ }
  stateLoaded = true
  const saved = pending
  const choice = saved.length ? await readChoice() : 'restore'
  if (quitting) return
  const plan = startPlan(choice, saved)
  pending = plan.open.concat(plan.ask)
  if (plan.open.length) {
    // The main window first, then the others over it.
    await new Promise((resolve) => {
      if (!mainWin || mainWin.isDestroyed() || mainWin.isVisible()) return resolve()
      const t = setTimeout(resolve, 3000)
      mainWin.once('ready-to-show', () => { clearTimeout(t); setTimeout(resolve, 50) })
    })
    if (quitting) return
    openSaved()
  }
  askingToRestore = plan.ask.length > 0
  saveNow()
  // For the suite (desktop/e2e/restore.spec.ts): what the start decided.
  globalThis.__spRestore = { choice, saved: saved.length, opened: plan.open.length, asked: plan.ask.length }
  decide(pending.length)
}

function openMain(url, width, height) {
  mainWin = openWindow(url, width, height)
  // The main window closed is the app closed: the others close with it and
  // come back next time.
  mainWin.on('close', () => {
    closing()
    for (const { win } of kept.values()) if (!win.isDestroyed()) win.close()
  })
  if (process.platform === 'win32') mainWin.on('session-end', closing)
  return mainWin
}

function stopDrag(win) {
  const d = dragging.get(win.id)
  if (d) { clearInterval(d.timer); dragging.delete(win.id) }
}

function openWindow(url, width, height, show = true, at = null) {
  const win = new BrowserWindow({
    width, height, minWidth: MIN_W, minHeight: MIN_H, ...(at || {}),
    frame: false, show: false, backgroundColor: '#0b0d0d',
    title: 'Slightly Parallel', autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, sandbox: true, nodeIntegration: false,
      spellcheck: false, devTools: args.inspect,
    },
  })
  win.removeMenu()
  const wc = win.webContents
  wc.setUserAgent(wc.getUserAgent() + ' SlightlyParallelWindow/1')
  // A link out of the app opens in the browser; a page of the app asked for
  // in a new window gets a window like this one.
  wc.setWindowOpenHandler(({ url: target }) => {
    if (sameSite(args.url, target)) keep(openWindow(target, 900, 600), target)
    else if (/^https?:\/\//.test(target)) shell.openExternal(target)
    return { action: 'deny' }
  })
  wc.on('will-navigate', (event, target) => {
    if (!sameSite(args.url, target)) {
      event.preventDefault()
      if (/^https?:\/\//.test(target)) shell.openExternal(target)
    }
  })
  wc.on('did-start-navigation', (details) => {
    if (details.isMainFrame && !details.isSameDocument) sidebarGrowth.delete(win)
  })
  win.on('closed', () => stopDrag(win))
  if (show) win.once('ready-to-show', () => win.show())
  win.loadURL(url)
  return win
}

ipcMain.on('sp-window', (event, msg) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win || !msg || typeof msg !== 'object') return
  // Only a page of our own server may ask the window for anything.
  if (!sameSite(args.url, event.sender.getURL())) return
  switch (msg.op) {
    case 'drag': {
      stopDrag(win)
      const start = screen.getCursorScreenPoint()
      const [x, y] = win.getPosition()
      const d = { dx: start.x - x, dy: start.y - y, timer: null }
      d.timer = setInterval(() => {
        if (win.isDestroyed()) return stopDrag(win)
        const p = screen.getCursorScreenPoint()
        win.setPosition(p.x - d.dx, p.y - d.dy)
      }, 8)
      dragging.set(win.id, d)
      break
    }
    case 'drag-end': stopDrag(win); break
    case 'close': win.close(); break
    case 'minimize': win.minimize(); break
    case 'title': win.setTitle(String(msg.text || 'Slightly Parallel').slice(0, 120)); break
    case 'grow': {
      if (win.isMaximized() || win.isFullScreen()) {
        sidebarGrowth.delete(win)
        break
      }
      const b = win.getBounds()
      const prior = sidebarGrowth.get(win) ?? { left: 0, right: 0 }
      const left = Math.max(-prior.left, num(msg.left, -2000, 2000))
      const right = Math.max(-prior.right, num(msg.right, -2000, 2000))
      if (!left && !right) break
      const [x, width] = grown(b.x, b.width, left, right)
      win.setBounds({ x, y: b.y, width, height: b.height })
      const observed = win.getBounds().width - b.width
      const wanted = left + right
      const fraction = wanted ? Math.max(0, Math.min(1, observed / wanted)) : 0
      const appliedLeft = Math.round(left * fraction)
      const appliedRight = Math.round(wanted * fraction) - appliedLeft
      sidebarGrowth.set(win, {
        left: prior.left + (left < 0 ? left : appliedLeft),
        right: prior.right + (right < 0 ? right : appliedRight),
      })
      break
    }
    case 'detach': {
      const url = pageUrl(args.url, msg.url)
      if (url) keep(openWindow(url, num(msg.width, MIN_W, 4000, 900), num(msg.height, MIN_H, 3000, 600)), url)
      break
    }
    case 'restore': {
      // The operator's answer to the main window's question.
      if (win !== mainWin || !askingToRestore) break
      askingToRestore = false
      if (msg.open === true) openSaved()
      else pending = []
      saveNow()
      break
    }
    case 'open':
      if (/^https?:\/\//.test(String(msg.url || ''))) shell.openExternal(String(msg.url))
      break
  }
})

ipcMain.handle('sp-save-draft', async (event, name, text) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win || win.isDestroyed() || event.senderFrame !== event.sender.mainFrame ||
      !sameSite(args.url, event.senderFrame.url)) return false
  if (typeof name !== 'string' || typeof text !== 'string') throw new Error('Invalid Markdown draft')
  const defaultPath = name.replace(/[^\p{L}\p{N}._-]/gu, '-').replace(/^\.+/, '').slice(0, 100)
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    defaultPath: defaultPath ? `${defaultPath}.md` : 'draft.md',
    filters: [{ name: 'Markdown', extensions: ['md'] }],
  })
  if (canceled || !filePath) return false
  const chosenMarkdown = /\.md$/i.test(filePath)
  // If the platform did not append the extension, avoid overwriting a
  // different file from the one the operator chose in the save dialog.
  await fs.promises.writeFile(chosenMarkdown ? filePath : `${filePath}.md`, text, {
    encoding: 'utf8', flag: chosenMarkdown ? 'w' : 'wx',
  })
  return true
})

// How many windows of last time wait for the operator's answer: only the
// main window asks, once the start has decided (0 when there is nothing to ask).
ipcMain.handle('sp-restore-offer', async (event) => {
  if (!sameSite(args.url, event.sender.getURL())) return 0
  const n = await decided
  return askingToRestore && mainWin && event.sender === mainWin.webContents ? Math.min(n, pending.length) : 0
})

// Read only: what the window's processes use, for the page's terminal log.
ipcMain.handle('sp-metrics', (event) => {
  if (!sameSite(args.url, event.sender.getURL())) return null
  return app.getAppMetrics().map((m) => ({
    type: m.type, kb: m.memory ? m.memory.workingSetSize : 0, cpu: m.cpu ? m.cpu.percentCPUUsage : 0,
  }))
})

async function check(url, width, height) {
  const win = openWindow(url, width, height, false)
  const report = { url, ok: false, electron: process.versions.electron, chrome: process.versions.chrome }
  const done = (code) => { process.stdout.write(JSON.stringify(report, null, 1) + '\n'); app.exit(code) }
  const timer = setTimeout(() => { report.error = 'timed out'; done(1) }, 25000)
  win.webContents.on('did-fail-load', (_e, _code, text, target) => { report.error = `${target}: ${text}`; clearTimeout(timer); done(1) })
  win.webContents.on('did-finish-load', () => setTimeout(async () => {
    try {
      Object.assign(report, await win.webContents.executeJavaScript(`({
        title: document.title, bridge: !!(window.spWindow && window.spWindow.postMessage),
        terminals: document.querySelectorAll('.xterm').length,
        webgl: !!document.createElement('canvas').getContext('webgl2'),
        text: (document.body.innerText || '').slice(0, 200) })`))
      report.gpu = app.getGPUFeatureStatus()
      report.ok = true
    } catch (e) { report.error = String(e) }
    clearTimeout(timer)
    done(report.ok ? 0 : 1)
  }, 2500))
}

const start = pageUrl(args.url, args.path)
if (!start) {
  process.stderr.write(`--path must be a page of ${args.url}\n`)
  app.exit(2)
} else if (args.check) {
  app.whenReady().then(() => check(start, ...sizeOf(args.size)))
} else if (!app.requestSingleInstanceLock()) {
  // A second start: the first one brings its window forward.
  app.quit()
} else {
  app.on('second-instance', () => {
    const win = mainWin && !mainWin.isDestroyed() ? mainWin : BrowserWindow.getAllWindows()[0]
    if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus() } else openMain(start, ...sizeOf(args.size))
  })
  app.on('window-all-closed', () => app.quit())
  // Quit, the session ending, a signal: the set is kept as it is.
  app.on('before-quit', closing)
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(sig, () => { closing(); app.quit() })
  app.whenReady().then(() => {
    if (quitting) return
    powerMonitor.on('shutdown', closing)
    openMain(start, ...sizeOf(args.size))
    void restoreAtStart()
  })
}
