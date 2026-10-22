"""Builds every final file of the Slightly Parallel identity (variant C, "drawing sheet") and the brand book.

    python3 build.py            -> files/*.svg, files/*.png (via Playwright, see render step), index.html

Every element has an id SP-xx; the book shows the id next to the element and names its file.
Change a colour or a measure here, run again, and every file follows.
"""
import os, re, json, subprocess, sys
from draw import (M, glyphs, label, hair, dim, arc, specimen, title_block, mark_drawing, mark_small, r)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'files'); os.makedirs(OUT, exist_ok=True)

# ---- the system -----------------------------------------------------------------------------
PAPER = '#F3F1EA'; INK = '#17181A'; HAIR = '#B9B4A5'; LABEL = '#7D7766'; RUST = '#B5533C'; GRID = '#E2DED1'
DARK_BG = '#0C0E0E'; DARK_INK = '#F2F4F3'; DARK_HAIR = '#2E3634'; DARK_LABEL = '#8A918E'; RUST_ON_DARK = '#D0694F'
LEAN = 5            # degrees, wordmark / mark / monogram
LEAN_SMALL = 7      # favicon 32 and 16
SHEET = dict(bg=PAPER, ink=INK, hair=HAIR, label=LABEL, accent=RUST, grid=GRID)
SHEET_DARK = dict(bg=DARK_BG, ink=DARK_INK, hair=DARK_HAIR, label=DARK_LABEL, accent=RUST_ON_DARK, grid='#1C2321')
TB = [('DRAWING', 'WORDMARK, LOWERCASE'), ('SCALE', '1 : 1'), ('LEAN', f'{LEAN}° · SECOND L'), ('SHEET', '1 OF 1'), ('REV', 'A · 2026-10-06')]
TAG = 'A DASHBOARD FOR CODING AGENTS · SELF-HOSTED · ONE LAPTOP'
LEAN_IDX = 14       # 'slightly parallel' -> the second l of parallel

def svg(w, h, body, extra=''):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"{extra}>\n{body}\n</svg>\n'

def wordmark_file(ink, accent, bg=None, size=100):
    L = M['sg']['lower']; w = L['width'] * size; m = M['sg']['metrics']
    pad = size * 0.14; W = r(w + pad * 2); H = r((m['asc'] - m['desc']) * size + pad * 2)
    g, _, _ = glyphs('sg', 'lower', size, pad, pad + m['asc'] * size, LEAN_IDX, LEAN, ink, accent)
    body = (f'<rect width="{W}" height="{H}" fill="{bg}"/>\n' if bg else '') + g
    return svg(W, H, body)

def mark_file(ink, accent, bg=None, box=64, angle=LEAN, radius=None):
    body = mark_small(0, 0, box, dict(ink=ink, accent=accent), angle, bg=None)
    if bg: body = f'<rect width="{box}" height="{box}" rx="{radius if radius is not None else box * 0.22}" fill="{bg}"/>' + body
    return svg(box, box, body)

def monogram_file(ink, accent, bg=None, size=100):
    s = M['sg']['s']['recs'][0]; p = M['sg']['p']['recs'][0]; m = M['sg']['metrics']
    xh = -s['bb']['y1'] * size; sw = size * 0.135; gap = size * 0.085
    sx = 0; stems_x = M['sg']['s']['width'] * size + size * 0.08; px = stems_x + sw * 2 + gap + size * 0.08
    w = px + M['sg']['p']['width'] * size; asc = m['asc'] * size; desc = -m['desc'] * size; pad = size * 0.14
    W = r(w + pad * 2); H = r(asc + desc + pad * 2)
    def stem(x, rot, fill):
        t = f' transform="rotate({rot} {r(x + sw / 2)} 0)"' if rot else ''
        return f'<rect x="{r(x)}" y="{r(-xh)}" width="{r(sw)}" height="{r(xh)}" rx="{r(sw / 2)}" fill="{fill}"{t}/>'
    inner = (f'<g transform="scale({size})"><path fill="{ink}" d="{s["d"]}"/></g>' + stem(stems_x, 0, ink) + stem(stems_x + sw + gap, -LEAN, accent)
             + f'<g transform="translate({r(px)} 0) scale({size})"><path fill="{ink}" d="{p["d"]}"/></g>')
    body = (f'<rect width="{W}" height="{H}" rx="{r(W * 0.18)}" fill="{bg}"/>\n' if bg else '') + f'<g transform="translate({pad} {r(pad + asc)})">{inner}</g>'
    return svg(W, H, body)

def stacked_file(th, dark=False):
    W, H = 760, 330
    s = [f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>']
    s.append(f'<g transform="translate({(W - 120) / 2} 24)">{mark_small(0, 0, 120, th, LEAN)}</g>')
    g, w, _ = glyphs('sg', 'lower', 90, (W - M['sg']['lower']['width'] * 90) / 2, 262, LEAN_IDX, LEAN, th['ink'], th['accent'])
    s.append(g)
    return svg(W, H, '\n'.join(s))

def specimen_file(th, W=1120, H=460, size=118, level='full', tb=True, grid=True):
    body = specimen('sg', 'lower', size, W, H, th, LEAN_IDX, LEAN, level, y0=H * 0.56, grid=grid, title=TB if tb else None)
    return svg(W, H, body)

def banner_file(th):
    W, H = 1280, 320
    body = specimen('sg', 'lower', 96, W, H, th, LEAN_IDX, LEAN, 'full', x0=72, y0=H * 0.62, grid=True, title=TB)
    body += label(72, H - 40, TAG, th['label'], 11, tracking=2.2)
    return svg(W, H, body)

def endcard_file(th):
    W, H = 1920, 1080
    body = specimen('sg', 'lower', 160, W, H, th, LEAN_IDX, LEAN, 'full', y0=H * 0.58, grid=True, title=TB)
    body += label(W / 2, H * 0.58 + 120, 'AGENTS, SIDE BY SIDE', th['label'], 22, anchor='middle', tracking=8)
    return svg(W, H, body)

def banner_containers_file():
    """README banner on the dark ground: plate monogram + wordmark left, the container train right."""
    W, H = 1280, 320
    scene = open(os.path.join(HERE, 'container-scene.svg')).read()
    scene = re.sub(r'<svg [^>]*>', '', scene, count=1).rsplit('</svg>', 1)[0]
    # the light ballast bed and sleepers become night tones
    scene = scene.replace('fill="#B6BAB8"', 'fill="#1A1F22"').replace('fill="#C9CDCB"', 'fill="#15191C"').replace('fill="#9AA09D"', 'fill="#2A3034"').replace('fill="#DDE3E1"', 'fill="#1A1F22"')
    mono = monogram_file(DARK_INK, RUST_ON_DARK, bg='#1E2427')
    mono = re.sub(r'<svg [^>]*>', '', mono, count=1).rsplit('</svg>', 1)[0]
    body = [f'<rect width="{W}" height="{H}" fill="{DARK_BG}"/>',
            f'<defs><linearGradient id="fadeL" x1="0" x2="1"><stop offset="0" stop-color="{DARK_BG}"/><stop offset="1" stop-color="{DARK_BG}" stop-opacity="0"/></linearGradient><radialGradient id="haze" cx="0.75" cy="0.1" r="0.7"><stop offset="0" stop-color="#E8A33D" stop-opacity="0.18"/><stop offset="1" stop-color="#E8A33D" stop-opacity="0"/></radialGradient></defs>',
            f'<svg x="520" y="0" width="760" height="320" viewBox="230 150 902 380" preserveAspectRatio="xMidYMid slice">{scene}</svg>',
            f'<rect x="520" y="0" width="200" height="{H}" fill="url(#fadeL)"/>',
            f'<rect width="{W}" height="{H}" fill="url(#haze)"/>',
            f'<g transform="translate(72 70) scale(0.42)"><rect x="0" y="0" width="{W}" height="0"/>{mono}</g>']
    g, w, _ = glyphs('sg', 'lower', 56, 72, 232, LEAN_IDX, LEAN, DARK_INK, RUST_ON_DARK)
    body.append(g)
    body.append(label(74, 268, TAG, DARK_LABEL, 11, tracking=2.2))
    return svg(W, H, '\n'.join(body))

def sidebar_file(dark):
    W, H = 240, 110
    th = SHEET_DARK if dark else dict(SHEET, bg='#FFFFFF', hair='#DCE1DF', label='#8A918E', ink='#101113')
    s = [f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>', mark_small(16, 18, 28, th, LEAN)]
    g, w, _ = glyphs('sg', 'lower', 15, 50, 38, LEAN_IDX, LEAN, th['ink'], th['accent'])
    s.append(g); s.append(label(W - 12, 36, 'v1.0', th['label'], 8, anchor='end'))
    s.append(f'<g font-family="system-ui,sans-serif" font-size="11" fill="{"#B6BEBB" if dark else "#4B5250"}"><text x="18" y="76">Settings</text><text x="18" y="96">Monitor</text></g>')
    return svg(W, H, '\n'.join(s))

def tab_file():
    W, H = 420, 44
    s = [f'<rect width="{W}" height="{H}" rx="6" fill="#DEE2E0"/><rect x="8" y="8" width="230" height="36" rx="8" fill="#FFFFFF"/>',
         f'<g transform="translate(18 18) scale(0.25)">{mark_small(0, 0, 64, dict(ink=DARK_INK, accent=DARK_INK), LEAN_SMALL, bg=INK)}</g>',
         f'<text x="42" y="30" font-family="system-ui,sans-serif" font-size="12" fill="#101113">Tasks — Slightly Parallel</text><text x="262" y="30" font-family="system-ui,sans-serif" font-size="12" fill="#8A918E">New tab</text>']
    return svg(W, H, '\n'.join(s))

def mark_drawing_file(th):
    return svg(400, 300, mark_drawing(400, 300, th, LEAN, 64, 'full'))

# ---- the elements: id, title, file, builder, caption -------------------------------------------
E = []
def el(id, title, file, builder, caption, group, bg=None, width=None):
    E.append(dict(id=id, title=title, file=file, builder=builder, caption=caption, group=group, bg=bg, width=width))

el('SP-01', 'Mark', 'mark-ink.svg', lambda: mark_file(INK, RUST), 'Two stems, the second 5° off. Ink, the leaning stem rust. Use on paper and light grounds.', 'marks', width=96)
el('SP-02', 'Mark, one colour', 'mark-ink-mono.svg', lambda: mark_file(INK, INK), 'The same without the accent, for one-colour print and stamps.', 'marks', width=96)
el('SP-03', 'Mark on dark', 'mark-paper.svg', lambda: mark_file(DARK_INK, RUST_ON_DARK), 'Paper stems on the dark ground; the rust is lifted one step for contrast.', 'marks', bg=DARK_BG, width=96)
el('SP-04', 'Mark in a plate', 'mark-plate.svg', lambda: mark_file(DARK_INK, RUST_ON_DARK, bg=INK, box=64), 'The mark in its rounded ink plate: avatars, the sidebar head, the About page.', 'marks', width=96)
el('SP-05', 'Favicon', 'favicon.svg', lambda: mark_file(DARK_INK, DARK_INK, bg=INK, box=64, angle=LEAN_SMALL), f'7° instead of 5°: at 32 and 16 px five degrees is under a pixel. One colour. Also favicon.ico (16/32/48/64) and favicon-16/32/64.png.', 'marks', width=64)
el('SP-06', 'App icon', 'app-icon.svg', lambda: mark_file(DARK_INK, RUST_ON_DARK, bg=INK, box=512, angle=LEAN, radius=112), '512 px, radius 112. Also app-icon-128/256/512.png.', 'marks', width=128)
el('SP-07', 'Monogram s∥p', 'monogram-ink.svg', lambda: monogram_file(INK, RUST), 'The s and p from the wordmark with the two stems between them at x-height. Social avatars, the About dialog.', 'marks', width=220)
el('SP-08', 'The logo: monogram in a plate', 'monogram-plate.svg', lambda: monogram_file(DARK_INK, RUST_ON_DARK, bg=INK), 'The logo (chosen 6 Oct): the app icon, avatars, the sidebar head, the README banner. The ∥ mark alone stays for the favicon.', 'marks', width=220)

el('SP-10', 'Wordmark', 'wordmark-ink.svg', lambda: wordmark_file(INK, RUST), 'slightly parallel, lowercase, Schibsted Grotesk 700, the second l of "parallel" leaning 5°, in rust. Outlined: no font needed.', 'wordmark', width=560)
el('SP-11', 'Wordmark, one colour', 'wordmark-ink-mono.svg', lambda: wordmark_file(INK, INK), 'Ink only. The lean still reads at 120 px and above.', 'wordmark', width=560)
el('SP-12', 'Wordmark on dark', 'wordmark-paper.svg', lambda: wordmark_file(DARK_INK, RUST_ON_DARK), 'For the dashboard\'s dark theme and the video.', 'wordmark', bg=DARK_BG, width=560)
el('SP-13', 'Stacked lockup', 'stacked-ink.svg', lambda: stacked_file(SHEET), 'Mark over wordmark on the sheet paper; splash screens, the About page, a square post.', 'wordmark', width=560)
el('SP-14', 'Stacked lockup, dark', 'stacked-paper.svg', lambda: stacked_file(SHEET_DARK), 'The same on the dark ground.', 'wordmark', width=560)

el('SP-20', 'The drawing, dark (default)', 'drawing-dark.svg', lambda: specimen_file(SHEET_DARK), 'The wordmark inside its construction: ascender 732, x-height 527, baseline, descender 190 (per mille of the em), the leaning l\'s upright ghost, the 5° arc, the offset at the top and the stem width, the title block. This is the hero for the landing page and the About page.', 'drawing')
el('SP-25', 'The drawing, paper', 'drawing.svg', lambda: specimen_file(SHEET), 'The same on the paper sheet, for print.', 'drawing')
el('SP-21', 'The drawing, lines only', 'drawing-lines.svg', lambda: specimen_file(SHEET, level='lines', tb=False, grid=False), 'Hairlines and the arc, no labels, no title block: for places with less room (a section header, a print footer).', 'drawing')
el('SP-22', 'The drawing, one arc', 'drawing-arc.svg', lambda: specimen_file(SHEET, level='minimal', tb=False, grid=False), 'Baseline and the arc only.', 'drawing')
el('SP-23', 'The mark, dimensioned', 'mark-drawing.svg', lambda: mark_drawing_file(SHEET), 'Stem 8, gap 7, height 35 on a 64 grid; the arc at the leaning stem.', 'drawing', width=400)
el('SP-24', 'Title block', 'title-block.svg', lambda: svg(332, 110, f'<rect width="332" height="110" fill="{PAPER}"/>' + title_block(332, 110, SHEET, TB)), 'DRAWING · SCALE · LEAN · SHEET · REV. The REV line changes when the wordmark changes; nothing else on the page carries a date.', 'drawing', width=332)

el('SP-30', 'Sidebar head, light', 'sidebar-light.svg', lambda: sidebar_file(False), 'The mark in its plate and the wordmark, as the app\'s sidebar head shows them.', 'where', width=240)
el('SP-31', 'Sidebar head, dark', 'sidebar-dark.svg', lambda: sidebar_file(True), 'The same on the dark theme.', 'where', width=240)
el('SP-32', 'Browser tab', 'tab.svg', lambda: tab_file(), 'The favicon (SP-05) beside the page title.', 'where', width=420)
el('SP-33', 'Banner, the drawing', 'readme-banner.svg', lambda: banner_file(SHEET_DARK), '1280×320, the drawing on the dark ground: for a docs site header or a print strip. Also readme-banner.png.', 'where')
el('SP-37', 'README banner with the container world', 'readme-banner-containers.svg', lambda: banner_containers_file(), '1280×320 on the dark ground: the plate monogram and the wordmark left, the container train from round 2 right. The containers are the kinds of entry; the jade one is the product\'s. This is the one for the README and the GitHub social preview. Also readme-banner-containers.png.', 'where')
el('SP-34', 'End card, dark', 'endcard-dark.svg', lambda: endcard_file(SHEET_DARK), '1920×1080, the still of the drawing on the dark ground, paper ink, the lean in rust. Also endcard-dark.png. The video uses SP-36, the same without a ground.', 'where')
el('SP-36', 'End card, overlay', 'endcard-overlay.svg', lambda: endcard_file(dict(SHEET_DARK, bg='none')), 'The dark end card without its ground: the video draws it over the dimmed yard, so the colour behind the name is the scene\'s own.', 'where')
el('SP-35', 'End card, paper', 'endcard.svg', lambda: endcard_file(SHEET), 'The same sheet on paper, for a light cut or a still. Not used in the video.', 'where')

def write_all():
    for e in E:
        open(os.path.join(OUT, e['file']), 'w').write(e['builder']())
    # colour and type swatches are drawn in the book itself
    print(f'{len(E)} files → {OUT}')

# ---- the book ---------------------------------------------------------------------------------
def book():
    groups = [('marks', 'Marks'), ('wordmark', 'Wordmark and lockups'), ('drawing', 'The drawing'), ('where', 'Where it lives')]
    def tile(e):
        s = open(os.path.join(OUT, e['file'])).read()
        s = re.sub(r'<svg ', f'<svg style="max-width:{e["width"] or 1120}px;width:100%;height:auto" ', s, count=1)
        bg = f' style="background:{e["bg"]}"' if e['bg'] else ''
        wide = ' class="wide"' if not e['width'] else ''
        return f'''<figure id="{e['id']}"{wide}><div class="art"{bg}>{s}</div><figcaption><span class="id">{e['id']}</span><b>{e['title']}</b><code>files/{e['file']}</code><span>{e['caption']}</span></figcaption></figure>'''
    sections = ''
    for key, name in groups:
        sections += f'<section><div class="eyebrow">{name}</div><div class="grid">{"".join(tile(e) for e in E if e["group"] == key)}</div></section>'
    sw = lambda id, name, hexv, use, light=False: f'<figure id="{id}" class="sw"><div class="art" style="background:{hexv};min-height:72px"></div><figcaption><span class="id">{id}</span><b>{name}</b><code>{hexv}</code><span>{use}</span></figcaption></figure>'
    colours = ''.join([
        sw('SP-45', 'Dark ground (default)', DARK_BG, 'The default ground: landing page, README banner, end card, the dashboard\'s dark theme. On it: paper ink #F2F4F3, rust #D0694F, hairline #2E3634, label #8A918E.'),
        sw('SP-40', 'Paper', PAPER, 'The light sheet: print, a light-theme page, the paper stills.'),
        sw('SP-41', 'Ink', INK, 'Text, the mark, the upright stems.'),
        sw('SP-42', 'Rust', RUST, 'The leaning stem and the leaning l only. The redline. Never a button, never a status.'),
        sw('SP-43', 'Hairline', HAIR, 'Construction lines, the title block frame, dimension lines.'),
        sw('SP-44', 'Label', LABEL, 'The mono labels on the drawing and the tagline.'),
        sw('SP-46', 'Jade (product)', '#3E9B84', 'Stays the dashboard\'s own brand token inside the app. It does not appear in the identity files.'),
    ])
    types = f'''<figure id="SP-50"><div class="art" style="padding:24px"><div style="font:700 44px/1.1 'Schibsted Grotesk',sans-serif">Schibsted Grotesk 700</div><div style="font:500 16px/1.5 'Schibsted Grotesk',sans-serif;color:{LABEL};margin-top:6px">The wordmark (outlined in the files) and headings on the sheet. A Norwegian newspaper grotesk; its straight-backed l with no tail is why the tilt reads as a lean and not as another letter.</div></div><figcaption><span class="id">SP-50</span><b>Display and headings</b><code>Google Fonts · OFL · kit/fonts/Schibsted-700.ttf</code></figcaption></figure>
<figure id="SP-51"><div class="art" style="padding:24px"><div style="font:500 13px/1.6 'JetBrains Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:{LABEL}">ASCENDER · 732 &nbsp; X-HEIGHT · 527 &nbsp; BASELINE &nbsp; LEAN 5°</div><div style="font:500 16px/1.5 'Schibsted Grotesk',sans-serif;color:{LABEL};margin-top:8px">Labels, dimensions, the title block, the tagline: JetBrains Mono 500, caps, tracked 12 %.</div></div><figcaption><span class="id">SP-51</span><b>Labels</b><code>Google Fonts · OFL</code></figcaption></figure>
<figure id="SP-52"><div class="art" style="padding:24px"><div style="font:400 16px/1.6 'Schibsted Grotesk',sans-serif">Running text on the sheet is Schibsted Grotesk 400 at 16 px, 66 characters wide. Inside the dashboard nothing changes: the app keeps its own type.</div></div><figcaption><span class="id">SP-52</span><b>Text</b><code>Schibsted Grotesk 400</code></figcaption></figure>'''
    rules = [
        ('SP-60', 'The lean', f'{LEAN}° in the wordmark, the mark, the monogram and the drawing. {LEAN_SMALL}° in the favicon only. Never 0°, never above 7°.'),
        ('SP-61', 'The name', 'Always both words. "Slightly Parallel" in text, lowercase in the wordmark. Never "SP" in text, never "Parallel" alone.'),
        ('SP-62', 'Clear space', 'Mark: one stem width on every side. Wordmark: the height of the l. Minimum sizes: mark 16 px, wordmark 120 px wide; below that the mark alone.'),
        ('SP-63', 'Rust', 'Rust marks the leaning element and nothing else. It is not a link colour, not a warning, not a button. On dark grounds it lifts to #D0694F.'),
        ('SP-64', 'The drawing', 'The construction lines may appear wherever the wordmark has room for them (SP-20/21/22); they never appear around the mark in the sidebar or the tab.'),
        ('SP-65', 'The title block', 'Only on sheets (banner, end card, landing hero, print). REV changes when the wordmark changes.'),
        ('SP-66', 'Inside the dashboard', 'Only SP-30/31 (sidebar head) and SP-05 (favicon). The jade token, the flat tiles and the app type stay as they are.'),
        ('SP-67', 'Around the product', 'The yard video (SP-70), the sheets, the README. The container world is the README banner (SP-33) and the landing page; it is not in the kit.'),
    ]
    rules_html = ''.join(f'<figure id="{i}" class="rule"><figcaption><span class="id">{i}</span><b>{t}</b><span>{c}</span></figcaption></figure>' for i, t, c in rules)
    video = f'''<figure id="SP-70"><div class="art" style="background:#07090B"><video controls playsinline muted loop poster="../video/intro-yard-poster.png" src="../video/intro-yard.webm" style="display:block;width:100%;height:auto"></video></div><figcaption><span class="id">SP-70</span><b>Intro · "Yard"</b><code>video/intro-yard.webm · video/intro-yard.html · video/render.mjs</code><span>8 s, 1920×1080, loops. The drawing of the name over the dimmed yard; it fades and the yard brightens; a container train comes out of the distance on the third track, each box stencilled with a kind of entry, and passes the camera; the yard dims and the drawing returns. The last frame is the first. Source is a canvas drawing with window.__render(t); the renderer writes a VP8 .webm through Playwright's ffmpeg.</span></figcaption></figure>'''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Slightly Parallel</title>
<link rel="icon" href="files/favicon.svg"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Schibsted+Grotesk:wght@400;500;700&display=swap">
<style>
:root{{--bg:{DARK_BG};--surface:#141817;--ink:{DARK_INK};--ink-2:#B6BEBB;--ink-3:{DARK_LABEL};--line:#242A28;--rust:{RUST_ON_DARK}}}
*{{box-sizing:border-box}}html,body{{margin:0}}body{{background:var(--bg);color:var(--ink);font:15px/1.5 "Schibsted Grotesk",system-ui,sans-serif;padding-inline:16px;padding-block:0 80px}}
.frame{{max-width:1120px;margin:0 auto;display:flex;flex-direction:column;gap:56px}}header{{padding-block:48px 0;display:flex;flex-direction:column;gap:18px}}
h1{{margin:0;font-size:34px;letter-spacing:-.01em}}p{{margin:0;color:var(--ink-2);max-width:68ch}}
.eyebrow{{font:500 11px/1 "JetBrains Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}}
section{{display:flex;flex-direction:column;gap:14px;scroll-margin-top:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}}
figure{{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:6px;overflow:hidden;display:flex;flex-direction:column;min-width:0}}
figure.wide{{grid-column:1/-1}}
.art{{display:grid;place-items:center;padding:20px;background:{PAPER};border-bottom:1px solid var(--line);min-height:120px}}.art.dark{{background:{DARK_BG}}}
figcaption{{padding:12px 14px 14px;display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-2)}}
figcaption .id{{font:500 11px/1 "JetBrains Mono",monospace;color:var(--rust);letter-spacing:.08em}}figcaption b{{color:var(--ink);font-size:14px}}figcaption code{{font:400 11px/1.5 "JetBrains Mono",monospace;color:var(--ink-3);word-break:break-all}}
figure.rule figcaption{{padding:14px 16px}}figure.sw .art{{padding:0;border-bottom:1px solid var(--line)}}
nav{{display:flex;gap:16px;flex-wrap:wrap;font:500 12px/1 "JetBrains Mono",monospace}}nav a{{color:var(--ink-2);text-decoration:none}}nav a:hover{{color:var(--rust)}}
.hero{{border:1px solid var(--line);border-radius:6px;overflow:hidden}}.hero svg{{display:block;width:100%;height:auto}}
table{{border-collapse:collapse;width:100%;font-size:13px;background:var(--surface);border:1px solid var(--line);border-radius:6px;overflow:hidden}}th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{font:500 11px/1 "JetBrains Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}}td.m{{font:400 12px/1.4 "JetBrains Mono",monospace}}tr:last-child td{{border-bottom:0}}
</style></head><body><div class="frame">
<header><div class="eyebrow">Slightly Parallel · brand book · rev A · 6 Oct 2026 · brand/kit/index.html</div>
<div class="hero">{open(os.path.join(OUT, 'drawing-dark.svg')).read()}</div>
<p>The wordmark and its construction drawing — the dark ground is the default, the paper sheet is for print — the lean in redline rust. Every element below has an id (SP-xx) and a file under <code>brand/kit/files/</code>; say the id to change it. All files are rebuilt by <code>python3 brand/kit/build.py</code> from <code>draw.py</code> and the glyph outlines in <code>metrics.json</code>; the five constants at the top of <code>build.py</code> are the colours and the lean.</p>
<nav><a href="#marks">Marks SP-01…08</a><a href="#wordmark">Wordmark SP-10…14</a><a href="#drawing">Drawing SP-20…24</a><a href="#where">Where it lives SP-30…34</a><a href="#colour">Colour SP-40…46</a><a href="#type">Type SP-50…52</a><a href="#rules">Rules SP-60…67</a><a href="#video">Video SP-70</a><a href="#name">Name SP-80</a></nav></header>
{sections.replace('<section>', '<section id="marks">', 1)}
<section id="colour"><div class="eyebrow">Colour</div><div class="grid">{colours}</div></section>
<section id="type"><div class="eyebrow">Type</div><div class="grid">{types}</div></section>
<section id="rules"><div class="eyebrow">Rules</div><div class="grid">{rules_html}</div></section>
<section id="video"><div class="eyebrow">Video</div>{video}</section>
<section id="name"><div class="eyebrow">Name · SP-80 · checked 6 Oct 2026</div><table><thead><tr><th>Where</th><th>Looked for</th><th>Result</th></tr></thead><tbody>
<tr><td>Domains (registry RDAP)</td><td class="m">slightlyparallel .com .dev .app .ai .org · slightly-parallel.com</td><td>unregistered</td></tr>
<tr><td>Domain</td><td class="m">slightlyparallel.io</td><td>no RDAP answer from the .io registry; check at a registrar</td></tr>
<tr><td>GitHub · npm · PyPI · crates.io · Docker Hub · X</td><td class="m">slightlyparallel · slightly-parallel</td><td>free</td></tr>
<tr><td>Web</td><td class="m">"slightly parallel" software · company · app</td><td>no product, company or project; only the phrase</td></tr>
<tr><td>Trademarks</td><td class="m">"slightly parallel"</td><td>nothing in web search; USPTO TESS and EUIPO TMview still to query by hand</td></tr>
<tr><td>Neighbours</td><td class="m">Parallels · Parallel Works · parallel.ai · Parallel (Colorado)</td><td>all one-word; always use both words</td></tr>
</tbody></table></section>
</div></body></html>'''
    # section ids for the nav
    for key, _ in groups[1:]:
        html = html.replace(f'<section><div class="eyebrow">{dict(groups)[key]}</div>', f'<section id="{key}"><div class="eyebrow">{dict(groups)[key]}</div>', 1)
    open(os.path.join(HERE, 'index.html'), 'w').write(html)
    print('index.html')

# ---- the app's copies --------------------------------------------------------------------------
# The product draws the identity from outlines too. These two files are written from here and
# nowhere else: frontend/src/components/Brand.tsx (the sidebar head, About) and
# frontend/src/features/timelapse/spmark.ts (the Timelapse bookends). A test in the frontend
# compares spmark.ts with metrics.json, so a wordmark changed here and not rebuilt fails it.
REPO = os.path.dirname(os.path.dirname(HERE))
GENERATED = 'Written by brand/kit/build.py from the kit; do not edit, rebuild.'

def _inner(name):
    s = open(os.path.join(OUT, name)).read()
    vb = re.search(r'viewBox="([^"]+)"', s).group(1)
    return vb, s[s.index('>', s.index('<svg')) + 1:s.rindex('</svg>')].strip()

def write_app_files():
    L = M['sg']['lower']; m = M['sg']['metrics']; S = M['sg']['s']; P = M['sg']['p']
    recs = [{'ch': x['ch'], 'x': round(x['x'], 4), 'd': x['d'],
             'bb': [round(x['bb']['x1'], 4), round(x['bb']['x2'], 4), round(x['bb']['y1'], 4), round(x['bb']['y2'], 4)]}
            for x in L['recs']]
    s0 = S['recs'][0]; p0 = P['recs'][0]
    colours = dict(ink=INK, paper=DARK_INK, rust=RUST, rustOnDark=RUST_ON_DARK, dark=DARK_BG, hairDark=DARK_HAIR,
                   labelDark=DARK_LABEL, sheet=PAPER, hair=HAIR, label=LABEL)
    ts = f"""/**
 * The Slightly Parallel identity as outlines (brand/kit/metrics.json: Schibsted Grotesk 700,
 * per-glyph paths in em units). Nothing here needs a font. {GENERATED}
 */
export const SP_METRICS = {{ asc: {round(m['asc'], 4)}, xh: {round(m['xh'], 4)}, desc: {round(m['desc'], 4)} }}
/** 'slightly parallel': glyph paths at em scale, their pen x and their bbox [x1, x2, y1, y2] (y down). */
export const SP_WORDMARK: Array<{{ ch: string; x: number; d: string; bb: [number, number, number, number] }}> = {json.dumps(recs)}
export const SP_WORDMARK_WIDTH = {round(L['width'], 4)}
/** The second l of parallel, the one that leans. */
export const SP_LEAN_INDEX = {LEAN_IDX}
export const SP_LEAN_DEG = {LEAN}
/** The s and the p of the monogram. */
export const SP_S = {{ d: {json.dumps(s0['d'])}, width: {round(S['width'], 4)}, top: {round(s0['bb']['y1'], 4)} }}
export const SP_P = {{ d: {json.dumps(p0['d'])}, width: {round(P['width'], 4)} }}
export const SP_COLOURS = {{ {', '.join(f"{k}: '{v}'" for k, v in colours.items())} }}
"""
    open(os.path.join(REPO, 'frontend/src/features/timelapse/spmark.ts'), 'w').write(ts)

    mvb, mono = _inner('monogram-plate.svg')
    wvb, word = _inner('wordmark-ink.svg')
    # The wordmark takes the text colour, so it reads on either theme; the lean takes the token.
    word = word.replace(f'fill="{INK}"', 'fill="currentColor"').replace(f'fill="{RUST}"', 'fill={LEAN}')
    mono = mono.replace(f'fill="{RUST}"', 'fill={LEAN}').replace(f'fill="{RUST_ON_DARK}"', 'fill={LEAN}')
    mw, mh = (float(v) for v in mvb.split()[2:]); ww, wh = (float(v) for v in wvb.split()[2:])
    tsx = f"""/*
 * The identity (SP-08 the logo, SP-10/12 the wordmark). Paths are outlines of Schibsted
 * Grotesk 700; nothing here depends on a font. {GENERATED}
 * The plate is the same in both themes; the wordmark takes the text colour, the leaning l rust.
 */
const LEAN = 'var(--brand-lean, {RUST_ON_DARK})'

/** SP-08 — the monogram in its plate. `size` is the height in px. */
export function BrandMark({{ size = 24, title = 'Slightly Parallel' }}: {{ size?: number; title?: string }}) {{
  const w = Math.round(size * ({mw} / {mh}))
  return (
    <svg width={{w}} height={{size}} viewBox="{mvb}" role="img" aria-label={{title}} className="shrink-0">
      {mono}
    </svg>
  )
}}

/** SP-10/12 — the wordmark `slightly parallel`, the second l of parallel leaning {LEAN}°. */
export function BrandWordmark({{ height = 14 }}: {{ height?: number }}) {{
  const w = Math.round(height * ({ww} / {wh}))
  return (
    <svg width={{w}} height={{height}} viewBox="{wvb}" aria-hidden="true" className="shrink-0 block">
      {word}
    </svg>
  )
}}
"""
    open(os.path.join(REPO, 'frontend/src/components/Brand.tsx'), 'w').write(tsx)
    print('frontend: Brand.tsx, spmark.ts')


if __name__ == '__main__':
    write_all(); book(); write_app_files()
