import { useEffect } from 'react'

import { ChatsPage } from '../features/chats/ChatsPage'
import { t } from '../i18n/scope/pages'

/**
 * /chats — the captured chats, read as a day book. /sessions answers here
 * too: it is the address the page had until 2026-09-24, and an address
 * Slightly Parallel has published is never taken away.
 *
 * The page opens the way /scans and /standups open — title, guide, month —
 * so a month of chats looks like the same month wherever it is read. Beside
 * the month: the agents, and what a chat holds. The body is shared with the
 * Lab variant it was chosen from.
 */
export default function SessionsPage() {
  useEffect(() => {
    document.title = `${t('Chats')} — Slightly Parallel`
  }, [])
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <ChatsPage />
    </div>
  )
}
