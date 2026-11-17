/**
 * Variant A — Reader. The note is a document: a list of substantial rows
 * on the left (kind, title, first paragraph, what is open, the pictures),
 * the note at reading width in the middle, and a rail on the right with
 * the outline (what each section holds, what is open in it) and the links.
 * A find lands on the section the words are in.
 */

import { useState } from 'react'

import { EmptyState } from '../../../../components/states'
import { LABEL } from '../../../../components/ui'
import { t } from '../../../../i18n/scope/notes'
import { Gallery } from '../blocks'
import { allBlocks, type Block, type Note, type NoteKind } from '../model'
import {
  agoOf, FindBox, goTo, hitOf, KindMark, KindPills, LinksLine, matches, newestFirst, OpenWords, Outline, ProjectMark, ProjectPills, useOpen,
} from '../parts'
import { NoteRead } from '../reader'

function Row({ note, on, q, onPick }: { note: Note; on: boolean; q: string; onPick: (anchor?: string) => void }) {
  const open = useOpen(note)
  const hit = q ? hitOf(note, q) : null
  const gallery = allBlocks(note).map((x) => x.block).find((b): b is Extract<Block, { type: 'gallery' }> => b.type === 'gallery')
  return (
    <button type="button" onClick={() => onPick(hit ? `${note.id}-${hit.section.id}` : undefined)} aria-current={on}
      className={`text-left w-full flex flex-col gap-4 rounded-card border px-10 py-8 min-w-0 transition-colors ${on ? 'border-brand bg-brand-glow/50' : 'border-border-subtle bg-surface hover:bg-hover'}`}>
      <span className="flex items-center gap-8 min-w-0">
        <KindMark kind={note.kind} />
        <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{agoOf(note.updated)}</span>
      </span>
      <span className="text-13 text-primary font-medium leading-snug">{note.title}</span>
      <span className="text-12 text-secondary leading-snug line-clamp-3">{hit ? <>§ {hit.section.title || t('Opening')}: {hit.text}</> : note.lead}</span>
      {gallery && <span className="block pt-2"><Gallery block={gallery} size="strip" /></span>}
      <span className="flex items-center gap-8 flex-wrap min-w-0">
        <ProjectMark code={note.project} />
        <OpenWords open={open} done={false} />
      </span>
    </button>
  )
}

export function Reader({ notes, initial }: { notes: Note[]; initial?: string }) {
  const [q, setQ] = useState('')
  const [project, setProject] = useState('')
  const [kind, setKind] = useState<NoteKind | ''>('')
  const list = notes.filter((n) => (!project || n.project === project) && (!kind || n.kind === kind) && matches(n, q)).sort(newestFirst)
  const [pick, setPick] = useState(initial ?? [...notes].sort(newestFirst)[0]?.id ?? '')
  const note = notes.find((n) => n.id === pick) ?? list[0]
  const choose = (id: string, anchor?: string) => {
    setPick(id)
    if (anchor) requestAnimationFrame(() => goTo(anchor))
  }
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <div className="flex flex-col gap-8 min-w-0">
        <FindBox value={q} onChange={setQ} found={list.length} of={notes.length} className="max-w-[520px]" />
        <div className="flex items-center gap-12 flex-wrap">
          <ProjectPills notes={notes} value={project} onChange={setProject} />
          <KindPills notes={notes} value={kind} onChange={setKind} />
        </div>
      </div>
      <div className="grid gap-16 min-w-0 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_220px] items-start">
        <nav aria-label={t('Notes')} className="flex flex-col gap-6 min-w-0 lg:sticky lg:top-0 lg:max-h-[calc(100vh-120px)] lg:overflow-y-auto lg:pr-4">
          {list.map((n) => <Row key={n.id} note={n} on={n.id === note?.id} q={q} onPick={(a) => choose(n.id, a)} />)}
          {!list.length && <EmptyState compact title={t('Nothing matches.')} />}
        </nav>
        {note ? (
          <>
            <div className="min-w-0 max-w-[760px] w-full rounded-card border border-border-subtle bg-surface px-24 py-20 max-sm:px-12">
              <details className="xl:hidden mb-12 rounded-card border border-border-subtle px-8 py-4">
                <summary className={`${LABEL} cursor-pointer`}>{t('Outline')}</summary>
                <Outline note={note} onGo={goTo} />
              </details>
              <NoteRead key={note.id} note={note} />
            </div>
            <aside aria-label={t('Outline and links')} className="hidden xl:flex flex-col gap-12 min-w-0 sticky top-0">
              <div className="flex flex-col gap-4">
                <span className={LABEL}>{t('Outline')}</span>
                <Outline note={note} onGo={goTo} />
              </div>
              <div className="flex flex-col gap-4">
                <span className={LABEL}>{t('Links')}</span>
                <LinksLine note={note} />
              </div>
            </aside>
          </>
        ) : <EmptyState compact title={t('Pick a note.')} />}
      </div>
    </div>
  )
}
