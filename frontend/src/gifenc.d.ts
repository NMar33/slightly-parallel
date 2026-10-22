/** gifenc ships no types; these are the three calls the exporter uses. */
declare module 'gifenc' {
  export type Palette = number[][]
  export function quantize(
    rgba: Uint8Array | Uint8ClampedArray,
    maxColors: number,
    opts?: { format?: 'rgb565' | 'rgb444' | 'rgba4444'; oneBitAlpha?: boolean },
  ): Palette
  export function applyPalette(
    rgba: Uint8Array | Uint8ClampedArray,
    palette: Palette,
    format?: 'rgb565' | 'rgb444' | 'rgba4444',
  ): Uint8Array
  export function GIFEncoder(opts?: { auto?: boolean; initialCapacity?: number }): {
    writeFrame(
      index: Uint8Array,
      width: number,
      height: number,
      opts?: {
        palette?: Palette
        delay?: number
        repeat?: number
        first?: boolean
        transparent?: boolean
        transparentIndex?: number
        /** The GIF disposal method; 1 keeps the frame for the next one to paint over. */
        dispose?: number
      },
    ): void
    finish(): void
    bytes(): Uint8Array
  }
}
