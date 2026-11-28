'use strict'

const { sameSite, webUrl } = require('./lib')

const PATH = '/_sp/terminal-agent/'
const AGENT = /^(?:(?:cc|codex|cursor)-[0-9a-f]{8}|oc-(?=[a-z]{0,7}[0-9])[0-9a-z]{8})$/
const TAB = /^t[0-9a-f]{8}$/

function terminalAgent(agent, tab) {
  if (typeof agent !== 'string' || AGENT.exec(agent)?.[0] !== agent) return null
  if (tab !== undefined && (typeof tab !== 'string' || TAB.exec(tab)?.[0] !== tab)) return null
  return { agent, tab }
}

/** The preload-free dashboard can request only an agent and optional tab ID. */
function bindDashboardAgent(contents, origin, open) {
  contents.on('dom-ready', () => {
    if (!sameSite(origin, contents.getURL())) return
    void contents.executeJavaScript(
      "window.__spDashboardAgentMenus = true; window.dispatchEvent(new Event('sp-dashboard-agent-menus'))",
    ).catch(() => {})
  })
  contents.on('will-frame-navigate', (event) => {
    const url = webUrl(event.url)
    if (!url || !sameSite(origin, url.href) || !url.pathname.startsWith(PATH)) return
    event.preventDefault()
    if (url.search || url.hash || !event.isMainFrame || event.frame !== contents.mainFrame ||
        event.initiator !== contents.mainFrame || !sameSite(origin, contents.getURL())) return
    const [agent, tab, ...extra] = url.pathname.slice(PATH.length).split('/')
    if (!extra.length) open(agent, tab)
  })
}

module.exports = { terminalAgent, bindDashboardAgent }
