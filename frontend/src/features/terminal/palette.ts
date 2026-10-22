/*
 * The terminal's colours. xterm takes literal colours, not CSS variables,
 * so this file is on the raw-hex allowlist (scripts/check-no-raw-hex.sh);
 * keep every other colour of the terminal out of it.
 */

/** A calm dark palette: the terminal keeps its ground in both themes. */
export const THEME = {
  background: '#0E1013', foreground: '#E6E8EB', cursor: '#4FB39A', cursorAccent: '#0E1013',
  selectionBackground: 'rgba(79,179,154,0.30)',
  black: '#1B1E23', red: '#EF6B73', green: '#5CC98B', yellow: '#E8B75C', blue: '#6E9CF2', magenta: '#B98BEB', cyan: '#4FBFC8', white: '#C9CDD3',
  brightBlack: '#5B616B', brightRed: '#FF8A91', brightGreen: '#7DDBA5', brightYellow: '#F5CC7E', brightBlue: '#92B6F7', brightMagenta: '#CDA8F2', brightCyan: '#79D3DA', brightWhite: '#F3F4F6',
}
