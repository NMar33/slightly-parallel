import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { AgentDossier, type SectionId } from './dossier'
import { ActivityBadge, AgentIdentity, EditAgentButton, useDrawer, useTaskOpener } from './parts'
import { PersonalFrame, WalkRoster, type AgentPageData } from './personal'

import { t } from '../../i18n/scope/views'
/**
 * The agent's own page — the stage, standing on its own.
 *
 * What the stage overlay shows for an agent (identity, the headline, the
 * numbers, the folder, eight sections on a rail) is the page, so a link
 * to an agent lands on the same reading the operator already knows —
 * with the section in the URL (`#sec=chats`) and ← → walking the
 * project's roster. Chosen from four Lab shapes (v01).
 */

const SECTIONS: SectionId[] = ['overview', 'chats', 'files', 'decisions', 'tasks', 'work', 'links']

function readSec(): SectionId {
  if (typeof window === 'undefined') return 'overview'
  const m = /sec=([a-z]+)/.exec(window.location.hash)
  const v = m?.[1] as SectionId | undefined
  return v && SECTIONS.includes(v) ? v : 'overview'
}

export function AgentDossierPage() {
  const params = useParams<{ id: string }>()
  const id = params.id ? decodeURIComponent(params.id) : ''
  const [sec, setSec] = useState<SectionId>(readSec)
  // A new agent (← →) keeps the section; a new URL hash wins on load.
  useEffect(() => {
    const url = new URL(window.location.href)
    url.hash = sec === 'overview' ? '' : `sec=${sec}`
    window.history.replaceState(window.history.state, '', url.toString())
  }, [sec])

  return (
    <PersonalFrame id={id}>
      {(d) => <Dossier d={d} sec={sec} setSec={setSec} />}
    </PersonalFrame>
  )
}

function Dossier({ d, sec, setSec }: { d: AgentPageData; sec: SectionId; setSec: (s: SectionId) => void }) {
  const { p, code, range, peak, byId } = d
  const { open: openDrawer, drawer } = useDrawer()
  const { open: openTask, modal } = useTaskOpener(code)
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <header className="flex items-start gap-12 flex-wrap min-w-0">
        <AgentIdentity p={p} size="lg" linkTo={false} />
        <ActivityBadge p={p} />
        <span className="ml-auto flex items-center gap-8 flex-wrap">
          <WalkRoster d={d} />
          <EditAgentButton p={p} code={code} label />
          <Link to={`/project/${encodeURIComponent(code)}#agents`} className="text-11 font-mono text-tertiary hover:text-primary">{t('project →')}</Link>
          <Link to="/agent" className="text-11 font-mono text-tertiary hover:text-primary">{t('all agents →')}</Link>
        </span>
      </header>
      <div className="rounded-card border border-border-subtle bg-surface p-16 min-w-0">
        <AgentDossier
          p={p}
          range={range}
          peak={peak}
          byId={byId}
          onOpenLens={openDrawer}
          onOpenTask={openTask}
          section={sec}
          onSectionChange={setSec}
          hotkeys
        />
      </div>
      {drawer}
      {modal}
    </div>
  )
}

