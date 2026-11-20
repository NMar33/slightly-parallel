"""One drawn sheet of how Slightly Parallel's commands work and connect (tk_bba7c02c).

Drawn objects, left to right: the operator's terminal with the commands typed
in a chat about a sample task (shopfront · частичные возвраты), the capture
hook, the SP server with the record each command makes, the task in the
centre with what attaches to it, and the browser with the SP pages where each
record is seen. Below: the agent (what it writes back through MCP), AGENTS.md
and skills (the dashed loop that changes agents), the repository and CI, and
articles going out to a release.

Each command is one row at one height across the sheet, so its path reads
straight: typed → captured by the hook → record on the server → task or page.
Arrow colour = who acts (operator / program / agent, as in sysmap.py);
dashed = changes how agents behave. Numbers are live: how often the operator
typed the command in the last 30 days.

The layout is hand-kept here (ROWS and the coordinates below);
`missing_commands(model)` lists the program's commands the sheet does not name.
"""

from __future__ import annotations

import html
import re

from sysmap import all_commands, counter, fmt, rounded_path

O, S, A, X = "#eb6834", "#14a06f", "#2a78d6", "#8d8b85"
TINT = {O: "#fdeee6", S: "#e3f4ec", A: "#e7f0fb", X: "#efeeea"}
WHO = {"o": O, "s": S, "a": A, "x": X}
W = 3080

# Columns (css px)
TX0, TX1 = 40, 690          # terminal
HX0, HX1 = 750, 850         # hook
SX0, SX1 = 910, 1300        # server
CX0, CX1 = 1370, 1910       # task
BX0, BX1 = 1990, 2990       # browser
TOP = 270                   # top of the drawn objects

# One row per command line. kind: words → a page line, mini → a small task
# card, task → a row of the task card, page → a page line below the task,
# service → stays on the server. who = who writes the record (its arrow
# colour after the server); text_who = whose words the record keeps.
ROWS = [
    ("group", "слова → правила и поведение агентов"),
    dict(id="vision", cmds=["vision"], typed="возврат — без звонка в поддержку", kind="words", who="s",
         rec="видение", sub="слова дословно + толкование агента", text="oa", dest="Видения",
         line="возврат — без звонка в поддержку"),
    dict(id="rule", cmds=["rule"], typed="суммы возвратов — в копейках", kind="words", who="s",
         rec="правило", sub="→ AGENTS.md всех проектов", text="o", dest="Правила",
         line="суммы возвратов — в копейках"),
    dict(id="problem", cmds=["problem", "problem solved"], typed="банк не отдаёт возврат",
         show="#problem · #problem solved", kind="words", who="s",
         rec="проблема", sub="открыта → решена (#problem solved)", text="o", dest="Проблемы",
         line="банк не отдаёт частичный возврат · открыта"),
    dict(id="prompt", cmds=["prompt"], typed="проверь все суммы по строкам", kind="words", who="s",
         rec="промпт", sub="в библиотеку, для повторов", text="oa", dest="Промпты",
         line="проверь все суммы по строкам"),
    dict(id="skill", cmds=["skill"], typed="как мы тестируем возвраты", kind="words", who="a",
         rec="скилл", sub="агент пишет SKILL.md → ставится в проекты", text="a", dest="Скиллы",
         line="testing-refunds · стоит в 4 проектах"),
    dict(id="artifact", cmds=["artifact"], typed="выгрузка возвратов за месяц", kind="words", who="a",
         rec="артефакт", sub="результат папкой", text="a", dest="Артефакты",
         line="refunds-2026-10/ · таблица"),
    ("agent", "◆ записал видение и правило; беру задачу"),
    ("group", "задачи"),
    dict(id="now-col", cmds=["now-todo", "now-to-do", "now-next", "now-backlog", "now-review", "now-parked",
                             "now-done", "now-doing"],
         typed="экспорт возвратов в CSV", show="#now-todo", kind="mini", who="s",
         rec="задача в колонке, без работы",
         sub="-to-do -next -backlog -review -parked -doing<br>-done — сразу в «Готово», без участка чата", text="oa", h=16,
         card="экспорт возвратов в CSV", col="к работе"),
    dict(id="task", cmds=["task"], typed="запиши: письмо клиенту о возврате", kind="mini", who="a",
         rec="задача от агента", sub="из разговора, в колонку «агент»", text="a",
         card="письмо клиенту о возврате", col="агент"),
    ("card", None),
    dict(id="now", cmds=["now"], typed="частичный возврат по строкам заказа", kind="task", who="s",
         rec="задача в работе", sub="задача этого чата · заголовок пишет агент", text="oa",
         part="слова оператора дословно", note="заголовок — агент", pw="oa"),
    dict(id="done", cmds=["done"], typed="", kind="task", who="s",
         rec="готово", sub="текущая задача → «Готово» + её участок чата", text="s",
         part="участок чата", note="→ коммиты · время · токены · отчёт агента", pw="sa"),
    dict(id="evidence", cmds=["evidence"], typed="скрин страницы возврата", kind="task", who="a",
         rec="доказательства", sub="агент прикладывает по указанию", text="a",
         part="доказательства", note="если включены у задачи", pw="a"),
    dict(id="decision", cmds=["decision"], typed="", kind="task", who="a",
         rec="решение", sub="с весом · к задаче и к архитектуре", text="a",
         part="решения · заметки", note="агент, после работы", pw="a"),
    dict(id="entrypoint", cmds=["entrypoint"], typed="как запустить витрину", kind="task", who="a",
         rec="точка входа", sub="где живёт, как запустить, где остановились", text="a",
         part="точка входа «витрина»", note="«где остановились» после #done", pw="a"),
    dict(id="publish", cmds=["publish"], typed="частичные возвраты в 1.4", kind="task", who="s",
         rec="карточка публикации", sub="+ задачи, коммиты, заметки → статьи", text="oa",
         part="карточка «выпущено»", note="→ статьи, релиз", pw="oa"),
    dict(id="core-new", cmds=["core-new"], typed="модуль возвратов", kind="task", who="a",
         rec="ядро", sub="имя, тип, файлы — агент", text="a",
         part="ядро «модуль возвратов»", note="↔ файлы ↔ коммиты", pw="a"),
    dict(id="core", cmds=["core-note", "core", "core-off"], typed="", show="#core-note · #core · #core-off",
         kind="task", who="s", rec="заметка ядра · связь · убрать",
         sub="лента модуля · сообщение ↔ задача · после «да»", text="oa",
         part="заметки ядра", note="лента модуля", pw="oa"),
    ("group", "код, день, сохранить"),
    dict(id="scan", cmds=["scan"], typed="", kind="page", who="a",
         rec="скан", sub="коммиты с прошлого скана → файлы → форма", text="a", dest="Архитектура",
         line="скан 18.11 · 14 файлов · форма архитектуры"),
    dict(id="arch", cmds=["architecture", "page", "map"], typed="", show="#architecture · #page · #map",
         kind="page", who="a", rec="архитектура", sub="форма, страница проекта, карта программы",
         text="a", dest="Карта", line="страница проекта · карта программы"),
    dict(id="standup", cmds=["standup"], typed="", kind="page", who="a",
         rec="стендап", sub="помощник: все чаты дня + задачи → что дальше", text="a", dest="Стендапы",
         line="17.11 · сделано · отклонения · следующие задачи"),
    dict(id="marks", cmds=["important", "important-agent", "important-task", "important-message", "pin"],
         typed="", show="#important · #pin", kind="page", who="s",
         rec="звезда · закреп", sub="#important-agent -task -message · #pin", text="o", dest="Закреплённые",
         line="★ сумма по строке без скидки"),
    dict(id="carry", cmds=["carry", "carry-brief", "fork-later"], typed="",
         show="#carry · #carry-brief · #fork-later", kind="page", who="s",
         rec="вернуть агенту · отложить", sub="после сжатия хук отдаёт агенту · работа для другого",
         text="o", dest="Отложенные", line="для другого агента: письмо в банк"),
    dict(id="undo", cmds=["undo", "undo-yes"], typed="", show="#undo · #undo-yes", kind="page", who="a",
         rec="отмена", sub="записи этого тега → архив, по номерам", text="a", dest="Архив",
         line="2 записи → архив · можно вернуть"),
    dict(id="service", cmds=["mute", "usage", "usage-on", "usage-off", "usage-warnings-on", "usage-warnings-off",
                             "usage-price", "sp", "help"], typed="",
         show="#mute · ###тег · #usage… · #sp · #help", kind="service", who="s", h=44,
         rec="служебное", sub="#mute глушит теги сообщения, ###тег оставляет один<br>#usage, #usage-on, #usage-off — расход токенов<br>#usage-warnings-on/-off, #usage-price — цены<br>#sp — проверка SP · #help — справка",
         text="s"),
]

# Browser panels: (title, rows whose arrows land there, mini-UI kind)
PANELS = [
    ("Видения · Правила · Проблемы · Промпты · Скиллы · Артефакты", ["vision", "rule", "problem", "prompt", "skill", "artifact"], "list"),
    ("Доска", ["now-col", "task", "card"], "board"),
    ("Задача", ["now", "done", "evidence", "decision"], "task"),
    ("Точки входа · Публикации", ["entrypoint", "publish"], "pub"),
    ("Ядра · Архитектура · Карта", ["core-new", "core", "scan", "arch"], "list"),
    ("Стендапы", ["standup"], "list"),
    ("Закреплённые · Отложенные · Архив", ["marks", "carry", "undo"], "list"),
]


def missing_commands(model: dict) -> list[str]:
    have = {c for r in ROWS if isinstance(r, dict) for c in r["cmds"]}
    return sorted(all_commands(model) - have)


def esc(s: str) -> str:
    return html.escape(s or "")


# ---------------------------------------------------------------------------
# layout

def layout() -> tuple[list, dict]:
    y = TOP + 120
    items, at = [], {}
    for r in ROWS:
        if isinstance(r, tuple):
            kind, text = r
            if kind == "group":
                y += 14
                items.append(("group", text, y))
                y += 34
            elif kind == "agent":
                items.append(("agent", text, y + 4))
                y += 50
            elif kind == "card":
                at["card"] = y + 44           # the card's header line
                items.append(("agent", "◆ беру «частичные возвраты», пишу заголовок", y + 44))
                y += 112
            continue
        h = r.get("h", 0)
        at[r["id"]] = y + 25 + h / 2
        items.append(("row", r, y + 25 + h / 2))
        y += 56 + h
    return items, at


# ---------------------------------------------------------------------------
# drawing primitives

class Svg:
    def __init__(self):
        self.under: list[str] = []
        self.over: list[str] = []

    def arrow(self, pts, color, dashed=False, head=True, width=2.6, halo=True, r=14):
        d = rounded_path([tuple(p) for p in pts], r)
        if halo:
            self.under.append(f'<path d="{d}" fill="none" stroke="#eef0f2" stroke-width="{width + 7}" stroke-linecap="round" stroke-linejoin="round"/>')
        dash = ' stroke-dasharray="10 7"' if dashed else ""
        mk = f' marker-end="url(#h{color[1:]})"' if head else ""
        self.under.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash}{mk}/>')

    def defs(self) -> str:
        out = []
        for c in (O, S, A, X, "#52514e"):
            out.append(f'<marker id="h{c[1:]}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5.2" markerHeight="5.2" orient="auto-start-reverse"><path d="M0,0.6 L9.4,5 L0,9.4 z" fill="{c}"/></marker>')
        return "<defs>" + "".join(out) + "</defs>"


def box(x, y, w, h, cls="", inner="", style=""):
    return f'<div class="{cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{style}">{inner}</div>'


def label(x, y, text, color, cls="lb", anchor="c"):
    tr = {"c": "translate(-50%,-50%)", "l": "translate(0,-50%)", "r": "translate(-100%,-50%)"}[anchor]
    return f'<div class="{cls}" style="left:{x}px;top:{y}px;transform:{tr};--c:{color}">{text}</div>'


def dots(text: str) -> str:
    return "".join(f'<i class="wd" style="background:{WHO[w]}"></i>' for w in text)


ROBOT = """<svg viewBox="0 0 120 130" width="128" height="138"><line x1="60" y1="6" x2="60" y2="22" stroke="#2a78d6" stroke-width="4" stroke-linecap="round"/>
<circle cx="60" cy="7" r="6" fill="#2a78d6"/><rect x="18" y="22" width="84" height="58" rx="16" fill="#e7f0fb" stroke="#2a78d6" stroke-width="4"/>
<circle cx="44" cy="51" r="8" fill="#2a78d6"/><circle cx="76" cy="51" r="8" fill="#2a78d6"/><rect x="48" y="66" width="24" height="5" rx="2.5" fill="#2a78d6"/>
<rect x="8" y="42" width="10" height="20" rx="4" fill="#2a78d6"/><rect x="102" y="42" width="10" height="20" rx="4" fill="#2a78d6"/>
<rect x="30" y="86" width="60" height="38" rx="10" fill="#e7f0fb" stroke="#2a78d6" stroke-width="4"/><rect x="48" y="96" width="24" height="6" rx="3" fill="#2a78d6"/><rect x="48" y="108" width="14" height="6" rx="3" fill="#9cc0ec"/></svg>"""

RACK = """<svg viewBox="0 0 60 64" width="46" height="50"><rect x="4" y="3" width="52" height="16" rx="4" fill="#e3f4ec" stroke="#14a06f" stroke-width="3"/>
<rect x="4" y="24" width="52" height="16" rx="4" fill="#e3f4ec" stroke="#14a06f" stroke-width="3"/><rect x="4" y="45" width="52" height="16" rx="4" fill="#e3f4ec" stroke="#14a06f" stroke-width="3"/>
<circle cx="14" cy="11" r="3" fill="#14a06f"/><circle cx="14" cy="32" r="3" fill="#14a06f"/><circle cx="14" cy="53" r="3" fill="#14a06f"/>
<rect x="24" y="9" width="24" height="4" rx="2" fill="#14a06f"/><rect x="24" y="30" width="24" height="4" rx="2" fill="#14a06f"/><rect x="24" y="51" width="24" height="4" rx="2" fill="#14a06f"/></svg>"""

HOOK = """<svg viewBox="0 0 40 52" width="30" height="40"><path d="M20 4 V30 a10 10 0 1 1 -14 -9" fill="none" stroke="#14a06f" stroke-width="5" stroke-linecap="round"/><circle cx="20" cy="5" r="4" fill="#14a06f"/></svg>"""

BRANCH = """<svg viewBox="0 0 40 48" width="30" height="36"><circle cx="10" cy="8" r="5" fill="none" stroke="#52514e" stroke-width="3.5"/><circle cx="10" cy="40" r="5" fill="none" stroke="#52514e" stroke-width="3.5"/>
<circle cx="30" cy="16" r="5" fill="none" stroke="#52514e" stroke-width="3.5"/><path d="M10 13 V35 M30 21 C30 30 12 26 10 35" fill="none" stroke="#52514e" stroke-width="3.5"/></svg>"""

FILEDOC = """<svg viewBox="0 0 40 48" width="28" height="34"><path d="M6 3 H26 L36 13 V45 H6 Z" fill="#fff" stroke="#52514e" stroke-width="3" stroke-linejoin="round"/><path d="M26 3 V13 H36" fill="none" stroke="#52514e" stroke-width="3" stroke-linejoin="round"/>
<rect x="12" y="22" width="18" height="3" rx="1.5" fill="#52514e"/><rect x="12" y="30" width="14" height="3" rx="1.5" fill="#52514e"/><rect x="12" y="38" width="18" height="3" rx="1.5" fill="#52514e"/></svg>"""


# ---------------------------------------------------------------------------

def render(model: dict) -> str:
    get = counter(model)
    T = model["counts"]["typed"]["d30"]
    items, at = layout()
    rows = {it[1]["id"]: it[1] for it in items if it[0] == "row"}
    svg = Svg()
    el: list[str] = []          # boxes (under the svg)
    top: list[str] = []         # labels (over the svg)
    y_last = max(at.values())
    bottom = y_last + 60        # bottom of terminal / hook / server / browser

    # ---- terminal ---------------------------------------------------------
    el.append(box(TX0, TOP, TX1 - TX0, bottom - TOP, "term", """
<div class="tbar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i>
<span>терминал SP · claude · shopfront</span></div>"""))
    el.append(label(TX0 + 26, TOP + 82, "оператор пишет в чате с агентом; тег в сообщении — команда", "#9aa0a6", "tnote", "l"))
    for kind, r, y in items:
        if kind == "group":
            el.append(label(TX0 + 26, y + 14, f"# {esc(r)}", "#6f7680", "tgrp", "l"))
            continue
        if kind == "agent":
            el.append(label(TX0 + 26, y + 18, esc(r), A, "tagent", "l"))
            continue
        show = r.get("show") or "#" + r["cmds"][0]
        cmd = re.sub(r"(#+[\w\-…]+(?: solved)?)", r'<b>\1</b>', esc(show))
        n = sum(T.get(c, 0) for c in r["cmds"])
        el.append(label(TX0 + 26, y, f'<span class="pr">›</span>{cmd} <span class="ty">{esc(r["typed"])}</span>', O, "tline", "l"))
        el.append(label(TX1 - 22, y, fmt(n) if n else "0", "#8a9099", "tcount", "r"))
        # typed → hook
        svg.arrow([(TX1 + 6, y), (HX0 - 4, y)], O, width=2.4)

    # ---- hook -------------------------------------------------------------
    el.append(box(HX0, TOP, HX1 - HX0, bottom - TOP + 20, "hook", f"""<div class="hh">{HOOK}<b>хук</b></div>
<div class="hs">записывает каждое сообщение, узнаёт тег</div>"""))
    for kind, r, y in items:
        if kind == "row":
            el.append(f'<i class="cap" style="left:{(HX0 + HX1) / 2}px;top:{y}px"></i>')
            svg.arrow([((HX0 + HX1) / 2 + 9, y), (SX0 - 4, y)], S, width=2.4)
            svg.under.append(f'<line x1="{HX0 + 2}" y1="{y}" x2="{(HX0 + HX1) / 2 - 9}" y2="{y}" stroke="{O}" stroke-width="2.4"/>')

    # ---- server -----------------------------------------------------------
    sb = bottom + 70
    el.append(box(SX0, TOP, SX1 - SX0, sb - TOP, "srv", f"""<div class="sh">{RACK}<div><b>сервер Slightly Parallel</b>
<span>хранит слова дословно · двигает задачи · считает время и токены</span></div></div>"""))
    for kind, r, y in items:
        if kind != "row":
            continue
        cl = WHO[r["who"]]
        hh = 46 + r.get("h", 0) + (12 if r.get("h") else 0)
        sub = esc(r['sub']).replace("&lt;br&gt;", "<br>")
        el.append(box(SX0 + 14, y - hh / 2, SX1 - SX0 - 28, hh, "chip", f"""<div class="c1"><b style="color:{cl}">{esc(r['rec'])}</b>{dots(r['text'])}</div>
<div class="c2">{sub}</div>""", f"--c:{cl}"))
    el.append(box(SX0 + 14, sb - 54, SX1 - SX0 - 28, 40, "mcp", f'<b>MCP</b> · {len(model.get("tools", []))} инструментов агента'))

    # ---- task (centre) ----------------------------------------------------
    card_y0 = at["card"] - 34
    card_y1 = at["core"] + 34
    el.append(box(CX0, card_y0, CX1 - CX0, card_y1 - card_y0, "task", f"""
<div class="tk"><span class="tkk">задача · shopfront</span><span class="tkid">tk_…</span></div>
<div class="tt">частичные возвраты</div>
<div class="st"><span>агент</span><span>к работе</span><span class="on">в работе</span><span class="dn">готово</span></div>"""))
    for kind, r, y in items:
        if kind != "row":
            continue
        cl = WHO[r["who"]]
        if r["kind"] == "words" or r["kind"] == "page":
            dest_x = BX0 + 18
            svg.arrow([(SX1 - 10, y), (dest_x, y)], cl)
            top.append(label((CX0 + CX1) / 2 + 40, y, esc(r["dest"]), cl, "pill"))
        elif r["kind"] == "mini":
            el.append(box(CX0 + 30, y - 19, CX1 - CX0 - 60, 38, "mini",
                          f'<b>{esc(r["card"])}</b><span>{esc(r["col"])}</span>', f"--c:{cl}"))
            svg.arrow([(SX1 - 10, y), (CX0 + 26, y)], cl)
            svg.arrow([(CX1 - 30, y), (BX0 + 18, y)], S)
        elif r["kind"] == "task":
            el.append(box(CX0 + 16, y - 21, CX1 - CX0 - 32, 42, "part",
                          f'<span class="pdots">{dots(r["pw"])}</span><b>{esc(r["part"])}</b><span>{esc(r["note"])}</span>'))
            svg.arrow([(SX1 - 10, y), (CX0 + 12, y)], cl)
            svg.arrow([(CX1 - 16, y), (BX0 + 18, y)], S)
    svg.arrow([(CX1, at["card"]), (BX0 + 18, at["card"])], S)
    top.append(label(CX1 + 40, at["card"] - 16, "на доске", S, "tiny"))

    # vision → rule hint
    vy, ry = at["vision"], at["rule"]
    hx = CX0 + 120
    svg.under.append(f'<path d="M{hx},{vy + 6} C{hx - 34},{vy + 14} {hx - 34},{ry - 14} {hx - 4},{ry - 6}" fill="none" stroke="#52514e" stroke-width="2" marker-end="url(#h52514e)"/>')
    top.append(label(hx - 40, (vy + ry) / 2, "часто становится", "#52514e", "tiny", "r"))

    # ---- browser ----------------------------------------------------------
    el.append(box(BX0, TOP, BX1 - BX0, bottom - TOP, "brw", """
<div class="bbar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i>
<span class="url">127.0.0.1:8123 · Slightly Parallel</span></div>
<div class="tabs"><span class="on">Доска</span><span>Задача</span><span>Видения</span><span>Правила</span><span>Ядра</span><span>Архитектура</span><span>Стендапы</span><span>Публикации</span><span>Закреплённые</span></div>"""))
    lines_of = {r["id"]: r.get("line") for r in rows.values()}
    for title, ids, kind in PANELS:
        ys = [at[i] for i in ids]
        y0, y1 = min(ys) - 27, max(ys) + 27
        inner = f'<div class="pt">{esc(title)}</div>'
        el.append(box(BX0 + 14, y0, BX1 - BX0 - 28, y1 - y0, "pnl", inner))
        px = BX0 + 330
        for i in ids:
            y = at[i]
            if kind == "list" or kind == "pub":
                txt = lines_of.get(i) or {"core-new": "модуль возвратов · 6 файлов · 3 задачи",
                                          "core": "лента: округление по строкам",
                                          "entrypoint": "витрина: где живёт · как запустить · где остановились",
                                          "publish": "1.4 · частичные возвраты · 3 задачи, 9 коммитов"}.get(i, "")
                el.append(box(px, y - 17, BX1 - px - 30, 34, "pl", esc(txt)))
            elif kind == "task":
                txt = {"now": "частичный возврат по строкам заказа", "done": "участок чата · 12 коммитов · 3 ч 40 мин · 1,2 млн токенов",
                       "evidence": "скрин страницы возврата", "decision": "округлять по строке, не по заказу · вес: обычный"}[i]
                el.append(box(px, y - 17, BX1 - px - 30, 34, "pl", esc(txt)))
        if kind == "board":
            cols = [("агент", ["письмо клиенту"]), ("к работе", ["экспорт в CSV"]), ("в работе", ["частичные возвраты"]), ("готово", ["скидки на доставку"])]
            cw = (BX1 - px - 30 - 30) / 4
            for k, (cn, cards) in enumerate(cols):
                cx = px + k * (cw + 10)
                cards_html = "".join(f'<div class="bc{" hot" if c == "частичные возвраты" else ""}">{esc(c)}</div>' for c in cards)
                el.append(box(cx, y0 + 12, cw, y1 - y0 - 24, "bcol", f'<div class="bch">{esc(cn)}</div>{cards_html}'))

    # ---- below: agent, AGENTS.md, repo + CI, articles ----------------------
    ay0 = sb + 80
    ay1 = ay0 + 390
    H = ay1 + 120
    el.append(box(TX0, ay0, TX1 - TX0, ay1 - ay0, "agent", f"""<div class="ag">{ROBOT}<div><b>агент</b>
<span>Claude Code · Codex · OpenCode — в том же чате</span><span>читает подсказку хука, делает работу</span></div></div>
<div class="agh">пишет через MCP</div>
<div class="agl"><span>заголовок задачи</span><span>толкование видения</span><span>задачу из разговора</span>
<span>отчёт «сделано», одна строка</span><span>доказательства</span><span>решение с весом</span><span>заметку</span>
<span>скан и форму архитектуры</span><span>страницу проекта, карту</span><span>стендап (помощник)</span>
<span>ядро, точку входа</span><span>скилл, артефакт</span></div>"""))
    hx_mid = (HX0 + HX1) / 2
    svg.arrow([(hx_mid, bottom + 20), (hx_mid, ay0 + 50), (TX1 + 4, ay0 + 50)], S)
    top.append(label(hx_mid + 14, ay0 - 18, "подсказка агенту: тег, задача, стендап · после сжатия — #carry", S, "pill", "l"))
    mx = (SX0 + SX1) / 2
    svg.arrow([(TX1, ay0 + 110), (mx, ay0 + 110), (mx, sb + 4)], A)
    top.append(label(mx - 14, ay0 + 80, "пишет записи через MCP", A, "pill", "r"))

    # repository + CI
    rx0, rx1 = CX0, 2590
    ry0, ry1 = ay0, ay1
    svg.arrow([(TX1, ay0 + 170), (rx0 - 4, ay0 + 170)], A)
    top.append(label((TX1 + rx0) / 2 + 160, ay0 + 170, "коммиты · Task: tk_…", A, "pill"))
    el.append(box(rx0, ry0, rx1 - rx0, ry1 - ry0, "repo", f"""<div class="rh" style="padding-left:80px">{BRANCH}<b>разработка</b><span>репозиторий и проверка</span></div>"""))
    stages = [("master", "коммиты агентов; Task: tk_… связывает с задачей", "#52514e"),
              ("ветки ci-*", "scripts/publish-ci.sh", "#52514e"),
              ("GitHub Actions", "Linux · macOS · Windows", X),
              ("релиз", "ветка release · main на GitHub", X)]
    sw = (rx1 - rx0 - 60 - 3 * 50) / 4
    sy0 = ry0 + 120
    for k, (t, s, c) in enumerate(stages):
        sx = rx0 + 30 + k * (sw + 50)
        extra = ""
        if t == "GitHub Actions":
            extra = '<div class="os"><span>Linux</span><span>macOS</span><span>Windows</span></div>'
        el.append(box(sx, sy0, sw, 150, "stage", f"<b>{esc(t)}</b><span>{esc(s)}</span>{extra}"))
        if k:
            svg.arrow([(sx - 46, sy0 + 75), (sx - 6, sy0 + 75)], "#52514e", halo=False)
    # commits → task
    cxv = rx0 + 64
    svg.arrow([(cxv, sy0 - 2), (cxv, card_y1 + 4)], S)
    top.append(label(cxv + 12, ay0 - 30, "коммиты → к задаче по участку чата", S, "pill", "l"))
    el.append(label(rx0 + 30, ry1 - 46, "тесты: pytest · vitest · e2e окна", "#52514e", "rnote", "l"))

    # articles → release
    ax0, ax1 = 2650, BX1
    el.append(box(ax0, ry0, ax1 - ax0, ry1 - ry0, "out", f"""<div class="rh">{FILEDOC}<b>наружу</b></div>
<div class="ol"><span>карточка #publish с задачами, коммитами, заметками</span><span>→ статьи, посты (проект текстов)</span><span>→ релиз</span></div>"""))
    py = at["publish"]
    svg.arrow([(BX1 - 14, py), (BX1 + 22, py), (BX1 + 22, ry0 - 30), (ax0 + 170, ry0 - 30), (ax0 + 170, ry0 - 4)], O)
    top.append(label(BX1 + 10, ry0 - 52, "#publish → статьи", O, "pill", "r"))
    rel_x = rx0 + 30 + 3 * (sw + 50) + sw
    svg.arrow([(ax0, sy0 + 75), (rel_x + 6, sy0 + 75)], O)

    # AGENTS.md + skills, the dashed loop
    gx0, gx1 = SX0 - 20, SX1 + 20
    gy0 = ay0 + 230
    el.append(box(gx0, gy0, gx1 - gx0, ay1 - gy0, "agmd", f"""<div class="rh">{FILEDOC}<b>AGENTS.md · SKILL.md</b></div>
<div class="ol"><span>правила — во всех проектах</span><span>скиллы — стоят в проектах</span><span>меняют, как работает каждый агент</span></div>"""))
    lx = BX1 + 48
    for i in ("rule", "skill"):
        svg.arrow([(BX1 - 14, at[i]), (lx, at[i])], S, dashed=True, head=False)
    svg.arrow([(lx, at["rule"]), (lx, H - 50), ((gx0 + gx1) / 2, H - 50), ((gx0 + gx1) / 2, ay1 + 4)], S, dashed=True)
    top.append(label(1700, H - 50, "правило и скилл программа ставит во все проекты", S, "pill"))
    svg.arrow([(gx0, gy0 + 110), (TX1 + 4, gy0 + 110)], S, dashed=True)
    top.append(label((gx0 + TX1) / 2, gy0 + 82, "меняет агента", S, "tiny"))

    # ---- header -----------------------------------------------------------
    key = f"""<div class="key">
<div class="kr"><i class="ar" style="--c:{O}"></i><span><b>оператор</b> — пишет команду</span></div>
<div class="kr"><i class="ar" style="--c:{S}"></i><span><b>программа</b> — хук и сервер</span></div>
<div class="kr"><i class="ar" style="--c:{A}"></i><span><b>агент</b> — пишет через MCP</span></div>
<div class="kr"><i class="ar dsh" style="--c:{S}"></i><span>меняет, как работают агенты</span></div>
<div class="kr"><i class="wd" style="background:{O}"></i><i class="wd" style="background:{A}"></i><span>чьи слова в записи</span></div>
<div class="kr"><span class="kn">134</span><span>раз за 30 дней</span></div></div>"""
    gen = model.get("today", "")
    head = f"""<header><div><div class="kicker"><span class="tag">Slightly Parallel</span> команды · {esc(gen)}</div>
<h1>Как команды связаны</h1>
<p class="lede">Пример: проект <b>shopfront</b>, задача <b>частичные возвраты</b>. Каждая команда — одна строка через весь лист: где её пишут → кто её ловит → какая запись → где её видно.</p></div>{key}</header>"""

    svg_html = f'<svg class="wires" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{svg.defs()}{"".join(svg.under)}</svg>'
    body = f'<div class="canvas" style="width:{W}px;height:{H}px">{head}{"".join(el)}{svg_html}{"".join(top)}</div>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={W}">
<title>Как команды связаны</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<section class="sheet" id="main">{body}</section></body></html>"""


CSS = """
:root{--page:#eef0f2;--surface:#fbfbf9;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e6e5df}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--page);color:var(--ink)}
body{width:3080px;font-family:"Manrope",system-ui,sans-serif}
.sheet{width:3080px;background:var(--page)}
header{position:absolute;left:40px;top:40px;width:2950px;display:grid;grid-template-columns:1fr 1040px;gap:60px;align-items:end}
.kicker{font:500 19px "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--ink2);display:flex;gap:14px;align-items:center}
.tag{display:inline-flex;border:2px solid var(--ink);border-radius:8px;padding:5px 12px;color:var(--ink);font-weight:600}
h1{font:800 60px/1.05 "Manrope",sans-serif;letter-spacing:-.03em;margin:14px 0 10px}
.lede{font-size:23px;line-height:1.45;color:var(--ink2);max-width:1700px}
.lede b{color:var(--ink)}
.key{background:var(--surface);border-radius:16px;padding:18px 24px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px 26px;font-size:17px;color:var(--ink2)}
.kr{display:flex;gap:10px;align-items:center}
.kr b{color:var(--ink)}
.ar{display:inline-block;width:46px;height:0;border-top:3px solid var(--c);position:relative;flex:none}
.ar:after{content:"";position:absolute;right:-2px;top:-7px;border:5.5px solid transparent;border-left:9px solid var(--c)}
.ar.dsh{border-top-style:dashed}
.kn{font:600 15px "IBM Plex Mono",monospace;color:#8a9099;background:#1f2328;border-radius:5px;padding:1px 7px}
.canvas{position:relative}
.canvas>div,.canvas>header{position:absolute}
.wires{position:absolute;left:0;top:0;pointer-events:none}
.wd{display:inline-block;width:9px;height:9px;border-radius:50%;margin-left:4px;flex:none}

.term{background:#1f2328;border-radius:16px;box-shadow:0 2px 0 rgba(0,0,0,.05)}
.tbar{height:46px;display:flex;align-items:center;gap:9px;padding:0 18px;border-bottom:1px solid #30363d}
.tbar i,.bbar i{width:13px;height:13px;border-radius:50%;display:inline-block}
.tbar span{margin-left:14px;font:500 15px "IBM Plex Mono",monospace;color:#9aa0a6}
.tnote{font:400 14px "IBM Plex Mono",monospace;color:#8a9099;white-space:nowrap}
.tgrp{font:500 14.5px "IBM Plex Mono",monospace;color:#6f7680;white-space:nowrap;letter-spacing:.02em}
.tagent{font:500 15.5px "IBM Plex Mono",monospace;color:#6ea8f0;white-space:nowrap}
.tline{font:400 17px "IBM Plex Mono",monospace;color:#d6dae0;white-space:nowrap}
.tline .pr{color:#6f7680;margin-right:10px}
.tline b{color:#ff8a52;font-weight:600}
.tline .ty{color:#c9cdd3}
.tcount{font:500 14px "IBM Plex Mono",monospace;color:#8a9099}

.hook{background:#e3f4ec;border:2px solid #14a06f;border-radius:14px}
.hh{display:flex;flex-direction:column;align-items:center;gap:2px;padding-top:10px}
.hh b{font:800 19px "Manrope";color:#0c6b49}
.hs{font-size:12.5px;line-height:1.25;color:#0c6b49;text-align:center;padding:4px 6px 0;font-weight:600}
.cap{position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:#fff;border:3px solid #14a06f;z-index:3}

.srv{background:#fbfbf9;border:2px solid #14a06f;border-radius:16px}
.sh{display:flex;gap:12px;align-items:center;padding:12px 16px 0}
.sh b{font:800 19px "Manrope";display:block}
.sh span{font-size:13.5px;color:var(--ink2);line-height:1.3;display:block}
.chip{background:#fff;border:1.5px solid #dcdcd6;border-left:5px solid var(--c);border-radius:9px;padding:4px 10px 0 10px;z-index:2}
.c1{display:flex;align-items:center;font-size:15.5px;line-height:19px;white-space:nowrap}
.c1 b{font-weight:800;margin-right:4px}
.c2{font-size:12.3px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:17px}
.mcp{background:#e7f0fb;border:2px solid #2a78d6;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px;color:#1d5aa6}
.mcp b{margin-right:6px}

.task{background:#fff;border:3px solid #0b0b0b;border-radius:20px;box-shadow:0 10px 0 #dfe1e4;padding:16px 26px}
.tk{display:flex;justify-content:space-between;font:500 14px "IBM Plex Mono",monospace;color:var(--muted)}
.tt{font:800 30px/1.1 "Manrope";letter-spacing:-.02em;margin-top:6px}
.st{display:flex;gap:6px;margin-top:10px}
.st span{font-size:13px;font-weight:600;padding:3px 10px;border-radius:20px;background:#f1f1ee;color:var(--muted)}
.st .on{background:#0b0b0b;color:#fff}
.st .dn{border:1.5px dashed #c3c2b7;background:none}
.part{background:#f7f7f4;border-radius:10px;display:flex;align-items:center;gap:10px;padding:0 14px;white-space:nowrap}
.part b{font-size:16.5px;font-weight:700}
.part span{font-size:13px;color:var(--ink2);overflow:hidden;text-overflow:ellipsis}
.pdots{display:flex;margin-left:-4px}
.mini{background:#fff;border:2px solid #0b0b0b;border-radius:10px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;box-shadow:0 4px 0 #dfe1e4}
.mini b{font-size:16px}
.mini span{font-size:13px;font-weight:600;color:var(--ink2);background:#f1f1ee;border-radius:20px;padding:2px 10px}

.brw{background:#fbfbf9;border:2px solid #c3c2b7;border-radius:16px;overflow:hidden}
.bbar{height:46px;display:flex;align-items:center;gap:9px;padding:0 18px;background:#e6e5df}
.url{margin-left:18px;background:#fff;border-radius:8px;padding:4px 16px;font:500 14px "IBM Plex Mono",monospace;color:var(--ink2);flex:1}
.tabs{display:flex;gap:4px;padding:8px 14px 0;border-bottom:1px solid #e0dfd8}
.tabs span{font-size:14px;font-weight:600;color:var(--ink2);padding:6px 11px;border-radius:8px 8px 0 0}
.tabs .on{background:#fff;color:var(--ink);box-shadow:0 -2px 0 #0b0b0b inset}
.pnl{background:#fff;border:1.5px solid #e0dfd8;border-radius:12px}
.pt{position:absolute;left:18px;top:50%;transform:translateY(-50%);width:270px;font:800 17px/1.25 "Manrope";color:var(--ink)}
.pl{background:#f7f7f4;border-radius:7px;font-size:14px;color:var(--ink2);display:flex;align-items:center;padding:0 12px;white-space:nowrap;overflow:hidden}
.bcol{background:#f3f3f0;border-radius:9px;padding:6px}
.bch{font:600 12px "IBM Plex Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.bc{background:#fff;border:1.5px solid #dcdcd6;border-radius:7px;font-size:13.5px;font-weight:600;padding:6px 9px;margin-bottom:5px}
.bc.hot{border:2px solid #0b0b0b}

.agent{background:#fbfbf9;border:2px solid #2a78d6;border-radius:18px;padding:18px 24px}
.ag{display:flex;gap:18px;align-items:center}
.ag b{font:800 26px "Manrope";color:#1d5aa6;display:block}
.ag span{display:block;font-size:15px;color:var(--ink2);line-height:1.45}
.agh{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#1d5aa6;margin:12px 0 6px}
.agl{display:grid;grid-template-columns:1fr 1fr;gap:3px 18px}
.agl span{font-size:15px;line-height:1.5;color:var(--ink)}
.agl span:before{content:"";display:inline-block;width:8px;height:8px;border-radius:2px;background:#2a78d6;margin-right:9px;transform:rotate(45deg) translateY(-2px)}

.repo,.out,.agmd{background:#fbfbf9;border:2px solid #c3c2b7;border-radius:18px;padding:16px 22px}
.agmd{border:2px dashed #14a06f}
.rh{display:flex;gap:12px;align-items:center}
.rh b{font:800 21px "Manrope"}
.rh span{font-size:15px;color:var(--ink2)}
.stage{background:#fff;border:1.5px solid #dcdcd6;border-radius:12px;padding:16px 18px}
.stage b{display:block;font-size:19px;font-weight:800}
.stage span{display:block;font-size:14.5px;color:var(--ink2);margin-top:4px}
.os{display:flex;gap:6px;margin-top:10px}
.os span{font:500 13px "IBM Plex Mono",monospace;background:#efeeea;border-radius:6px;padding:3px 8px;color:var(--ink)}
.ol{display:flex;flex-direction:column;gap:4px;margin-top:10px}
.ol span{font-size:15.5px;color:var(--ink2)}
.rnote{font:500 14px "IBM Plex Mono",monospace;color:var(--ink2);white-space:nowrap}

.lb,.pill,.tiny{position:absolute;white-space:nowrap;z-index:4}
.pill{font-size:14px;font-weight:700;color:var(--c);background:#fff;border:1.5px solid var(--c);border-radius:20px;padding:2px 11px}
.tiny{font-size:13px;font-weight:600;color:var(--c);background:var(--page);padding:0 4px;border-radius:4px}
"""
