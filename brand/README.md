# Slightly Parallel — name and identity

The product ships under the name **Slightly Parallel**. Two words, always
both: the neighbours are all one-word "Parallel" (Parallels, Parallel Works, parallel.ai),
and the adverb is the distance.

## The idea

Agents run in parallel on a project, never quite in step. Rails in perspective are the one
place where parallel lines look slightly not. The identity is that geometry: two stems, the
second leaning a few degrees. Everything else — the yard, the containers, the board — is the
world around the product, not inside it.

Chosen on 6 Oct 2026 (round 4, variant C "drawing sheet"): the wordmark lives inside its
construction drawing — ascender, x-height, baseline, descender, the 5° arc, the dimensions,
a title block — on drawing-office paper, the lean in redline rust.

- **Mark** (SP-01) — two stems, the second 5° off (7° in the favicon). The ∥ sign, slightly wrong.
- **Wordmark** (SP-10) — `slightly parallel`, lowercase, Schibsted Grotesk 700, the second *l*
  of "parallel" leaning 5°, in rust.
- **The drawing** (SP-20) — the wordmark with its construction lines and title block: the hero
  for the landing page, the README banner, the video end card, print.
- **Monogram** (SP-07) — `s∥p` for avatars and the About dialog.
- **The world** — the yard at night is the intro (SP-70); the container world is the README
  banner (SP-33) and the landing page.

Every element has an id **SP-xx** in the brand book (`kit/index.html`); say the id to change it.

## What is where

| folder | holds |
|---|---|
| `kit/` | `index.html` — the brand book, every element with its SP-id, file and caption. `files/` — every final file (SVG outlined, no font needed; PNG, ICO where a format needs it). `build.py` writes all of them and the book; `draw.py` is the drawing engine; `metrics.json` holds the glyph outlines and font metrics, made by `metrics.js` from `fonts/` (`npm i opentype.js && node metrics.js`). The colours and the lean are the constants at the top of `build.py`. |
| `video/` | `intro-yard.html` / `intro-flap.html` — the two intros drawn in code (canvas, `window.__render(t)`); `render.mjs` renders either to a VP8 `.webm` through Playwright's bundled ffmpeg (`cd frontend && node ../brand/video/render.mjs ../brand/video/intro-yard.html out 30`); `intro-yard.webm` is the final (7.5 s, ends on the sheet, SP-34); `intro-board.webm` the alternative. `render-timelapse.mjs` renders a project's Timelapse with the Slightly Parallel bookends from the running studio (`cd frontend && node ../brand/video/render-timelapse.mjs "<studio url>" out 24 25`). The end card is `kit/files/endcard.svg`, embedded into the scene by the build. An `.mp4` needs a full ffmpeg install. |
| `site/` | the landing page: the yard video as the hero, the drawing, the container banner, the install lines. Opens from disk; the links are relative to this folder. |

The fonts in `kit/fonts/` (Big Shoulders Display, JetBrains Mono, Schibsted Grotesk) are under the SIL Open Font License 1.1: `kit/fonts/OFL.txt`.

## Name check (6 Oct 2026)

`slightlyparallel` .com .dev .app .ai .org and `slightly-parallel.com` unregistered (RDAP);
GitHub, npm, PyPI, crates.io, Docker Hub and @slightlyparallel free; no product or company
under the name in web search. Not done: `.io` (registry gave no RDAP answer), trademark
databases (USPTO TESS, EUIPO TMview) by hand.

## Open

- The container world lives on the README banner, the landing page and the intro video; not on
  the kanban, whose cards stay flat tiles.
