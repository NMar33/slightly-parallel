import type { BadgeTone as PrimitiveTone } from '../components/primitives/Badge'
import type { BadgeTone as LensTone } from './config'

const MAP: Record<LensTone, PrimitiveTone> = {
  neutral: 'neutral',
  green: 'done',
  amber: 'warning',
  red: 'error',
  blue: 'info',
  purple: 'active',
}

/** Map a lens-level tone onto the Badge primitive's tone vocabulary. */
export function toBadgeTone(tone: LensTone = 'neutral'): PrimitiveTone {
  return MAP[tone]
}
