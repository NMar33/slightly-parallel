import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { t } from '../i18n/scope/shell'

/**
 * The one way text reaches the clipboard.
 *
 * `writeClipboard` is the bare write: true when it landed, false when the
 * browser refused (the text on the page stays selectable). `useCopy` adds
 * the tick every copy control shows for 1.2 s. What a caller says besides
 * the tick — a toast, an error — is its own; `onCopied` and `onFailed` are
 * where it says it.
 */

export const COPIED_MS = 1200

export async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) return false
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/**
 * Copy, and say so in a toast — `said` when it landed, a plain word when
 * the browser refused (the text on the page stays selectable).
 */
export async function copyText(text: string, said?: string): Promise<boolean> {
  const ok = await writeClipboard(text)
  if (ok) toast.success(said ?? t('Copied'))
  else toast.error(t('The browser did not allow copying. Select the text and copy it by hand.'))
  return ok
}

interface CopyOptions {
  onCopied?: () => void
  onFailed?: () => void
}

export function useCopy(options: CopyOptions = {}): {
  copied: boolean
  copy: (text: string) => Promise<boolean>
} {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latest = useRef(options)
  latest.current = options
  // The clipboard answers later: a control gone by then sets no tick and no timer.
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; if (timer.current) clearTimeout(timer.current) }
  }, [])

  const copy = useCallback(async (text: string) => {
    const ok = await writeClipboard(text)
    if (!mounted.current) return ok
    if (!ok) {
      latest.current.onFailed?.()
      return false
    }
    setCopied(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), COPIED_MS)
    latest.current.onCopied?.()
    return true
  }, [])

  return { copied, copy }
}
