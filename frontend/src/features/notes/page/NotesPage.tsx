/**
 * Notes — the long texts agents write for the operator (tk_3e544086): context
 * to come back to, a text to paste, a review with pictures, a plan for
 * helpers, a report, the steps only the operator can do. An agent writes
 * one with the MCP tool note_write; the operator reads, ticks, answers and
 * copies here.
 *
 * The page is the design round's K · Zoom on the server's notes: the list,
 * an endless feed of whole notes and the outline following the note in
 * view; the lines between the columns fold them; Group by task; one switch,
 * Reading | Tiles, flips to the notes as tiles shelved by what you do and
 * back to the same section. The address keeps it all
 * (`&by=task&hide=…&view=tiles&note=…&at=…`). Archived notes open with
 * `?archived=1`. The design round's variants stay at /notes/design?v=….
 */

import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { NotebookText } from 'lucide-react'

import { PageHeader } from '../../../components/PageHeader'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { t, tn } from '../../../i18n/scope/notes'
import type { Guide } from '../../visions/guides'
import { PageGuide } from '../../visions/parts'
import { Workspace3 } from '../render/Workspace'
import { toNote, useNotesFeed } from './data'
import { ServerNoteEnv } from './ServerEnv'

const GUIDE: Guide = {
  intro: [
    t('Long texts agents write for you: context for later, a text to paste into another chat, a review with pictures, a plan for helpers, a report, the actions only you can do.'),
    t('Read them one after another; the list and the outline follow the note in view. The switch in the toolbar shows them as tiles, shelved by what you do with each.'),
  ],
  parts: [
    [t('Chips'), t('task, entry point, decision and publish ids show their title and status now.')],
    [t('To paste'), t('a block with a copy button; it copies the text as written, ids and all.')],
    [t('To tick, to answer'), t('checklists and numbered choices; the server keeps the marks.')],
    [t('Pictures, diagrams, folds'), t('a picture series with captions, a diagram, sections folded until opened.')],
  ],
  steps: [
    t('An agent writes a note instead of a long reply or a file, with the tool note_write; the chat says one line and the note\'s id.'),
    t('A new version keeps the ticks and answers of items whose text did not change.'),
    t('The agent reads your ticks and answers back with the tool notes. A task\'s notes show in its window.'),
  ],
}

export function NotesPage() {
  const [params] = useSearchParams()
  const archived = params.get('archived') === '1'
  const feed = useNotesFeed({ archived })
  useEffect(() => { document.title = `${t('Notes')} — Slightly Parallel` }, [])
  const notes = (feed.data?.notes ?? []).map((w) => toNote(w))
  const body = (() => {
    if (feed.isPending) return <LoadingSkeleton variant="card" count={3} label={t('Loading the notes')} />
    if (feed.isError) return <ErrorBanner title={t('Could not load the notes.')} message={String((feed.error as Error).message)} onRetry={() => void feed.refetch()} hideDismiss />
    if (!notes.length) {
      return <EmptyState icon={<NotebookText size={24} />} title={archived ? t('No archived notes.') : t('No notes yet.')}
        subtitle={t('An agent writes a note when a text is too long for the chat or is one you will read again: context for later, a text to paste, a plan, a report, steps for you. It calls the Slightly Parallel tool note_write, and the note appears here with its task and chat. The skill write-a-note tells it how.')} />
    }
    return <Workspace3 v="k" notes={notes} initial={params.get('note') ?? undefined} initialAt={params.get('at') ?? undefined} />
  })()
  return (
    <ServerNoteEnv feed={feed.data}>
      <div className="flex flex-col gap-16 min-w-0">
        <PageHeader variant="lens" icon={NotebookText} title={archived ? t('Archived notes') : t('Notes')}
          count={feed.data ? tn(notes.length, '{n} note', '{n} notes') : undefined}
          below={(
            <Link to={archived ? '/notes' : '/notes?archived=1'} className="self-start text-12 text-tertiary hover:text-brand">
              {archived ? t('Notes') : t('Archived')}
            </Link>
          )} />
        <PageGuide id="notes" guide={GUIDE} examples={0} />
        {body}
      </div>
    </ServerNoteEnv>
  )
}
