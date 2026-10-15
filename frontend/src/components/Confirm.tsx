/**
 * The one way a page asks before it destroys something.
 *
 * An inline row in place of the control that was pressed: what will happen
 * in a sentence, the act named on a red button, and Cancel. No browser
 * dialog — it blocks the page and cannot say what is lost. The caller keeps
 * the state (what is being asked) and renders this while it is set.
 */
export function Confirm({ text, action, busy = false, onYes, onNo }: {
  /** What happens, and what is lost. */
  text: string
  /** The word on the button: Remove, Delete, Archive. */
  action: string
  busy?: boolean
  onYes: () => void
  onNo: () => void
}) {
  return (
    <div role="group" aria-label={action}
      className="flex items-center gap-8 flex-wrap rounded-input border border-border-subtle bg-elevated px-12 py-8">
      <span className="text-12 text-secondary min-w-0">{text}</span>
      <button type="button" disabled={busy} onClick={onYes}
        className="ml-auto h-24 px-10 rounded-input bg-status-red text-on-brand text-12 hover:opacity-90 disabled:opacity-40">
        {action}
      </button>
      <button type="button" onClick={onNo}
        className="h-24 px-8 rounded-input text-12 text-tertiary hover:text-primary hover:bg-hover">
        Cancel
      </button>
    </div>
  )
}
