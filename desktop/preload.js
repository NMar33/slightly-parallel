'use strict'
/** The page's way to its window: `window.spWindow.postMessage({op, …})`.
 *  Nothing else of Electron or Node reaches the page. */
const { contextBridge, ipcRenderer } = require('electron')

const OPS = new Set(['drag', 'close', 'minimize', 'fullscreen', 'title', 'grow', 'detach', 'open', 'restore'])

function postMessage(msg) {
  if (!msg || typeof msg !== 'object' || !OPS.has(msg.op)) return
  if (msg.op === 'drag') {
    // The window follows the pointer until the button is let go, here or
    // anywhere: the page never has to say that the drag is over.
    const end = () => {
      window.removeEventListener('pointerup', end, true)
      window.removeEventListener('blur', end, true)
      ipcRenderer.send('sp-window', { op: 'drag-end' })
    }
    window.addEventListener('pointerup', end, true)
    window.addEventListener('blur', end, true)
  }
  ipcRenderer.send('sp-window', JSON.parse(JSON.stringify(msg)))
}

/** Read only: the window's processes, their memory (KB) and CPU (%), for
 *  the terminal log (frontend/src/features/terminal/telemetry.ts). */
function metrics() {
  return ipcRenderer.invoke('sp-metrics')
}

/** How many windows of last time wait for the operator's answer (Settings ›
 *  Terminal › On start: ask). Only the main window is asked; the answer is
 *  `postMessage({op: 'restore', open})`. */
function restoreOffer() {
  return ipcRenderer.invoke('sp-restore-offer')
}

function saveDraft(name, text) {
  return ipcRenderer.invoke('sp-save-draft', name, text)
}

function observeFullscreen(receive) {
  let current = true
  let changed = false
  const listener = (_event, value) => { changed = true; receive(value === true) }
  ipcRenderer.on('sp-fullscreen-changed', listener)
  void ipcRenderer.invoke('sp-fullscreen').then((value) => {
    if (current && !changed) receive(value === true)
  }).catch(() => {})
  return () => {
    current = false
    ipcRenderer.removeListener('sp-fullscreen-changed', listener)
  }
}

function setDashboardView(visible, titleHeight) {
  ipcRenderer.send('sp-dashboard-view', visible === true, titleHeight)
}

function openDashboardRecord(id) {
  ipcRenderer.send('sp-dashboard-record', id)
}

function openAgentTerminal(agent, tab) {
  ipcRenderer.send('sp-terminal-agent', agent, tab)
}

function observeAgentTerminal(receive) {
  const listener = (_event, target) => receive(target)
  ipcRenderer.on('sp-terminal-agent-selected', listener)
  return () => ipcRenderer.removeListener('sp-terminal-agent-selected', listener)
}

if (location.pathname === '/term') {
  contextBridge.exposeInMainWorld('spWindow', {
    postMessage, metrics, restoreOffer, saveDraft, observeFullscreen, setDashboardView, openDashboardRecord,
    openAgentTerminal, observeAgentTerminal,
  })
}
