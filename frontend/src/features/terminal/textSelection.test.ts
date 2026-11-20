import { afterEach, expect, it, vi } from 'vitest'
import type { Terminal } from 'xterm'
import { keepSelectionLocal } from './explicitClipboard'
import { enableTextSelection, hasTextSelectionAnchor, transferTextSelection } from './textSelection'

const mounted: { term: Terminal; host: HTMLElement }[] = []

async function terminal(text: string) {
  // Tests use xterm's DOM renderer. Its import probes canvas color parsing,
  // which jsdom does not implement and these selection tests do not use.
  const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  const XTerminal = await import('xterm').then((module) => module.Terminal).finally(() => getContext.mockRestore())
  const term = new XTerminal({ allowProposedApi: true, cols: 24, rows: 5 })
  const host = document.body.appendChild(document.createElement('div'))
  mounted.push({ term, host })
  term.open(host)
  await new Promise<void>((resolve) => term.write(text, resolve))
  return term
}

afterEach(() => {
  for (const { term, host } of mounted.splice(0)) {
    term.dispose()
    host.remove()
  }
  vi.restoreAllMocks()
})

it('uses the actual xterm selection service and only forces local or Shift selections', async () => {
  const term = await terminal('alpha')
  const service = (term as unknown as {
    _core: { _selectionService: { shouldForceSelection(event: MouseEvent): boolean } }
  })._core._selectionService
  const ordinary = new MouseEvent('mousedown', { button: 0 })
  let ownsMouse = true
  enableTextSelection(term, () => ownsMouse, true)
  expect(service.shouldForceSelection(ordinary)).toBe(true)
  expect(service.shouldForceSelection(new MouseEvent('mousedown', { button: 2 }))).toBe(false)
  ownsMouse = false
  expect(service.shouldForceSelection(ordinary)).toBe(false)
  expect(service.shouldForceSelection(new MouseEvent('mousedown', { button: 0, shiftKey: true }))).toBe(true)
  expect(hasTextSelectionAnchor(term)).toBe(false)
  term.select(0, 0, 5)
  expect(hasTextSelectionAnchor(term)).toBe(true)
})

it('transfers selection only if the mapped rows still contain the same text', async () => {
  const source = await terminal('alpha\r\nbravo')
  const target = await terminal('older\r\nalpha\r\nbravo')
  const changed = await terminal('older\r\nalpha\r\nother')
  source.select(0, 1, 5)
  expect(source.getSelection()).toBe('bravo')
  expect(transferTextSelection(source, target, (row) => row + 1)).toBe(true)
  expect(target.getSelection()).toBe('bravo')
  expect(target.getSelectionPosition()?.start.y).toBe(2)
  changed.select(0, 0, 5)
  expect(transferTextSelection(source, changed, (row) => row + 1)).toBe(false)
  expect(changed.getSelection()).toBe('older')
})

it('paints Linux mouse selection locally while keeping keyboard focus in the terminal', async () => {
  vi.spyOn(navigator, 'platform', 'get').mockReturnValue('Linux')
  const term = await terminal('alpha')
  const service = (term as unknown as {
    _core: { _selectionService: { refresh(publishToPrimary?: boolean): void } }
  })._core._selectionService
  const refresh = vi.spyOn(service, 'refresh')
  term.select(0, 0, 5)
  term.textarea!.blur()
  refresh.mockClear()
  keepSelectionLocal(term)
  service.refresh(true)
  expect(refresh).toHaveBeenCalledWith(false)
  expect(document.activeElement).toBe(term.textarea)
  expect(term.getSelection()).toBe('alpha')
})
