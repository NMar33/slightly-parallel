import { memo, useMemo, useState } from 'react'

import { coreColor } from '../architecture/cores/data'
import { cardLife, hostOf, useCard, type Card, type CardImage } from './data'
import { LifeRail, TextEditor, shortDay } from './parts'
import { t, tn } from '../../i18n/scope/system'

export const CARD_MIME = 'application/x-sp-publish-card'

/**
 * One card of the feed: the current text; the message as typed under it
 * when an edit changed it; who and where (date, chat, tasks, cores); what
 * the work left (images with where they came from, links, files, commits,
 * tasks); and the card's life rail on the right. Opened (Enter or o), it
 * shows every version of the text and the card's history across the
 * documents. An image file dropped on the card is attached to it.
 *
 * Memoised: every prop is stable across a cursor move, so `j` re-renders
 * only the two cards whose `selected` changed.
 */
export const FeedCard = memo(function FeedCard({
  card, order, colorOf, selected, open, editing, onSelect, onEdit, onSave, onCancel, onZoom, onOpenDoc, onAttachFiles, onRemoveAttachment,
}: {
  card: Card
  order: string[]
  colorOf: (docId: string) => string
  selected: boolean
  open: boolean
  editing: boolean
  onSelect: (id: string) => void
  onEdit: (id: string) => void
  onSave: (id: string, text: string) => void
  onCancel: () => void
  onZoom: (id: string, index: number) => void
  onOpenDoc: (docId: string) => void
  onAttachFiles: (id: string, files: File[]) => void
  onRemoveAttachment: (attachmentId: string) => void
}) {
  const life = useMemo(() => cardLife(card, order), [card, order])
  const [fileOver, setFileOver] = useState(false)
  // The commits and the files fold under one line: a card that names a
  // busy task carried a dozen chips, and the feed read as a log.
  const [work, setWork] = useState(false)
  const changed = card.message.trim() !== card.text.trim()
  const chat = card.agent_id || (card.session_id ? card.session_id.slice(0, 8) : '')
  const links = card.links ?? []
  const files = card.files ?? []
  const hasGoods = card.images.length > 0 || links.length > 0 || files.length > 0 || card.commits.length > 0 || card.tasks.length > 0
  return (
    <article data-card={card.id} aria-current={selected ? 'true' : undefined}
      draggable={!editing}
      onDragStart={(e) => { e.dataTransfer.setData(CARD_MIME, card.id); e.dataTransfer.effectAllowed = 'copy'; onSelect(card.id) }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setFileOver(true) } }}
      onDragLeave={() => setFileOver(false)}
      onDrop={(e) => {
        const dropped = Array.from(e.dataTransfer.files ?? []).filter((f) => f.type.startsWith('image/'))
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
            {card.tasks.slice(0, 2).map((tk) => <span key={tk.id} title={tk.title}>· {tk.id}</span>)}
            {card.cores.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-4">
                · <i aria-hidden className="inline-block w-[7px] h-[7px] rounded-[2px]" style={{ background: coreColor(c.type) }} />{c.name}
              </span>
            ))}
            {card.versions.length > 0 && <span>· U{card.versions.length}</span>}
          </div>

          {editing ? (
            <TextEditor text={card.text} label={t('Card text')}
              against={card.message} againstLabel={t('the original')}
              reset={card.message} resetLabel={t('use the original')}
              onSave={(text) => onSave(card.id, text)} onCancel={onCancel} />
          ) : (
            <p className="m-0 text-14 leading-snug text-primary whitespace-pre-wrap break-words"
              onDoubleClick={(e) => { e.stopPropagation(); onEdit(card.id) }}>
              {card.text}
            </p>
          )}

          {changed && !open && !editing && (
            <p className="m-0 pl-8 border-l border-border-default text-12 text-tertiary line-clamp-2 break-words">
              <span className="text-10 font-mono mr-6">{t('was')} · {shortDay(card.at)}</span>
              {card.message}
            </p>
          )}

          {open && <CardOpen card={card} />}

          {hasGoods && (
            <div className="flex flex-col gap-6 pt-2">
              {card.images.length > 0 && (
                <div className="flex gap-8 overflow-x-auto pb-2">
                  {card.images.map((img, i) => (
                    <Thumb key={(img.id ?? img.url) + i} img={img}
                      onOpen={() => { onSelect(card.id); onZoom(card.id, i) }}
                      onRemove={img.from === 'attached' && img.id ? () => onRemoveAttachment(img.id!) : undefined} />
                  ))}
                </div>
              )}
              <div className="flex items-center gap-6 flex-wrap">
                {links.map((l) => (
                  <a key={l.id ?? l.url} href={l.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                    title={l.by ? `${l.url} · ${l.by}` : l.url}
                    className="inline-flex items-center gap-4 max-w-[240px] rounded-pill border border-border-subtle px-8 h-20 text-11 text-secondary hover:text-brand hover:border-brand">
                    <span className="truncate">{l.label || hostOf(l.url)}</span>
                    {l.label && <span className="text-10 font-mono text-tertiary shrink-0">{hostOf(l.url)}</span>}
                  </a>
                ))}
                {card.tasks.map((tk) => (
                  <span key={tk.id} title={`${tk.id} · ${tk.status}`}
                    className="inline-flex items-center max-w-[220px] rounded-pill bg-elevated px-8 h-20 text-11 text-secondary">
                    <span className="truncate">{tk.title || tk.id}</span>
                  </span>
                ))}
                {(card.commits.length > 0 || files.length > 0) && (
                  <button type="button" aria-expanded={work}
                    onClick={(e) => { e.stopPropagation(); setWork((w) => !w) }}
                    className="inline-flex items-center gap-4 h-20 px-6 rounded-input text-10 font-mono text-tertiary hover:text-primary hover:bg-elevated">
                    <span aria-hidden className="inline-block w-[10px] text-center">{work ? '▾' : '▸'}</span>
                    {[card.commits.length ? tn(card.commits.length, '{n} commit', '{n} commits') : '',
                      files.length ? tn(files.length, '{n} file', '{n} files') : ''].filter(Boolean).join(' · ')}
                  </button>
                )}
              </div>
              {work && card.commits.length > 0 && (
                <ol className="m-0 p-0 list-none flex flex-col gap-2">
                  {card.commits.map((c) => (
                    <li key={c.sha} className="flex items-baseline gap-6 text-11 min-w-0">
                      <span className="font-mono text-10 text-brand shrink-0">{c.sha.slice(0, 7)}</span>
                      <span className="truncate text-secondary" title={c.subject}>{c.subject}</span>
                      <span className="font-mono text-10 text-tertiary shrink-0 ml-auto tabular">{shortDay(c.at)} {c.at.slice(11, 16)}</span>
                    </li>
                  ))}
                </ol>
              )}
              {work && files.length > 0 && (
                <div className="flex items-center gap-4 flex-wrap text-10 font-mono text-tertiary">
                  {files.map((f) => (
                    <span key={f.path} title={f.path} className="inline-flex items-center gap-4 max-w-[260px] rounded-input bg-elevated px-6 h-20">
                      <span className="truncate text-secondary">{f.path.split('/').slice(-2).join('/')}</span>
                      <span className="text-status-green">+{f.add}</span><span className="text-status-red">−{f.del}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <LifeRail nodes={life} colorOf={colorOf} lit={selected} onOpenDoc={onOpenDoc} />
      </div>
    </article>
  )
})

function fromWord(img: CardImage): string {
  switch (img.from) {
    case 'evidence': return t('evidence')
    case 'story': return t('story')
    case 'attached': return img.by ? t('attached · by {who}', { who: img.by }) : t('attached')
    default: return ''
  }
}

/** One image of the strip: the thumbnail, where it came from, and × on one attached to the card. */
function Thumb({ img, onOpen, onRemove }: { img: CardImage; onOpen: () => void; onRemove?: () => void }) {
  const from = fromWord(img)
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

/** The opened card: the message as typed, every edit, and what happened to it in the documents. */
function CardOpen({ card }: { card: Card }) {
  const { data } = useCard(card.id)
  const history = data?.history ?? []
  return (
    <div className="flex flex-col gap-6 pl-8 border-l border-border-default">
      <Line label={`${t('original')} · ${shortDay(card.at)}`} text={card.message} />
      {card.versions.map((v) => <Line key={v.n} label={`U${v.n} · ${shortDay(v.at)}${v.note ? ` · ${v.note}` : ''}`} text={v.text} />)}
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
    case 'edited': return t('edited')
    case 'placed': return t('placed in')
    case 'edited in': return t('edited in')
    case 'removed from': return t('removed from')
    default: return what
  }
}
