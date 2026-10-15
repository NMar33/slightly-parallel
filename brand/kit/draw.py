"""Drawing engine for the Slightly Parallel identity: glyph outlines + font metrics -> annotated SVG."""
import json, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, 'metrics.json')))
r = lambda v: round(v, 2)

def glyphs(face, key, size, x0, y0, lean_idx=None, angle=5, fill='#101113', lean_fill=None, only=None):
    """Draw a laid-out string; returns (svg, width, lean_info)."""
    L = M[face][key]; out = []; info = None
    for i, g in enumerate(L['recs']):
        if only is not None and i not in only: continue
        x = x0 + g['x'] * size
        cx = x + (g['bb']['x1'] + g['bb']['x2']) / 2 * size
        if i == lean_idx:
            out.append(f'<path transform="rotate({-angle} {r(cx)} {r(y0)})" fill="{lean_fill or fill}" d="{g["d"]}" style="transform-box:fill-box" />')
            # proper rotation about (cx, baseline): use nested transform
            out[-1] = f'<g transform="translate({r(x)} {r(y0)}) rotate({-angle} {r(cx - x)} 0) scale({size} {size})"><path fill="{lean_fill or fill}" d="{g["d"]}"/></g>'
            info = {'cx': cx, 'x1': x + g['bb']['x1'] * size, 'x2': x + g['bb']['x2'] * size, 'top': y0 + g['bb']['y1'] * size}
        else:
            out.append(f'<g transform="translate({r(x)} {r(y0)}) scale({size} {size})"><path fill="{fill}" d="{g["d"]}"/></g>')
    return '\n'.join(out), L['width'] * size, info

def label(x, y, text, color, size=10, anchor='start', tracking=1.6):
    """mono caps label drawn as outlines (JetBrains Mono 500), so no file depends on a font"""
    G = M['mono']; parts = []; cx = 0
    for ch in text:
        g = G.get(ch) or G.get('?')
        parts.append((cx, g['d'])); cx += g['adv'] * size + tracking
    w = cx - tracking
    x0 = x if anchor == 'start' else (x - w if anchor == 'end' else x - w / 2)
    out = [f'<g transform="translate({r(x0)} {r(y)})">']
    for px, d in parts:
        out.append(f'<g transform="translate({r(px)} 0) scale({size})"><path fill="{color}" d="{d}"/></g>')
    out.append('</g>')
    return ''.join(out)

def hair(x1, y1, x2, y2, color, dash=None, w=1):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{r(x1)}" y1="{r(y1)}" x2="{r(x2)}" y2="{r(y2)}" stroke="{color}" stroke-width="{w}"{d}/>'

def dim(x1, x2, y, text, color, above=True):
    """horizontal dimension line with end ticks and a centred label"""
    t = 5
    s = hair(x1, y, x2, y, color) + hair(x1, y - t, x1, y + t, color) + hair(x2, y - t, x2, y + t, color)
    s += label((x1 + x2) / 2, y - 6 if above else y + 14, text, color, anchor='middle')
    return s

def arc(cx, cy, rad, angle, color, text):
    """angle arc from vertical to `angle` degrees clockwise at (cx,cy) going up"""
    a = math.radians(angle)
    x1, y1 = cx, cy - rad
    x2, y2 = cx + rad * math.sin(a), cy - rad * math.cos(a)
    s = f'<path d="M{r(x1)} {r(y1)} A{rad} {rad} 0 0 1 {r(x2)} {r(y2)}" fill="none" stroke="{color}" stroke-width="1"/>'
    s += label(cx + rad * math.sin(a / 2) + 10, cy - rad * math.cos(a / 2) + 4, f'{angle}°', color)
    return s

def specimen(face, key, size, W, H, th, lean_idx, angle=5, level='full', x0=None, y0=None, grid=False, title=None, text_fill=None, lean_fill=None):
    """The annotated drawing. level: full | lines | minimal"""
    m = M[face]['metrics']; L = M[face][key]
    width = L['width'] * size
    x0 = (W - width) / 2 if x0 is None else x0
    y0 = H * 0.66 if y0 is None else y0
    ink = text_fill or th['ink']; hairc = th['hair']; lab = th['label']
    s = [f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>'] if th['bg'] != 'none' else []
    if grid:
        gid = 'g' + th['grid'].lstrip('#').lower()   # the same id on every build: no noise in the files' history
        s.append(f'<defs><pattern id="{gid}" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.8" fill="{th["grid"]}"/></pattern></defs><rect width="{W}" height="{H}" fill="url(#{gid})"/>')
    rows = [('ASCENDER', m['asc']), ('X-HEIGHT', m['xh']), ('BASELINE', 0), ('DESCENDER', m['desc'])]
    if key.isupper(): rows = [('CAP HEIGHT', m['cap']), ('BASELINE', 0)]
    if level in ('full', 'lines'):
        for name, v in rows:
            y = y0 - v * size
            s.append(hair(x0 - 60, y, x0 + width + 60, y, hairc, dash=None if name == 'BASELINE' else '2 4'))
            if level == 'full':
                s.append(label(x0 - 60, y - 5, f'{name} · {int(abs(v) * 1000)}', lab))
    elif level == 'minimal':
        s.append(hair(x0 - 40, y0, x0 + width + 40, y0, hairc))
    g, _, info = glyphs(face, key, size, x0, y0, lean_idx, angle, ink, lean_fill or th.get('accent', ink))
    s.append(g)
    if info:
        cx, top = info['cx'], info['top']
        stem_h = y0 - top
        # construction: the upright ghost and the leaning axis
        s.append(hair(cx, y0 + 20, cx, top - 40, hairc, dash='3 3'))
        dx = stem_h * math.tan(math.radians(angle))
        s.append(hair(cx, y0, cx + dx * 1.18, top - 0.18 * stem_h, th.get('accent', hairc), dash='3 3'))
        s.append(arc(cx, y0, stem_h * 0.78, angle, lab, f'{angle}°'))
        if level == 'full':
            s.append(dim(cx, cx + dx, top - 46, f'{int(dx)} · AT THE TOP', lab))
            s.append(dim(info['x1'], info['x2'], y0 + 28, f'STEM {int(info["x2"] - info["x1"])}', lab, above=False))
    if title:
        s.append(title_block(W, H, th, title))
    return '\n'.join(s)

def title_block(W, H, th, rows):
    """engineering title block, bottom right"""
    bw, bh = 300, 18 * len(rows) + 14
    x, y = W - bw - 16, H - bh - 16
    s = [f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="none" stroke="{th["hair"]}"/>']
    for i, (k, v) in enumerate(rows):
        yy = y + 18 * (i + 1) - 4
        if i: s.append(hair(x, yy - 13, x + bw, yy - 13, th['hair']))
        s.append(label(x + 8, yy, k, th['label'], 9))
        s.append(label(x + bw - 8, yy, v, th['ink'], 9, anchor='end'))
    s.append(hair(x + 110, y, x + 110, y + bh, th['hair']))
    return '\n'.join(s)

def mark_drawing(W, H, th, angle=5, box=64, level='full'):
    """the two stems with dimensions"""
    sw, sh, gap = box * 0.14, box * 0.56, box * 0.12
    sc = min(W, H) / box * 0.55
    ox, oy = W / 2 - box * sc / 2, H / 2 - box * sc / 2
    cy = oy + box * sc / 2; x1 = ox + (box / 2 - gap / 2 - sw) * sc; x2 = ox + (box / 2 + gap / 2) * sc
    SW, SH = sw * sc, sh * sc
    ink, hairc, lab, acc = th['ink'], th['hair'], th['label'], th.get('accent', th['ink'])
    s = [f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>']
    s.append(f'<rect x="{r(x1)}" y="{r(cy - SH / 2)}" width="{r(SW)}" height="{r(SH)}" rx="{r(SW / 2)}" fill="{ink}"/>')
    s.append(f'<rect x="{r(x2)}" y="{r(cy - SH / 2)}" width="{r(SW)}" height="{r(SH)}" rx="{r(SW / 2)}" fill="{acc}" transform="rotate({-angle} {r(x2 + SW / 2)} {r(cy + SH / 2)})"/>')
    if level != 'none':
        s.append(hair(x1 - 60, cy + SH / 2, x2 + SW + 60, cy + SH / 2, hairc))
        s.append(hair(x1 - 60, cy - SH / 2, x2 + SW + 60, cy - SH / 2, hairc, dash='2 4'))
        s.append(hair(x2 + SW / 2, cy + SH / 2 + 30, x2 + SW / 2, cy - SH / 2 - 50, hairc, dash='3 3'))
        s.append(arc(x2 + SW / 2, cy + SH / 2, SH * 0.9, angle, lab, f'{angle}°'))
        if level == 'full':
            s.append(dim(x1, x1 + SW, cy - SH / 2 - 22, f'{int(sw)}', lab))
            s.append(dim(x1 + SW, x2, cy - SH / 2 - 22, f'{int(gap)}', lab))
            s.append(label(x1 - 60, cy + SH / 2 + 16, f'BASELINE · {box} GRID', lab, 9))
            s.append(label(x1 - 60, cy - SH / 2 - 6, f'STEM HEIGHT · {int(sh)}', lab, 9))
    return '\n'.join(s)

def sidebar(th, dark=False, face='sg', with_lines=False):
    W, H = 240, 110
    bg = '#0C0E0E' if dark else '#FFFFFF'; ink = '#F2F4F3' if dark else '#101113'; lab = '#737B78' if dark else '#8A918E'
    hairc = '#2A3230' if dark else '#DCE1DF'
    t = dict(th); t.update(bg=bg, ink=ink, label=lab, hair=hairc)
    acc = ink if th.get('accent') == th['ink'] else th.get('accent', ink); t['accent'] = acc
    s = [f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    s.append(mark_small(16, 18, 28, t))
    g, w, info = glyphs('sg', 'lower', 15, 50, 38, 14, 5, ink, acc)
    if with_lines:
        s.append(hair(48, 38, 52 + w + 8, 38, hairc))
        s.append(hair(48, 38 - M['sg']['metrics']['asc'] * 17, 52 + w + 8, 38 - M['sg']['metrics']['asc'] * 17, hairc, dash='2 3'))
    s.append(g)
    s.append(label(W - 12, 36, 'v1.0', lab, 8, anchor='end'))
    s.append(f'<g font-family="system-ui,sans-serif" font-size="11" fill="{"#B6BEBB" if dark else "#4B5250"}"><text x="18" y="76">Settings</text><text x="18" y="96">Monitor</text></g>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">' + '\n'.join(s) + '</svg>'

def mark_small(x, y, box, th, angle=5, bg=None):
    sw, sh, gap = box * 0.14, box * 0.56, box * 0.12
    cy = y + box / 2; x1 = x + box / 2 - gap / 2 - sw; x2 = x + box / 2 + gap / 2
    ink = th['ink']; acc = th.get('accent', ink)
    s = ''
    if bg: s += f'<rect x="{x}" y="{y}" width="{box}" height="{box}" rx="{box * 0.22}" fill="{bg}"/>'
    s += f'<rect x="{r(x1)}" y="{r(cy - sh / 2)}" width="{r(sw)}" height="{r(sh)}" rx="{r(sw / 2)}" fill="{ink}"/>'
    s += f'<rect x="{r(x2)}" y="{r(cy - sh / 2)}" width="{r(sw)}" height="{r(sh)}" rx="{r(sw / 2)}" fill="{acc}" transform="rotate({-angle} {r(x2 + sw / 2)} {r(cy + sh / 2)})"/>'
    return s

def banner(th, face, key, level, title=None, grid=False, size=None):
    W, H = 1280, 320
    size = size or (150 if face == 'bs' else 96)
    inner = specimen(face, key, size, W, H, th, 14, 5, level, x0=72, y0=H * 0.62, grid=grid, title=title)
    tag = label(72, H - 40, 'A DASHBOARD FOR CODING AGENTS · SELF-HOSTED · ONE LAPTOP', th['label'], 11, tracking=2.2)
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block">{inner}{tag}</svg>'

def endcard(th, face, key, level, size, grid=False):
    W, H = 1920, 1080
    inner = specimen(face, key, size, W, H, th, 14 if key == 'lower' else 5, 5, level, y0=H * 0.6, grid=grid)
    tag = label(W / 2, H * 0.6 + 110, 'AGENTS, SIDE BY SIDE', th['label'], 22, anchor='middle', tracking=8)
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block">{inner}{tag}</svg>'

