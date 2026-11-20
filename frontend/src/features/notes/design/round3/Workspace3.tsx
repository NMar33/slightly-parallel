/**
 * Round 3 of the Notes design (tk_3e544086): J, K and L. The workspace moved
 * to the shared module the Notes page draws with (../../render/Workspace),
 * where K is the page; J and L print the keys line they had.
 */

import type { ComponentProps } from 'react'

import { t } from '../../../../i18n/scope/notes'
import { Workspace3 as Shared } from '../../render/Workspace'
import { KeysLine3 } from './Divider'

export { VIEW_KEY, type R3 } from '../../render/Workspace'

export function Workspace3(props: Omit<ComponentProps<typeof Shared>, 'keysLine'>) {
  return <Shared {...props} keysLine={props.v === 'k' ? undefined : <KeysLine3 tiles={props.v === 'l' ? t('shelves') : t('tiles')} />} />
}
