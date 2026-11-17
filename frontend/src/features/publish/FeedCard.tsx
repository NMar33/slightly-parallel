import { memo, useMemo, useState, type ReactNode } from 'react'

import { coreColor } from '../architecture/cores/data'
import { PillGroup } from '../../components/PillGroup'
import { LABEL } from '../../components/ui'
import { Button } from '../../components/primitives'
import { attachBody, cardLife, hostOf, sizeOf, useCard, type Card, type CardImage, type CardSource } from './data'
import { LifeRail, TextEditor, shortDay } from './parts'
import { t, tn } from '../../i18n/scope/system'

export const CARD_MIME = 'application/x-sp-publish-card'

const FIELD = 'bg-elevated text-primary border border-border-default rounded-input px-8 py-4 text-12 font-mono outline-none focus:border-brand'

export type AttachKind = 'task' | 'note' | 'link' | 'commit'

/**
 * One card of the feed: the current text; the operator's own message under
 * it when the text is not that message, and the messages other chats added;
 * the context the agent wrote; what was attached (images, links, files,
 * tasks with their project, notes, commits); and the card's life rail on
 * the right. Opened (Enter or o), it shows every version of the text and the
 * context and the card's history across the documents. A file dropped on
 * the card is attached to it; `a` attaches a task, note, link or commit by
 * hand; `m` merges it into another card.
 *
 * Memoised: every prop is stable across a cursor move, so `j` re-renders
 * only the two cards whose `selected` changed.
 */
export const FeedCard = memo(function FeedCard({
  card, order, colorOf, selected, open, editing, attaching, onSelect, onEdit, onSave, onSaveContext, onCancel, onZoom, onOpenDoc,
  onAttachFiles, onAttach, onAttachOpen, onRemoveAttachment, onRemoveSource, onMerge,
}: {
  card: Card
  order: string[]
  colorOf: (docId: string) => string
  selected: boolean
  open: boolean
  /** '' | 'text' | 'context': which part of this card is being edited. */
  editing: '' | 'text' | 'context'
  attaching: boolean
  onSelect: (id: string) => void
  onEdit: (id: string, part: 'text' | 'context') => void
  onSave: (id: string, text: string) => void
  onSaveContext: (id: string, context: string) => void
  onCancel: () => void
  onZoom: (id: string, index: number) => void
  onOpenDoc: (docId: string) => void
  onAttachFiles: (id: string, files: File[]) => void
  onAttach: (id: string, kind: AttachKind, value: string, title: string) => void
  onAttachOpen: (id: string, on: boolean) => void
  onRemoveAttachment: (attachmentId: string, what: 'image' | 'link') => void
  onRemoveSource: (sourceId: string) => void
  onMerge: (id: string) => void
}) {
  const life = useMemo(() => cardLife(card, order), [card, order])
  const [fileOver, setFileOver] = useState(false)
  // The commits fold under one line: a card with a busy task carried a
  // dozen chips, and the feed read as a log.
  const [work, setWork] = useState(false)
  const changed = card.message.trim() !== card.text.trim()
  const chat = card.agent_id || (card.session_id ? card.session_id.slice(0, 8) : '')
  const links = card.links ?? []
  const files = card.files ?? []
  const notes = card.notes ?? []
  const added = (card.sources ?? []).filter((s) => s.kind !== 'kept')
  const context = card.context ?? ''
  const hasGoods = card.images.length > 0 || links.length > 0 || files.length > 0 || card.commits.length > 0 || card.tasks.length > 0 || notes.length > 0
  return (
    <article data-card={card.id} aria-current={selected ? 'true' : undefined}
      draggable={!editing && !attaching}
      onDragStart={(e) => { e.dataTransfer.setData(CARD_MIME, card.id); e.dataTransfer.effectAllowed = 'copy'; onSelect(card.id) }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setFileOver(true) } }}
      onDragLeave={() => setFileOver(false)}
      onDrop={(e) => {
        const dropped = Array.from(e.dataTransfer.files ?? [])
        setFileOver(false)
        if (dropped.length) { e.preventDefault(); onSelect(card.id); onAttachFiles(card.id, dropped) }
      }}
      onClick={() => onSelect(card.id)}
      className={`relative rounded-card border p-12 transition-colors duration-fast ${selected ? 'border-brand bg-surface' : 'border-border-subtle bg-base hover:border-border-default'}`}
      style={{
        contentVisibility: 'auto', containIntrinsicSize: 'auto 128px',
        boxShadow: fileOver ? 'inset 0 0 0 2px var(--brand)' : selected ? '0 0 0 3px var(--brand-glow)' : undefined,
      }}>
      <div className="grid gap-12 grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex flex-col gap-6 min-w-0">
          <div className="flex items-center gap-6 flex-wrap text-10 font-mono text-tertiary">
            <span className="text-secondary tabular">{shortDay(card.at)} {card.at.slice(11, 16)}</span>
            {chat && <span title={card.session_id}>· {chat}</span>}
            <span title={t('The card id: #publish {id} in any chat of the project adds to this card', { id: card.id })}>· {card.id}</span>
            {card.cores.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-4">
                · <i aria-hidden className="inline-block w-[7px] h-[7px] rounded-[2px]" style={{ background: coreColor(c.type) }} />{c.name}
              </span>
            ))}
            {card.versions.length > 0 && <span>· U{card.versions.length}</span>}
            {added.length > 0 && <span>· {tn(added.length, '+{n} message', '+{n} messages')}</span>}
          </div>

          {editing === 'text' ? (
            <TextEditor text={card.text} label={t('Card text')}
              against={card.message} againstLabel={t('the original')}
              reset={card.message} resetLabel={t('use the original')}
              onSave={(text) => onSave(card.id, text)} onCancel={onCancel} />
          ) : (
            <p className="m-0 text-14 leading-snug text-primary whitespace-pre-wrap break-words"
              onDoubleClick={(e) => { e.stopPropagation(); onEdit(card.id, 'text') }}>
              {card.text}
            </p>
          )}

          {changed && !open && editing !== 'text' && (
            <p className="m-0 pl-8 border-l border-border-default text-12 text-tertiary line-clamp-2 break-words">
              <span className="text-10 font-mono mr-6">{t('your words')} · {shortDay(card.at)}</span>
              {card.message}
            </p>
          )}
          {!open && added.map((s) => <SourceLine key={s.id} source={s} onRemove={() => onRemoveSource(s.id)} />)}

          {editing === 'context' ? (
            <TextEditor text={context} label={t('Card context')}
              against={context} againstLabel={t('the context')}
              reset={context} resetLabel={t('use the context')}
              onSave={(text) => onSaveContext(card.id, text)} onCancel={onCancel} />
          ) : context ? (
            <div className="rounded-input bg-elevated px-10 py-6 min-w-0" onDoubleClick={(e) => { e.stopPropagation(); onEdit(card.id, 'context') }}>
              <span className="block text-10 font-mono text-tertiary mb-2">
                {t('context')}{(card.context_versions?.length ?? 0) > 1 ? ` · v${card.context_versions!.length}` : ''}
                {card.context_versions?.length ? ` · ${card.context_versions[card.context_versions.length - 1]!.by ?? ''}` : ''}
              </span>
              <p className="m-0 text-12 text-secondary whitespace-pre-wrap break-words">{context}</p>
            </div>
          ) : null}

          {open && <CardOpen card={card} />}

          {hasGoods && (
            <div className="flex flex-col gap-6 pt-2">
              {card.images.length > 0 && (
                <div className="flex gap-8 overflow-x-auto pb-2">
                  {card.images.map((img, i) => (
                    <Thumb key={(img.id ?? img.url) + i} img={img}
                      onOpen={() => { onSelect(card.id); onZoom(card.id, i) }}
                      onRemove={img.id ? () => onRemoveAttachment(img.id!, 'image') : undefined} />
                  ))}
                </div>
              )}
              <div className="flex items-center gap-6 flex-wrap">
                {links.map((l) => (
                  <Chip key={l.id ?? l.url} label={t('Remove {what}', { what: l.label || hostOf(l.url) })}
                    onRemove={l.id ? () => onRemoveAttachment(l.id!, 'link') : undefined}>
                    <a href={l.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                      title={l.by ? `${l.url} · ${l.by}` : l.url}
                      className="inline-flex items-center gap-4 min-w-0 text-secondary hover:text-brand">
                      <span className="truncate">{l.label || hostOf(l.url)}</span>
                      {l.label && <span className="text-10 font-mono text-tertiary shrink-0">{hostOf(l.url)}</span>}
                    </a>
                  </Chip>
                ))}
                {files.map((f) => (
                  <Chip key={f.id} label={t('Remove {what}', { what: f.name })} onRemove={() => onRemoveAttachment(f.id, 'link')}>
                    <a href={f.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                      title={f.path ? `${f.path} · ${sizeOf(f.size)}` : sizeOf(f.size)}
                      className="inline-flex items-center gap-4 min-w-0 text-secondary hover:text-brand">
                      <span aria-hidden className="text-10 font-mono text-tertiary">{t('file')}</span>
                      <span className="truncate">{f.name}</span>
                      <span className="text-10 font-mono text-tertiary shrink-0">{sizeOf(f.size)}</span>
                    </a>
                  </Chip>
                ))}
                {card.tasks.map((tk) => (
                  <Chip key={tk.id} tone="task" label={t('Remove {what}', { what: tk.id })}
                    onRemove={tk.attachment_id ? () => onRemoveAttachment(tk.attachment_id!, 'link') : undefined}>
                    <span className="inline-flex items-center gap-4 min-w-0" title={`${tk.id} · ${tk.status}${tk.project ? ` · ${tk.project}` : ''}`}>
                      {tk.project && tk.project !== card.project && <span className="text-10 font-mono text-status-info shrink-0">{tk.project}</span>}
                      <span className="truncate">{tk.title || tk.id}</span>
                    </span>
                  </Chip>
                ))}
                {notes.map((n) => (
                  <Chip key={n.id} tone="task" label={t('Remove {what}', { what: n.id })}
                    onRemove={n.attachment_id ? () => onRemoveAttachment(n.attachment_id!, 'link') : undefined}>
                    <a href={`/notes?note=${encodeURIComponent(n.id)}`} onClick={(e) => e.stopPropagation()} title={n.id}
                      className="inline-flex items-center gap-4 min-w-0 text-secondary hover:text-brand">
                      <span aria-hidden className="text-10 font-mono text-tertiary">{t('note')}</span>
                      <span className="truncate">{n.title || n.id}</span>
                    </a>
                  </Chip>
                ))}
                {card.commits.length > 0 && (
                  <button type="button" aria-expanded={work}
                    onClick={(e) => { e.stopPropagation(); setWork((w) => !w) }}
                    className="inline-flex items-center gap-4 h-20 px-6 rounded-input text-10 font-mono text-tertiary hover:text-primary hover:bg-elevated">
                    <span aria-hidden className="inline-block w-[10px] text-center">{work ? '▾' : '▸'}</span>
                    {tn(card.commits.length, '{n} commit', '{n} commits')}
                  </button>
                )}
              </div>
              {work && card.commits.length > 0 && (
                <ol className="m-0 p-0 list-none flex flex-col gap-2">
                  {card.commits.map((c) => (
                    <li key={c.sha + (c.repo ?? '')} className="group flex items-baseline gap-6 text-11 min-w-0">
                      <span className="font-mono text-10 text-brand shrink-0">{c.sha.slice(0, 7)}</span>
                      <span className="truncate text-secondary" title={c.subject}>{c.subject}</span>
                      {c.repo && <span className="font-mono text-10 text-tertiary shrink-0 truncate max-w-[140px]" title={c.repo}>{c.repo.split('/').filter(Boolean).pop()}</span>}
                      <span className="font-mono text-10 text-tertiary shrink-0 ml-auto tabular">{shortDay(c.at)} {c.at.slice(11, 16)}</span>
                      {c.attachment_id && (
                        <button type="button" aria-label={t('Remove {what}', { what: c.sha.slice(0, 7) })}
                          onClick={(e) => { e.stopPropagation(); onRemoveAttachment(c.attachment_id!, 'link') }}
                          className="text-11 leading-none text-tertiary hover:text-status-red opacity-0 group-hover:opacity-100 focus:opacity-100">×</button>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {attaching ? (
            <AttachForm onAdd={(kind, value, title) => onAttach(card.id, kind, value, title)} onClose={() => onAttachOpen(card.id, false)} />
          ) : selected && (
            <div className="flex items-center gap-10 text-10 font-mono text-tertiary">
              {!context && editing !== 'context' && (
                <Button variant="text" size="bare" onClick={(e) => { e.stopPropagation(); onEdit(card.id, 'context') }}>+ {t('context')}</Button>
              )}
              {context && editing !== 'context' && (
                <Button variant="text" size="bare" onClick={(e) => { e.stopPropagation(); onEdit(card.id, 'context') }}>{t('edit the context')} <span className="text-tertiary">x</span></Button>
              )}
              <Button variant="text" size="bare" onClick={(e) => { e.stopPropagation(); onAttachOpen(card.id, true) }}>+ {t('attach')} <span className="text-tertiary">a</span></Button>
              <Button variant="text" size="bare" onClick={(e) => { e.stopPropagation(); onMerge(card.id) }}>{t('merge into…')} <span className="text-tertiary">m</span></Button>
            </div>
          )}
        </div>
        <LifeRail nodes={life} colorOf={colorOf} lit={selected} onOpenDoc={onOpenDoc} />
      </div>
    </article>
  )
})

/** A chip of the card's attachments, with × on hover when it can be removed. */
function Chip({ children, onRemove, label, tone }: { children: ReactNode; onRemove?: () => void; label: string; tone?: 'task' }) {
  return (
    <span className={`group inline-flex items-center gap-4 max-w-[260px] rounded-pill px-8 h-20 text-11 ${tone === 'task' ? 'bg-elevated text-secondary' : 'border border-border-subtle text-secondary hover:border-brand'}`}>
      {children}
      {onRemove && (
        <button type="button" aria-label={label} title={label}
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          className="text-11 leading-none text-tertiary hover:text-status-red opacity-0 group-hover:opacity-100 focus:opacity-100 shrink-0">×</button>
      )}
    </span>
  )
}

/** A message the operator added to the card later, from a chat or by a merge. */
function SourceLine({ source, onRemove }: { source: CardSource; onRemove: () => void }) {
  const word = source.kind === 'merged' ? t('merged') : t('added')
  return (
    <p className="group m-0 pl-8 border-l border-border-default text-12 text-tertiary line-clamp-2 break-words">
      <span className="text-10 font-mono mr-6">{word} · {shortDay(source.at)}{source.agent_id ? ` · ${source.agent_id}` : ''}</span>
      {source.text || source.from_card}
      <button type="button" onClick={(e) => { e.stopPropagation(); onRemove() }}
        aria-label={source.kind === 'merged' ? t('Take the merge back') : t('Remove the message from the card')}
        title={source.kind === 'merged' ? t('Take the merge back') : t('Remove the message from the card')}
        className="ml-6 text-11 leading-none text-tertiary hover:text-status-red opacity-0 group-hover:opacity-100 focus:opacity-100">×</button>
    </p>
  )
}

/**
 * Attach by hand, in the task window's idiom: the kind as a PillGroup, one
 * mono field (ids comma-separated; a commit as `sha` or `sha repo-folder`),
 * a title for a link. Enter adds, Escape closes.
 */
function AttachForm({ onAdd, onClose }: { onAdd: (kind: AttachKind, value: string, title: string) => void; onClose: () => void }) {
  const [kind, setKind] = useState<AttachKind>('task')
  const [value, setValue] = useState('')
  const [title, setTitle] = useState('')
  const ok = attachBody(kind, value, title) !== null
  const hint: Record<AttachKind, string> = {
    task: t('tk_… ids, comma-separated'),
    note: t('nt_… ids, comma-separated'),
    link: 'https://…',
    commit: t('sha, or sha and the repository folder'),
  }
  const add = () => { if (ok) { onAdd(kind, value, title); setValue(''); setTitle('') } }
  return (
    <div className="flex flex-col gap-6 rounded-input border border-border-subtle p-8" onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === 'Escape') { e.preventDefault(); onClose() }
        if (e.key === 'Enter') { e.preventDefault(); add() }
      }}>
      <PillGroup label={t('attach')} value={kind} onChange={(v) => setKind((v || 'task') as AttachKind)}
        options={[['task', t('task')], ['note', t('note')], ['link', t('link')], ['commit', t('commit')]]} />
      <div className="grid gap-6 grid-cols-[minmax(0,1fr)_auto] items-end">
        <label className="flex flex-col gap-2 min-w-0">
          <span className={LABEL}>{kind === 'link' ? t('url') : kind === 'commit' ? t('commit') : t('ids')}</span>
          <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder={hint[kind]} aria-label={t('What to attach')} className={FIELD} />
        </label>
        <span className="flex items-center gap-6">
          <Button variant="ghost" size="sm" onClick={onClose}>{t('Cancel')}</Button>
          <Button size="sm" disabled={!ok} onClick={add}>{t('Attach')}</Button>
        </span>
        {kind === 'link' && (
          <label className="flex flex-col gap-2 min-w-0 col-span-2">
            <span className={LABEL}>{t('title')}</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label={t('Link title')} className={FIELD} />
          </label>
        )}
      </div>
      <span className="text-10 font-mono text-tertiary">{t('A file dropped on the card is copied onto it.')}</span>
    </div>
  )
}

/** One image of the strip: the thumbnail, who attached it, and × to remove it. */
function Thumb({ img, onOpen, onRemove }: { img: CardImage; onOpen: () => void; onRemove?: () => void }) {
  const from = img.by ? t('attached · by {who}', { who: img.by }) : ''
  return (
    <figure className="group relative m-0 flex flex-col gap-2 shrink-0 w-[96px]">
      <button type="button" title={img.label} onClick={(e) => { e.stopPropagation(); onOpen() }}
        className="h-[60px] w-[96px] rounded-input overflow-hidden border border-border-subtle bg-elevated hover:border-brand">
        <img src={img.url} alt={img.label} loading="lazy" decoding="async" className="h-full w-full object-cover" />
      </button>
      {from && <figcaption className="text-10 font-mono text-tertiary truncate" title={from}>{from}</figcaption>}
      {onRemove && (
        <button type="button" aria-label={t('Remove the image')} title={t('Remove the image')}
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          className="absolute top-2 right-2 h-[18px] w-[18px] rounded-pill bg-surface text-11 leading-none text-secondary hover:text-status-red opacity-0 group-hover:opacity-100 focus:opacity-100 shadow-sm">
          ×
        </button>
      )}
    </figure>
  )
}

/** The opened card: every message it carries, every text and context version, and what happened to it in the documents. */
function CardOpen({ card }: { card: Card }) {
  const { data } = useCard(card.id)
  const history = data?.history ?? []
  const sources = card.sources?.length ? card.sources : [{ id: card.id, kind: 'kept', at: card.at, agent_id: card.agent_id, text: card.message, from_card: '' }]
  return (
    <div className="flex flex-col gap-6 pl-8 border-l border-border-default">
      {sources.map((s) => (
        <Line key={s.id} label={`${s.kind === 'kept' ? t('your words') : s.kind === 'merged' ? t('merged') : t('added')} · ${shortDay(s.at)}${s.agent_id ? ` · ${s.agent_id}` : ''}`} text={s.text} />
      ))}
      {card.versions.map((v) => <Line key={`u${v.n}`} label={`U${v.n} · ${shortDay(v.at)}${v.by ? ` · ${v.by}` : ''}${v.note ? ` · ${v.note}` : ''}`} text={v.text} />)}
      {(card.context_versions ?? []).slice(0, -1).map((v) => (
        <Line key={`c${v.n}`} label={`${t('context')} v${v.n} · ${shortDay(v.at)}${v.by ? ` · ${v.by}` : ''}${v.note ? ` · ${v.note}` : ''}`} text={v.text} />
      ))}
      {history.length > 0 && (
        <ol className="m-0 p-0 list-none flex flex-col gap-2 pt-4">
          {history.map((h, i) => (
            <li key={i} className="text-10 font-mono text-tertiary truncate" title={h.text}>
              <span className="tabular">{shortDay(h.at)} {h.at.slice(11, 16)}</span> · <span className="text-secondary">{whatWord(h.what)}</span>
              {h.doc_name && <> · {h.doc_name}{h.version_n ? ` v${h.version_n}` : ''}</>}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function Line({ label, text }: { label: string; text: string }) {
  return (
    <div className="min-w-0">
      <span className="block text-10 font-mono text-tertiary">{label}</span>
      <p className="m-0 text-13 text-secondary whitespace-pre-wrap break-words">{text}</p>
    </div>
  )
}

function whatWord(what: string): string {
  switch (what) {
    case 'kept': return t('kept')
    case 'appended': return t('added')
    case 'merged': return t('merged')
    case 'written': return t('written by the agent')
    case 'context': return t('context')
    case 'edited': return t('edited')
    case 'placed': return t('placed in')
    case 'edited in': return t('edited in')
    case 'removed from': return t('removed from')
    default: return what
  }
}
