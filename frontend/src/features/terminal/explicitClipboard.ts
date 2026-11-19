import type { Terminal } from 'xterm'

type SelectionService = { refresh(publishToPrimary?: boolean): void }
type XtermCore = { _core?: { _selectionService?: SelectionService } }

/** Let xterm paint the selection without claiming Linux's PRIMARY clipboard. */
export function keepSelectionLocal(term: Terminal): void {
  const selection = (term as unknown as XtermCore)._core?._selectionService
  if (!selection || !/Linux/.test(navigator.platform)) return
  const refresh = selection.refresh.bind(selection)
  selection.refresh = (publishToPrimary) => {
    // The upstream handler also focuses the terminal before publishing.
    if (publishToPrimary && term.hasSelection() && term.textarea?.ownerDocument.activeElement !== term.textarea) term.focus()
    refresh(false)
  }
}
