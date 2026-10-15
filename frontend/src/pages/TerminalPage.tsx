import { useEffect } from 'react'
import { SquareTerminal } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { TerminalPage as Page } from '../features/terminal/Deck'
import { TERMINAL_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t } from '../i18n/scope/pages'

/**
 * /terminal — every terminal, in a list by project beside the one open.
 * The drawer (`) is the terminal on every other page.
 */
export default function TerminalPage() {
  useEffect(() => { document.title = `${t('Terminal')} — Slightly Parallel` }, [])
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader variant="lens" icon={SquareTerminal} title={t('Terminal')}>
        <span className="text-12 text-tertiary">{t('` shows the terminal on any page')}</span>
      </PageHeader>
      <PageGuide id="terminal" guide={TERMINAL_GUIDE} examples={0} />
      <Page />
    </div>
  )
}
