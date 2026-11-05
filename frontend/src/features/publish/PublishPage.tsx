import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Modal } from '../../components/Modal'
import { PageHeader } from '../../components/PageHeader'
import { ProjectPills } from '../../components/ProjectPills'
import { Segmented } from '../../components/Segmented'
import { StatTile, StatTiles } from '../../components/StatTile'
import { Button, Input, toast } from '../../components/primitives'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { api, qk } from '../../lib/api'
import { fail } from '../../lib/getJson'
import { isTypingTarget } from '../../lib/typing'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { DocPane } from './DocPane'
import { FeedCard } from './FeedCard'
import { docColor, docOrder, fileToUpload, itemsOf, usePublish, usePublishWrites, type Card, type Doc } from './data'
import { Kbd, Zoom } from './parts'
import { t, tn } from '../../i18n/scope/system'

/**
 * /publish — what shipped, worth telling. The cards the operator kept with
 * #publish in a chat run down the left, newest first, each with its life
 * rail; the documents he makes from them are tabs on the right, each in
 * versions. A card goes into a document with one key (1–9) or a drag.
 * Cards are only made in a chat; this page never makes one.
 */
export function PublishPage() {
  const [hash, setHash] = useHashState()
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const codes = useMemo(() => (snapshot.data?.projects ?? []).map((p) => p.code), [snapshot.data])
  const project = hash.project || codes[0] || ''
  const onProject = useCallback((c: string) => setHash({ project: c, doc: '' }), [setHash])
  return (
    <div className="flex flex-col gap-12 min-w-0">
      {project ? <Board key={project} project={project} codes={codes} onProject={onProject} />
        : snapshot.isLoading ? <LoadingSkeleton variant="card" count={3} />
          : <EmptyState title={t('No projects yet.')} />}
    </div>
  )
}

type Filter = 'all' | 'unplaced' | 'placed'

const FEED_KEY = 'sp-publish-feed'

/** Is `el` inside the visible part of `box`? The cursor scrolls only when it is not. */
function inView(el: HTMLElement, box: HTMLElement): boolean {
  const r = el.getBoundingClientRect()
  const b = box.getBoundingClientRect()
  return r.top >= b.top && r.bottom <= b.bottom
}

function Board({ project, codes, onProject }: { project: string; codes: string[]; onProject: (c: string) => void }) {
  const { data, isLoading, isError, error, refetch } = usePublish(project)
  const writes = usePublishWrites(project)
  const [hash, setHash] = useHashState()
  const [filter, setFilter] = useState<Filter>('all')
  const [cursor, setCursor] = useState('')
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const [editing, setEditing] = useState('')
  const [zoom, setZoom] = useState<{ id: string; index: number } | null>(null)
  const [newDoc, setNewDoc] = useState(false)
  const [newCard, setNewCard] = useState(false)
  const [keysShown, setKeysShown] = useState(false)
  const [history, setHistory] = useState(false)
  const [collapsed, setCollapsed] = useState(() => readPref(FEED_KEY) === 'collapsed')
  const feedRef = useRef<HTMLDivElement>(null)

  const cards = useMemo(() => (data?.cards ?? []).filter((c) => !c.archived_at), [data])
  const docs = useMemo(() => docOrder(data?.docs ?? []), [data])
  const order = useMemo(() => docs.map((d) => d.id), [docs])
  const colorOf = useCallback((docId: string) => docColor(order.indexOf(docId) === -1 ? order.length : order.indexOf(docId)), [order])
  const byId = useMemo(() => new Map(cards.map((c) => [c.id, c])), [cards])
  const shown = useMemo(() => cards.filter((c) => filter === 'all' || (filter === 'unplaced' ? c.placements.length === 0 : c.placements.length > 0)), [cards, filter])
  const cursorCard = byId.get(cursor) ?? shown[0] ?? null
  const openDocId = docs.find((d) => d.id === hash.doc)?.id ?? docs[0]?.id ?? ''
  const litDocs = useMemo(() => [...new Set((cursorCard?.placements ?? []).map((p) => p.doc_id))].sort().join(' '), [cursorCard])

  const stats = useMemo(() => ({
    unplaced: cards.filter((c) => c.placements.length === 0).length,
    edited: cards.filter((c) => c.versions.length > 0).length,
    versions: docs.reduce((n, d) => n + (d.current || 0), 0),
    items: docs.reduce((n, d) => n + itemsOf(d).length, 0),
  }), [cards, docs])

  // The mutations' own functions are stable across renders; the result
  // objects around them are not. Callbacks hang on the functions only, so
  // the memoised cards see the same props on every cursor move.
  const placeMutate = writes.place.mutate
  const textMutate = writes.cardText.mutate
  const attachMutate = writes.attach.mutate
  const removeAttachmentMutate = writes.removeAttachment.mutate

  const select = useCallback((id: string) => setCursor(id), [])
  const openDoc = useCallback((id: string) => setHash({ doc: id }), [setHash])
  const askNewDoc = useCallback(() => setNewDoc(true), [])
  const toggleFeed = useCallback(() => setCollapsed((c) => { persistPref(FEED_KEY, c ? 'open' : 'collapsed'); return !c }), [])

  const place = useCallback((doc: Doc, cardId: string, before?: string) => {
    placeMutate({ docId: doc.id, card_id: cardId, ...(before ? { before } : {}) }, {
      onSuccess: (got) => {
        if (got?.existing) toast(t('Already in {doc} v{n}.', { doc: doc.name, n: doc.current }))
        else toast.success(t('Placed in {doc} v{n}.', { doc: doc.name, n: doc.current }))
      },
      onError: fail,
    })
  }, [placeMutate])

  const saveText = useCallback((id: string, text: string) => {
    textMutate({ id, text }, { onSuccess: () => setEditing(''), onError: fail })
  }, [textMutate])
  const cancelEdit = useCallback(() => setEditing(''), [])
  const onZoom = useCallback((id: string, index: number) => setZoom({ id, index }), [])

  const attachFiles = useCallback((id: string, files: File[], title?: string) => {
    Promise.all(files.map((f) => fileToUpload(f, t('Pasted image'))))
      .then((images) => {
        const named = title ? images.map((im) => ({ ...im, title })) : images
        attachMutate({ id, images: named }, {
          onSuccess: () => toast.success(tn(named.length, 'Attached {n} image.', 'Attached {n} images.')),
          onError: fail,
        })
      }, fail)
  }, [attachMutate])
  const removeAttachment = useCallback((attachmentId: string) => {
    removeAttachmentMutate(attachmentId, { onSuccess: () => toast.success(t('Removed the image.')), onError: fail })
  }, [removeAttachmentMutate])

  // The cursor scrolls into view only when it has left it: no layout read
  // and scroll on every move through cards already on screen.
  useEffect(() => {
    const box = feedRef.current
    if (!cursor || !box) return
    const el = box.querySelector<HTMLElement>(`[data-card="${cursor}"]`)
    if (el && !inView(el, box)) el.scrollIntoView?.({ block: 'nearest' })
  }, [cursor])

  // The keys read the page through a ref: one listener for the page's
  // life, not a new one on every cursor move.
  const live = useRef({ cursorCard, shown, docs, place, zoom, newDoc, newCard, keysShown, editing, toggleFeed })
  live.current = { cursorCard, shown, docs, place, zoom, newDoc, newCard, keysShown, editing, toggleFeed }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e)) return
      const s = live.current
      if (s.zoom || s.newDoc || s.newCard || s.keysShown || s.editing) return
      if (document.querySelector('[role="dialog"]')) return
      const k = e.key
      // Enter and space on a focused button press the button.
      if ((k === 'Enter' || k === ' ') && (e.target as HTMLElement | null)?.closest?.('button, a, [role="tab"]')) return
      const card = s.cursorCard
      const at = card ? s.shown.findIndex((c) => c.id === card.id) : -1
      const move = (d: number) => {
        const next = s.shown[Math.max(0, Math.min(s.shown.length - 1, at + d))]
        if (next) setCursor(next.id)
      }
      if (k === 'j' || k === 'ArrowDown') { e.preventDefault(); move(1) }
      else if (k === 'k' || k === 'ArrowUp') { e.preventDefault(); move(-1) }
      else if ((k === 'Enter' || k === 'o') && card) {
        e.preventDefault()
        setOpen((o) => { const n = new Set(o); if (n.has(card.id)) n.delete(card.id); else n.add(card.id); return n })
      } else if (k === 'e' && card) { e.preventDefault(); setCursor(card.id); setEditing(card.id) }
      else if (/^[1-9]$/.test(k) && card) {
        e.preventDefault()
        const doc = s.docs[Number(k) - 1]
        if (doc) s.place(doc, card.id)
        else toast(t('No document {n}. Press n to make one.', { n: k }))
      } else if (k === 'n') { e.preventDefault(); setNewDoc(true) }
      else if (k === 'c') { e.preventDefault(); setNewCard(true) }
      else if (k === 'v' && s.docs.length) { e.preventDefault(); setHistory((h) => !h) }
      else if (k === 'f') { e.preventDefault(); s.toggleFeed() }
      else if (k === ' ' && card) {
        e.preventDefault()
        if (card.images.length) setZoom({ id: card.id, index: 0 })
      } else if (k === '?') { e.preventDefault(); setKeysShown(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // An image pasted while a card is selected is attached to it.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (isTypingTarget(e)) return
      const s = live.current
      if (!s.cursorCard || s.editing || document.querySelector('[role="dialog"]')) return
      const images = Array.from(e.clipboardData?.items ?? [])
        .filter((it) => it.kind === 'file' && it.type.startsWith('image/'))
        .map((it) => it.getAsFile())
        .filter((f): f is File => !!f)
      if (!images.length) return
      e.preventDefault()
      attachFiles(s.cursorCard.id, images, t('Pasted image'))
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [attachFiles])

  const header = (
    <PageHeader variant="tool" title={t('Publish')} sub={t('cards from #publish, documents made from them')}
      actions={<Button variant="text" size="bare" onClick={() => setKeysShown(true)}>{t('keys')} <Kbd>?</Kbd></Button>}
      below={
        <div className="flex flex-col gap-10">
          {codes.length > 1 && <ProjectPills label={false} dots value={project} onPick={(c) => c && onProject(c)} projects={codes} />}
          <StatTiles min={150}>
            <StatTile label={t('cards')} value={cards.length} sub={tn(stats.edited, '{n} edited', '{n} edited')} />
            <StatTile label={t('not placed')} value={stats.unplaced} sub={t('in no document')} />
            <StatTile label={t('documents')} value={docs.length} sub={tn(stats.items, '{n} item', '{n} items')} />
            <StatTile label={t('versions')} value={stats.versions} sub={t('over all documents')} />
          </StatTiles>
        </div>
      } />
  )

  if (isError) return <>{header}<ErrorBanner title={t('Could not load the cards.')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss /></>
  if (isLoading || !data) return <>{header}<LoadingSkeleton variant="card" count={3} /></>

  const zoomCard = zoom ? byId.get(zoom.id) : undefined
  const grid = collapsed
    ? 'grid-cols-[56px_minmax(0,1fr)]'
    : 'grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]'

  return (
    <>
      {header}
      <div className={`grid gap-12 ${grid} min-h-0 lg:h-[calc(100vh-250px)]`}>
        {collapsed ? (
          <FeedStrip count={shown.length} card={cursorCard} onOpen={toggleFeed} />
        ) : (
          <section className="flex flex-col min-h-0 min-w-0" aria-label={t('Cards')}>
            <div className="flex items-center gap-10 pb-8 text-11 font-mono text-tertiary shrink-0">
              <Segmented label={t('Show')} shape="pill" value={filter} onChange={setFilter}
                options={[['all', t('all'), t('Every card')], ['unplaced', t('not placed'), t('Cards in no document yet')], ['placed', t('placed'), t('Cards in at least one document')]]} />
              <span className="tabular">{shown.length}</span>
              <Button variant="text" size="bare" className="ml-auto" onClick={() => setNewCard(true)} title={t('Write a card by hand (c)')}>+ {t('card')} <Kbd>c</Kbd></Button>
              <Button variant="text" size="bare" onClick={toggleFeed} title={t('Narrow the cards to a strip (f)')}>{t('narrow')} <Kbd>f</Kbd></Button>
            </div>
            <div ref={feedRef} className="flex-1 overflow-y-auto overscroll-contain flex flex-col gap-8 pr-4 pb-24">
              {cards.length === 0 ? (
                <EmptyState title={t('No cards yet.')}
                  subtitle={t('Add #publish to a message in a chat with an agent. The message becomes a card here, with the task, its commits and its images.')} />
              ) : shown.length === 0 ? (
                <EmptyState compact title={t('No cards match.')} />
              ) : shown.map((c) => (
                <FeedCard key={c.id} card={c} order={order} colorOf={colorOf}
                  selected={cursorCard?.id === c.id} open={open.has(c.id)} editing={editing === c.id}
                  onSelect={select} onEdit={setEditing} onSave={saveText} onCancel={cancelEdit} onZoom={onZoom} onOpenDoc={openDoc}
                  onAttachFiles={attachFiles} onRemoveAttachment={removeAttachment} />
              ))}
            </div>
            <KeyLegend />
          </section>
        )}
        <DocPane project={project} docs={docs} colorOf={colorOf} openId={openDocId} onOpen={openDoc} cards={byId}
          litDocs={litDocs} history={history} onHistory={setHistory}
          onNewDoc={askNewDoc} onPlace={place} />
      </div>

      {zoom && zoomCard && (
        <Zoom images={zoomCard.images} index={zoom.index} onIndex={(i) => setZoom({ id: zoom.id, index: i })} onClose={() => setZoom(null)} />
      )}
      {newDoc && <NewDocModal project={project} onClose={() => setNewDoc(false)} onMade={openDoc} />}
      {newCard && <NewCardModal project={project} onClose={() => setNewCard(false)} onMade={(id) => setCursor(id)} />}
      {keysShown && <KeysModal onClose={() => setKeysShown(false)} />}
    </>
  )
}

/** The cards narrowed to a strip: how many, and the selected card's first words, upright. */
function FeedStrip({ count, card, onOpen }: { count: number; card: Card | null; onOpen: () => void }) {
  const words = card ? card.text.split(/\s+/).slice(0, 8).join(' ') : ''
  return (
    <button type="button" onClick={onOpen} title={t('Show the cards ([)')} aria-label={t('Show the cards ([)')}
      className="flex flex-col items-center gap-10 py-10 rounded-card border border-border-subtle bg-surface hover:border-brand min-h-0 overflow-hidden">
      <Kbd>f</Kbd>
      <span className="text-20 font-semibold tabular text-primary leading-none">{count}</span>
      <span className="text-10 font-mono uppercase tracking-wider text-tertiary [writing-mode:vertical-rl]">{t('cards')}</span>
      {words && <span className="flex-1 min-h-0 overflow-hidden text-12 text-secondary [writing-mode:vertical-rl] rotate-180 whitespace-nowrap">{words}</span>}
    </button>
  )
}

const KEYS: Array<[string, string]> = [
  ['j k', 'move through the cards'],
  ['Enter o', 'show the original and the history'],
  ['e', 'edit the card text (Enter saves, Esc cancels)'],
  ['1–9', 'place the card in document 1–9'],
  ['n', 'new document'],
  ['c', 'new card, written by hand'],
  ['v', 'history of the open document'],
  ['f', 'narrow or widen the cards'],
  ['space', 'first image large'],
  ['?', 'this list'],
]

/** The keys in one mono line, under the cards. */
function KeyLegend() {
  return (
    <div className="flex items-center gap-10 flex-wrap pt-8 border-t border-border-subtle text-10 font-mono text-tertiary shrink-0">
      <span><Kbd>j</Kbd> <Kbd>k</Kbd> {t('move')}</span>
      <span><Kbd>o</Kbd> {t('original')}</span>
      <span><Kbd>e</Kbd> {t('edit')}</span>
      <span><Kbd>1</Kbd>–<Kbd>9</Kbd> {t('place')}</span>
      <span><Kbd>n</Kbd> {t('document')}</span>
      <span><Kbd>c</Kbd> {t('card')}</span>
      <span><Kbd>v</Kbd> {t('history')}</span>
      <span><Kbd>f</Kbd> {t('narrow')}</span>
      <span><Kbd>␣</Kbd> {t('image')}</span>
      <span className="ml-auto">{t('drop or paste an image to attach it')}</span>
    </div>
  )
}

function KeysModal({ onClose }: { onClose: () => void }) {
  const label = (s: string) => {
    switch (s) {
      case 'move through the cards': return t('move through the cards')
      case 'show the original and the history': return t('show the original and the history')
      case 'edit the card text (Enter saves, Esc cancels)': return t('edit the card text (Enter saves, Esc cancels)')
      case 'place the card in document 1–9': return t('place the card in document 1–9')
      case 'new document': return t('new document')
      case 'new card, written by hand': return t('new card, written by hand')
      case 'history of the open document': return t('history of the open document')
      case 'narrow or widen the cards': return t('narrow or widen the cards')
      case 'first image large': return t('first image large')
      default: return t('this list')
    }
  }
  return (
    <Modal labelledBy="pub-keys-title" onClose={onClose} width="w-[440px]">
      <div className="flex flex-col gap-10">
        <h3 id="pub-keys-title" className="text-16 font-semibold text-primary m-0">{t('Keys')}</h3>
        <dl className="m-0 grid grid-cols-[96px_minmax(0,1fr)] gap-x-12 gap-y-6 text-12">
          {KEYS.map(([k, what]) => (
            <div key={k} className="contents">
              <dt className="font-mono text-secondary">{k.split(' ').map((p) => <span key={p} className="mr-4"><Kbd>{p}</Kbd></span>)}</dt>
              <dd className="m-0 text-primary">{label(what)}</dd>
            </div>
          ))}
        </dl>
        <p className="m-0 text-11 text-tertiary">{t('Drag a card onto a tab to place it, or onto an item to place it in front of that item.')}</p>
        <p className="m-0 text-11 text-tertiary">{t('Drop an image file on a card, or paste one while the card is selected, to attach it.')}</p>
      </div>
    </Modal>
  )
}

/** A card written here, not in a chat: the text as the operator types it. */
function NewCardModal({ project, onClose, onMade }: { project: string; onClose: () => void; onMade: (id: string) => void }) {
  const writes = usePublishWrites(project)
  const [text, setText] = useState('')
  const submit = () => {
    const body = text.trim()
    if (!body) return
    writes.newCard.mutate({ text: body }, {
      onSuccess: (got) => {
        if (got.existing) toast(t('This card is already here.'))
        onClose()
        if (got?.card?.id) onMade(got.card.id)
      },
      onError: fail,
    })
  }
  return (
    <Modal labelledBy="pub-card-title" onClose={onClose} width="w-[560px]">
      <form className="flex flex-col gap-12" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <h3 id="pub-card-title" className="text-16 font-semibold text-primary m-0">{t('New card')}</h3>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('text')}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} autoFocus maxLength={20000}
            placeholder={t('What shipped, worth telling. In a chat, #publish on a message does the same.')}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit() } }}
            className="w-full resize-y rounded-input border border-border-default bg-base px-10 py-8 text-14 text-primary outline-none focus:border-brand" />
        </label>
        <div className="flex items-center justify-end gap-8">
          <span className="mr-auto text-10 font-mono text-tertiary">{t('Ctrl+Enter saves')}</span>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>{t('Cancel')}</Button>
          <Button type="submit" size="sm" disabled={!text.trim() || writes.newCard.isPending}>{t('Make the card')}</Button>
        </div>
      </form>
    </Modal>
  )
}

function NewDocModal({ project, onClose, onMade }: { project: string; onClose: () => void; onMade: (id: string) => void }) {
  const writes = usePublishWrites(project)
  const [name, setName] = useState('')
  const submit = () => {
    const n = name.trim()
    if (!n) return
    writes.newDoc.mutate({ name: n }, {
      onSuccess: (got) => {
        if (got.existing) toast(t('A document with this name exists. It is open now.'))
        onClose()
        if (got?.doc?.id) onMade(got.doc.id)
      },
      onError: fail,
    })
  }
  return (
    <Modal labelledBy="pub-doc-title" onClose={onClose} width="w-[440px]">
      <form className="flex flex-col gap-12" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <h3 id="pub-doc-title" className="text-16 font-semibold text-primary m-0">{t('New document')}</h3>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('name')}
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoFocus placeholder={t('Name on the tab: Release note 1.2, Launch post')} />
        </label>
        <div className="flex justify-end gap-8">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>{t('Cancel')}</Button>
          <Button type="submit" size="sm" disabled={!name.trim() || writes.newDoc.isPending}>{t('Make the document')}</Button>
        </div>
      </form>
    </Modal>
  )
}
