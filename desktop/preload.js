'use strict'
/** The page's way to its window: `window.spWindow.postMessage({op, …})`.
 *  Nothing else of Electron or Node reaches the page. */
const { contextBridge, ipcRenderer } = require('electron')

const OPS = new Set(['drag', 'close', 'minimize', 'title', 'grow', 'detach', 'open'])

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

contextBridge.exposeInMainWorld('spWindow', { postMessage })
