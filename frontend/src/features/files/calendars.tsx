import { type FleetEntry, type FleetPayload } from './fleet'

/** The fleet payload the days list reads. */
export type Data = FleetPayload

/** What one checkpoint says, when there is room for one line about it. */
export const headline = (e: FleetEntry) => e.l1.replace(/^\+?[\d/−-]+ · /, '').replace(/^\d+ files · /, '')
