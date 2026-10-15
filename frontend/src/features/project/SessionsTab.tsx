import { ChatsPage } from '../chats/ChatsPage'

/**
 * The project's Chats tab — the /chats page with the project fixed: the
 * same month, agents, outcome chips, list, reader and focus mode, without
 * the project switch and the guide. One component, so the two surfaces
 * where a conversation is read cannot drift apart again (2026-09-25; it
 * was the older sessions workbench before).
 */
export function SessionsTab({ projectCode }: { projectCode: string }) {
  return <ChatsPage fixedProject={projectCode} />
}
