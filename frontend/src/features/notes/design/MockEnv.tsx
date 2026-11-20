/**
 * The design round's note env: the mock's chips (ENTITIES), the in-memory
 * marks (./store), the drawn stand-ins for screenshots and the mock's
 * morning as "now". Every variant draws inside it, so the shared renderer
 * (../render) reads the mock here and the server's on the Notes page.
 */

import { useMemo, type ReactNode } from 'react'

import { NoteEnvProvider, type NoteEnv } from '../render/env'
import { MockShot } from './blocks'
import { ENTITIES, MOCK_NOW } from './mock'
import { MockHeadTools } from './reader'
import { answer, markCopied, tick, useMarks } from './store'

function Picture({ src, small }: { src: string; alt: string; small?: boolean }) {
  return <MockShot src={src} small={small} />
}

export function MockNoteEnv({ children }: { children: ReactNode }) {
  const marks = useMarks()
  const env = useMemo<NoteEnv>(() => ({
    entity: (id) => ENTITIES[id], marks, tick, answer, copied: (id) => markCopied(id), Picture,
    now: () => MOCK_NOW, noteHref: (id) => `/notes/design?v=a&note=${id}`, useVersion: () => undefined, HeadTools: MockHeadTools,
  }), [marks])
  return <NoteEnvProvider value={env}>{children}</NoteEnvProvider>
}
