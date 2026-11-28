'use strict'

const { WebContentsView } = require('electron')
const { sameSite } = require('./lib')

function hostDashboard(win, url, guardNavigation) {
  const view = new WebContentsView({
    webPreferences: {
      session: win.webContents.session,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  })
  const contents = view.webContents
  const hide = () => view.setVisible(false)
  let titleHeight = 34
  let pending

  const layout = () => {
    const { width, height } = win.getContentBounds()
    view.setBounds({ x: 0, y: titleHeight, width, height: Math.max(0, height - titleHeight) })
  }
  const deliverRecord = () => {
    if (!pending || contents.isDestroyed() || contents.isLoadingMainFrame() || !sameSite(url, contents.getURL())) return
    const id = pending
    pending = undefined
    // There is no preload in this view. Its page reads this one validated ID
    // on mount or on receipt of the event and navigates using its own router.
    void contents.executeJavaScript(
      `window.__spDashboardRecord = ${JSON.stringify(id)}; window.dispatchEvent(new Event('sp-dashboard-record'))`,
    ).catch(() => {})
  }
  guardNavigation(contents)
  contents.on('did-stop-loading', deliverRecord)
  win.webContents.on('did-start-navigation', (details) => {
    if (details.isMainFrame && !details.isSameDocument) hide()
  })
  win.on('resize', layout)
  win.on('closed', () => { if (!contents.isDestroyed()) contents.close() })
  hide()
  win.contentView.addChildView(view)
  layout()
  void contents.loadURL(new URL('/', url).href).catch(() => {})

  return {
    show(visible, height) {
      titleHeight = height
      layout()
      const changed = view.getVisible() !== visible
      view.setVisible(visible)
      if (changed) (visible ? contents : win.webContents).focus()
    },
    open(id) {
      pending = id
      deliverRecord()
    },
  }
}

module.exports = { hostDashboard }
