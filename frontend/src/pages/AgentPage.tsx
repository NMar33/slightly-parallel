import { AgentDossierPage } from '../features/agents/AgentDossierPage'

/**
 * /agent/:id — one agent, on a page of its own.
 *
 * The dossier: identity on top, eight sections on a rail, the section in
 * the URL, ← → walking the project's roster. The composition lives in
 * features/agents/AgentDossierPage.
 */
export function AgentPage() {
  return <AgentDossierPage />
}

