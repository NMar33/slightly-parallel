import { projectColor } from '../utils/projectColor'

/**
 * A project's colour dot: the sidebar, the home page and the Timer page
 * draw the same one. `glow` adds the sidebar's halo.
 */
export function ProjectDot({ code, size = 8, glow = false }: { code: string; size?: number; glow?: boolean }) {
  const color = projectColor(code)
  return (
    <span aria-hidden className="inline-block rounded-pill shrink-0"
      style={{ width: size, height: size, backgroundColor: color, boxShadow: glow ? `0 0 6px ${color}` : undefined }} />
  )
}
