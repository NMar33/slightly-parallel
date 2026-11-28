import { createContext, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export const DASHBOARD_FRAME = 'sp-dashboard'
const SIDE_KEY = 'sp-aqua-window-side'
const READY = 'sp-dashboard-ready'
const OPEN_RECORD = 'sp-dashboard-open-record'
const OPENED_RECORD = 'sp-dashboard-opened-record'

export const DashboardRecord = createContext<((id: string) => boolean) | null>(null)

function recordPath(id: unknown): string {
  if (typeof id !== 'string') return ''
  if (/^tk_[0-9a-f]{8}$/.test(id)) return `/kanban?task=${id}`
  if (/^nt_[0-9a-f]{8}$/.test(id)) return `/notes?note=${id}`
  return ''
}

export function useDashboard(enabled: boolean) {
  const frame = useRef<HTMLIFrameElement>(null)
  const pending = useRef<string>()
  const [shown, setShown] = useState(() => {
    try { return enabled && localStorage.getItem(SIDE_KEY) === 'dashboard' } catch { return false }
  })

  const show = useCallback((dashboard: boolean) => {
    setShown(dashboard)
    try { localStorage.setItem(SIDE_KEY, dashboard ? 'dashboard' : 'terminal') } catch { /* storage is optional */ }
  }, [])

  const sendRecord = useCallback(() => {
    if (pending.current) {
      frame.current?.contentWindow?.postMessage({ type: OPEN_RECORD, id: pending.current }, window.location.origin)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow) return
      if (event.data === READY) sendRecord()
      else if (event.data?.type === OPENED_RECORD && event.data.id === pending.current) pending.current = undefined
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [enabled, sendRecord])

  const openRecord = useCallback((id: string) => {
    if (!enabled || !recordPath(id)) return false
    pending.current = id
    sendRecord()
    show(true)
    return true
  }, [enabled, sendRecord, show])

  return { frame, shown: enabled && shown, show, openRecord }
}

/** Keep record opens on the dashboard's own router so its document stays alive. */
export function useDashboardRecordNavigation() {
  const navigate = useNavigate()
  useEffect(() => {
    if (window.frameElement?.getAttribute('name') !== DASHBOARD_FRAME) return

    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== window.parent || event.data?.type !== OPEN_RECORD) return
      const path = recordPath(event.data.id)
      if (!path) return
      void navigate(path)
      window.parent.postMessage({ type: OPENED_RECORD, id: event.data.id }, window.location.origin)
    }
    window.addEventListener('message', receive)
    window.parent.postMessage(READY, window.location.origin)
    return () => window.removeEventListener('message', receive)
  }, [navigate])
}
