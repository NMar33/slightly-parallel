"""The feature map's flow sheets: how a message becomes a record (tk_bba7c02c).

Three compositions of one picture, drawn from feature-map.json:

  river   left to right: who starts → what comes in → who does it → records,
          links between records on the right;
  star    the server in the centre, what comes in on the left, records fanned
          out on the right with their links;
  metro   records as stations on lines by topic, the streams that feed each
          station from above, links as transfers.

`spec(model)` turns the model into nodes, ribbons and links (30-day volumes);
`render(model, variant)` returns one HTML page with one `section.sheet#main`
that flow.js draws after the fonts load (it sets window.__drawn).

Colours by who acts, validated with the dataviz skill's validate_palette.js
on #fbfbf9 (all checks pass, every colour >= 3:1): operator #eb6834,
program (hook and server) #14a06f, agent #2a78d6. Records are ink.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

O, S, A = "#eb6834", "#14a06f", "#2a78d6"
BIG, CAP = 300, 120  # a stream above BIG is drawn at CAP with a break mark


SHORT = {
    "#architecture #page #map": "#architecture …",
    "#important #pin #carry": "#important …",
    "#sp #help #usage-price": "#sp #help …",
    "способы входа, остановки": "способы входа",
    "запись сообщений и ответов": "запись чата",
    "токены каждого ответа": "токены ответов",
    "строки и связи ядер": "связи ядер",
    "коммиты по участку чата": "коммиты по чату",
    "решение после работы": "решение сам",
    "стендап нового дня": "стендап сам",
}


def spec(model: dict) -> dict:
    c = model["counts"]
    L = {l["key"]: l for l in c["ledgers"]}
    T = c["typed"]["d30"]
    F = c.get("flow") or {}
    msgs = c["typed"]["messages"]

    def t(*names):
        return sum(T.get(n, 0) for n in names)

    def d(key):
        return L.get(key, {}).get("d30", 0)

    cl = F.get("core_links", {})
    cores_n = d("cores") + d("core_notes") + d("core_links")
    core_cmd = t("core-new", "core-note", "core", "core-off")
    marks_cmd = t("important", "important-agent", "important-task", "important-message", "pin", "carry", "carry-brief", "fork-later")
    ep_agent = d("entrypoint_ways") + d("entrypoint_stops") + d("entrypoint_shots")
    replies = F.get("replies", 0)
    log_n = msgs["d30"] + replies

    # Records: key, label, count shown, page, cluster
    records = [
        ("tasks", "Задачи", d("tasks"), "Доска", "tasks"),
        ("done", "Закрыто #done", d("done"), "Доска", "tasks"),
        ("evidence", "Доказательства", d("task_evidence"), "Доска", "tasks"),
        ("notes", "Заметки", d("notes"), "", "tasks"),
        ("commits", "Коммиты и файлы", F.get("commits", 0) + d("commit_links"), "Доска", "tasks"),
        ("cores", "Ядра", cores_n, "Архитектура", "cores"),
        ("decisions", "Решения", d("decisions"), "", "work"),
        ("standups", "Стендапы", d("standups"), "", "work"),
        ("scans", "Сканы, архитектура", d("scans") + d("files") + d("architecture"), "", "work"),
        ("visions", "Видения", d("visions"), "", "kept"),
        ("rules", "Правила", d("rules"), "", "kept"),
        ("problems", "Проблемы", d("problems"), "", "kept"),
        ("interp", "Толкования", F.get("interpreted", 0), "у записи", "kept"),
        ("entrypoints", "Точки входа", d("entrypoints") + ep_agent, "", "kept"),
        ("publish", "Публикации", d("publish") + d("publish_attachments"), "", "kept"),
        ("skills", "Скиллы", d("skills"), "", "kept"),
        ("prompts", "Промпты", d("prompts"), "", "kept"),
        ("artifacts", "Артефакты", d("artifacts"), "", "kept"),
        ("marks", "Звёзды и закрепы", d("marks"), "Важное", "marks"),
        ("undo", "Отменено #undo", d("undo"), "в архив", "marks"),
        ("reply", "Ответ в чате", 0, "без записи", "prog"),
        ("log", "Лог чата", log_n, "Чаты", "prog"),
        ("usage", "Расход токенов", F.get("usage_rows", 0), "", "prog"),
        ("time", "Время", d("time_entries"), "Таймер", "prog"),
        ("backups", "Резервные копии", F.get("backups", 0), "", "prog"),
    ]

    # Streams: id, label, count, who starts (o/a/s), who does it (srv/agent/hook), record
    streams = [
        ("now", "#now", t("now", "now-doing"), "o", "agent", "tasks"),
        ("now-col", "#now-todo …", t("now-todo", "now-to-do", "now-next", "now-backlog", "now-review", "now-parked", "now-done"), "o", "agent", "tasks"),
        ("task", "#task", t("task"), "o", "agent", "tasks"),
        ("done", "#done", t("done"), "o", "srv", "done"),
        ("evidence", "#evidence", t("evidence"), "o", "agent", "evidence"),
        ("core", "#core …", core_cmd, "o", "agent", "cores"),
        ("decision", "#decision", t("decision"), "o", "agent", "decisions"),
        ("standup", "#standup", t("standup"), "o", "agent", "standups"),
        ("scan", "#scan", t("scan"), "o", "agent", "scans"),
        ("arch", "#architecture #page #map", t("architecture", "page", "map"), "o", "agent", "scans"),
        ("vision", "#vision", t("vision"), "o", "srv", "visions"),
        ("rule", "#rule", t("rule"), "o", "srv", "rules"),
        ("problem", "#problem", t("problem", "problem solved"), "o", "srv", "problems"),
        ("entrypoint", "#entrypoint", t("entrypoint"), "o", "srv", "entrypoints"),
        ("publish", "#publish", t("publish"), "o", "srv", "publish"),
        ("skill", "#skill", t("skill"), "o", "srv", "skills"),
        ("prompt", "#prompt", t("prompt"), "o", "srv", "prompts"),
        ("artifact", "#artifact", t("artifact"), "o", "srv", "artifacts"),
        ("important", "#important #pin #carry", marks_cmd, "o", "srv", "marks"),
        ("undo", "#undo", t("undo", "undo-yes"), "o", "srv", "undo"),
        ("hookreply", "#usage #mute", t("usage", "usage-on", "usage-off", "usage-warnings-on", "usage-warnings-off", "mute"), "o", "hook", "reply"),
        ("agentreply", "#sp #help #usage-price", t("sp", "help", "usage-price"), "o", "agent", "reply"),
        # the operator by hand, on the pages
        ("board", "задача на доске", c["tasks"]["origins30"].get("доска (вручную)", 0), "o", "srv", "tasks"),
        ("buttons", "кнопки ★ и закреп", max(d("marks") - marks_cmd, 0), "o", "srv", "marks"),
        # the agent on its own
        ("a-dec", "решение после работы", max(d("decisions") - t("decision"), 0), "a", "agent", "decisions"),
        ("a-std", "стендап нового дня", max(d("standups") - t("standup"), 0), "a", "agent", "standups"),
        ("a-note", "заметка", d("notes"), "a", "agent", "notes"),
        ("a-core", "строки и связи ядер", max(cores_n - core_cmd, 0), "a", "agent", "cores"),
        ("a-interp", "толкование слов", F.get("interpreted", 0), "a", "agent", "interp"),
        ("a-ep", "способы входа, остановки", ep_agent, "a", "agent", "entrypoints"),
        ("a-pub", "вложения публикаций", d("publish_attachments"), "a", "agent", "publish"),
        ("a-commit", "привязка коммитов", d("commit_links"), "a", "agent", "commits"),
        # the program on its own
        ("s-log", "запись сообщений и ответов", log_n, "s", "hook", "log"),
        ("s-usage", "токены каждого ответа", F.get("usage_rows", 0), "s", "hook", "usage"),
        ("s-commit", "коммиты по участку чата", F.get("commits", 0), "s", "srv", "commits"),
        ("s-time", "авто-таймер", d("time_entries"), "s", "srv", "time"),
        ("s-backup", "резервные копии", F.get("backups", 0), "s", "srv", "backups"),
    ]

    links = [
        ("tasks", "done", d("done"), "участок чата"),
        ("tasks", "commits", F.get("commits", 0) + d("commit_links"), "коммиты задачи"),
        ("tasks", "notes", F.get("notes_on_task", 0), "заметки задачи"),
        ("tasks", "evidence", d("task_evidence"), "доказательства"),
        ("cores", "tasks", cl.get("task", 0), "ядро ↔ задача"),
        ("cores", "commits", cl.get("anchor", 0), "ядро ↔ файлы"),
        ("interp", "visions", F.get("interpreted", 0), "толкование слов"),
        ("log", "visions", d("visions") + d("rules") + d("problems"), "слова из лога"),
        ("marks", "log", t("carry", "carry-brief"), "#carry: после сжатия"),
    ]

    who_of_actor = {"agent": "a", "srv": "s", "hook": "s"}
    return {
        "today": model["today"],
        "colors": {"o": O, "s": S, "a": A},
        "big": BIG, "cap": CAP,
        "messages": msgs["d30"],
        "with_command": msgs["with_command30"],
        "replies": replies,
        "server_wrote_card": c["tasks"].get("server_wrote_card", 0),
        "scan_typed": t("scan"),
        "scans_made": d("scans"),
        "commits": F.get("commits", 0),
        "records": [dict(id=k, label=l, n=n, page=p, cluster=g) for k, l, n, p, g in records],
        "streams": [dict(id=i, label=l, short=SHORT.get(l, l), n=n, who=w, actor=a, rec=r, actor_who=who_of_actor[a])
                    for i, l, n, w, a, r in streams],
        "links": [dict(a=a, b=b, n=n, label=l) for a, b, n, l in links],
    }


CSS = """
:root{--page:#eef0f2;--surface:#fbfbf9;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e6e5df;--axis:#c3c2b7;--well:#f1f1ee;
--o:#eb6834;--s:#14a06f;--a:#2a78d6}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--page);color:var(--ink)}
body{width:1560px;font-family:"Manrope",system-ui,sans-serif}
.sheet{width:1560px;padding:48px 52px 40px;background:var(--page)}
header{display:grid;grid-template-columns:1fr 430px;gap:40px;align-items:end}
.kicker{font:500 14px "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--ink2);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tag{display:inline-flex;border:1.5px solid var(--ink);border-radius:6px;padding:4px 9px;color:var(--ink);font-weight:600}
h1{font:800 40px/1.1 "Manrope",sans-serif;letter-spacing:-.03em;margin:16px 0 10px}
.lede{font-size:17px;line-height:1.5;color:var(--ink2)}
.lede b{color:var(--ink)}
.key{background:var(--surface);border-radius:14px;padding:14px 18px;font-size:14px;color:var(--ink2)}
.kh{font:600 12px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.kr{display:grid;grid-template-columns:34px 1fr;gap:10px;align-items:center;line-height:1.75}
.sw{height:12px;border-radius:3px}
.p{background:var(--surface);border-radius:14px;padding:20px 22px;margin-top:22px}
.cos{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}
.co{background:var(--surface);border-radius:12px;padding:14px 16px}
.cv{font:600 17px "IBM Plex Mono",monospace;white-space:nowrap;margin-bottom:4px}
.ct{font-size:14px;line-height:1.4;color:var(--ink2)}
.foot{margin-top:16px;font:13.5px/1.5 "Manrope";color:var(--muted)}
svg text{font-family:"Manrope",sans-serif}
svg .m{font-family:"IBM Plex Mono",monospace}
"""

TITLES = {
    "river": ("Как сообщение становится записью",
              "Слева — кто начинает: <b>оператор</b> командой или руками, <b>агент</b> и <b>программа</b> сами. "
              "В середине — кто делает работу. Справа — записи, на какой странице они видны, и как записи связаны между собой."),
    "star": ("Всё проходит через сервер",
             "Слева приходят команды оператора и то, что агент и программа делают сами. Сервер в центре хранит слова, "
             "двигает задачи и подписывает записи агента. Справа — записи и связи между ними."),
    "metro": ("Записи и связи между ними",
              "Круг — вид записи, его размер — сколько их пришло за 30 дней. Кольцо — кто начал: <b>оператор</b>, "
              "<b>агент</b> или <b>программа</b>. Под кругом — что в него вошло. Серые линии — связи между записями."),
}


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def tiles(sp: dict) -> str:
    items = [
        (f"{fmt(sp['with_command'])} из {fmt(sp['messages'])}", "сообщений оператора за 30 дней несли команду; остальные хук только записал"),
        (f"{fmt(sp['server_wrote_card'])}", "карточек #now сервер записал сам, когда агент не записал (за всё время)"),
        (f"{fmt(sp['scan_typed'])} → {fmt(sp['scans_made'])}", "#scan в сообщениях → новых сканов; в счёт идут и упоминания в ссылках и коде"),
        (f"{fmt(sp['commits'])}", "коммитов программа сама привязала к задачам по участку чата"),
    ]
    return '<div class="cos">' + "".join(f'<div class="co"><div class="cv">{html.escape(a)}</div><div class="ct">{html.escape(b)}</div></div>' for a, b in items) + "</div>"


def render(model: dict, variant: str) -> str:
    sp = spec(model)
    title, lede = TITLES[variant]
    c = sp["colors"]
    key = f"""<div class="key"><div class="kh">кто делает</div>
<div class="kr"><div class="sw" style="background:{c['o']}"></div><div><b style="color:var(--ink)">Оператор</b> — команда в сообщении или кнопка</div></div>
<div class="kr"><div class="sw" style="background:{c['s']}"></div><div><b style="color:var(--ink)">Программа</b> — хук и сервер</div></div>
<div class="kr"><div class="sw" style="background:{c['a']}"></div><div><b style="color:var(--ink)">Агент</b> — пишет через MCP</div></div>
<div class="kr"><div class="sw" style="background:#3d3c39"></div><div><b style="color:var(--ink)">Запись</b> · толщина — сколько за 30 дней</div></div></div>"""
    js = (HERE / "flow.js").read_text(encoding="utf-8")
    day = model["today"]
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1560">
<title>Карта потоков</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<section class="sheet" id="main">
<header><div><div class="kicker"><span class="tag">Slightly Parallel</span> как устроен · последние 30 дней · {day}</div>
<h1>{title}</h1><p class="lede">{lede}</p></div>{key}</header>
<div class="p"><svg id="fig"></svg></div>
{tiles(sp)}
<div class="foot">Все проекты, чаты помощников не в счёт. Команда считается раз на сообщение, вместе с упоминаниями в ссылках и коде. Поток больше {BIG} нарисован короче, с разрывом. Подробно по каждой команде — листы-таблицы.</div>
</section>
<script>window.__drawn=false;const SPEC={json.dumps(sp, ensure_ascii=False)};const VARIANT={json.dumps(variant)};
{js}
document.fonts.ready.then(()=>{{draw(SPEC,VARIANT);window.__drawn=true}});</script>
</body></html>"""
