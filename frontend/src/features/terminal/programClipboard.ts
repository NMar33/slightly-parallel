import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { t as shellText } from '../../i18n/scope/shell'
import { t } from '../../i18n/scope/system'
import { useStrSetting } from '../../lib/settings'
import { copyText, writeClipboard } from '../../lib/useCopy'

export function useProgramClipboard(sid: string, visible: boolean, program: string) {
  const mode = useStrSetting('terminal.program_clipboard', 'block')
  const config = useRef({ visible, mode, program })
  config.current = { visible, mode, program }
  const prompt = `terminal-clipboard-${sid}`
  const readingSelection = useRef<{ received?: string }>()
  const explicit = useRef<{ text: string; until: number }>()
  useEffect(() => () => { toast.dismiss(prompt) }, [mode, prompt, visible])

  const offer = useCallback((text: string) => {
    const { visible, program, mode } = config.current
    if (!visible || (mode !== 'allow' && mode !== 'ask')) return
    const name = program || t('Terminal program')
    const copy = async () => {
      const id = `${prompt}-result`
      if (await writeClipboard(text)) toast.success(t('{program} copied text', { program: name }), { id })
      else toast.error(shellText('The browser did not allow copying. Select the text and copy it by hand.'), { id })
    }
    if (mode === 'allow') void copy()
    else toast.info(t('{program} wants to copy text', { program: name }), {
      id: prompt,
      action: { label: t('Copy'), onClick: () => { if (config.current.visible && config.current.mode === 'ask') void copy() } },
    })
  }, [prompt])

  const receive = useCallback((data: string) => {
    if (!config.current.visible || config.current.mode === 'block') return true
    const encoded = data.slice(data.indexOf(';') + 1)
    if (!encoded || encoded === '?') return true
    try {
      const text = new TextDecoder().decode(Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)))
      const last = explicit.current
      if (last?.text === text && last.until > performance.now()) return true
      // tmux can echo an explicit selection as OSC 52 before the API returns it.
      if (readingSelection.current) readingSelection.current.received = text
      else offer(text)
    } catch { /* invalid encoding */ }
    return true
  }, [offer])

  const copySelection = useCallback(async (read: () => Promise<string | null>) => {
    if (readingSelection.current) return true
    const request: { received?: string } = {}
    readingSelection.current = request
    let text: string | null = null
    try {
      text = await read()
      if (text === null) return false
      explicit.current = { text, until: performance.now() + 1000 }
      await copyText(text)
      return true
    } finally {
      readingSelection.current = undefined
      if (request.received !== undefined && request.received !== text) offer(request.received)
    }
  }, [offer])

  return { receive, copySelection }
}
