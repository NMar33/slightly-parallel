import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from '../../../lib/getJson'
import type { Entity, Marks } from '../render/env'
import { parseNote, type Note, type NoteKind } from '../render/model'

/**
 * Notes on the server (backend notelib.py, routers/notes.py): the wire
 * shapes, the reads and the operator's writes (a tick, an answer, a copy,
 * an archive). Every write asks the notes again.
 */

export interface WireNote {
  id: string
  project: string
  kind: NoteKind
  title: string
  task: string
  entrypoint: string
  chat: string
  agent_id: string
  created: string
  updated: string
  versions: number
  archived_at: string
  replaces: string[]
  replaced_by: string
  words: number
  body: string
  images: Array<{ id: string; caption: string; width: number; height: number; src: string }>
}

export interface Feed {
  notes: WireNote[]
  marks: Marks
  entities: Record<string, Omit<Entity, 'id'>>
  projects: string[]
}

export const KEY = ['notes'] as const

export function toNote(w: WireNote, body = w.body): Note {
  return parseNote({
    id: w.id, project: w.project, kind: w.kind, task: w.task, chat: w.chat, entrypoint: w.entrypoint || undefined,
    created: w.created, updated: w.updated, versions: w.versions, body,
    replacedBy: w.replaced_by || undefined, replaces: w.replaces, images: w.images, archivedAt: w.archived_at || undefined,
  })
}

export function useNotesFeed(params: { task?: string; archived?: boolean } = {}, enabled = true) {
  const q = new URLSearchParams()
  if (params.task) q.set('task', params.task)
  if (params.archived) q.set('archived', 'true')
  return useQuery({
    queryKey: [...KEY, 'feed', params.task ?? '', !!params.archived],
    queryFn: ({ signal }) => getJson<Feed>(`/api/notes/feed${q.size ? `?${q}` : ''}`, signal),
    enabled,
  })
}

/** An earlier version's text, read when the operator picks it. */
export function useNoteVersionText(id: string, n: number | null) {
  return useQuery({
    queryKey: [...KEY, 'version', id, n],
    queryFn: ({ signal }) => getJson<WireNote>(`/api/notes/${id}/full?v=${n}`, signal),
    enabled: n != null,
    staleTime: Infinity,
  })
}

export type MarkKind = 'tick' | 'answer' | 'copy'

export function useNoteWrites() {
  const qc = useQueryClient()
  const again = () => qc.invalidateQueries({ queryKey: KEY })
  const mark = useMutation({
    mutationFn: (m: { item: string; kind: MarkKind; value: boolean | number | '' }) =>
      postJson(`/api/notes/${m.item.split(':')[0]}/marks`, { item: m.item, kind: m.kind, value: m.value }),
    onSettled: again,
  })
  const archive = useMutation({
    mutationFn: (a: { id: string; archived: boolean }) => postJson(`/api/notes/${a.id}/archive`, { archived: a.archived }),
    onSettled: again,
  })
  return { mark, archive }
}
