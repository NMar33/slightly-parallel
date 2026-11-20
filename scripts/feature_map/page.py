"""The feature map's pages: variant A (rows) and variant B (cards).

Each page is a column of `.sheet` sections, 1560 css px wide; the renderer
takes one PNG per sheet. Style family e6-dashboard: Manrope + IBM Plex Mono,
light cards. Colours by who acts, the same everywhere:
operator #eb6834, program (server and hook) #1baf7a, agent #2a78d6
(dataviz validate_palette.js: all checks pass on #fbfbf9; the green is under
3:1 against the surface, so a colour is never the only label: every mark
carries its letter О / П / А and text stays in ink).
"""

from __future__ import annotations

import html

WHO = {"o": ("О", "Оператор", "#eb6834"), "s": ("П", "Программа", "#1baf7a"), "a": ("А", "Агент", "#2a78d6")}

CSS = """
:root{--page:#eef0f2;--surface:#fbfbf9;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e6e5df;--axis:#c3c2b7;
--o:#eb6834;--s:#1baf7a;--a:#2a78d6;--ot:#fcefe8;--st:#e7f5ef;--at:#eaf1fb}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--page);color:var(--ink)}
body{width:1560px;font-family:"Manrope",system-ui,sans-serif}
.sheet{width:1560px;padding:44px 52px 40px;background:var(--page)}
.mono{font-family:"IBM Plex Mono",monospace}
header{display:grid;grid-template-columns:1fr 470px;gap:36px;align-items:end;margin-bottom:22px}
.kicker{font:500 13px "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--ink2);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tag{display:inline-flex;border:1.5px solid var(--ink);border-radius:6px;padding:3px 8px;color:var(--ink);font-weight:600}
h1{font:800 40px/1.08 "Manrope",sans-serif;letter-spacing:-.03em;margin:14px 0 8px}
.lede{font-size:16px;line-height:1.5;color:var(--ink2)}
.lede b{color:var(--ink)}
.key{background:var(--surface);border-radius:14px;padding:14px 16px;font-size:13.5px}
.kh{font:600 11.5px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.kr{display:grid;grid-template-columns:22px 108px 1fr;gap:8px;align-items:center;line-height:1.8}
.kr .v{color:var(--ink2)}
.lt{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:5px;color:#fff;font:700 12px "Manrope"}
.lt.o{background:var(--o)}.lt.s{background:var(--s)}.lt.a{background:var(--a)}
.lt.sm{width:16px;height:16px;font-size:10px;border-radius:4px}
.p{background:var(--surface);border-radius:14px;padding:18px 20px 16px}
.ph{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.ph h3{font:700 18px "Manrope";letter-spacing:-.01em}
.ph .u{font:500 12.5px "IBM Plex Mono",monospace;color:var(--muted);white-space:nowrap}
.pq{font-size:13.5px;color:var(--ink2);margin:3px 0 10px;line-height:1.4}
.pq b{color:var(--ink)}
/* flow */
.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin-bottom:16px}
.fb{position:relative;background:var(--surface);border-radius:12px;padding:12px 14px;margin-right:22px;border-top:4px solid var(--axis)}
.fb:last-child{margin-right:0}
.fb:not(:last-child)::after{content:"→";position:absolute;right:-19px;top:34%;font:700 18px "Manrope";color:var(--muted)}
.fb.o{border-top-color:var(--o)}.fb.s{border-top-color:var(--s)}.fb.a{border-top-color:var(--a)}
.fb h4{font:700 14.5px "Manrope";display:flex;gap:6px;align-items:center}
.fb p{font-size:12.5px;color:var(--ink2);line-height:1.4;margin-top:4px}
.fb .n{font:600 12px "IBM Plex Mono",monospace;color:var(--ink);margin-top:6px}
/* rows (variant A) */
.grp{margin-top:14px}
.grp h2{font:800 20px "Manrope";letter-spacing:-.01em;margin:0 0 6px 2px;display:flex;gap:10px;align-items:baseline}
.grp h2 span{font:500 12.5px "IBM Plex Mono",monospace;color:var(--muted)}
.hd,.row{display:grid;grid-template-columns:158px 210px 1fr 1fr 1fr 232px 112px;gap:0}
.hd{font:600 11px "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:0 0 4px}
.hd>div{padding:0 10px}
.row{background:var(--surface);border-radius:10px;margin-bottom:5px}
.row>div{padding:9px 10px;font-size:12.5px;line-height:1.38;color:var(--ink2);border-left:1px solid var(--grid)}
.row>div:first-child{border-left:0}
.row .who{border-left:0;border-top:3px solid transparent}
.row .who.o{background:var(--ot);border-top-color:var(--o)}
.row .who.s{background:var(--st);border-top-color:var(--s)}
.row .who.a{background:var(--at);border-top-color:var(--a)}
.cmd{font:700 13.5px "IBM Plex Mono",monospace;color:var(--ink);display:flex;flex-wrap:wrap;gap:2px 7px}
.cmd .x{font-weight:500;color:var(--ink2);font-size:12px}
.cnt{font:500 11.5px "IBM Plex Mono",monospace;color:var(--muted);margin-top:5px;line-height:1.45}
.cnt b{color:var(--ink);font-weight:600}
.does{color:var(--ink)!important}
.rec{font:600 12px "IBM Plex Mono",monospace;color:var(--ink);margin-bottom:4px}
.fl{display:flex;flex-wrap:wrap;gap:3px}
.f{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--grid);border-radius:5px;padding:1px 5px 1px 3px;font:500 11.5px "IBM Plex Mono",monospace;color:var(--ink);background:#fff}
.pg{color:var(--ink)!important;font-weight:600}
.pg .mono{display:block;font-size:11px;color:var(--muted);font-weight:400}
/* cards (variant B) */
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.card{background:var(--surface);border-radius:14px;padding:14px 16px 12px;display:flex;flex-direction:column;gap:7px}
.card .top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.card .big{font:800 26px "Manrope";letter-spacing:-.02em;line-height:1;text-align:right}
.card .big small{display:block;font:500 11px "IBM Plex Mono",monospace;color:var(--muted);letter-spacing:0}
.card .d{font-size:13.5px;line-height:1.4;color:var(--ink);font-weight:600}
.lane{display:grid;grid-template-columns:20px 1fr;gap:8px;font-size:12.5px;line-height:1.38;color:var(--ink2);padding:6px 8px;border-radius:8px}
.lane.o{background:var(--ot)}.lane.s{background:var(--st)}.lane.a{background:var(--at)}
.card .foot{display:flex;justify-content:space-between;gap:8px;align-items:flex-end;border-top:1px solid var(--grid);padding-top:7px;margin-top:auto}
.card .foot .pgn{font:600 12px "Manrope";text-align:right;white-space:nowrap}
/* blocks */
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}
.three{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:14px;margin-top:14px}
.li{display:grid;grid-template-columns:1fr auto;gap:10px;padding:6px 0;border-top:1px solid var(--grid);font-size:13px;line-height:1.38}
.li:first-of-type{border-top:0}
.li .t{color:var(--ink)}
.li .s{font:500 10.5px "IBM Plex Mono",monospace;color:var(--muted);text-align:right;max-width:330px}
.li .who2{font:600 10.5px "IBM Plex Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
/* bars */
.r{display:grid;grid-template-columns:172px 1fr 60px 58px;gap:8px;align-items:center;height:24px}
.r .l{font-size:12.5px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.r .tr{position:relative;height:24px;display:flex;align-items:center}
.r .seg{height:12px;margin-right:2px}
.r .seg:last-child{border-radius:0 4px 4px 0;margin-right:0}
.r .v{text-align:right;font:600 12.5px "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.r .v2{text-align:right;font:500 12px "IBM Plex Mono",monospace;color:var(--muted);font-variant-numeric:tabular-nums}
.rh{display:grid;grid-template-columns:172px 1fr 60px 58px;gap:8px;font:600 10.5px "IBM Plex Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px}
.rh div:nth-child(3),.rh div:nth-child(4){text-align:right}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.chip{font:500 11.5px "IBM Plex Mono",monospace;border:1px solid var(--grid);background:#fff;border-radius:5px;padding:1px 6px;color:var(--ink)}
.sub{font:700 13.5px "Manrope";margin:12px 0 4px}
.warn{font-size:12.5px;color:var(--ink2);line-height:1.45}
.warn li{margin-left:16px}
.find{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
.find div{border-radius:10px;background:var(--surface);padding:12px 14px;font-size:13px;line-height:1.42;color:var(--ink2)}
.find b{display:block;font:800 22px 'Manrope';color:var(--ink);margin-bottom:2px}
"""


def e(s) -> str:
    return html.escape(str(s or ""))


def lt(w: str, small: bool = False) -> str:
    return f'<span class="lt {w}{" sm" if small else ""}">{WHO[w][0]}</span>'


def head(model: dict, n: int, total: int, title: str, lede: str) -> str:
    d = model["today"]
    day = f"{d[8:10]}.{d[5:7]}.{d[0:4]}"
    return f"""<header><div>
<div class="kicker"><span class="tag">Slightly Parallel</span><span>КАРТА ФУНКЦИЙ · {day} · коммит {e(model['commit'])} · лист {n}/{total}</span></div>
<h1>{title}</h1><p class="lede">{lede}</p></div>
<div class="key"><div class="kh">Кто делает</div>
<div class="kr">{lt('o')}<b>Оператор</b><span class="v">пишет сообщение, решает, двигает</span></div>
<div class="kr">{lt('s')}<b>Программа</b><span class="v">сервер и хук, сами, без агента</span></div>
<div class="kr">{lt('a')}<b>Агент</b><span class="v">пишет через MCP-инструменты; папку артефакта — сам</span></div>
</div></header>"""


def fields_html(card: dict) -> str:
    out = []
    for f, w in card.get("fields") or []:
        out.append(f'<span class="f">{lt(w, True)}{e(f)}</span>')
    return '<div class="fl">' + "".join(out) + "</div>"


def counts_line(card: dict) -> str:
    t = card["typed"]
    s = f"30 дн: <b>{t['d30']}</b> · всего {t['total']}"
    return s


def record_line(card: dict, model: dict) -> str:
    rc = card.get("record_counts")
    if not card.get("record"):
        return '<div class="rec">— запись не создаётся</div>'
    ru = next((l["ru"] for l in model["counts"]["ledgers"] if l["key"] == card["record"]), card["record"])
    n = ""
    special = _task_count(card, model)
    if special is not None:
        n = f" · {special[0]} ({special[1]} за 30 дн)"
    elif rc:
        n = f" · {rc['total']} ({rc['d30']} за 30 дн)"
    return f'<div class="rec">{e(ru)}{n}</div>'


def _task_count(card, model):
    o = model["counts"]["tasks"]["origins"]
    o30 = model["counts"]["tasks"]["origins30"]
    key = {"now": "#now", "now-col": "#now-<колонка>", "task": "#task (агент)"}.get(card["id"])
    if key:
        return o.get(key, 0), o30.get(key, 0)
    return None


def page_cell(card: dict) -> str:
    if not card.get("page"):
        return '<div class="pg">—</div>'
    return f'<div class="pg">{e(card["page_ru"] or card["page"])}<span class="mono">{e(card["page"])}</span></div>'


def cmd_chips(card: dict) -> str:
    cm = card["cmds"]
    first = f"#{cm[0]}"
    rest = ""
    if len(cm) > 1:
        tails = [c.replace(cm[0].split("-")[0], "", 1) if c.startswith(cm[0].split("-")[0] + "-") else c for c in cm[1:]]
        rest = " ".join(f'<span class="x">{"#" + c if not t.startswith("-") else t}</span>' for c, t in zip(cm[1:], tails))
    return f'<div class="cmd">{e(first)} {rest}</div>'


def rows_group(model: dict, gid: str) -> str:
    cards = [c for c in model["cards"] if c["group"] == gid]
    out = [f'<div class="grp"><h2>{e(model["groups"][gid])} <span>{len(cards)} {"команда" if len(cards)==1 else "команды" if len(cards)<5 else "команд"}</span></h2>']
    out.append('<div class="hd"><div>Команда</div><div>Что делает</div><div>Оператор</div><div>Программа</div>'
               '<div>Агент</div><div>Запись и поля</div><div>Где видно</div></div>')
    for c in cards:
        out.append(f"""<div class="row">
<div>{cmd_chips(c)}<div class="cnt">{counts_line(c)}</div></div>
<div class="does">{e(c['does'])}</div>
<div class="who o">{e(c['operator'])}</div>
<div class="who s">{e(c['server'])}</div>
<div class="who a">{e(c['agent'])}</div>
<div>{record_line(c, model)}{fields_html(c)}</div>
{page_cell(c)}
</div>""")
    out.append("</div>")
    return "".join(out)


def cards_group(model: dict, gid: str) -> str:
    cards = [c for c in model["cards"] if c["group"] == gid]
    out = [f'<div class="grp"><h2>{e(model["groups"][gid])} <span>{len(cards)}</span></h2><div class="cards">']
    for c in cards:
        t = c["typed"]
        out.append(f"""<div class="card">
<div class="top">{cmd_chips(c)}<div class="big">{t['d30']}<small>раз за 30 дн</small></div></div>
<div class="d">{e(c['does'])}</div>
<div class="lane o">{lt('o', True)}<span>{e(c['operator'])}</span></div>
<div class="lane s">{lt('s', True)}<span>{e(c['server'])}</span></div>
<div class="lane a">{lt('a', True)}<span>{e(c['agent'])}</span></div>
<div>{record_line(c, model)}{fields_html(c)}</div>
<div class="foot"><span class="cnt">всего в сообщениях: <b>{t['total']}</b></span><span class="pgn">{e(c['page_ru'] or '—')}</span></div>
</div>""")
    out.append("</div></div>")
    return "".join(out)


def flow(model: dict) -> str:
    c = model["counts"]
    ty = c["typed"]
    kept = sum(l["by"]["o"] for l in c["ledgers"] if l["key"] in ("visions", "rules", "problems", "entrypoints", "publish", "prompts", "skills", "artifacts"))
    agent_rows = sum(l["by"]["a"] for l in c["ledgers"])
    sidebar = sum(1 for p in model["pages"] if p["in_sidebar"])
    boxes = [
        ("o", "Сообщение", "Оператор пишет в чат. Тег в любом месте — команда.",
         f"{ty['messages']['with_command30']} из {ty['messages']['d30']} сообщений за 30 дн с командой"),
        ("s", "Хук", "Записывает сообщение и ответ в лог чата, узнаёт тег, даёт агенту подсказку.",
         f"{len(model['hook']['commands']) + len(model['hook']['kept_tags'])} тегов в таблице хука"),
        ("s", "Сервер", "Хранит сообщение с тегом, ставит метку, двигает задачу. Проверяет каждую запись агента.",
         f"{kept} сохранённых сообщений всего"),
        ("a", "Агент", "Дописывает свою часть: заголовок, толкование, отчёт. Только MCP.",
         f"{len(model['tools'])} MCP-инструментов"),
        ("", "Запись", "Строка в реестре CSV каталога данных; подпись, проект и время ставит сервер.",
         f"{agent_rows} строк от агентов всего"),
        ("", "Страница", "Оператор читает и правит на странице дашборда.",
         f"{sidebar} страниц в боковой панели"),
    ]
    out = ['<div class="flow">']
    for w, h, p, n in boxes:
        out.append(f'<div class="fb {w}"><h4>{lt(w, True) if w else ""}{e(h)}</h4><p>{e(p)}</p><div class="n">{e(n)}</div></div>')
    out.append("</div>")
    return "".join(out)


def own_blocks(model: dict) -> str:
    a = "".join(f'<div class="li"><span class="t">{e(i["text"])}</span><span class="s">{e(", ".join(i.get("tools") or []))}</span></div>'
                for i in model["agent_own"])
    s = "".join(f'<div class="li"><span class="t">{e(i["text"])}</span><span class="s"><span class="who2">{e(i["who"])}</span> · {e(i["src"])}</span></div>'
                for i in model["server_own"])
    return f"""<div class="two">
<div class="p" style="border-top:4px solid var(--a)"><div class="ph"><h3>{lt('a', True)} Агент сам, без команды</h3><span class="u">{len(model['agent_own'])} пунктов</span></div>
<p class="pq">Пишет по своему решению или по подсказке хука. Статус задачи не меняет.</p>{a}</div>
<div class="p" style="border-top:4px solid var(--s)"><div class="ph"><h3>{lt('s', True)} Программа сама</h3><span class="u">{len(model['server_own'])} пунктов</span></div>
<p class="pq">Без команды и без агента. «хук» — скрипт в чате агента, «сервер» — процесс дашборда.</p>{s}</div>
</div>"""


def bar_rows(items: list[tuple[str, dict, int, int]], maxv: int, unit2: str = "") -> str:
    out = []
    for label, segs, v, v2 in items:
        seg = ""
        for w in ("o", "s", "a"):
            n = segs.get(w, 0)
            if n:
                seg += f'<div class="seg" style="width:{max(2, n / maxv * 100):.2f}%;background:var(--{w})" title="{WHO[w][1]}: {n}"></div>'
        out.append(f'<div class="r"><div class="l">{e(label)}</div><div class="tr">{seg}</div><div class="v">{v}</div><div class="v2">{v2}{unit2}</div></div>')
    return "".join(out)


TR_FIELDS = {
    "assignee": "исполнитель", "auto_manage": "авто-перенос", "due_date": "срок", "effort": "усилие",
    "evidence_prompt": "что доказать", "evidence_required": "нужны доказательства", "impact": "влияние",
    "lane": "полоса", "novelty": "новизна", "position": "место в колонке", "priority": "приоритет",
    "projects": "проекты карточки", "remember": "звезда", "resurface_every_days": "повтор, дней",
    "resurface_on": "поднять в дату", "resurface_to": "поднять в колонку", "sprint_id": "спринт",
    "stack_id": "стопка", "tokens": "токены",
}
TR_LENS = {"publish": "публикация", "rule": "правило", "sprint": "спринт", "time_entry": "запись времени",
           "prompt_run": "оценка промпта", "prompt": "промпт", "skill": "скилл", "artifact": "артефакт",
           "note": "заметка (только note_write)", "entrypoint": "точка входа"}


def numbers_sheet(model: dict, n: int, total: int) -> str:
    c = model["counts"]
    led = sorted(c["ledgers"], key=lambda l: -l["total"])
    mx = max(l["total"] for l in led) or 1
    led_rows = bar_rows([(l["ru"], l["by"], l["total"], l["d30"]) for l in led], mx)
    ty = c["typed"]
    t30_all = sorted(ty["d30"].items(), key=lambda kv: -kv[1])
    t30 = t30_all[:20]
    rest = t30_all[20:]
    mx2 = max([v for _, v in t30] or [1])
    typed_rows = bar_rows([("#" + k, {"o": v}, v, ty["total"].get(k, 0)) for k, v in t30], mx2)
    tk = c["tasks"]
    org_who = {"#task (агент)": "a"}
    mx3 = max(tk["origins"].values() or [1])
    org_rows = bar_rows([(k, {org_who.get(k, "o"): v}, v, tk["origins30"].get(k, 0)) for k, v in tk["origins"].items()], mx3)
    part_rows = bar_rows([(k, {"s" if k == "закрыта #done" else "a": v}, v, f"{v * 100 // max(1, tk['total'])}%") for k, v in tk["parts"].items()], tk["total"])
    op = model["operator"]
    fields = "".join(f'<span class="chip">{e(TR_FIELDS.get(f, f))}</span>' for f in op["task_fields"])
    lenses = "".join(f'<span class="chip">{e(TR_LENS.get(k, k))}</span>' for k in list(op["lenses"]) + list(op["agent_create_refused"]))
    acts = "".join(f'<span class="chip">{e(a["what"])}</span>' for a in op["acts"])
    # findings
    lmap = {l["key"]: l for l in c["ledgers"]}
    kh30 = sum(l["kept_from_helper"] for l in c["ledgers"])
    arch = sum(l["archived"] for l in c["ledgers"] if l["key"] in ("visions", "rules", "problems", "entrypoints", "publish", "prompts", "skills", "artifacts"))
    arch_h = sum(l["archived_from_helper"] for l in c["ledgers"])
    scans30 = lmap.get("scans", {}).get("d30", 0)
    typed_scan = ty["d30"].get("scan", 0)
    srv = tk["server_wrote_card"]
    nowall = tk["origins"].get("#now", 0) + tk["origins"].get("#now-<колонка>", 0)
    hp = ty.get("helper_d30", {})
    hp_s = ", ".join(f"#{k} {v}" for k, v in list(hp.items())[:5]) or "нет"
    warns = "".join(f"<li>{e(w)}</li>" for w in model["warnings"]) or "<li>нет</li>"
    return f"""<section class="sheet" id="{'n'}">
{head(model, n, total, "Что происходит на самом деле", f"Цифры из каталога данных на {e(model['today'])}: кто пишет записи, какие команды оператор набирает, откуда задачи. <b>Только чтение</b>; чаты помощников не считаются сообщениями оператора.")}
<div class="find">
<div><b>{arch_h} из {arch}</b>сохранённых тегом сообщений в архиве — из чатов помощников (Codex): тег в задании агента сервер сохранил как слова оператора. Не в архиве таких сейчас: {kh30}.</div>
<div><b>{typed_scan} → {scans30}</b>сообщений с #scan за 30 дн и новых сканов. Все 8 — упоминания: #scan в ссылке (…/app/#scan) и в коде (`#scan`) хук читает как команду.</div>
<div><b>{srv} из {nowall}</b>задач с #now и #now-&lt;колонка&gt; записал сервер (по записи в истории задачи): агент не вызвал write_entry, карточку сделала программа.</div>
</div>
<div class="two" style="grid-template-columns:1.1fr 1fr">
<div class="p"><div class="ph"><h3>Кто пишет записи</h3><span class="u">всего · за 30 дн</span></div>
<p class="pq">Строки реестров без архива, демо и снятых меток. Цвет — кто создал строку: сохранённое тегом сообщение — оператор, остальное — по agent_id / actor / author. Правки после создания не считаются. 30 дн — по дате создания.</p>
<div class="rh"><div>реестр</div><div>{lt('o',True)} {lt('s',True)} {lt('a',True)}</div><div>всего</div><div>30 дн</div></div>{led_rows}</div>
<div>
<div class="p"><div class="ph"><h3>{lt('o',True)} Команды в сообщениях оператора</h3><span class="u">30 дн · всего</span></div>
<p class="pq">{ty['messages']['with_command30']} из {ty['messages']['d30']} сообщений за 30 дн, {ty['chats']} чатов; {ty['helper_chats_skipped']} чатов помощников не в счёте. Счёт — как читает хук: команда раз на сообщение, упоминание в ссылке и коде тоже считается; это не выполненные команды.</p>
<div class="rh"><div>команда</div><div></div><div>30 дн</div><div>всего</div></div>{typed_rows}
<p class="pq" style="margin-top:8px">Ещё {len(rest)} команд по 1–{max([v for _, v in rest] or [0])} раза: {e(", ".join("#" + k for k, _ in rest))}.</p>
<p class="pq">В чатах помощников за 30 дн хук видит: {e(hp_s)}.</p></div>
</div></div>
<div class="three">
<div class="p"><div class="ph"><h3>Откуда задачи</h3><span class="u">всего · 30 дн</span></div>
<p class="pq">{tk['total']} задач без архива ({tk.get('archived', 0)} в архиве). Источник — по событию started/filed с тегом; без него — по agent_id карточки.</p>
<div class="rh"><div>источник</div><div></div><div>всего</div><div>30 дн</div></div>{org_rows}
<div class="sub">Что добавлено к задачам</div>
<div class="rh"><div></div><div></div><div>задач</div><div>доля</div></div>{part_rows}</div>
<div class="p" style="border-top:4px solid var(--o)"><div class="ph"><h3>{lt('o',True)} Только оператор</h3><span class="u">из кода</span></div>
<p class="pq">Поля задачи, которые агенту ставить нельзя (сервер отказывает по имени). Статус — тоже оператора, кроме авто-переноса и сброса своей карточки.</p>
<div class="chips">{fields}</div>
<div class="sub">Линзы, которые агент не создаёт через write_entry</div><p class="pq">Для части есть свой инструмент: заметка — note_write, скилл — skill_draft, артефакт — artifact_write, публикация — publish_write, правило и точка входа — interpret.</p><div class="chips">{lenses}</div></div>
<div class="p" style="border-top:4px solid var(--o)"><div class="ph"><h3>Действия только на странице</h3><span class="u">{len(op['acts'])} мест</span></div>
<p class="pq">Каждый вызов operator_only в маршрутах сервера; текст — как в коде. Агенту сервер отказывает.</p><div class="chips">{acts}</div>
<div class="sub">Предупреждения сборки</div><ul class="warn">{warns}</ul></div>
</div>
</section>"""


def render(model: dict, variant: str) -> str:
    groups = list(model["groups"])
    if variant == "a":
        sheets_groups = [["tasks", "work"], ["keep", "cores"], ["marks", "undo", "usage", "ask"]]
        body_of = rows_group
    else:
        sheets_groups = [["tasks", "work"], ["keep"], ["cores", "marks"], ["undo", "usage", "ask"]]
        body_of = cards_group
    for g in groups:
        assert any(g in s for s in sheets_groups), g
    total = len(sheets_groups) + 1
    titles = (["Команды: задачи и запись работы", "Команды: сохранить сообщение, ядра", "Команды: метки, отмена, токены, справка"]
              if variant == "a" else
              ["Команды: задачи и запись работы", "Команды: сохранить сообщение", "Команды: ядра и метки", "Команды: отмена, токены, справка"])
    ledes_a = [
        "Каждая команда — что делает и кто какую часть делает. Поля записи помечены владельцем. Число в первой колонке — сколько раз хук увидел команду в сообщениях оператора.",
        "Сообщение с тегом хранит сервер дословно; агент дописывает толкование или запись рядом. Слова оператора не переписываются.",
        "Метки ставит сервер по тегу или оператор кнопкой. Ниже — что агент и программа делают без команды.",
    ]
    ledes = ledes_a if variant == "a" else [ledes_a[0], ledes_a[1], "Ядро — часть программы, которую оператор держит в виду. Метки ставит сервер по тегу или оператор кнопкой.", "Ниже — что агент и программа делают без команды."]
    sheets = []
    for i, gs in enumerate(sheets_groups):
        body = "".join(body_of(model, g) for g in gs)
        extra = flow(model) if i == 0 else ""
        tail = own_blocks(model) if i == len(sheets_groups) - 1 else ""
        sheets.append(f'<section class="sheet" id="s{i + 1}">{head(model, i + 1, total, titles[i], ledes[i])}{extra}{body}{tail}</section>')
    sheets.append(numbers_sheet(model, total, total).replace('id="n"', f'id="s{total}"'))
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1560">
<title>Карта функций</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>{''.join(sheets)}</body></html>"""
