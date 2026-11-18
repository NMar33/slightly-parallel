'use strict'
/** The page's way to its window: `window.spWindow.postMessage({op, …})`.
 *  Nothing else of Electron or Node reaches the page. */
const { contextBridge, ipcRenderer } = require('electron')

const OPS = new Set(['drag', 'close', 'minimize', 'title', 'grow', 'detach', 'open', 'restore'])

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

contextBridge.exposeInMainWorld('spWindow', { postMessage, metrics, restoreOffer })
