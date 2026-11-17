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
 * grow {left, right}, detach {url, width, height}, open {url}.
 *
 * On Linux the window is a native Wayland window where the desktop is
 * Wayland, and an X11 one where it is not. On Wayland a window cannot move
 * itself, so it grows to the right only: a panel opening on the left pushes
 * the terminal. Everywhere else the left panel widens the window to the
 * left and the terminal stays where it was on the screen.
 *
 * --check loads the page in a hidden window, prints what it found as JSON
 * and quits.
 */
const path = require('node:path')
const { app, BrowserWindow, ipcMain, screen, shell } = require('electron')
const { MIN_W, MIN_H, sizeOf, sameSite, pageUrl, grown, num, parseArgs } = require('./lib')

const args = parseArgs(process.argv.slice(app.isPackaged ? 1 : 2), process.env)
if (process.platform === 'linux') app.commandLine.appendSwitch('ozone-platform-hint', 'auto')

const dragging = new Map() // window id → { timer, dx, dy }

function stopDrag(win) {
  const d = dragging.get(win.id)
  if (d) { clearInterval(d.timer); dragging.delete(win.id) }
}

function openWindow(url, width, height, show = true) {
  const win = new BrowserWindow({
    width, height, minWidth: MIN_W, minHeight: MIN_H,
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
    if (sameSite(args.url, target)) openWindow(target, 900, 600)
    else if (/^https?:\/\//.test(target)) shell.openExternal(target)
    return { action: 'deny' }
  })
  wc.on('will-navigate', (event, target) => {
    if (!sameSite(args.url, target)) {
      event.preventDefault()
      if (/^https?:\/\//.test(target)) shell.openExternal(target)
    }
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
      const b = win.getBounds()
      const [x, width] = grown(b.x, b.width, num(msg.left, -2000, 2000), num(msg.right, -2000, 2000))
      win.setBounds({ x, y: b.y, width, height: b.height })
      break
    }
    case 'detach': {
      const url = pageUrl(args.url, msg.url)
      if (url) openWindow(url, num(msg.width, MIN_W, 4000, 900), num(msg.height, MIN_H, 3000, 600))
      break
    }
    case 'open':
      if (/^https?:\/\//.test(String(msg.url || ''))) shell.openExternal(String(msg.url))
      break
  }
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
    const win = BrowserWindow.getAllWindows()[0]
    if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus() } else openWindow(start, ...sizeOf(args.size))
  })
  app.on('window-all-closed', () => app.quit())
  app.whenReady().then(() => openWindow(start, ...sizeOf(args.size)))
}
