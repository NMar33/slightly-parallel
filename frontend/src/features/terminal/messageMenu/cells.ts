import type { IBufferLine } from 'xterm'

/** A row's text with the cell each character stands in (a wide character takes two cells). */
export function lineCells(line: IBufferLine): { text: string; cells: number[] } {
  let text = ''
  const cells: number[] = []
  for (let x = 0; x < line.length; x++) {
    const c = line.getCell(x)
    if (!c || c.getWidth() === 0) continue
    const ch = c.getChars() || ' '
    text += ch
    for (let i = 0; i < ch.length; i++) cells.push(x)
  }
  return { text, cells }
}
