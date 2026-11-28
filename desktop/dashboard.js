'use strict'

const { WebContentsView } = require('electron')
const { sameSite, settingChoice } = require('./lib')
const { bindDashboardAgent } = require('./agent-terminal')

const DASHBOARD_PRELOAD_BYTES = 4 * 1024 ** 3

function shouldPreloadDashboard(settings, freeBytes) {
  const choice = settingChoice(settings, 'desktop.dashboard_preload', ['auto', 'on_launch', 'on_click']) ?? 'auto'
  return choice === 'on_launch' || (choice === 'auto' && freeBytes > DASHBOARD_PRELOAD_BYTES)
}

function hostDashboard(win, url, guardNavigation, openAgent) {
  let view
  let wanted = false
  let ready = false
  let titleHeight = 34
  let pending

  const layout = () => {
    if (!view) return
    const { width, height } = win.getContentBounds()
    view.setBounds({ x: 0, y: titleHeight, width, height: Math.max(0, height - titleHeight) })
  }
  const updateVisibility = () => {
    if (!view || win.isDestroyed()) return
    const visible = wanted && ready
    if (view.getVisible() === visible) return
    view.setVisible(visible)
    const contents = visible ? view.webContents : win.webContents
    contents.focus()
  }
  const deliverRecord = () => {
    const contents = view?.webContents
    if (!pending || !contents || contents.isDestroyed() || contents.isLoadingMainFrame() || !sameSite(url, contents.getURL())) return
    const id = pending
    pending = undefined
    // Its own router reads this validated ID on mount or on receipt of the event.
    void contents.executeJavaScript(
      `window.__spDashboardRecord = ${JSON.stringify(id)}; window.dispatchEvent(new Event('sp-dashboard-record'))`,
    ).catch(() => {})
  }

  function ensureView() {
    if (view || win.isDestroyed()) return
    view = new WebContentsView({
      webPreferences: {
        session: win.webContents.session,
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
      },
    })
    const contents = view.webContents
    guardNavigation(contents)
    bindDashboardAgent(contents, url, openAgent)
    contents.on('did-stop-loading', deliverRecord)
    view.setVisible(false)
    win.contentView.addChildView(view)
    layout()
    void contents.loadURL(new URL('/', url).href).catch(() => {}).then(() => {
      ready = true
      updateVisibility()
    })
  }

  win.webContents.on('did-start-navigation', (details) => {
    if (details.isMainFrame && !details.isSameDocument) {
      wanted = false
      view?.setVisible(false)
    }
  })
  win.on('resize', layout)
  win.on('closed', () => {
    const contents = view?.webContents
    if (contents && !contents.isDestroyed()) contents.close()
  })

  return {
    preload: ensureView,
    show(visible, height) {
      titleHeight = height
      wanted = visible
      if (visible) ensureView()
      layout()
      updateVisibility()
    },
    open(id) {
      pending = id
      deliverRecord()
    },
  }
}

module.exports = { hostDashboard, shouldPreloadDashboard }
