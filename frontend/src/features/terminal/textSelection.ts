import type { Terminal } from 'xterm'

type Cell = [column: number, row: number]
type Model = {
  selectionStart: Cell | undefined
  selectionEnd: Cell | undefined
  selectionStartLength: number
  isSelectAllActive: boolean
}
type Service = {
  _model: Model
  _enabled: boolean
  _activeSelectionMode: number
  _dragScrollIntervalTimer?: number
  _handleMouseUp: (event: MouseEvent) => void
  handleMouseDown: (event: MouseEvent) => void
  shouldForceSelection: (event: MouseEvent) => boolean
  refresh: () => void
}

// xterm 5.3 exposes the sorted selection bounds, but not its original anchor
// or a way to restore it. Keep the private dependency here and fall back to
// the terminal's built-in selection if this API changes.
function serviceOf(term: Terminal): Service | undefined {
  const core = term as unknown as { _core?: { _selectionService?: Service } }
  const service = core._core?._selectionService
  return service?._model && typeof service._enabled === 'boolean' &&
    typeof service.refresh === 'function' && typeof service.handleMouseDown === 'function' &&
    typeof service.shouldForceSelection === 'function' ? service : undefined
}

export function enableTextSelection(term: Terminal, ownOrdinarySelection: () => boolean, tmux = false, tmuxSelecting?: () => boolean): void {
  const service = serviceOf(term)
  if (!service) return
  const mouseDown = service.handleMouseDown.bind(service)
  const forceSelection = service.shouldForceSelection.bind(service)
  const extendsTmux = (event: MouseEvent) => event.button === 0 && event.shiftKey && tmuxSelecting?.() && !service._model.selectionStart
  const selectsHere = (event: MouseEvent) => event.button === 0 && !extendsTmux(event) &&
    (event.shiftKey || (!event.ctrlKey && !event.metaKey && ownOrdinarySelection()))
  let selectedHere = false
  if (tmux && typeof service._handleMouseUp === 'function') {
    term.element?.addEventListener('mouseup', (event) => {
      if (event.button !== 0 || !selectedHere || service._dragScrollIntervalTimer === undefined) return
      selectedHere = false
      // xterm reports a release over its element even when the matching
      // press stayed local. That report clears selection before the native
      // selection handler on the document runs. Finish it here instead.
      service._handleMouseUp(event)
      event.stopImmediatePropagation()
    }, true)
  }
  service.shouldForceSelection = (event) => !extendsTmux(event) && (selectsHere(event) || forceSelection(event))
  service.handleMouseDown = (event) => {
    const enabled = service._enabled
    const local = selectsHere(event)
    if (event.button === 0) selectedHere = local
    // When Shift is the first press, start a selection instead of trying
    // to extend an anchor that doesn't exist yet.
    const enableForPress = !event.shiftKey || !!service._model.selectionStart
    if (!local || enabled === enableForPress) {
      mouseDown(event)
      return
    }
    // Keep tmux mouse reporting enabled. Let xterm interpret just this
    // press as a selection, including its existing Shift-click behavior.
    service._enabled = enableForPress
    try { mouseDown(event) } finally { service._enabled = enabled }
  }
}

export function hasTextSelectionAnchor(term: Terminal): boolean {
  return !!serviceOf(term)?._model.selectionStart
}

export function transferTextSelection(from: Terminal, to: Terminal, mapRow: (row: number) => number | undefined): boolean {
  const source = serviceOf(from)
  const target = serviceOf(to)
  if (!source || !target || from.cols !== to.cols || source._model.isSelectAllActive) return false

  const mapCell = (cell: Cell | undefined): Cell | undefined => {
    if (!cell) return undefined
    const row = mapRow(cell[1])
    if (row === undefined || row < 0 || row >= to.buffer.active.length) return undefined
    const original = from.buffer.active.getLine(cell[1])?.translateToString(true)
    const replacement = to.buffer.active.getLine(row)?.translateToString(true)
    // Output can move the pane while its history snapshot is being made.
    return original === replacement ? [cell[0], row] : undefined
  }
  const start = mapCell(source._model.selectionStart)
  const end = mapCell(source._model.selectionEnd)
  if (!start || (source._model.selectionEnd && !end)) return false
  target._model.selectionStart = start
  target._model.selectionEnd = end
  target._model.selectionStartLength = source._model.selectionStartLength
  target._model.isSelectAllActive = false
  target._activeSelectionMode = source._activeSelectionMode
  target.refresh()
  return true
}
