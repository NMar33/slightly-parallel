import type { ReactNode } from 'react'
import { Check, Copy } from 'lucide-react'

import { useCopy } from '../lib/useCopy'
import { t } from '../i18n/scope/shell'

/**
 * A button that copies text and shows a tick for 1.2 s.
 *
 * `text` may be a function, for text that is costly or only known at the
 * click. With a `label` the button reads "Copy …" and then `copiedLabel`;
 * without one it is the icon alone. The click never reaches the row it
 * sits in. The look is the caller's (`className`); the behaviour is here.
 */
export function CopyButton({
  text, title, ariaLabel, label, copiedLabel = t('Copied'), className = '', size = 11,
  onCopied, onFailed, icon, tick = true,
}: {
  text: string | (() => string)
  /** Tooltip, and the accessible name unless `ariaLabel` says otherwise. */
  title: string
  ariaLabel?: string
  label?: ReactNode
  copiedLabel?: ReactNode
  className?: string
  size?: number
  onCopied?: () => void
  onFailed?: () => void
  /** Replaces the copy icon; `null` for none (the tick still shows when copied). */
  icon?: ReactNode
  /** False where the caller says it another way (a toast) and nothing on the button moves. */
  tick?: boolean
}) {
  const { copied: landed, copy } = useCopy({ onCopied, onFailed })
  const copied = tick && landed
  return (
    <button
      type="button"
      title={title}
      aria-label={ariaLabel ?? title}
      onClick={(e) => {
        e.stopPropagation()
        void copy(typeof text === 'function' ? text() : text)
      }}
      className={className}
    >
      {copied
        ? <Check size={size} className="text-status-green shrink-0" aria-hidden />
        : (icon === undefined ? <Copy size={size} className="shrink-0" aria-hidden /> : icon)}
      {label !== undefined && (copied ? copiedLabel : label)}
    </button>
  )
}
