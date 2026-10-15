import { useEffect, useMemo, useState } from 'react'
import { projectColor } from '../utils/projectColor'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Layers, Plus, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { persistPref, readPref } from '../lib/uiPrefs'

import { api, qk } from '../lib/api'
import { getJson, postJson } from '../lib/getJson'
import { Modal } from '../components/Modal'
import { Button, Input } from '../components/primitives'
import { LABEL } from '../features/promptlib/taskstyle'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/states'
import { TasksKanban, type KanbanBoard } from '../features/project/TasksKanban'
import { PageHeader } from '../components/PageHeader'
import { KANBAN_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t, tn } from '../i18n/scope/pages'

/**
 * KanbanPage — every board in one place.
 *
 * The strip at the top lists one board per project, then the saved boards
 * (combined: several projects seen as one; standalone: a tasks-only board
 * with its own code), then "+ new board". The board below is the same
 * component the project page uses, fed a board instead of a project.
 */

interface SavedBoard extends KanbanBoard {
  standalone?: boolean
}

const LAST_BOARD_KEY = 'sp-kanban-board'

export default function KanbanPage() {
  useEffect(() => {
    document.title = `${t('Kanban')} — Slightly Parallel`
  }, [])
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()

  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const saved = useQuery({
    queryKey: ['boards'],
    queryFn: ({ signal }) => getJson<{ boards: SavedBoard[] }>('/api/boards', signal),
  })

  const projectBoards: KanbanBoard[] = useMemo(
    () =>
      (snapshot.data?.projects ?? []).map((p) => ({
        id: p.code,
        name: p.name || p.code,
        projects: [p.code],
      })),
    [snapshot.data],
  )
  const savedBoards = useMemo(() => saved.data?.boards ?? [], [saved.data])
  const all: KanbanBoard[] = useMemo(
    () => [...projectBoards, ...savedBoards.filter((b) => !projectBoards.some((p) => p.id === b.id))],
    [projectBoards, savedBoards],
  )

  // Current board: ?board= wins, then the last one used, then the first.
  const requested = params.get('board') || readPref(LAST_BOARD_KEY) || ''
  const current = all.find((b) => b.id === requested) ?? all[0]
  const pick = (id: string) => {
    setParams((p) => { p.set('board', id); return p }, { replace: true })
    persistPref(LAST_BOARD_KEY, id)
  }

  const [creating, setCreating] = useState(false)
  const del = useMutation({
    mutationFn: (id: string) => postJson(`/api/boards/${encodeURIComponent(id)}/delete`, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['boards'] })
      pick(projectBoards[0]?.id ?? '')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if ((snapshot.isLoading && !snapshot.data) || (saved.isLoading && !saved.data)) return <LoadingSkeleton variant="row" count={4} />
  if (snapshot.isError || saved.isError) {
    return (
      <ErrorBanner
        title={t('Could not load boards')}
        onRetry={() => { void snapshot.refetch(); void saved.refetch() }}
        hideDismiss
      />
    )
  }

  return (
    <div className="flex flex-col gap-16">
      <PageHeader
        variant="tool"
        title={t('Kanban')}
        sub={`${tn(projectBoards.length, '{n} project board', '{n} project boards')}${savedBoards.length ? ` · ${t('{n} saved', { n: savedBoards.length })}` : ''}`}
      />
      <PageGuide id="kanban" guide={KANBAN_GUIDE} examples={0} />

      {/* Board strip */}
      <nav aria-label={t('Boards')} className="flex items-center gap-4 flex-wrap">
        {projectBoards.map((b) => (
          <BoardChip key={b.id} board={b} active={current?.id === b.id} onPick={() => pick(b.id)} />
        ))}
        {savedBoards.length > 0 && <span className="w-px h-16 bg-border-default mx-2" aria-hidden />}
        {savedBoards.map((b) => (
          <BoardChip
            key={b.id}
            board={b}
            saved
            active={current?.id === b.id}
            onPick={() => pick(b.id)}
            onDelete={() => del.mutate(b.id)}
          />
        ))}
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-4 h-20 px-8 rounded-pill border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-brand hover:border-brand transition-colors"
        >
          <Plus size={12} aria-hidden /> {t('new board')}
        </button>
      </nav>

      {current ? (
        <section className="flex flex-col gap-8">
          {current.projects.length > 1 && (
            <p className="text-12 text-tertiary flex items-center gap-6">
              <Layers size={12} aria-hidden />
              {t("This board shows the tasks of {projects} together. A task made here is filed under all of them, with the first as its home project. Untick projects in the task window's Projects row.", { projects: current.projects.join(' · ') })}
            </p>
          )}
          {current.projects.length === 1 && !projectBoards.some((p) => p.id === current.id) && (
            <p className="text-12 text-tertiary">
              {t('Standalone board: its tasks are filed under the code')} <code>{current.projects[0]}</code>{' '}
              ({t('a data-only project; it can be removed in')}{' '}
              <Link to="/setup" className="text-brand hover:underline">{t('Setup')}</Link>).
            </p>
          )}
          <TasksKanban
            key={current.id}
            projectCode={current.projects[0]!}
            board={current}
          />
        </section>
      ) : (
        <EmptyState
          title={t('No boards yet')}
          subtitle={t('Integrate a project on Setup, or create a standalone board.')}
        />
      )}

      {creating && (
        <NewBoardDialog
          projects={projectBoards.map((p) => p.id)}
          onClose={() => setCreating(false)}
          onCreated={(b) => {
            setCreating(false)
            void queryClient.invalidateQueries({ queryKey: ['boards'] })
            pick(b.id)
          }}
        />
      )}
    </div>
  )
}

function BoardChip({
  board, active, saved, onPick, onDelete,
}: {
  board: KanbanBoard
  active: boolean
  saved?: boolean
  onPick: () => void
  onDelete?: () => void
}) {
  return (
    <span
      className={`inline-flex items-center gap-4 h-20 pl-8 ${onDelete ? 'pr-2' : 'pr-8'} rounded-pill border text-11 font-mono whitespace-nowrap transition-colors ${
        active ? 'border-brand text-brand bg-brand-glow' : 'border-border-subtle text-secondary hover:text-primary'
      }`}
    >
      <button type="button" onClick={onPick} className="inline-flex items-center gap-4" aria-current={active || undefined}>
        {saved && board.projects.length > 1 && <Layers size={11} aria-hidden />}
        {!(saved && board.projects.length > 1) && (
          <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: projectColor(board.projects[0] ?? board.id) }} aria-hidden />
        )}
        {board.name}
        {saved && board.projects.length > 1 && (
          <span className="opacity-60">{board.projects.length}</span>
        )}
      </button>
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={t('Remove board {name}', { name: board.name })}
          title={t('Remove this board; its tasks are kept')}
          className="h-16 w-16 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-error hover:bg-hover"
        >
          <Trash2 size={10} aria-hidden />
        </button>
      )}
    </span>
  )
}

function NewBoardDialog({
  projects, onClose, onCreated,
}: {
  projects: string[]
  onClose: () => void
  onCreated: (b: SavedBoard) => void
}) {
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const create = useMutation({
    mutationFn: () => postJson<SavedBoard>('/api/boards', { name: name.trim(), projects: picked }),
    onSuccess: onCreated,
    onError: (e: Error) => toast.error(e.message),
  })
  const toggle = (c: string) => setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]))
  const standalone = picked.length === 0
  return (
    <Modal label={t('New board')} onClose={onClose} width="w-[440px]">
      <div className="flex flex-col gap-12">
        <div className="flex items-center gap-8">
          <h2 className="text-14 font-semibold text-primary">{t('New board')}</h2>
          <button type="button" onClick={onClose} aria-label={t('Close')} className="ml-auto h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover">
            <X size={14} aria-hidden />
          </button>
        </div>
        <form
          className="flex flex-col gap-10"
          onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate() }}
        >
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder={t('Board name')}
            aria-label={t('Board name')}
            maxLength={60}
          />
          <div className="flex flex-col gap-6">
            <span className={LABEL}>
              {t('Projects: tick several to combine them, or none for a standalone board')}
            </span>
            <div className="flex flex-wrap gap-6">
              {projects.map((c) => {
                const on = picked.includes(c)
                return (
                  <button
                    key={c}
                    type="button"
                    role="checkbox"
                    aria-checked={on}
                    onClick={() => toggle(c)}
                    className={`inline-flex items-center gap-4 px-8 h-24 rounded-input border text-11 font-mono transition-colors ${
                      on ? 'border-brand text-brand bg-brand/8' : 'border-border-default text-tertiary hover:text-primary'
                    }`}
                  >
                    <span className={`inline-block w-8 h-8 rounded-bar ${on ? 'bg-brand' : 'border border-border-default'}`} aria-hidden />
                    {c}
                  </button>
                )
              })}
            </div>
          </div>
          <p className="text-11 text-tertiary leading-relaxed">
            {standalone
              ? <>{t('Standalone: tasks get their own code')} (<code>{name.trim() ? name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') : '…'}</code>), {t('a data-only project.')}</>
              : <>{t('Combined: {projects}. One board; a new task belongs to all of them.', { projects: picked.join(' · ') })}</>}
          </p>
          <div className="flex items-center gap-8 justify-end">
            <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('Cancel')}</Button>
            <Button variant="primary" size="sm" type="submit" disabled={!name.trim() || create.isPending}>
              {t('Create')}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  )
}
