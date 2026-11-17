/**
 * The small parts every variant draws a note with — moved to the shared
 * module (../render/parts). The mock's "now" is the morning of the round.
 */

import { agoOf as ago, stampOf as stamp } from '../render/parts'
import { MOCK_NOW } from './mock'

export * from '../render/parts'

export const stampOf = (at: string, now = MOCK_NOW) => stamp(at, now)
export const agoOf = (at: string, now = MOCK_NOW) => ago(at, now)
