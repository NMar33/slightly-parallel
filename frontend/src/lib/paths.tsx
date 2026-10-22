import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getJson } from './getJson'

/**
 * One reading of a project's folder, and one way to copy a path.
 *
 * The pages show a path the way the agent wrote it: relative to the
 * project folder, because that is how the agent reads it. A path copied
 * out of a page goes into a terminal or an editor, where only an absolute
 * path works. So everything that copies a path copies it absolute.
 *
 * A page that knows its project wraps itself in `ProjectFolder`; anything
 * inside it, however deep, reads the folder with `useFolder()`.
 */

interface FoldersAnswer {
  folders: Record<string, string>
  data_root: string
}

function useProjectFolders() {
  return useQuery({
    queryKey: ['project-folders'],
    queryFn: ({ signal }) => getJson<FoldersAnswer>('/api/projects/folders', signal),
    staleTime: 10 * 60 * 1000,
  })
}

/** The project's folder on this machine, or undefined while it loads. */
export function useProjectFolder(project: string | undefined): string | undefined {
  const { data } = useProjectFolders()
  return project ? data?.folders?.[project] : undefined
}

const FolderContext = createContext<string | undefined>(undefined)

/** Give everything inside the folder of one project. */
export function ProjectFolder({ project, children }: { project: string | undefined; children: ReactNode }) {
  const folder = useProjectFolder(project)
  return <FolderContext.Provider value={folder}>{children}</FolderContext.Provider>
}

/** The folder of the project this part belongs to. */
export function useFolder(): string | undefined {
  return useContext(FolderContext)
}

const SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i

/** A path in a page, not prose: it has a folder step or a file suffix, and no spaces. */
export function looksLikePath(text: string): boolean {
  const t = (text ?? '').trim()
  if (!t || /\s/.test(t)) return false
  return t.includes('/') || /\.[A-Za-z0-9]{1,6}$/.test(t)
}

/**
 * The path as a person can paste it. A relative path is joined to the
 * folder; a path that is already absolute, a home path, a URL or prose is
 * given back unchanged. `file:Symbol` keeps its symbol.
 */
export function absolutePath(folder: string | undefined, path: string): string {
  const p = (path ?? '').trim()
  if (!p || !folder) return p
  if (p.startsWith('/') || p.startsWith('~') || SCHEME.test(p)) return p
  if (!looksLikePath(p.split(':')[0])) return p
  return `${folder.replace(/\/+$/, '')}/${p.replace(/^\.\//, '')}`
}
