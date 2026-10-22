/**
 * Assign a stable lane color to a project code via hash → `--lane-N` token.
 * Shared by the sidebar, overview cards, and anywhere else a project needs a
 * consistent accent.
 */
export function projectColor(code: string): string {
  let h = 0
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) | 0
  const n = (Math.abs(h) % 8) + 1
  return `var(--lane-${n})`
}
