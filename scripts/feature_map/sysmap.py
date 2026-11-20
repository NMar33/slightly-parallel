"""System maps of Slightly Parallel (tk_bba7c02c): the whole system on one sheet.

Two compositions, both drawn from feature-map.json (numbers) and
sysmap.yaml (the hand-kept layout: positions, lines, flows):

  metro   lines are processes and loops, stations are commands and records,
          interchanges are the shared hubs (message, task, commits,
          AGENTS.md, agents, standup, release); a badge says who acts;
  flow    a circular-flow map like an economy's: sectors (operator, program,
          agents, repository and CI, pages, outside) with labelled flows
          between them, the commands on the flows they trigger, loops
          numbered.

`render(model, kind)` returns one HTML page with one `section.sheet#main`.
Geometry is computed here; labels are HTML laid over an SVG, so text is
measured by the browser. `missing_commands(model)` lists the commands of the
program that no metro station names.

Who acts — the same key on both sheets, shape + letter + colour:
operator ● О #eb6834, program ■ П #14a06f, agent ◆ А #2a78d6, outside ⬡ В grey.
Actor colours and the metro line colours were checked with the dataviz
skill's validate_palette.js on #fbfbf9 (each set passes; lines and actors
never share a mark, and every line is also named).
"""

from __future__ import annotations

import html
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WHO = {
    "o": ("О", "#eb6834", "circle", "оператор"),
    "s": ("П", "#14a06f", "square", "программа"),
    "a": ("А", "#2a78d6", "diamond", "агент"),
    "x": ("В", "#8d8b85", "hex", "внешнее"),
}
W = 3200


def load_layout() -> dict:
    return yaml.safe_load((HERE / "sysmap.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# numbers

def counter(model: dict):
    c = model["counts"]
    L = {l["key"]: l for l in c["ledgers"]}
    T = c["typed"]["d30"]
    cards = {k["id"]: k for k in model["cards"]}
    F = c.get("flow") or {}
    O = c["tasks"].get("origins30", {})
    P = c["tasks"].get("parts", {})
    M = c["typed"]["messages"]

    def get(key: str | None):
        if not key:
            return None
        kind, _, arg = key.partition(":")
        if kind == "c":
            card = cards.get(arg)
            return sum(T.get(x, 0) for x in card["cmds"]) if card else None
        if kind == "t":
            return sum(T.get(x, 0) for x in arg.split(","))
        if kind == "l":
            return L.get(arg, {}).get("d30")
        if kind == "lt":
            return L.get(arg, {}).get("total")
        if kind == "f":
            k, _, sub = arg.partition(".")
            v = F.get(k)
            if sub and isinstance(v, dict):
                return v.get(sub)
            return sum(v.values()) if isinstance(v, dict) else v
        if kind == "o":
            return O.get(arg)
        if kind == "p":
            return P.get(arg)
        if kind == "m":
            return M.get(arg)
        return None
    return get


def fmt(v) -> str:
    if v is None:
        return ""
    return f"{v:,}".replace(",", " ")


def all_commands(model: dict) -> set[str]:
    cmds = set(model.get("contract_commands", {}))
    for card in model["cards"]:
        cmds.update(card["cmds"])
    return cmds


def missing_commands(model: dict, lay: dict | None = None) -> list[str]:
    lay = lay or load_layout()
    have = set()
    for st in lay["metro"]["stations"].values():
        have.update(st.get("cmds") or [])
    return sorted(all_commands(model) - have)


# ---------------------------------------------------------------------------
# shared pieces

def badge(w: str, size: int = 20) -> str:
    letter, color, shape, _ = WHO[w]
    return f'<i class="bd {shape}" style="--c:{color};--s:{size}px"><b>{letter}</b></i>'


def badges(who: str, size: int = 20) -> str:
    return "".join(badge(w, size) for w in who)


CSS = """
:root{--page:#eef0f2;--surface:#fbfbf9;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e6e5df;--axis:#c3c2b7}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--page);color:var(--ink)}
body{width:3200px;font-family:"Manrope",system-ui,sans-serif}
.sheet{width:3200px;padding:64px 72px 56px;background:var(--page)}
header{display:grid;grid-template-columns:1fr 1180px;gap:60px;align-items:end;margin-bottom:28px}
.kicker{font:500 19px "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--ink2);display:flex;gap:14px;align-items:center}
.tag{display:inline-flex;border:2px solid var(--ink);border-radius:8px;padding:5px 12px;color:var(--ink);font-weight:600}
h1{font:800 68px/1.05 "Manrope",sans-serif;letter-spacing:-.03em;margin:22px 0 16px}
.lede{font-size:24px;line-height:1.5;color:var(--ink2);max-width:1500px}
.lede b{color:var(--ink)}
.key{background:var(--surface);border-radius:18px;padding:22px 26px;display:grid;grid-template-columns:1fr 1fr;gap:6px 36px;font-size:18px;color:var(--ink2)}
.kh{font:600 14px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:2px 0 6px;grid-column:span 2}
.kh2{grid-column:span 1}
.kr{display:flex;gap:10px;align-items:center;line-height:1.55}
.kr b{color:var(--ink)}
.bd{display:inline-grid;place-items:center;width:var(--s);height:var(--s);flex:none;font-style:normal;position:relative;vertical-align:-4px;margin-right:3px}
.bd b{font:800 calc(var(--s)*.58)/1 "Manrope",sans-serif;color:#fff;position:relative;z-index:1}
.bd.circle{background:var(--c);border-radius:50%}
.bd.square{background:var(--c);border-radius:3px}
.bd.diamond::before{content:"";position:absolute;inset:12%;background:var(--c);transform:rotate(45deg);border-radius:2px}
.bd.hex{background:#fff;border:2px dashed var(--c);border-radius:50%}
.bd.hex b{color:var(--c)}
.map{position:relative;background:var(--surface);border-radius:22px;overflow:hidden}
.map svg{position:absolute;inset:0}
.lb{position:absolute;white-space:nowrap;line-height:1.25;pointer-events:none}
.lb .t{font:700 19px "Manrope",sans-serif;letter-spacing:-.01em;color:var(--ink);display:inline-flex;align-items:center;gap:6px}
.lb .t .n{font:500 15px "IBM Plex Mono",monospace;color:var(--muted);margin-left:4px}
.lb .s{font:500 15px "Manrope",sans-serif;color:var(--ink2);margin-top:2px}
.lb.hub .t{font-size:24px;font-weight:800}
.lb .bg{background:rgba(251,251,249,.92);border-radius:8px;padding:3px 8px;display:inline-block}
.lb.n{transform:translate(-50%,-100%);text-align:center}
.lb.s{transform:translate(-50%,0);text-align:center}
.lb.e{transform:translate(0,-50%);text-align:left}
.lb.w{transform:translate(-100%,-50%);text-align:right}
.lb.ne{transform:translate(0,-100%);text-align:left}
.lb.nw{transform:translate(-100%,-100%);text-align:right}
.lb.se{text-align:left}
.lb.sw{transform:translate(-100%,0);text-align:right}
.ltag{position:absolute;white-space:nowrap;display:flex;flex-direction:column;gap:2px;align-items:flex-start}
.ltag.w{transform:translateX(-100%);align-items:flex-end;text-align:right}
.ltag .nm{font:800 17px "Manrope",sans-serif;color:#fff;padding:4px 12px;border-radius:7px;letter-spacing:.01em;display:inline-block}
.ltag .nt{font:500 14px "Manrope",sans-serif;color:var(--ink2);background:rgba(251,251,249,.92);padding:1px 4px;border-radius:5px}
.inset{position:absolute;background:#f3f3ef;border-radius:16px;padding:18px 22px;width:1300px}
.ih{font:800 24px "Manrope";display:flex;align-items:center;gap:10px}
.hubdot{width:24px;height:24px;border-radius:50%;border:6px solid #1f1e1c;background:#fff;box-shadow:inset 0 0 0 3px #fff,inset 0 0 0 8px #1f1e1c}
.il{font-size:15px;color:var(--ink2);margin:2px 0 10px}
.ic{display:grid;grid-template-columns:400px 40px 1fr;align-items:start}
.ic .arrow{font:700 28px "Manrope";color:var(--muted);padding-top:60px;text-align:center}
.ic > div:last-child{display:grid;grid-template-columns:1fr 1fr;column-gap:28px}
.ic > div:last-child .ik{grid-column:span 2}
.ik{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.ir{display:grid;grid-template-columns:24px 1fr auto;align-items:center;font-size:16px;line-height:1.75;color:var(--ink2);border-bottom:1px solid var(--grid)}
.ir > b{font:600 16px "IBM Plex Mono",monospace;color:var(--ink);padding-left:12px}
.foot{margin-top:22px;font-size:17px;line-height:1.55;color:var(--muted)}
.foot b{color:var(--ink2)}
"""


def page(title: str, kicker: str, h1: str, lede: str, key: str, body: str, foot: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={W}">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}{extra_css}</style></head><body>
<section class="sheet" id="main">
<header><div><div class="kicker"><span class="tag">Slightly Parallel</span> {kicker}</div>
<h1>{h1}</h1><p class="lede">{lede}</p></div>{key}</header>
{body}
<div class="foot">{foot}</div>
</section></body></html>"""


def who_key() -> str:
    rows = [
        ("o", "Оператор", "пишет команду в сообщении, решает"),
        ("s", "Программа", "хук и сервер: записывают, двигают, считают"),
        ("a", "Агент", "работает и пишет записи через MCP"),
        ("x", "Внешнее", "GitHub Actions, GitHub"),
    ]
    return "".join(f'<div class="kr">{badge(w, 22)}<span><b>{n}</b> — {d}</span></div>' for w, n, d in rows)


# ---------------------------------------------------------------------------
# geometry

def rounded_path(pts: list[tuple[float, float]], r: float, closed: bool = False) -> str:
    n = len(pts)
    if n < 2:
        return ""
    seq = pts + [pts[0], pts[1]] if closed else pts
    out = []
    start = None
    for i in range(1, len(seq) - 1):
        p0, p1, p2 = seq[i - 1], seq[i], seq[i + 1]
        d0 = math.dist(p0, p1)
        d1 = math.dist(p1, p2)
        if d0 == 0 or d1 == 0:
            continue
        rr = min(r, d0 / 2, d1 / 2)
        a = (p1[0] - (p1[0] - p0[0]) / d0 * rr, p1[1] - (p1[1] - p0[1]) / d0 * rr)
        b = (p1[0] + (p2[0] - p1[0]) / d1 * rr, p1[1] + (p2[1] - p1[1]) / d1 * rr)
        if start is None:
            start = a if closed else pts[0]
            out.append(f"M{start[0]:.1f},{start[1]:.1f}")
        out.append(f"L{a[0]:.1f},{a[1]:.1f}Q{p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}")
    if start is None:
        out.append(f"M{pts[0][0]},{pts[0][1]}")
    if closed:
        out.append("Z")
    else:
        out.append(f"L{pts[-1][0]:.1f},{pts[-1][1]:.1f}")
    return "".join(out)


def chevrons(pts, stations, closed, color, skip=58):
    """Small white arrowheads on long free stretches, pointing along the line."""
    seq = pts + [pts[0]] if closed else pts
    out = []
    for p0, p1 in zip(seq, seq[1:]):
        L = math.dist(p0, p1)
        if L < 150:
            continue
        best, bd = None, 0
        for k in range(4, 17):
            t = k / 20
            q = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            d = min((math.dist(q, s) for s in stations), default=1e9)
            d = min(d, L * t, L * (1 - t))
            if d > bd:
                best, bd = q, d
        if best and bd > skip:
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            out.append(f'<path d="M-5,-6 L3,0 L-5,6" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" transform="translate({best[0]:.1f},{best[1]:.1f}) rotate({ang:.0f})"/>')
    return out


# ---------------------------------------------------------------------------
# metro

def render_metro(model: dict, lay: dict) -> str:
    M = lay["metro"]
    get = counter(model)
    st = M["stations"]
    H = M["height"]
    svg = []
    labels = []

    def xy(p):
        if isinstance(p, str):
            return tuple(st[p]["at"])
        return tuple(p)

    # attachment links under everything
    for a, b in M.get("links", []):
        (x0, y0), (x1, y1) = xy(a), xy(b)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = x1 - x0, y1 - y0
        cx, cy = mx - dy * .18, my + dx * .18
        svg.append(f'<path d="M{x0},{y0} Q{cx:.0f},{cy:.0f} {x1},{y1}" fill="none" stroke="#9a978f" stroke-width="2.5" stroke-dasharray="1 7" stroke-linecap="round"/>')

    st_pts = [tuple(s["at"]) for s in st.values()]
    chev = []
    for lid, ln in M["lines"].items():
        pts = [xy(p) for p in ln["pts"]]
        w = ln.get("width", 11)
        d = rounded_path(pts, ln.get("radius", 60), ln.get("closed", False))
        dash = f' stroke-dasharray="{ln["dash"]}"' if ln.get("dash") else ""
        cap = "round"
        svg.append(f'<path d="{d}" fill="none" stroke="#fbfbf9" stroke-width="{w + 8}" stroke-linejoin="round" stroke-linecap="{cap}"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{ln["color"]}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="{cap}"{dash}/>')
        if not ln.get("dash"):
            chev += chevrons(pts, st_pts, ln.get("closed", False), ln["color"])
        if ln.get("tag"):
            x, y = ln["tag"]
            side = " w" if ln.get("tag_side") == "w" else ""
            labels.append(f'<div class="ltag{side}" style="left:{x}px;top:{y}px"><span class="nm" style="background:{ln["color"]}">{html.escape(ln["name"])}</span><span class="nt">{html.escape(ln.get("note", ""))}</span></div>')
    svg += chev

    off = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0), "ne": (.7, -.7), "nw": (-.7, -.7), "se": (.7, .7), "sw": (-.7, .7)}
    for sid, s in st.items():
        x, y = s["at"]
        hub = s.get("hub")
        if hub:
            svg.append(f'<circle cx="{x}" cy="{y}" r="22" fill="#fff" stroke="#1f1e1c" stroke-width="6"/>')
            svg.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#1f1e1c"/>')
        else:
            svg.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#fff" stroke="#1f1e1c" stroke-width="4"/>')
        lp = s.get("lp", "s")
        r = 30 if hub else 18
        ox, oy = off[lp]
        lx, ly = x + ox * r, y + oy * r
        n = get(s.get("n"))
        num = f'<span class="n">{fmt(n)}</span>' if n is not None else ""
        sub = "<br>".join(html.escape(p) for p in s.get("s", "").split("|"))
        cls = "lb " + lp + (" hub" if hub else "")
        labels.append(f'<div class="{cls}" style="left:{lx:.0f}px;top:{ly:.0f}px"><div class="bg"><div class="t">{badges(s.get("who", ""))}{html.escape(s["t"])}{num}</div><div class="s">{sub}</div></div></div>')

    if M.get("inset"):
        labels.append(inset(M["inset"], get))
    body = f'<div class="map" style="height:{H}px"><svg width="{W - 144}" height="{H}" viewBox="0 0 {W - 144} {H}">{"".join(svg)}</svg>{"".join(labels)}</div>'
    lines_key = "".join(
        f'<div class="kr"><i style="display:inline-block;width:34px;height:9px;border-radius:5px;background:{ln["color"]}"></i><span><b>{html.escape(ln["name"])}</b></span></div>'
        for ln in M["lines"].values() if ln.get("name"))
    key = f"""<div class="key"><div class="kh">кто действует — значок у станции</div>{who_key()}
<div class="kh">линии — процессы</div>{lines_key}
<div class="kh">знаки</div>
<div class="kr"><svg width="34" height="34"><circle cx="17" cy="17" r="12" fill="#fff" stroke="#1f1e1c" stroke-width="5"/><circle cx="17" cy="17" r="5" fill="#1f1e1c"/></svg><span><b>Пересадка</b> — линии встречаются</span></div>
<div class="kr"><svg width="34" height="14"><path d="M2,7 L32,7" stroke="#8d8b85" stroke-width="9" stroke-dasharray="2 9" stroke-linecap="round"/></svg><span><b>Точки</b> — служебная линия</span></div>
<div class="kr"><svg width="34" height="14"><path d="M2,7 L32,7" stroke="#1f1e1c" stroke-width="9" stroke-linecap="round"/><path d="M13,2 L19,7 L13,12" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/></svg><span><b>Стрелка</b> — куда идёт процесс</span></div>
<div class="kr"><span style="font:500 16px 'IBM Plex Mono';color:var(--muted)">132</span><span>— сколько за 30 дней</span></div></div>"""
    foot = (f"Числа — последние 30 дней по всем проектам: команды, набранные оператором (чаты помощников не в счёт), и записи. "
            f"<b>#now-done</b> кладёт сообщение задачей сразу в Done; <b>#done</b> закрывает задачу этого чата и забирает её участок чата с коммитами и временем. "
            f"Собрано из кода и данных: scripts/feature_map/build.py, раскладка — sysmap.yaml · {model['generated_at']}")
    return page("Карта-метро SP", f"карта системы · последние 30 дней · {model['today']}", html.escape(M["title"]),
                html.escape(M["lede"]), key, body, foot)


def inset(I: dict, get) -> str:
    def rows(items):
        return "".join(f'<div class="ir">{badge(w, 18)}<span>{html.escape(t)}</span><b>{fmt(get(k))}</b></div>' for t, k, w in items)
    x, y = I["at"]
    return (f'<div class="inset" style="left:{x}px;top:{y}px"><div class="ih"><span class="hubdot"></span>{html.escape(I["title"])}</div>'
            f'<div class="il">{html.escape(I["lede"])}</div><div class="ic"><div><div class="ik">приходит</div>{rows(I["from"])}</div>'
            f'<div class="arrow">→</div><div><div class="ik">прикрепляется</div>{rows(I["attach"])}</div></div></div>')


def render(model: dict, kind: str) -> str:
    lay = load_layout()
    if kind == "metro":
        return render_metro(model, lay)
    if kind == "flow":
        return render_flow(model, lay)
    raise ValueError(kind)


FLOW_CSS = """
.box{position:absolute;border-radius:20px;padding:18px 22px;background:#fff;border:2px solid var(--c)}
.box .h{display:flex;align-items:center;gap:10px;font:800 28px "Manrope";letter-spacing:-.02em}
.box .hs{font-size:16px;color:var(--ink2);margin:2px 0 12px}
.box .it{font-size:17px;line-height:1.45;color:var(--ink2);padding:5px 0;border-top:1px solid var(--grid);display:flex;justify-content:space-between;gap:12px}
.box .it b{font:600 17px "IBM Plex Mono",monospace;color:var(--ink)}
.box.prog{background:#f2f7f4}
.part{position:absolute;border-radius:14px;padding:14px 16px;background:#fff;border:1.5px solid #b9dccb}
.part .h{font:800 22px "Manrope"}
.part .it{font-size:15.5px;line-height:1.4;color:var(--ink2);padding:6px 0;border-top:1px solid var(--grid);white-space:normal;display:flex;justify-content:space-between;gap:8px}
.part .it b{font:600 15px "IBM Plex Mono";color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{font:500 15px "IBM Plex Mono",monospace;border:1.5px solid var(--axis);border-radius:6px;padding:2px 8px;background:#fff;color:var(--ink);white-space:nowrap}
.chip i{font-style:normal;color:var(--muted);margin-left:5px;font-size:13px}
.chain{display:flex;align-items:center;gap:10px;margin-top:6px}
.chain .st{font:600 17px "IBM Plex Mono";border:2px solid var(--ink);border-radius:8px;padding:6px 12px;background:#fff}
.chain .os{display:flex;flex-direction:column;gap:4px}
.chain .os .st{padding:2px 10px;font-size:15px}
.chain .ar{font:700 22px "Manrope";color:var(--muted)}
.cn{font:500 14px "IBM Plex Mono";color:var(--muted);margin-top:12px}
.fl{position:absolute;white-space:nowrap;line-height:1.3}
.fl .t{font:800 21px "Manrope";letter-spacing:-.01em;display:inline-flex;align-items:center;gap:6px}
.fl .t .n{font:500 16px "IBM Plex Mono";color:var(--muted)}
.fl .s{font-size:16px;color:var(--ink2)}
.fl .bg{background:rgba(251,251,249,.94);border-radius:9px;padding:4px 10px;display:inline-block}
.fl .chips{margin-top:6px;display:grid;gap:5px}
.fl.n{transform:translate(-50%,-100%);text-align:center}
.fl.s{transform:translate(-50%,0);text-align:center}
.fl.e{transform:translate(0,-50%)}
.fl.w{transform:translate(-100%,-50%);text-align:right}
.fl.se{}
.lp{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#1f1e1c;color:#fff;font:800 14px "Manrope";flex:none}
.cat{position:absolute;width:396px}
.cat .g{font:600 13px "IBM Plex Mono";letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:10px 0 5px}
.cat .chip{font-size:14px;padding:1px 6px}
.rec{position:absolute;display:grid;gap:6px 10px}
.rec .r{display:flex;align-items:center;gap:6px;background:#fff;border:1.5px solid #cfe5da;border-radius:8px;padding:5px 9px;font-size:16px;color:var(--ink)}
.rec .r > b{font:600 15px "IBM Plex Mono";color:var(--muted);margin-left:auto}
.sat{position:absolute;white-space:nowrap;font-size:16px;font-weight:600;display:flex;align-items:center;gap:5px}
.sat > b{font:500 14px "IBM Plex Mono";color:var(--muted)}
.sat.w{transform:translate(-100%,-50%)}
.sat.e{transform:translate(0,-50%)}
.hubl{position:absolute;transform:translate(-50%,-50%);text-align:center}
.hubl .t{font:800 26px "Manrope";letter-spacing:-.01em}
.hubl .n{font:600 18px "IBM Plex Mono";color:var(--ink2)}
.loops{position:absolute;background:#f3f3ef;border-radius:18px;padding:20px 24px}
.loops .h{font:800 24px "Manrope";margin-bottom:8px;grid-column:span 2}
.loops{display:grid;grid-template-columns:1fr 1fr;column-gap:24px;align-content:start}
.loops .lr{display:grid;grid-template-columns:34px 1fr;gap:4px 8px;align-items:start;padding:8px 0;border-top:1px solid var(--grid)}
.loops .lr .lp{width:28px;height:28px;font-size:16px}
.loops .lr b{font:700 18px "Manrope"}
.loops .lr div{font-size:15px;white-space:normal;color:var(--ink2);line-height:1.4}
"""


def render_flow(model: dict, lay: dict) -> str:
    F = lay["flow"]
    get = counter(model)
    tools = len(model.get("tools", []))
    H = F["height"]
    svg, html_, over, late = [], [], [], []
    defs = "".join(
        f'<marker id="ar-{w}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="26" markerHeight="26" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c[1]}"/></marker>'
        for w, c in WHO.items())

    def val(k):
        if k == "tools":
            return tools
        return get(k)

    def items(lst, cls="it"):
        out = []
        for it in lst:
            t = html.escape(it[0])
            v = val(it[1]) if len(it) > 1 else None
            out.append(f'<div class="{cls}"><span>{t}</span>{"<b>" + fmt(v) + "</b>" if v is not None else ""}</div>')
        return "".join(out)

    for sid, S in F["sectors"].items():
        x, y, w, h = S["box"]
        col = WHO[S["who"]][1]
        cls = "box prog" if sid == "program" else "box"
        inner = items(S.get("items", []))
        if S.get("chips"):
            inner += '<div class="chips">' + "".join(f'<span class="chip">{html.escape(c)}</span>' for c in S["chips"]) + "</div>"
        if S.get("chain"):
            parts = []
            for c in S["chain"]:
                if isinstance(c, list):
                    parts.append('<div class="os">' + "".join(f'<span class="st">{html.escape(o)}</span>' for o in c) + "</div>")
                else:
                    parts.append(f'<span class="st">{html.escape(c)}</span>')
            inner += '<div class="chain">' + '<span class="ar">→</span>'.join(parts) + f'</div><div class="cn">{html.escape(S.get("chain_note", ""))}</div>'
        html_.append(f'<div class="{cls}" style="--c:{col};left:{x}px;top:{y}px;width:{w}px;height:{h}px"><div class="h">{badge(S["who"], 28)}{html.escape(S["name"])}</div><div class="hs">{html.escape(S.get("sub", ""))}</div>{inner}</div>')

    for pid, P in F["parts"].items():
        x, y, w, h = P["box"]
        html_.append(f'<div class="part" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><div class="h">{html.escape(P["name"])}</div>{items(P["items"])}</div>')

    fb = F["files_box"]
    x, y, w, h = fb["box"]
    html_.append(f'<div class="box" style="--c:#7a7870;border-style:dashed;left:{x}px;top:{y}px;width:{w}px;height:{h}px;padding:14px 18px"><div class="h" style="font-size:21px">{html.escape(fb["name"])}</div><div class="hs" style="margin-bottom:6px">{html.escape(fb["sub"])}</div>{items(fb["items"])}</div>')

    # task hub
    hb = F["hub"]
    hx, hy = hb["at"]
    r = hb["r"]
    for t, k, w, ang in F["satellites"]:
        a = math.radians(ang - 90)  # 0 = up, clockwise
        a = math.radians(ang) if False else a
        dx, dy = math.sin(math.radians(ang)) * -1, -math.cos(math.radians(ang))
        # angle: 0 = right, negative = up; mirror for |ang|>90
        rad = math.radians(ang)
        dx, dy = math.cos(rad), math.sin(rad)
        x0, y0 = hx + dx * (r + 6), hy + dy * (r + 6)
        x1, y1 = hx + dx * (r + 62), hy + dy * (r + 62)
        over.append(f'<path d="M{x0:.0f},{y0:.0f} L{x1:.0f},{y1:.0f}" stroke="#7d7b74" stroke-width="2.5" stroke-dasharray="1 6" stroke-linecap="round"/>')
        over.append(f'<circle cx="{x1:.0f}" cy="{y1:.0f}" r="6" fill="{WHO[w][1]}"/>')
        side = "w" if dx < 0 else "e"
        lx = x1 - 12 if side == "w" else x1 + 12
        late.append(f'<div class="sat {side}" style="left:{lx:.0f}px;top:{y1:.0f}px">{badge(w, 18)}{html.escape(t)} <b>{fmt(val(k))}</b></div>')
    over.append(f'<circle cx="{hx}" cy="{hy}" r="{r}" fill="#fff" stroke="#1f1e1c" stroke-width="9"/>')
    over.append(f'<circle cx="{hx}" cy="{hy}" r="{r - 16}" fill="none" stroke="#1f1e1c" stroke-width="2"/>')
    late.append(f'<div class="hubl" style="left:{hx}px;top:{hy}px"><div class="t">{html.escape(hb["t"])}</div><div class="n">{fmt(val(hb["n"]))}</div><div style="font-size:13px;color:var(--muted)">за 30 дней</div></div>')

    R = F["records"]
    x, y = R["at"]
    html_.append(f'<div class="rec" style="left:{x}px;top:{y}px;width:1156px;grid-template-columns:repeat({R["cols"]},1fr)"><div style="grid-column:span {R["cols"]};font:600 13px IBM Plex Mono;letter-spacing:.08em;color:var(--muted)">ДРУГИЕ ЗАПИСИ · ЗНАЧОК — КТО ПИШЕТ ТЕКСТ</div>'
                 + "".join(f'<div class="r">{badge(w, 18)}{html.escape(t)}<b>{fmt(val(k))}</b></div>' for t, k, w in R["items"]) + "</div>")

    L = F["loops"]
    x, y, w, h = L["box"]
    html_.append(f'<div class="loops" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><div class="h">Петли</div>'
                 + "".join(f'<div class="lr"><span class="lp">{i}</span><div><b>{html.escape(n)}</b><br>{html.escape(d)}</div></div>' for i, (n, d) in enumerate(L["items"], 1))
                 + "</div>")

    for a, b, w in F.get("inner", []):
        over.append(f'<path d="M{a[0]},{a[1]} L{b[0]},{b[1]}" stroke="{WHO[w][1]}" stroke-width="6" marker-end="url(#ar-{w})"/>')

    cards = model["cards"]
    T = model["counts"]["typed"]["d30"]
    for fl in F["flows"]:
        pts = [tuple(p) for p in fl["pts"]]
        col = WHO[fl["who"]][1]
        d = rounded_path(pts, fl.get("radius", 60))
        wdt = 10 if fl.get("kind") == "behav" else 12
        dash = ' stroke-dasharray="16 9"' if fl.get("kind") == "behav" else ""
        svg.append(f'<path d="{d}" fill="none" stroke="#fbfbf9" stroke-width="{wdt + 10}" stroke-linejoin="round"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wdt}" stroke-linejoin="round"{dash} marker-end="url(#ar-{fl["who"]})"/>')
        if not fl.get("t"):
            continue
        lx, ly = fl["lab"]
        lps = "".join(f'<span class="lp">{i}</span>' for i in fl.get("loops", []))
        n = val(fl.get("n")) if fl.get("n") else None
        num = f'<span class="n">{fmt(n)}</span>' if n is not None else ""
        chips = ""
        if fl.get("chips"):
            cols = fl.get("chipcols", 2)
            chips = f'<div class="chips" style="grid-template-columns:repeat({cols},auto)">' + "".join(f'<span class="chip">{html.escape(c)}</span>' for c in fl["chips"]) + "</div>"
        html_.append(f'<div class="fl {fl.get("lp", "n")}" style="left:{lx}px;top:{ly}px"><div class="bg"><div class="t">{lps}{badge(fl["who"], 22)}{html.escape(fl["t"])}{num}</div><div class="s">{html.escape(fl.get("s", ""))}</div>{chips}</div></div>')
        if fl.get("catalog"):
            groups = model["groups"]
            out = []
            for g, gname in groups.items():
                cs = [c for c in cards if c["group"] == g]
                chips_ = []
                for c in cs:
                    nm = "#" + c["cmds"][0] + (" …" if len(c["cmds"]) > 2 else "")
                    if c["id"] == "now-col":
                        nm = "#now-todo …"
                    cnt = sum(T.get(x, 0) for x in c["cmds"])
                    chips_.append(f'<span class="chip">{html.escape(nm)}<i>{cnt}</i></span>')
                    if c["id"] == "now-col":
                        chips_.append(f'<span class="chip">#now-done<i>{T.get("now-done", 0)}</i></span>')
                out.append(f'<div class="g">{html.escape(gname)}</div><div class="chips">{"".join(chips_)}</div>')
            out.append('<div class="g">служебные</div><div class="chips"><span class="chip">###тег</span></div>')
            html_.append(f'<div class="cat" style="left:{pts[0][0] + 22}px;top:{pts[0][1] + 36}px"><div class="g" style="color:var(--ink2)">команды в сообщении · число — за 30 дней</div>{"".join(out)}</div>')

    body = (f'<div class="map" style="height:{H}px"><svg width="{W - 144}" height="{H}" viewBox="0 0 {W - 144} {H}"><defs>{defs}</defs>{"".join(svg)}</svg>{"".join(html_)}<svg width="{W - 144}" height="{H}" viewBox="0 0 {W - 144} {H}" style="pointer-events:none"><defs>{defs.replace('id="ar-', 'id="ov-')}</defs>{"".join(over).replace("url(#ar-", "url(#ov-")}</svg>{"".join(late)}</div>')
    key = f"""<div class="key"><div class="kh">кто действует — цвет потока и значок</div>{who_key()}
<div class="kh">потоки</div>
<div class="kr"><svg width="54" height="16"><path d="M2,8 L40,8" stroke="#1f1e1c" stroke-width="9"/><path d="M38,1 L52,8 L38,15z" fill="#1f1e1c"/></svg><span><b>Сплошной</b> — передаёт</span></div>
<div class="kr"><svg width="54" height="16"><path d="M2,8 L40,8" stroke="#1f1e1c" stroke-width="8" stroke-dasharray="12 6"/><path d="M38,1 L52,8 L38,15z" fill="#1f1e1c"/></svg><span><b>Штрих</b> — меняет поведение агентов</span></div>
<div class="kr"><svg width="54" height="16"><path d="M4,8 L50,8" stroke="#7d7b74" stroke-width="2.5" stroke-dasharray="1 6" stroke-linecap="round"/></svg><span><b>Пунктир</b> — прикрепляется к задаче</span></div>
<div class="kr"><span class="lp" style="display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#1f1e1c;color:#fff;font:800 14px Manrope">1</span><span><b>Номер</b> — петля, список внизу</span></div></div>"""
    foot = (f"Числа — последние 30 дней по всем проектам (чаты помощников не в счёт). "
            f"<b>#now-done</b> кладёт сообщение задачей сразу в Done; <b>#done</b> закрывает задачу этого чата и забирает её участок с коммитами и временем. "
            f"Собрано из кода и данных: scripts/feature_map/build.py, раскладка — sysmap.yaml · {model['generated_at']}")
    return page("Карта потоков SP", f"карта системы · последние 30 дней · {model['today']}", html.escape(F["title"]),
                html.escape(F["lede"]), key, body, foot, FLOW_CSS)
