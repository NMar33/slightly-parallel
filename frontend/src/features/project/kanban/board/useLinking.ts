/**
 * Links mode: the overlay of lines between linked cards, plus the link
 * ports (drag a port onto a card, or click port then card) to create one;
 * hovering a linked card lights its whole graph.
 */

import { useEffect, useMemo, useState } from 'react'
import { toast } from '../../../../components/primitives'
import { postJson } from '../../../../lib/getJson'
import { persistPref, readPref } from '../../../../lib/uiPrefs'
import { OPERATOR_ACTOR } from '../../types'
import { linkGraph, linkInfoByTask } from '../model'
import type { LinkKind, TaskLink } from '../model'
import { t } from '../../../../i18n/scope/project'

export function useLinking({ links, reloadLinks }: {
  links: TaskLink[]
  reloadLinks: () => Promise<unknown>
}) {
  const [linksMode, setLinksMode] = useState(() => readPref('sp-kanban-links') === '1')
  const [linksHelp, setLinksHelp] = useState(false)
  const [linkSource, setLinkSource] = useState<string | null>(null)
  const [pendingLink, setPendingLink] = useState<{ from: string; to: string } | null>(null)
  const toggleLinks = (v: boolean) => {
    setLinksMode(v)
    setLinkSource(null)
    persistPref('sp-kanban-links', v ? '1' : '0')
    // The first time the switch goes on, say how linking works — once.
    if (v && readPref('sp-kanban-links-seen') !== '1') {
      persistPref('sp-kanban-links-seen', '1')
      setLinksHelp(true)
    }
  }
  const linkInfo = useMemo(() => linkInfoByTask(links), [links])
  const [hoverId, setHoverId] = useState<string | null>(null)
  // Hovering a linked card lights its whole graph: direct links strong,
  // the rest lighter, everything else fades.
  const hoverGraph = useMemo(
    () => (hoverId && linkInfo[hoverId]?.n ? linkGraph(links, hoverId) : null),
    [hoverId, links, linkInfo],
  )
  useEffect(() => {
    if (!linkSource && !pendingLink) return
    // One Esc backs out of whatever linking step is open.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setPendingLink(null)
      setLinkSource(null)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('keyup', onKey)
    }
  }, [linkSource, pendingLink])

  const createLink = async (from: string, to: string, kind: LinkKind) => {
    setPendingLink(null)
    setLinkSource(null)
    try {
      await postJson(`/api/tasks/${encodeURIComponent(from)}/link`, { to, kind, actor: OPERATOR_ACTOR })
      await reloadLinks()
    } catch (e) {
      toast.error(t('Couldn\'t link: {error}', { error: (e as Error).message }))
    }
  }
  const deleteLink = async (id: string) => {
    try {
      await postJson(`/api/tasks/links/${encodeURIComponent(id)}/delete`, { actor: OPERATOR_ACTOR })
      await reloadLinks()
    } catch (e) {
      toast.error(t("Couldn't remove the link: {reason}", { reason: (e as Error).message }))
    }
  }
  /** Change a link's kind or direction; answers its new id (the id
   *  follows the ends and the kind), or null when refused. */
  const updateLink = async (id: string, change: { kind?: LinkKind; reverse?: boolean }): Promise<string | null> => {
    try {
      const r = await postJson<{ link: { id: string } }>(`/api/tasks/links/${encodeURIComponent(id)}/update`, { ...change, actor: OPERATOR_ACTOR })
      await reloadLinks()
      return r.link.id
    } catch (e) {
      toast.error(t('Couldn\'t change the link: {error}', { error: (e as Error).message }))
      return null
    }
  }
  /** A card was clicked while a link source is armed, or a port was dropped on it. */
  const targetPicked = (to: string) => {
    if (!linkSource || linkSource === to) { setLinkSource(null); return }
    setPendingLink({ from: linkSource, to })
  }

  return {
    linksMode, toggleLinks, linksHelp, setLinksHelp, linkInfo, hoverId, setHoverId, hoverGraph,
    linkSource, setLinkSource, pendingLink, setPendingLink, createLink, deleteLink, updateLink, targetPicked,
  }
}
