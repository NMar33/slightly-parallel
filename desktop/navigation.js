'use strict'

const { shell } = require('electron')
const { sameSite, webUrl } = require('./lib')

const sessions = new WeakMap()

/** Document events miss javascript: in the current document. Keep all
 *  scripts in hosted documents on the server and block inline script URLs. */
function protectScripts(contents, origin) {
  const session = contents.session
  let owned = sessions.get(session)
  if (!owned) {
    owned = new Set()
    sessions.set(session, owned)
    session.webRequest.onHeadersReceived((details, done) => {
      if (!owned.has(details.webContentsId) || !sameSite(origin, details.url) ||
          (details.resourceType !== 'mainFrame' && details.resourceType !== 'subFrame')) return done({})
      const headers = { ...details.responseHeaders }
      const key = Object.keys(headers).find((name) => name.toLowerCase() === 'content-security-policy') ||
        'Content-Security-Policy'
      headers[key] = [...(headers[key] || []), "script-src 'self'"]
      done({ responseHeaders: headers })
    })
  }
  const id = contents.id
  owned.add(id)
  contents.once('destroyed', () => owned.delete(id))
}

function openExternal(value) {
  const url = webUrl(value)
  if (url) void shell.openExternal(url.href).catch(() => {})
}

/** Bind policy to the native contents before starting its first load. */
function guardNavigation(contents, origin, openPopup, onMainBlocked) {
  protectScripts(contents, origin)
  const check = (details) => {
    if (sameSite(origin, details.url)) return
    details.preventDefault()
    if (details.isMainFrame) {
      openExternal(details.url)
      onMainBlocked?.()
    }
  }
  contents.on('will-frame-navigate', check)
  contents.on('will-redirect', check)
  contents.setWindowOpenHandler(({ url, postBody }) => {
    if (sameSite(origin, url)) {
      if (!postBody) openPopup(url)
    } else openExternal(url)
    return { action: 'deny' }
  })
}

module.exports = { guardNavigation, openExternal }
