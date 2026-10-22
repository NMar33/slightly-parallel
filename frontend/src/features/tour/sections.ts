/**
 * The presets as the /tour page lists them: one group per article section,
 * in the order the library files them, every preset once.
 */

import type { Script } from './script'

export type SectionGroup = { name: string; scripts: Script[] }

export function bySection(scripts: Script[]): SectionGroup[] {
  const groups: SectionGroup[] = []
  for (const s of scripts) {
    const name = s.section ?? ''
    const group = groups.find((g) => g.name === name)
    if (group) group.scripts.push(s)
    else groups.push({ name, scripts: [s] })
  }
  return groups
}
