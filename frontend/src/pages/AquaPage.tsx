import { useSearchParams } from 'react-router-dom'

import { AquaDesign } from '../features/aqua/design/AquaDesign'
import { TerminalExperiments } from '../features/aqua/design/TerminalExperiments'

/** SP Aqua: the design round's variants of the desktop terminal app, on mock data (tk_bbb84183). */
export default function AquaPage() {
  const [params] = useSearchParams()
  return params.get('experiments') === 'terminal' ? <TerminalExperiments /> : <AquaDesign />
}
