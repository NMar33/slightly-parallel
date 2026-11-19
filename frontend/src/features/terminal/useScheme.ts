/**
 * The terminal's colour scheme as the page reads it (tk_83077846): the
 * settings `terminal.scheme` and `terminal.scheme_scope`, read from
 * /api/settings like any setting.
 *
 * A pick applies at once, in every window: this page's settings are patched
 * before the server answers, and the other windows of Slightly Parallel (the
 * terminal window at /term, a second browser tab) hear it on a
 * BroadcastChannel and read the settings again. A window coming to the front
 * reads them again too, in case a message was missed.
 */

import { useEffect } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { SETTINGS_CHANNEL, SETTINGS_QUERY_KEY, saveSettings, useSettingsValues } from '../../lib/settings'
import { t } from '../../i18n/scope/aqua'
import { DEFAULT_SCHEME, isSchemeId, schemeOf, termTokens, type Scheme, type SchemeScope } from './schemes'

export const SCHEME_KEY = 'terminal.scheme'
export const SCOPE_KEY = 'terminal.scheme_scope'

type Payload = { groups: Array<{ name: string; settings: Array<{ key: string; value: unknown }> }> }

/** The scheme and where it applies; sp-now and the terminal only until settings load. */
export function useTermScheme(): { scheme: Scheme; scope: SchemeScope } {
  const values = useSettingsValues()
  useSettingsSync()
  const id = values?.[SCHEME_KEY]
  return {
    scheme: schemeOf(isSchemeId(id) ? id : DEFAULT_SCHEME),
    scope: values?.[SCOPE_KEY] === 'window' ? 'window' : 'terminal',
  }
}

let listeners = 0
let channel: BroadcastChannel | null = null

/** One channel and one focus listener per page, however many screens read the scheme. */
function useSettingsSync() {
  const qc = useQueryClient()
  useEffect(() => {
    const again = () => void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
    listeners += 1
    if (listeners === 1 && typeof BroadcastChannel !== 'undefined') {
      try { channel = new BroadcastChannel(SETTINGS_CHANNEL) } catch { channel = null }
    }
    channel?.addEventListener('message', again)
    window.addEventListener('focus', again)
    return () => {
      channel?.removeEventListener('message', again)
      window.removeEventListener('focus', again)
      listeners -= 1
      if (listeners === 0) { channel?.close(); channel = null }
    }
  }, [qc])
}

function patch(qc: QueryClient, values: Record<string, string>) {
  qc.setQueryData<Payload>(SETTINGS_QUERY_KEY, (old) => old && ({
    ...old,
    groups: old.groups.map((g) => ({ ...g, settings: g.settings.map((s) => (s.key in values ? { ...s, value: values[s.key] } : s)) })),
  }))
}

/** Pick a scheme or a scope: shown at once here, saved, then told to the other windows. */
export async function saveScheme(qc: QueryClient, values: { scheme?: string; scope?: SchemeScope }) {
  const v: Record<string, string> = {}
  if (values.scheme) v[SCHEME_KEY] = values.scheme
  if (values.scope) v[SCOPE_KEY] = values.scope
  const before = qc.getQueryData<Payload>(SETTINGS_QUERY_KEY)
  patch(qc, v)
  try {
    await saveSettings(v)
  } catch (e) {
    if (before) qc.setQueryData(SETTINGS_QUERY_KEY, before)
    toast.error(t('The colour scheme was not saved: {error}', { error: e instanceof Error ? e.message : String(e) }))
    return false
  }
  void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
  return true
}

/**
 * The page's terminal tokens on the root (--term-ground and its kin, and
 * --sp-term-bg, the ground every screen and drawer paints): the drawer's
 * bars, the find box and the menus follow the scheme. sp-now leaves the
 * skin's own tokens alone.
 */
export function useApplyTermScheme() {
  const { scheme } = useTermScheme()
  useEffect(() => {
    const root = document.documentElement
    const vars = { ...termTokens(scheme), '--sp-term-bg': scheme.bg }
    for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v)
    return () => { for (const k of Object.keys(vars)) root.style.removeProperty(k) }
  }, [scheme])
}
