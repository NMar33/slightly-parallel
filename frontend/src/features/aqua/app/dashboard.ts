import { createContext, useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { openDashboardRecord } from './bridge'

const SIDE_KEY = 'sp-aqua-window-side'

declare global {
  interface Window {
    __spDashboardRecord?: string
  }
}

export const DashboardRecord = createContext<((id: string) => boolean) | null>(null)

function recordPath(id: unknown): string {
  if (typeof id !== 'string' || id.length !== 11) return ''
  if (/^tk_[0-9a-f]{8}$/.test(id)) return `/kanban?task=${id}`
  if (/^nt_[0-9a-f]{8}$/.test(id)) return `/notes?note=${id}`
  return ''
}

export function useDashboard(enabled: boolean) {
  const [shown, setShown] = useState(() => {
    try { return enabled && localStorage.getItem(SIDE_KEY) === 'dashboard' } catch { return false }
  })

  const show = useCallback((dashboard: boolean) => {
    setShown(dashboard)
    try { localStorage.setItem(SIDE_KEY, dashboard ? 'dashboard' : 'terminal') } catch { /* storage is optional */ }
  }, [])

  const openRecord = useCallback((id: string) => {
    if (!enabled || !recordPath(id)) return false
    openDashboardRecord(id)
    show(true)
    return true
  }, [enabled, show])

  return { shown: enabled && shown, show, openRecord }
}

/** Native opens route the already loaded dashboard by record ID. */
export function useDashboardRecordNavigation() {
  const navigate = useNavigate()
  useEffect(() => {
    const receive = () => {
      const id = window.__spDashboardRecord
      delete window.__spDashboardRecord
      const path = recordPath(id)
      if (path) void navigate(path)
    }
    window.addEventListener('sp-dashboard-record', receive)
    receive()
    return () => window.removeEventListener('sp-dashboard-record', receive)
  }, [navigate])
}
