/**
 * The tours saved on the server and the pictures already taken: one read
 * each, shared by the tour list, the studio and the live tour.
 */
import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import { EMPTY, type Manifest } from './media'
import type { Script } from './script'

export const TOUR_SCRIPTS_KEY = ['tour', 'scripts'] as const
export const TOUR_SHOTS_KEY = ['tour', 'shots'] as const

/** GET /api/tour/scripts: `{scripts: Script[]}`, every saved script. */
export function useTourScripts(enabled = true) {
  return useQuery({
    queryKey: TOUR_SCRIPTS_KEY,
    queryFn: ({ signal }) => getJson<{ scripts?: unknown }>('/api/tour/scripts', signal)
      .then((d) => (Array.isArray(d.scripts) ? (d.scripts as Script[]) : [])),
    enabled,
  })
}

/** GET /api/tour/shots: the manifest of what has been photographed. */
export function useTourShots() {
  return useQuery({
    queryKey: TOUR_SHOTS_KEY,
    queryFn: ({ signal }) => getJson<Partial<Manifest>>('/api/tour/shots', signal)
      .then((d): Manifest => ({
        files: d.files ?? [], shots: d.shots ?? [], at: d.at ?? '', view: d.view ?? {}, scale: d.scale ?? 0,
      })),
    placeholderData: EMPTY,
  })
}
