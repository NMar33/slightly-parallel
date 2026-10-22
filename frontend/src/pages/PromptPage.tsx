import { PromptCompare } from '../features/promptlib/ComparePage'

/**
 * /prompts/:id — the prompt's page chosen in the Lab (v05). The body lives in
 * features/promptlib/ComparePage.tsx and is shared with the variant.
 */
export default function PromptPage() {
  return <PromptCompare />
}
