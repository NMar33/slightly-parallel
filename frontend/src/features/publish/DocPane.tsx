import { memo, useState, type DragEvent } from 'react'

import { Confirm } from '../../components/Confirm'
import { Modal } from '../../components/Modal'
import { Button, Input, toast } from '../../components/primitives'
import { EmptyState } from '../../components/states'
import { fail, getText } from '../../lib/getJson'
import { writeClipboard } from '../../lib/useCopy'
import { CARD_MIME } from './FeedCard'
import { itemsOf, markdownUrl, usePublishWrites, versionDiffs, type Card, type Doc, type DocItem } from './data'
import { Kbd, TextEditor, shortDay } from './parts'
import { t, tn } from '../../i18n/scope/system'

const ITEM_MIME = 'application/x-sp-publish-item'

/**
 * The documents: a tab per document (its key, name, version and count),
 * the open one's versions, and its items in order — each edited in place,
 * dragged to a new place, or removed. A card dropped on a tab or on the
 * list is placed into that document's current version. History shows the
 * versions side by side, with what came in, changed and left in each.
 */
export const DocPane = memo(function DocPane({
  project, docs, colorOf, openId, onOpen, cards, litDocs, history, onHistory, onNewDoc, onPlace,
}: {
  project: string
  docs: Doc[]
  colorOf: (docId: string) => string
  openId: string
  onOpen: (id: string) => void
  cards: Map<string, Card>
  /** The documents the selected card is in, joined by spaces: a string, so a cursor move to a card in the same documents re-renders nothing here. */
  litDocs: string
  history: boolean
  onHistory: (on: boolean) => void
  onNewDoc: () => void
  onPlace: (doc: Doc, cardId: string, before?: string) => void
}) {
  const doc = docs.find((d) => d.id === openId) ?? docs[0] ?? null
  const lit = new Set(litDocs.split(' ').filter(Boolean))
  const [dropTab, setDropTab] = useState('')

  const cardDrop = (e: DragEvent) => e.dataTransfer.types.includes(CARD_MIME)

  return (
    <section className="flex flex-col min-h-0 min-w-0 rounded-card border border-border-subtle bg-surface overflow-hidden" aria-label={t('Documents')}>
      <div className="flex items-end gap-8 border-b border-border-default px-8 shrink-0">
        <div role="tablist" aria-label={t('Documents')} className="flex flex-wrap gap-x-4 flex-1 min-w-0">
          {docs.map((d, i) => {
            const on = doc?.id === d.id
            const c = colorOf(d.id)
            const n = itemsOf(d).length
            return (
              <button key={d.id} role="tab" type="button" aria-selected={on}
                title={i < 9 ? t('Press {n} to place the selected card here', { n: i + 1 }) : undefined}
                onClick={() => onOpen(d.id)}
                onDragOver={(e) => { if (cardDrop(e)) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setDropTab(d.id) } }}
                onDragLeave={() => setDropTab('')}
                onDrop={(e) => { const id = e.dataTransfer.getData(CARD_MIME); setDropTab(''); if (id) { e.preventDefault(); onPlace(d, id) } }}
                className={`relative inline-flex items-center gap-6 px-12 py-8 text-13 font-medium whitespace-nowrap rounded-t-input transition-colors duration-fast ease-out ${on ? 'text-primary' : 'text-tertiary hover:text-secondary'}`}
                style={dropTab === d.id ? { boxShadow: `inset 0 0 0 2px ${c}` } : undefined}>
                {i < 9 && <Kbd>{i + 1}</Kbd>}
                <i aria-hidden className="inline-block w-[8px] h-[8px] rounded-[2px]" style={{ background: c }} />
                {d.name}
                <span className="text-10 font-mono font-regular text-tertiary tabular">v{d.current} · {n}</span>
                {lit.has(d.id) && <span role="img" aria-label={t('The selected card is here')} title={t('The selected card is here')}
                  className="inline-block w-[6px] h-[6px] rounded-pill" style={{ background: c }} />}
                {on && <span aria-hidden className="absolute left-0 right-0 -bottom-px h-[2px] bg-brand" />}
              </button>
            )
          })}
        </div>
        <div className="shrink-0 pb-6">
          <Button variant="text" size="bare" onClick={onNewDoc} title={t('New document (n)')}>+ {t('document')}</Button>
        </div>
      </div>

      {!doc ? (
        <div className="p-16">
          <EmptyState title={t('No documents yet.')} subtitle={t('Make a document for each text you put together: a release note, a post, a video script. Then press 1–9 or drag a card onto its tab.')}
            cta={{ label: t('New document'), onClick: onNewDoc }} />
        </div>
      ) : (
        <DocBody key={doc.id} project={project} doc={doc} color={colorOf(doc.id)} cards={cards} history={history} onHistory={onHistory} onPlace={onPlace} />
      )}
    </section>
  )
})

function DocBody({ project, doc, color, cards, history, onHistory, onPlace }: {
  project: string; doc: Doc; color: string; cards: Map<string, Card>; history: boolean; onHistory: (on: boolean) => void
  onPlace: (doc: Doc, cardId: string, before?: string) => void
}) {
  const writes = usePublishWrites(project)
  const [viewN, setViewN] = useState(doc.current)
  const [asking, setAsking] = useState<null | 'version' | 'archive'>(null)
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState('')
  const [over, setOver] = useState('')
  const n = doc.versions.some((v) => v.n === viewN) ? viewN : doc.current
  const current = n === doc.current
  const items = itemsOf(doc, n)
  const versions = [...doc.versions].sort((a, b) => a.n - b.n)

  const copy = async () => {
    try {
      const text = await getText(markdownUrl(doc.id, n))
      if (await writeClipboard(text)) toast.success(t('Copied {name} v{n} as markdown.', { name: doc.name, n }))
      else toast.error(t('The browser did not allow copying.'))
    } catch (e) { fail(e) }
  }

  const dropOn = (e: DragEvent, before?: string) => {
    if (!current) return
    const cardId = e.dataTransfer.getData(CARD_MIME)
    const itemId = e.dataTransfer.getData(ITEM_MIME)
    setOver('')
    if (cardId) { e.preventDefault(); e.stopPropagation(); onPlace(doc, cardId, before) }
    else if (itemId && before && itemId !== before) {
      e.preventDefault(); e.stopPropagation()
      writes.updateItem.mutate({ id: itemId, before }, { onError: fail })
    }
  }
  const allowDrop = (e: DragEvent, id: string) => {
    if (!current) return
    const types = e.dataTransfer.types
    if (types.includes(CARD_MIME) || types.includes(ITEM_MIME)) { e.preventDefault(); setOver(id) }
  }

  return (
    <div className="flex flex-col min-h-0 flex-1 bg-base">
      <div className="flex items-center gap-6 flex-wrap px-12 py-8 border-b border-border-subtle text-11 font-mono shrink-0">
        <span className="text-10 uppercase tracking-wider text-tertiary mr-2">{t('versions')}</span>
        {versions.map((v) => (
          <button key={v.n} type="button" onClick={() => setViewN(v.n)} title={`${shortDay(v.at)}${v.note ? ` · ${v.note}` : ''}`}
            className={`h-20 px-6 rounded-input tabular ${v.n === n ? 'text-on-brand' : 'text-secondary hover:text-primary hover:bg-elevated'}`}
            style={v.n === n ? { background: color } : undefined}>
            v{v.n}
          </button>
        ))}
        <Button variant="text" size="bare" onClick={() => { setNote(''); setAsking('version') }}>+ {t('version')}</Button>
        <span className="ml-auto flex items-center gap-10">
          <Button variant="text" size="bare" onClick={() => onHistory(!history)} aria-pressed={history}
            className={history ? 'text-brand' : ''}>{t('history')} <Kbd>v</Kbd></Button>
          <Button variant="text" size="bare" onClick={() => void copy()}>{t('Copy as markdown')}</Button>
          <Button variant="danger-text" size="bare" onClick={() => setAsking('archive')}>{t('Remove')}</Button>
        </span>
      </div>

      {history ? <HistoryView doc={doc} color={color} /> : (
        <div className="flex-1 overflow-y-auto px-12 py-10 flex flex-col gap-6"
          onDragOver={(e) => allowDrop(e, 'end')} onDragLeave={() => setOver('')} onDrop={(e) => dropOn(e)}>
          {!current && (
            <p className="m-0 text-11 font-mono text-tertiary">{t('An older version: read only. Edit the current version, v{n}.', { n: doc.current })}</p>
          )}
          {items.length === 0 && (
            <EmptyState compact title={t('This version is empty.')} subtitle={t('Press {n} on a card, or drag a card here.', { n: '1–9' })} />
          )}
          {items.map((it, i) => (
            <ItemRow key={it.id} item={it} index={i} card={cards.get(it.card_id)} color={color} editable={current}
              editing={editing === it.id} over={over === it.id}
              onEdit={() => setEditing(it.id)} onCancel={() => setEditing('')}
              onSave={(text) => writes.updateItem.mutate({ id: it.id, text }, { onSuccess: () => setEditing(''), onError: fail })}
              onRemove={() => writes.removeItem.mutate(it.id, { onError: fail })}
              onDragOver={(e) => allowDrop(e, it.id)} onDrop={(e) => dropOn(e, it.id)} />
          ))}
          {current && items.length > 0 && (
            <div className={`h-32 rounded-input border border-dashed text-10 font-mono flex items-center justify-center transition-colors ${over === 'end' ? 'border-brand text-brand' : 'border-border-subtle text-tertiary'}`}>
              {t('Drop a card here to add it at the end')}
            </div>
          )}
        </div>
      )}

      {asking === 'version' && (
        <Modal labelledBy="pub-version-title" onClose={() => setAsking(null)} width="w-[440px]">
          <form className="flex flex-col gap-12" onSubmit={(e) => {
            e.preventDefault()
            writes.newVersion.mutate({ id: doc.id, note: note.trim() || undefined }, {
              onSuccess: () => { setAsking(null); setViewN(doc.current + 1) },
              onError: fail,
            })
          }}>
            <h3 id="pub-version-title" className="text-16 font-semibold text-primary m-0">{t('New version of {name}', { name: doc.name })}</h3>
            <p className="m-0 text-12 text-secondary">{t('The items of v{n} are copied into v{next}. Edits then go into v{next}; v{n} stays as it is.', { n: doc.current, next: doc.current + 1 })}</p>
            <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
              {t('note')}
              <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} autoFocus placeholder={t('Optional: what this version is for')} />
            </label>
            <div className="flex justify-end gap-8">
              <Button type="button" variant="ghost" size="sm" onClick={() => setAsking(null)}>{t('Cancel')}</Button>
              <Button type="submit" size="sm" disabled={writes.newVersion.isPending}>{t('Make v{n}', { n: doc.current + 1 })}</Button>
            </div>
          </form>
        </Modal>
      )}
      {asking === 'archive' && (
        <Modal label={t('Remove the document')} onClose={() => setAsking(null)} width="w-[440px]">
          <Confirm text={t('The document is removed from the tabs. Its versions are kept, and the cards keep their history.')}
            action={t('Remove')} busy={writes.updateDoc.isPending} onNo={() => setAsking(null)}
            onYes={() => writes.updateDoc.mutate({ id: doc.id, archived: true }, { onSuccess: () => setAsking(null), onError: fail })} />
        </Modal>
      )}
    </div>
  )
}

function ItemRow({ item, index, card, color, editable, editing, over, onEdit, onCancel, onSave, onRemove, onDragOver, onDrop }: {
  item: DocItem; index: number; card: Card | undefined; color: string; editable: boolean; editing: boolean; over: boolean
  onEdit: () => void; onCancel: () => void; onSave: (text: string) => void; onRemove: () => void
  onDragOver: (e: DragEvent) => void; onDrop: (e: DragEvent) => void
}) {
  return (
    <div data-item={item.id}
      draggable={editable && !editing}
      onDragStart={(e) => { e.dataTransfer.setData(ITEM_MIME, item.id); e.dataTransfer.effectAllowed = 'move' }}
      onDragOver={onDragOver} onDrop={onDrop}
      className="group relative grid grid-cols-[20px_minmax(0,1fr)_auto] gap-8 rounded-input px-8 py-6 hover:bg-surface"
      style={over ? { boxShadow: `inset 0 2px 0 0 ${color}` } : undefined}>
      <span className="text-10 font-mono text-tertiary tabular pt-3 cursor-grab" title={editable ? t('Drag to move') : undefined}>{index + 1}</span>
      <div className="flex flex-col gap-2 min-w-0">
        {editing ? (
          <TextEditor text={item.text} label={t('Text in this document')}
            against={card?.text ?? item.text} againstLabel={t('the card text')}
            reset={card?.text ?? item.text} resetLabel={t('use the card text')}
            onSave={onSave} onCancel={onCancel} />
        ) : (
          <p className={`m-0 text-13 text-primary whitespace-pre-wrap break-words ${editable ? 'cursor-text' : ''}`}
            onClick={editable ? onEdit : undefined}>{item.text}</p>
        )}
        <span className="text-10 font-mono text-tertiary flex items-center gap-6">
          {card ? t('from card {date}', { date: `${shortDay(card.at)} ${card.at.slice(11, 16)}` }) : item.card_id}
          {item.changed && <span style={{ color }}>· ● {t('edited here')}</span>}
        </span>
      </div>
      {editable && !editing && (
        <button type="button" onClick={onRemove} aria-label={t('Remove from this version')} title={t('Remove from this version')}
          className="self-start text-12 text-tertiary hover:text-status-red opacity-0 group-hover:opacity-100 focus:opacity-100 px-4">×</button>
      )}
    </div>
  )
}

/** The versions side by side: + came in, ~ changed, − left (struck), the rest quiet. */
function HistoryView({ doc, color }: { doc: Doc; color: string }) {
  const diffs = versionDiffs(doc)
  return (
    <div className="flex-1 overflow-auto px-12 py-10">
      <div className="flex gap-10 items-start min-w-0">
        {diffs.map((d) => {
          const added = d.rows.filter((r) => r.mark === 'new').length
          const changed = d.rows.filter((r) => r.mark === 'changed').length
          return (
            <div key={d.n} className="w-[240px] shrink-0 flex flex-col gap-4 rounded-input bg-surface p-8">
              <div className="flex items-baseline gap-6 text-11 font-mono">
                <b className="tabular" style={{ color: d.n === doc.current ? color : undefined }}>v{d.n}</b>
                <span className="text-tertiary">{shortDay(d.at)}</span>
                <span className="ml-auto text-10 text-tertiary tabular">
                  {added ? `+${added} ` : ''}{changed ? `~${changed} ` : ''}{d.left.length ? `−${d.left.length}` : ''}
                </span>
              </div>
              {d.note && <span className="text-10 text-secondary">{d.note}</span>}
              {d.rows.map(({ item, mark }) => (
                <p key={item.id} className={`m-0 text-11 pl-6 border-l-2 break-words ${mark === 'same' ? 'text-tertiary border-transparent' : 'text-primary'}`}
                  style={mark === 'new' ? { borderColor: color } : mark === 'changed' ? { borderColor: 'var(--status-amber)' } : undefined}>
                  <span className="font-mono text-10 mr-4 text-tertiary">{mark === 'new' ? '+' : mark === 'changed' ? '~' : '·'}</span>
                  {item.text}
                </p>
              ))}
              {d.left.map((item) => (
                <p key={`left-${item.id}`} className="m-0 text-11 pl-6 border-l-2 line-through text-tertiary break-words" style={{ borderColor: 'var(--status-red)' }}>
                  <span className="font-mono text-10 mr-4">−</span>{item.text}
                </p>
              ))}
              {d.rows.length === 0 && d.left.length === 0 && <span className="text-10 font-mono text-tertiary">{t('empty')}</span>}
              <span className="text-10 font-mono text-tertiary">{tn(d.rows.length, '{n} item', '{n} items')}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
