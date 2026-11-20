/**
 * Notes — the design round (tk_3e544086). Five variants of the Notes page
 * behind a switch, each a different organising idea, and the compact form
 * a task's notes take in the task window. Mock data: no server, no MCP.
 *
 *   /notes/design?v=a  Reader   — a note is a document: list, reading width, outline rail
 *   /notes/design?v=b  Queue    — what waits on you, working in place; the rest for reference
 *   /notes/design?v=c  Topics   — by entry point: a dossier per subject, newest note in full
 *   /notes/design?v=d  Feed     — day by day, cards that already show what is open
 *   /notes/design?v=e  Handoff  — by what you do: paste, hand to helpers, by hand, decide
 *   /notes/design?v=task        — a task's notes in the task window
 *
 * Round 2, on the basis of A (round2/Workspace.tsx): an endless feed in the
 * middle, the list and the feed can be hidden, tiles when the feed is.
 *
 *   /notes/design?v=f  Scroll   — a two-button switch; shelves by project; the rail shows the note's task
 *   /notes/design?v=g  Waiting  — hide buttons on the columns; the feed opens with what waits on you; shelves by what you do
 *   /notes/design?v=h  Tasks    — list and feed grouped by task; shelves of tasks opening the task window's notes
 *   /notes/design?v=i  Modes    — one four-mode control; a by-task filter; shelves by entry point
 *
 * Round 3, on the basis of F (round3/Workspace3.tsx): a group-by-task switch,
 * the line between columns folds the side column, and three ways to move
 * between reading and the tiles.
 *
 *   /notes/design?v=j  Switch        — the Entry points page's read | tiles switch in the toolbar
 *   /notes/design?v=k  Zoom          — o or the tab on the feed's top edge zooms out; the line read flies into its tile
 *   /notes/design?v=l  Shelves first — the page opens on the shelves; a tile drills into reading under a breadcrumb
 *
 * `?state=empty|loading|error` shows the page's other states.
 */

import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { NotebookText } from 'lucide-react'

import { PageHeader } from '../../../components/PageHeader'
import { Segmented } from '../../../components/Segmented'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { t, tn } from '../../../i18n/scope/notes'
import type { Guide } from '../../visions/guides'
import { PageGuide } from '../../visions/parts'
import { ENTITIES, NOTES, SEED } from './mock'
import { MockNoteEnv } from './MockEnv'
import { resetMarks } from './store'
import { TaskNotes } from './TaskNotes'
import { Feed } from './variants/Feed'
import { Handoff } from './variants/Handoff'
import { Queue } from './variants/Queue'
import { Reader } from './variants/Reader'
import { Topics } from './variants/Topics'
import { IdChip } from './blocks'
import { Workspace } from './round2/Workspace'
import { Workspace3 } from './round3/Workspace3'

resetMarks(SEED)

export type VariantKey = 'a' | 'b' | 'c' | 'd' | 'e' | 'task' | 'f' | 'g' | 'h' | 'i' | 'j' | 'k' | 'l'
export const VARIANTS: Array<readonly [VariantKey, string, string]> = [
  ['a', t('A · Reader'), t('A note is a document: the list, the note at reading width, the outline with what is open')],
  ['b', t('B · Queue'), t('What waits on you, working in place; every other note for reference')],
  ['c', t('C · Topics'), t('By entry point: a dossier per subject, the newest note in full')],
  ['d', t('D · Feed'), t('Day by day: cards that already show what is open, the whole note in place')],
  ['e', t('E · Handoff'), t('By what you do: paste into a chat, hand to helpers, do by hand, decide')],
  ['task', t('Task window'), t('A task\'s notes inside the task window, the same for every variant')],
  ['f', t('F · Scroll'), t('A on an endless feed: the list and the outline follow the note in view; l hides the list, f the feed for tiles by project; the rail shows the note\'s task')],
  ['g', t('G · Waiting'), t('The feed opens with what waits on you, task by task, as in the task window; each column has its hide button; tiles by what you do')],
  ['h', t('H · Tasks'), t('The list and the feed grouped by task under a task band; tiles shelved by task, the first tile opening the task window\'s notes')],
  ['i', t('I · Modes'), t('One control: all three, reading, list and tiles, tiles; a by-task filter puts the task window\'s notes over the feed; tiles by entry point')],
  ['j', t('J · Switch'), t('F with a group-by-task switch; the line between columns folds the list or the outline; the Entry points switch in the toolbar flips reading and tiles (o)')],
  ['k', t('K · Zoom'), t('F with a group-by-task switch and folding lines; o or the tab on the feed\'s top edge zooms out to the tiles, the line you read flying into its tile; a tile or Esc zooms back in')],
  ['l', t('L · Shelves first'), t('F with a group-by-task switch and folding lines; the page opens on the shelves, what waits on you first; a tile drills into reading under a breadcrumb, Esc goes back')],
]
const isVariant = (v: string | null): v is VariantKey => VARIANTS.some(([k]) => k === v)

const GUIDE: Guide = {
  intro: [
    t('Long texts agents write for you: context for later, a text to paste into another chat, a review with pictures, a plan for helpers, a report, the actions only you can do.'),
    t('Design round: five ways to lay the page out, on mock notes. The switch under the title changes the variant; ticks and answers carry across.'),
  ],
  parts: [
    [t('Chips'), t('task, entry point, decision and publish ids show their title and status now.')],
    [t('To paste'), t('a block with a copy button; it copies the text as written, ids and all.')],
    [t('To tick, to answer'), t('checklists and numbered choices; the server keeps the marks.')],
    [t('Pictures, diagrams, folds'), t('a picture series with captions, a diagram, sections folded until opened.')],
  ],
  steps: [
    t('An agent writes a note through one MCP tool, linked to its task, chat, entry point and project.'),
    t('A new version keeps the ticks and answers of items whose text did not change.'),
    t('A note can be attached to a Publish card.'),
  ],
}

function TaskWindowMock() {
  const [task, setTask] = useState('tk_51b87348')
  const tasks = ['tk_51b87348', 'tk_fc2d244e', 'tk_9b20e4f1', 'tk_2c7d90a1']
  const e = ENTITIES[task]!
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <Segmented label={t('Task')} shape="pill" value={task} onChange={setTask}
        options={tasks.map((id) => [id, id, ENTITIES[id]?.title] as const)} className="self-start max-w-full overflow-x-auto" />
      <div role="dialog" aria-label={e.title} className="w-full max-w-[760px] rounded-modal border border-border-default bg-elevated shadow-lg p-14 flex flex-col gap-10 min-w-0">
        <div className="flex items-center gap-8 min-w-0"><IdChip id={task} full /></div>
        <div className="flex items-center gap-4 flex-wrap">
          {['todo', 'doing', 'done'].map((s) => (
            <span key={s} className={`text-11 font-mono px-8 h-20 inline-flex items-center rounded-pill border ${s === e.status ? 'border-brand text-brand bg-brand-glow' : 'border-border-subtle text-tertiary'}`}>{s}</span>
          ))}
        </div>
        <div className="text-16 font-semibold text-primary">{e.title}</div>
        <div className="h-48 rounded-input border border-border-subtle bg-surface" aria-hidden />
        {[t('Evidence'), t('Links'), t('Story')].map((w) => <div key={w} className="border-t border-border-subtle pt-8 text-10 uppercase tracking-wide font-mono text-tertiary">{w}</div>)}
        <TaskNotes key={task} taskId={task} notes={NOTES} />
      </div>
    </div>
  )
}

export function NotesDesign() {
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('v')
  const v: VariantKey = isVariant(fromUrl) ? fromUrl : 'a'
  const state = params.get('state')
  useEffect(() => { document.title = `${t('Notes')} — Slightly Parallel` }, [])
  const pick = (k: VariantKey) => {
    const next = new URLSearchParams(params)
    next.set('v', k)
    next.delete('note')
    next.delete('hide')
    next.delete('task')
    next.delete('view')
    next.delete('at')
    setParams(next, { replace: true })
  }
  const notes = state === 'empty' ? [] : NOTES
  const hint = VARIANTS.find(([k]) => k === v)![2]
  const body = (() => {
    if (state === 'loading') return <LoadingSkeleton variant="card" count={3} label={t('Loading the notes')} />
    if (state === 'error') return <ErrorBanner title={t('Could not load the notes.')} message="502 Bad Gateway" onRetry={() => undefined} hideDismiss />
    if (!notes.length && v !== 'task') {
      return <EmptyState icon={<NotebookText size={24} />} title={t('No notes yet.')}
        subtitle={t('An agent writes a note when a text is too long for the chat: context for later, a text to paste, a plan, a report. It appears here with its task and chat.')} />
    }
    switch (v) {
      case 'a': return <Reader notes={notes} initial={params.get('note') ?? undefined} />
      case 'b': return <Queue notes={notes} />
      case 'c': return <Topics notes={notes} />
      case 'd': return <Feed notes={notes} />
      case 'e': return <Handoff notes={notes} />
      case 'task': return <TaskWindowMock />
      case 'f': case 'g': case 'h': case 'i': return <Workspace key={v} v={v} notes={notes} initial={params.get('note') ?? undefined} />
      case 'j': case 'k': case 'l': return <Workspace3 key={v} v={v} notes={notes} initial={params.get('note') ?? undefined} initialAt={params.get('at') ?? undefined} />
    }
  })()
  return (
    <MockNoteEnv>
    <div className="flex flex-col gap-16 min-w-0" data-variant={v}>
      <PageHeader variant="lens" icon={NotebookText} title={t('Notes')} count={tn(notes.length, '{n} note', '{n} notes')}
        below={(
          <div className="flex flex-col gap-6 min-w-0">
            <div className="max-w-full overflow-x-auto">
              <Segmented label={t('Variant')} shape="pill" value={v} onChange={pick} options={VARIANTS} />
            </div>
            <p className="m-0 text-12 text-secondary">{hint}</p>
          </div>
        )} />
      <PageGuide id="notes" guide={GUIDE} examples={0} />
      {body}
    </div>
    </MockNoteEnv>
  )
}
