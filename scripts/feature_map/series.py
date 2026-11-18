"""A series of five drawn sheets that explain Slightly Parallel (tk_bba7c02c).

1  «Архитектура Slightly Parallel» — four levels top to bottom: interfaces
   (terminal, web UI, entry points), the SP service (hook, server, MCP tools,
   agents), subsystems (the project's cores, and the subsystems in the code
   not set up as cores, dashed), storage and CI (data root, git and CI,
   AGENTS.md and skills). On the right, one column per command with its
   numbered steps, placed on the level where each runs.
2-5 one family of commands per sheet, a panel per command: what the
   operator types and what of it is kept, what the program does, what the
   agent writes and its limits (from the code), whether the agent can change
   it later, the record, where it is seen and what it links to.

A teaching series: it prints no usage counts. The only live data is the
project's list of cores (read from the data root, read only). The texts are
hand-kept here, in plain technical wording (the operator's standard: the
wording-choices artifact), and were checked against backend/backend/limits.py,
corelib.py, mcp.py, prompts/contract and the skills on 18.11.2026;
`missing_commands(model)` names a command of the program that no panel of
sheets 2-5 shows.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

from sysmap import all_commands

O, S, A = "#eb6834", "#1baf7a", "#2a78d6"   # the article's three series colours (ARTICLE_STYLE.md)
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
AXIS = "#c3c2b7"
WHO = {"o": O, "s": S, "a": A}
LETTER = {"o": "О", "s": "П", "a": "А"}
W = 2800
W1 = 3000   # sheet 1 is wider: the shafts need room

csv.field_size_limit(1 << 30)


def esc(s: str) -> str:
    """Escape; a space inside a number (20 000) never breaks."""
    return re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", html.escape(s or ""))


def rich(s: str) -> str:
    """Escape, then **bold** and `mono`."""
    t = esc(s)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r'<code>\1</code>', t)
    return t


def who(w: str, cls: str = "who") -> str:
    return f'<span class="{cls}" style="--c:{WHO[w]}">{LETTER[w]}</span>'


# ---------------------------------------------------------------------------
# live data (read only)

def _rows(root: Path, name: str) -> list[dict]:
    p = root / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def live(model: dict, project: str = "merkhet") -> dict:
    root = Path(model.get("data_root") or "")
    cores = [c for c in _rows(root, "cores.csv") if c.get("project") == project and not (c.get("off_at") or "").strip()]
    cores.sort(key=lambda c: float(c.get("position") or 0))
    return {"cores": cores}


# ---------------------------------------------------------------------------
# the command panels of sheets 2-5
#
# you: what the operator writes and what of it is kept; prog: the program's
# steps; agent: (what, how much) — None when the agent writes nothing;
# edit: (can, how); rec: the record's fields (name, who, sample); seen;
# links. All texts in Russian, short.

FAMILIES = [
    ("s2", "Задачи", "Создание и закрытие задач.", 3, [
        dict(cmds=["now", "now-doing"], show="#now", alias="+ #now-doing", does="Сообщение становится задачей в статусе «в работе» для этого чата.",
             typed="#now частичный возврат по строкам заказа: клиент выбирает строки, сумма — по строкам",
             you="сообщение **целиком, дословно** = текст задачи", kept="весь текст, как набран",
             prog=["хук распознаёт `#now`, передаёт агенту", "сервер ставит карточку в «в работе», текст — оператора", "если агент не создал карточку, её создаёт сервер"],
             agent=[("заголовок", "≤ 80 знаков"), ("теги ag_*", "1–3")], agent_note="свой текст — только в комментарий",
             edit=("частично", "заголовок — да (`task_update`); текст оператора — нет, только комментарий ≤ 20 000 знаков; колонка — только оператор"),
             rec=("задача", [("заголовок", "a", "Частичный возврат по строкам"), ("текст", "o", "частичный возврат по строкам заказа…"),
                             ("колонка", "s", "в работе"), ("теги", "a", "ag_followup"), ("приоритет", "o", "—")]),
             seen="Доска · окно задачи", links=["#done закрывает", "коммиты с Task: tk_…", "core «Task commands»"]),
        dict(cmds=["now-todo", "now-to-do", "now-next", "now-backlog", "now-review", "now-parked", "now-done"], show="#now-todo",
             alias="-next · -backlog · -review · -parked · -done", does="Сообщение становится задачей в указанной колонке, без начала работы.",
             typed="#now-todo экспорт возвратов в CSV для бухгалтерии",
             you="сообщение **целиком, дословно** = текст задачи", kept="весь текст, как набран",
             prog=["сервер создаёт карточку в колонке из команды", "`-done` — сразу в «готово», без участка чата"],
             agent=[("заголовок", "≤ 80 знаков"), ("теги ag_*", "1–3")], agent_note="работу не начинает",
             edit=("частично", "заголовок — да; текст — только комментарий; колонка — только оператор"),
             rec=("задача", [("заголовок", "a", "Экспорт возвратов в CSV"), ("текст", "o", "экспорт возвратов в CSV для…"),
                             ("колонка", "s", "к выполнению"), ("теги", "a", "ag_idea")]),
             seen="Доска", links=["позже: #now в другом чате", "-done: без участка чата"]),
        dict(cmds=["task"], show="#task", does="Агент создаёт задачу по разговору в колонке «агент».",
             typed="#task письмо клиенту о возврате — обсуждали выше",
             you="**подсказка** для агента; текст оператора в задачу не копируется", kept="подсказка — в логе чата",
             prog=["сервер принимает задачу только в колонку «агент»", "проверяет теги"],
             agent=[("заголовок", "≤ 80 знаков"), ("описание", "2–6 строк"), ("теги ag_*", "1–3")],
             edit=("да", "`task_update`: заголовок, описание, комментарий; свою карточку — в архив (done-archived)"),
             rec=("задача", [("заголовок", "a", "Письмо клиенту о возврате"), ("описание", "a", "2–6 строк из разговора"),
                             ("колонка", "s", "агент"), ("теги", "a", "ag_followup")]),
             seen="Доска, колонка «агент»", links=["в работу переносит оператор"]),
        dict(cmds=["done"], show="#done", does="Закрытие задачи из чата; сообщения до команды привязываются к задаче.",
             typed="#done", you="**только команда** (можно с tk_…)", kept="отметка в логе",
             prog=["сервер переносит задачу в «готово» от имени оператора", "привязывает участок чата: коммиты, время, токены"],
             agent=[("отчёт", "одна строка"), ("где остановились", "1–2 предложения, ≤ 1 000 знаков"), ("следующие задачи", "предложить ≤ 3")],
             edit=("да", "новый `task_report` заменяет отчёт; статус — только оператор"),
             rec=("задача → готово", [("статус", "s", "готово"), ("участок чата", "s", "сообщения до #done"),
                                      ("коммиты", "s", "по строке Task: tk_…"), ("отчёт", "a", "возврат по строкам работает")]),
             seen="Доска · окно задачи · точка входа", links=["коммиты и токены → к задаче", "#evidence", "стендап дня"]),
        dict(cmds=["evidence"], show="#evidence", does="Доказательства к задаче: затронутые файлы и сделанные изменения.",
             typed="#evidence скрин страницы возврата и список изменённых файлов",
             you="**указания**, что приложить (можно задать заранее в задаче)", kept="указания — в задаче",
             prog=["хук передаёт id задачи", "сервер отдаёт агенту указания и файлы, изменённые в задаче"],
             agent=[("пунктов", "до 8 за раз"), ("текст", "≤ 20 000 знаков"), ("пояснение к изменению", "≤ 500 знаков"), ("скриншот", "≤ 12 МБ")],
             edit=("только добавить", "новой записью; повторный пункт не дублируется"),
             rec=("доказательства", [("указания", "o", "скрин + файлы"), ("скриншот", "a", "страница возврата"),
                                     ("файлы", "a", "refunds.py, cart.tsx"), ("изменение", "a", "сумма по строкам")]),
             seen="окно задачи", links=["#done", "запрос из task_report"]),
    ]),
    ("s3", "Тексты оператора", "Сообщения, которые сервер хранит дословно, и поля, которые добавляет агент.", 3, [
        dict(cmds=["vision"], show="#vision", does="Сообщение сохраняется как видение продукта.",
             typed="#vision возврат — без звонка в поддержку, клиент делает его сам",
             you="сообщение **целиком, дословно** = видение", kept="весь текст, как набран",
             prog=["сервер хранит дословно, выдаёт id vs_…"],
             agent=[("толкование", "до 20 000 знаков"), ("категория", "одно слово")],
             edit=("да", "толкование — новой версией; текст оператора — нет"),
             rec=("видение", [("слова", "o", "возврат — без звонка…"), ("толкование", "a", "что имеется в виду, v3"),
                              ("категория", "a", "продукт")]),
             seen="Видения", links=["→ #rule"]),
        dict(cmds=["rule"], show="#rule", does="Сообщение сохраняется как правило для агентов.",
             typed="#rule суммы возвратов храним в копейках, не в рублях",
             you="сообщение **целиком, дословно** = правило", kept="весь текст; область действия задаёт оператор",
             prog=["сервер хранит дословно", "активные правила — в AGENTS.md всех проектов"],
             agent=[("толкование", "до 20 000 знаков: правило в повелительной форме + случай")],
             edit=("да", "толкование — новой версией; статус и вид — только оператор"),
             rec=("правило", [("слова", "o", "суммы — в копейках"), ("толкование", "a", "Храни суммы в копейках…"),
                              ("статус", "o", "активно"), ("вид", "o", "все проекты")]),
             seen="Правила · AGENTS.md", links=["AGENTS.md → все агенты"], loop=True),
        dict(cmds=["problem", "problem solved"], show="#problem", alias="+ #problem solved", does="Сообщение сохраняется как открытая проблема; «solved» закрывает её.",
             typed="#problem банк не отдаёт частичный возврат, только полный",
             you="сообщение **целиком, дословно** = проблема", kept="весь текст, статус «открыта»",
             prog=["сервер хранит дословно, статус open", "`#problem solved pb_…` → агент ставит «решена» и дату"],
             agent=[("толкование", "до 20 000 знаков"), ("серьёзность", "low…critical")], agent_note="при блокировке пишет проблему сам",
             edit=("да", "толкование — версиями; статус и дату — `update_entry`"),
             rec=("проблема", [("слова", "o", "банк не отдаёт частичный…"), ("толкование", "a", "API банка: только полный"),
                               ("статус", "a", "открыта → решена"), ("серьёзность", "a", "high")]),
             seen="Проблемы", links=["задача на обход"]),
        dict(cmds=["prompt"], show="#prompt", does="Сообщение сохраняется в библиотеку промптов.",
             typed="#prompt (сверка сумм) проверь все суммы по строкам и сверь с итогом",
             you="сообщение **целиком, дословно** = промпт; имя — в скобках", kept="весь текст + счёт повторов",
             prog=["сервер берёт сообщение из лога дословно", "считает повторные отправки"],
             agent=None, edit=("нет", "версии и имя — оператор на странице"),
             rec=("промпт", [("текст", "o", "проверь все суммы…"), ("имя", "o", "сверка сумм"), ("повторов", "s", "счёт отправок")]),
             seen="Промпты", links=["отправить снова в любом чате"]),
        dict(cmds=["skill"], show="#skill", does="Процедура из чата оформляется как скилл для агентов.",
             typed="#skill как мы тестируем возвраты",
             you="**заявка**: что сделать скиллом; скилл пишет агент", kept="сообщение — черновик скилла",
             prog=["сервер хранит черновик, проверяет SKILL.md", "по команде оператора «поставить» копирует в проекты"],
             agent=[("SKILL.md", "шаги, как их делали в чате"), ("имя", "≤ 64 знаков"), ("файлы рядом", "по нужде")],
             edit=("да", "`skill_draft` снова, пока черновик; сервер возвращает проверки"),
             rec=("скилл", [("имя", "a", "testing-refunds"), ("описание", "a", "когда звать скилл"),
                            ("статус", "o", "черновик → стоит"), ("установка", "o", "выбранные проекты")]),
             seen="Скиллы", links=["установка в проекты"], loop=True),
        dict(cmds=["artifact"], show="#artifact", does="Результат хранится папкой: данные, документ, страница, приложение.",
             typed="#artifact выгрузка возвратов за октябрь",
             you="**что сохранить**; саму папку пишет агент", kept="сообщение — черновик записи",
             prog=["сервер хранит черновик", "читает папку в data root"],
             agent=[("папка", "файлы результата"), ("имя", "≤ 64 знаков"), ("описание", "1–2 предложения"), ("вид", "данные · документ · страница · приложение")],
             edit=("да", "поправить папку и снова `artifact_write`"),
             rec=("артефакт", [("имя", "a", "refunds-2026-10"), ("вид", "a", "данные"), ("описание", "a", "возвраты за октябрь"),
                               ("статус", "s", "готов")]),
             seen="Артефакты", links=["папка в data root"]),
        dict(cmds=["publish"], show="#publish", does="Карточка выпущенного изменения для анонса.",
             typed="#publish частичные возвраты вышли в 1.4: клиент сам выбирает строки",
             you="сообщение **целиком, дословно** = текст карточки", kept="весь текст; `#publish pu_…` дополняет",
             prog=["сервер хранит карточку pu_…", "каждая запись текста — новая версия"],
             agent=[("контекст", "что сделано, для кого, до/после, числа"), ("текст", "только по запросу оператора"),
                    ("вложения", "задачи, коммиты, файлы ≤ 25 МБ, картинки, ссылки")],
             edit=("да", "новая версия (от прочитанной); текст оператора — только по запросу"),
             rec=("публикация", [("текст", "o", "частичные возвраты вышли…"), ("контекст", "a", "что изменилось для клиента"),
                                 ("вложения", "a", "задачи, коммиты"), ("документы", "o", "пост, статья")]),
             seen="Публикации", links=["→ статьи, посты", "→ релиз"]),
        dict(cmds=["entrypoint"], show="#entrypoint", does="Точка входа в тему: расположение, запуск, текущее состояние.",
             typed="#entrypoint витрина: как её запустить",
             you="**имя темы**; затем выбор темы по номеру", kept="команда хранится до выбора оператора",
             prog=["сервер ищет похожие темы; до выбора записи нет", "проверяет ответ и порты"],
             agent=[("запись", "5 частей: Что · Где · Как · Состояние · Дальше; версия ≤ 200 000 знаков"), ("способы входа", "страница, команда, папка"),
                    ("где остановились", "1–2 предложения ≤ 1 000"), ("скриншоты", "≤ 12 МБ")],
             edit=("да", "каждая запись — новая версия; способы входа — `entrypoint_way`"),
             rec=("точка входа", [("имя", "o", "витрина"), ("запись", "a", "Что · Где · Как · …"), ("способы входа", "a", "127.0.0.1:5173"),
                                  ("остановки", "a", "после #done")]),
             seen="Точки входа", links=["задачи темы", "#done пишет остановку"]),
    ]),
    ("s4", "Архитектура и отчёты", "Сканы, архитектура, решения, стендапы, cores.", 3, [
        dict(cmds=["scan"], show="#scan", does="Изменения этого чата с прошлого скана, включая незакоммиченные.",
             typed="#scan", you="**только команда**; скан пишется только по ней", kept="отметка в логе",
             prog=["сервер отдаёт коммиты чата с прошлого скана, файлы, счётчики", "после скана — файловая запись и форма архитектуры"],
             agent=[("скан", "≤ 300 слов"), ("итог", "1 предложение ≤ 30 слов"), ("почему", "2 предложения ≤ 45 слов"), ("форма архитектуры", "8 групп")],
             edit=("да, кроме итога", "`update_entry`: почему, изменения, доказательства"),
             rec=("скан", [("итог", "a", "возврат по строкам: API + экран"), ("почему", "a", "клиенты просили"),
                           ("файлы", "s", "из коммитов чата"), ("строки", "s", "добавлено / удалено")]),
             seen="Сканы → Архитектура", links=["коммиты в git", "форма → страница, карта"]),
        dict(cmds=["architecture", "page", "map"], show="#architecture", alias="#page · #map", does="Архитектура проекта: форма скана, страница проекта, карта программы.",
             typed="#architecture", you="**только команда**; для `#map` — подтверждение «да»", kept="ничего",
             prog=["сервер сообщает, что устарело и почему", "проверяет пути и словарь"],
             agent=[("страница проекта", "версия ≤ 40 000 знаков"), ("карта", "каждая часть строкой + связи (помощник)"), ("примечание", "одна строка, что изменилось")],
             edit=("да", "только новой версией страницы или карты"),
             rec=("архитектура", [("форма", "a", "8 групп за скан"), ("страница", "a", "новая версия"), ("карта", "a", "строка на часть"),
                                  ("устарело", "s", "сканов после версии")]),
             seen="Архитектура · Карта", links=["#scan", "cores на карте"]),
        dict(cmds=["decision"], show="#decision", does="Запись решения: выбор, причина, отклонённые варианты.",
             typed="#decision округляем по строке, не по заказу",
             you="**команда** или «да» на предложение агента", kept="текст оператора в запись не входит",
             prog=["хук распознаёт фразы-решения, передаёт агенту"],
             agent=[("решение", "≤ 20 слов"), ("почему", "≤ 40 слов"), ("отклонено", "варианты"), ("вес", "minor · normal · major")], agent_note="может записать без команды",
             edit=("частично", "почему, варианты, вес — да; само решение — нет, только новая запись"),
             rec=("решение", [("решение", "a", "округлять по строке"), ("почему", "a", "иначе копейки теряются"),
                              ("отклонено", "a", "по заказу"), ("вес", "a", "normal")]),
             seen="Решения · задача · архитектура", links=["к задаче", "к стендапу дня"]),
        dict(cmds=["standup"], show="#standup", does="Стендап за вчера по всем чатам того дня.",
             typed="#standup", you="**команда** или «да» в первом чате дня", kept="ничего",
             prog=["хук предлагает в первом сообщении дня", "сервер отдаёт сообщения дня и изменения задач"],
             agent=[("итог", "≤ 30 слов"), ("рассказ", "1–3 абзаца"), ("сделано", "пункты ≤ 35 слов"), ("решения, отклонения", "списком")],
             agent_note="пишет агент-помощник",
             edit=("да, кроме итога", "`update_entry`"),
             rec=("стендап", [("итог", "a", "возвраты по строкам готовы"), ("сделано", "a", "New: … · Fixed: …"),
                              ("отклонения", "a", "—"), ("числа дня", "s", "chats · commits · часы")]),
             seen="Стендапы", links=["затем — предложение #map"]),
        dict(cmds=["core-new"], show="#core-new", does="Создание core: подсистема под наблюдением.",
             typed="#core-new модуль возвратов: всё, что считает частичный возврат",
             you="сообщение **дословно** = первая заметка core", kept="весь текст",
             prog=["сервер создаёт core и первую заметку"],
             agent=[("имя", "≤ 60 знаков, словами оператора"), ("тип", "1 из 8"), ("причина", "одна строка ≤ 200"), ("файлы", "что знает")],
             edit=("нет", "через MCP не правится; имя, файлы, отслеживание — оператор на странице"),
             rec=("core", [("имя", "a", "Модуль возвратов"), ("тип", "a", "capability"), ("файлы", "a", "refunds.py, …"),
                           ("отслеживание", "o", "вкл. до 30.11")]),
             seen="Архитектура › ядра", links=["#core-note", "#core", "коммиты по файлам"]),
        dict(cmds=["core-note"], show="#core-note", does="Сообщение сохраняется как заметка core.",
             typed="#core-note округление — только по строке, не по заказу",
             you="сообщение **дословно** = заметка", kept="весь текст; заметка оператора одобрена сразу",
             prog=["сервер хранит заметку", "строка агента ждёт одобрения оператора"],
             agent=[("комментарий", "одна строка (сервер пропустит до 4 000)")], agent_note="при отслеживании — строка после работы, автоматически",
             edit=("нет", "только новая заметка"),
             rec=("заметка core", [("текст", "o", "округление — только по строке"), ("строка агента", "a", "закреплено в refunds.py"),
                                   ("одобрена", "o", "ждёт")]),
             seen="Архитектура › ядра, лента", links=["core", "задача чата"]),
        dict(cmds=["core"], show="#core", does="Сообщение и задача этого чата прикрепляются к core.",
             typed="#core это про модуль возвратов", you="**команда**; сообщение — что прикрепить", kept="ссылка на сообщение",
             prog=["сервер хранит связь"],
             agent=[("связь", "core + сообщение / задача")], agent_note="два подходящих core — запрос номера",
             edit=("нет", "связь снимает оператор"),
             rec=("связь core", [("core", "a", "Модуль возвратов"), ("что", "a", "сообщение, tk_…")]),
             seen="Архитектура › ядра", links=["задача", "лента core"]),
        dict(cmds=["core-off"], show="#core-off", does="Core скрывается; заметки и связи сохраняются.",
             typed="#core-off модуль возвратов", you="**что скрыть**; подтверждение номером", kept="ничего",
             prog=["сервер ставит отметку скрытия"],
             agent=[("скрытие", "после номера от оператора")], edit=("нет", "вернуть — на странице"),
             rec=("core", [("скрыто", "s", "18.11"), ("заметки", "s", "сохранены")]),
             seen="Архитектура › ядра (скрыто)", links=["заметки и связи сохранены"]),
    ]),
    ("s5", "Метки и служебные команды", "Метки сообщений и служебные команды SP.", 4, [
        dict(cmds=["important", "important-agent", "important-task", "important-message"], show="#important", alias="-agent · -task · -message",
             does="Отметка «важное» на сообщении, агенте чата и его задачах.",
             typed="#important сумма по строке — без скидки доставки",
             you="**только тег**", kept="отметка; сообщение — в логе",
             prog=["сервер ставит отметки по тегу из лога", "`-agent` / `-task` / `-message` — только одну"],
             agent=None, edit=("—", "снимает оператор кнопкой"),
             rec=("отметка", [("на что", "o", "сообщение, агент, задача")]), seen="Важное", links=[]),
        dict(cmds=["pin"], show="#pin", does="Закрепление сообщения.",
             typed="#pin формула суммы по строке", you="**только тег**", kept="закреп",
             prog=["сервер ставит закреп по тегу из лога"],
             agent=None, agent_note="по запросу читает `pins`", edit=("—", "снимает оператор"),
             rec=("закреп", [("сообщение", "o", "cc-…#14")]), seen="Закреплённые", links=[]),
        dict(cmds=["carry"], show="#carry", does="После сжатия контекста сообщение передаётся агенту целиком.",
             typed="#carry вот договорённость по округлению", you="**только тег**", kept="сообщение + ответ агента",
             prog=["после сжатия хук отдаёт агенту сообщение и ответ (≤ 4 000 знаков)", "всё вместе ≤ 30 000"],
             agent=None, edit=("—", "снимает оператор"),
             rec=("метка", [("вид", "o", "carry")]), seen="Закреплённые", links=[]),
        dict(cmds=["carry-brief"], show="#carry-brief", does="После сжатия контекста агенту передаётся пересказ.",
             typed="#carry-brief весь разговор про возвраты выше", you="**тег**; пересказ пишет агент", kept="метка + пересказ",
             prog=["после сжатия хук отдаёт пересказ вместо сообщения"],
             agent=[("пересказ", "несколько предложений, ≤ 4 000 знаков")], edit=("да", "новая запись заменяет"),
             rec=("метка", [("вид", "o", "carry-brief"), ("пересказ", "a", "кто просил, зачем, что решили")]),
             seen="Закреплённые", links=[]),
        dict(cmds=["fork-later"], show="#fork-later", does="Отметка работы для отдельного агента (форк).",
             typed="#fork-later письмо в банк про частичный возврат", you="**только тег**", kept="метка",
             prog=["сервер выдаёт команду запуска форка", "запуск — вручную"],
             agent=None, agent_note="продолжает текущую работу", edit=("—", "запускает оператор из списка"),
             rec=("метка", [("вид", "o", "fork-later"), ("состояние", "o", "ждёт")]), seen="Закреплённые", links=[]),
        dict(cmds=["undo", "undo-yes"], show="#undo", alias="+ #undo-yes", does="Архивация записей, созданных тегом по ошибке.",
             typed="#undo видение было не про возвраты", you="**описание ошибки**; затем номера и `#undo-yes`", kept="запрос в логе",
             prog=["сервер сверяет запрос и подтверждение по логу", "переносит записи в архив"],
             agent=[("кандидаты", "по номерам"), ("подтверждение", "текст сервера как есть")],
             edit=("да", "вернуть — `undo_restore`"),
             rec=("отмена", [("запрос", "o", "видение не про…"), ("предложение", "a", "номера записей"), ("итог", "s", "записи в архиве")]),
             seen="Архив", links=[]),
        dict(cmds=["mute"], show="#mute", does="Команды в сообщении не выполняются.",
             typed="#mute вот лог: … #now … #rule …", you="**тег**; остальные теги — простой текст", kept="ничего",
             prog=["хук пропускает все команды, включая ###"], agent=None, agent_note="теги не обрабатывает",
             edit=("—", "—"), rec=None, seen="в чате", links=[]),
        dict(cmds=[], show="###тег", does="В сообщении выполняется только эта команда.",
             typed="###now-todo экспорт в CSV, а #rule тут просто слово", you="**три решётки**: только эта команда", kept="как у этой команды",
             prog=["хук выполняет и передаёт агенту только её"], agent=None, agent_note="как у этой команды",
             edit=("—", "—"), rec=None, seen="как у команды", links=[]),
        dict(cmds=["usage", "usage-on", "usage-off", "usage-warnings-on", "usage-warnings-off"], show="#usage",
             alias="-on/-off · -warnings-on/-off", does="Токены чата и лимиты плана; показ после ответов.",
             typed="#usage", you="**только команда**", kept="ничего",
             prog=["ответ даёт хук: токены чата, лимиты плана", "в Claude Code модель не вызывается"],
             agent=None, agent_note="Codex, OpenCode: отдаёт текст хука как есть", edit=("—", "—"),
             rec=None, seen="Расход", links=[]),
        dict(cmds=["usage-price"], show="#usage-price", does="Обновление цен API для расчёта в долларах.",
             typed="#usage-price", you="**только команда**", kept="ничего",
             prog=["сервер отдаёт модели чатов и текущие цены"],
             agent=[("цены", "со страниц поставщиков")], agent_note="пишет агент-помощник", edit=("да", "следующим обновлением"),
             rec=("цены", [("модель", "a", "opus · sonnet · …"), ("$ за 1 млн", "a", "вход / выход")]), seen="Расход", links=[]),
        dict(cmds=["sp"], show="#sp", does="Проверка: работает ли SP для этого чата и папки.",
             typed="#sp не вижу вчерашний чат", you="**команда** и описание проблемы (необязательно)", kept="ничего",
             prog=["сервер проверяет: запись, MCP, хуки, данные, копии, память"],
             agent=[("отчёт", "в заданной форме")], agent_note="изменения — только после «да»", edit=("—", "—"),
             rec=None, seen="ответ в чате · Монитор", links=[]),
        dict(cmds=["help"], show="#help", does="Список команд: что делает каждая и где видно.",
             typed="#help", you="**только команда**", kept="ничего", prog=["записи нет; ответ из скилла"],
             agent=[("список", "из скилла sp-help как есть")], edit=("—", "—"), rec=None, seen="ответ в чате", links=[]),
    ]),
]


def missing_commands(model: dict) -> list[str]:
    have = {c for _id, _t, _l, _n, panels in FAMILIES for p in panels for c in p["cmds"]}
    return sorted(all_commands(model) - have)


# ---------------------------------------------------------------------------
# shared pieces

def legend() -> str:
    return f"""<div class="key">
<div class="kr">{who('o')}<span><b>оператор</b> — пишет в чате</span></div>
<div class="kr">{who('s')}<span><b>программа</b> — хук и сервер</span></div>
<div class="kr">{who('a')}<span><b>агент</b> — пишет через MCP</span></div>
<div class="kr"><i class="dsh"></i><span>попадает в инструкции агентов</span></div>
<div class="kr"><span class="eg">✎</span><span>правка агентом после записи</span></div></div>"""


def header(n: int, title: str, lede: str, today: str) -> str:
    return f"""<header><div><div class="kicker"><span class="tag">Slightly Parallel</span> архитектура SP · лист {n} из 5 · {esc(today)}</div>
<h1>{esc(title)}</h1><p class="lede">{lede}</p></div>{legend()}</header>"""


# ---------------------------------------------------------------------------
# sheet 1: the architecture

G1, G2, G3, G4, G5 = 330, 1000, 1420, 1880, 2330
SH_X0 = 1900
SHAFTS = [
    ("now", "#now", [(1, "o", "оператор: «частичный возврат по строкам заказа»"), (2, "s", "хук: распознаёт #now"),
                     (2, "s", "сервер: задача из текста, статус «в работе»"), (2, "a", "агент: заголовок ≤ 80 знаков"),
                     (3, "s", "cores: Task commands, Логика реплик"), (4, "s", "tasks.csv · коммиты с Task: tk_…"),
                     (1, "x", "UI: Доска, окно задачи")]),
    ("rule", "#rule", [(1, "o", "оператор: «суммы — в копейках»"), (2, "s", "сервер: хранит текст дословно"),
                       (2, "a", "агент: толкование ≤ 20 000 знаков"), (3, "u", "Сохранённые сообщения (не core)"),
                       (4, "s", "AGENTS.md всех проектов"), (2, "l", "AGENTS.md → агенты при старте чата"),
                       (1, "x", "UI: Правила")]),
    ("scan", "#scan", [(1, "o", "оператор: #scan"), (4, "s", "git: коммиты чата с прошлого скана"),
                       (2, "s", "сервер: отдаёт коммиты и файлы"), (2, "a", "агент: скан ≤ 300 слов + форма"),
                       (3, "u", "Архитектура и карта (не core)"), (1, "x", "UI: Сканы, Архитектура")]),
    ("publish", "#publish", [(1, "o", "оператор: «возвраты вышли в 1.4»"), (2, "s", "сервер: карточка из текста, версии"),
                             (2, "a", "агент: контекст, задачи, коммиты"), (3, "s", "core: Ветки и публикация"),
                             (4, "s", "релиз: ветка release на GitHub"), (1, "x", "UI: Публикации")]),
    ("core-note", "#core-note", [(1, "o", "оператор: «округление — по строке»"), (2, "s", "сервер: хранит заметку дословно"),
                                 (2, "a", "агент: одна строка (≤ 4 000)"), (3, "s", "core: заметка в ленте"),
                                 (4, "s", "core_notes.csv"), (1, "x", "UI: Архитектура › ядра")]),
]

CORE_RU = {
    "Логика реплик": ("внутреннее", "какой текст считается сообщением оператора и запускает команды"),
    "Task commands": ("процесс", "команды задач: создание карточки, смена колонки"),
    "Cores": ("функция", "#core-команды, отслеживание, одобрение заметок"),
    "Ветки и публикация": ("процесс", "master → ci-* → CI → release"),
    "Testing approach": ("процесс", "методика тестирования"),
}
TYPE_RU = {"workflow": "процесс", "internals": "внутреннее", "feature": "функция", "capability": "возможность",
           "interface": "интерфейс", "store": "хранилище", "integration": "интеграция", "experiment": "эксперимент"}
UNNAMED = [
    ("Сохранённые сообщения", "#vision/#rule/#problem дословно; толкование версиями", "keeplib.py · kept_versions/"),
    ("Учёт токенов и времени", "токены: ответ → чат → задача → день; таймер", "usagelib.py · timeauto.py"),
    ("Архитектура и карта", "скан → форма → страница проекта → карта", "scanlib.py · archpage.py · repomap.py"),
    ("Заметки", "тексты агента для оператора; версии, изображения", "notelib.py · note_versions.csv"),
]

PAGES = [("Доска", "колонки задач"), ("Задача", "текст, участок чата, коммиты"), ("Видения · Правила", "текст оператора + толкование"),
         ("Ядра · Архитектура", "cores, страница проекта, карта"), ("Стендапы", "отчёт за вчера"), ("Публикации", "карточки релизов"),
         ("Заметки", "тексты агента для оператора"), ("Закреплённые", "pin, carry, fork-later"), ("Расход", "токены, лимиты")]


def sheet1(model: dict, L: dict) -> str:
    today = model.get("today", "")
    el: list[str] = []
    svg: list[str] = []
    H = G5 + 120

    # levels: no fills, a thin rule between them (the article's .rule)
    for y in (G1, G2, G3, G4, G5):
        svg.append(f'<line x1="40" y1="{y}" x2="{W1 - 40}" y2="{y}" stroke="{AXIS}" stroke-width="1.5"/>')

    # band labels (left)
    labels = [
        (G1, G2, "1", "Интерфейсы", "терминал, веб-интерфейс SP, точки входа"),
        (G2, G3, "2", "Сервис SP", "хук, сервер, MCP-инструменты, агенты"),
        (G3, G4, "3", "Подсистемы (cores)", "сплошная рамка — core проекта; пунктир — не оформлено как core"),
        (G4, G5, "4", "Хранилище и CI", "data root (CSV, DuckDB), git и CI, AGENTS.md и скиллы"),
    ]
    for y0, y1, n, name, sub in labels:
        el.append(f'<div class="lay" style="left:40px;top:{y0 + 34}px;width:250px"><span class="ln">{n}</span>'
                  f'<b>{esc(name)}</b><span>{esc(sub)}</span></div>')
    el.append(f'<div class="altname" style="left:40px;top:{G3 + 250}px;width:250px">название уровня:<br>«Подсистемы» · «Модули» · «Cores (ядра)»</div>')

    # ---- band 1: terminal, web UI, entry points
    y0 = G1 + 40
    term_lines = [
        ("o", "#now", "частичный возврат по строкам заказа"),
        ("a", None, "◆ агент: заголовок записан"),
        ("o", "#vision", "возврат — без звонка в поддержку"),
        ("o", "#rule", "суммы возвратов — в копейках"),
        ("o", "#core-note", "округление — только по строке"),
        ("o", "#scan", ""),
        ("o", "#publish", "частичные возвраты в 1.4"),
        ("o", "#entrypoint", "витрина: как запустить"),
        ("o", "#done", ""),
    ]
    tl = "".join(
        (f'<div class="tl"><span class="pr">›</span><b>{esc(c)}</b> {esc(t)}</div>' if c else f'<div class="tl ag">{esc(t)}</div>')
        for w, c, t in term_lines)
    el.append(f"""<div class="term" style="left:330px;top:{y0}px;width:500px;height:560px">
<div class="tbar"><span>терминал · claude · shopfront</span></div>
<div class="tls">{tl}</div><div class="tfoot">команда: тег <b>#…</b> в любом месте сообщения</div></div>""")
    tiles = "".join(f'<div class="pg"><b>{esc(a)}</b><span>{esc(b)}</span></div>' for a, b in PAGES)
    el.append(f"""<div class="brw" style="left:860px;top:{y0}px;width:620px;height:560px">
<div class="bbar"><span class="url">127.0.0.1:8123 · веб-интерфейс SP</span></div>
<div class="pgs">{tiles}</div><div class="bfoot">просмотр записей, статусы задач, одобрение</div></div>""")
    # entry points: the record's parts
    parts = [("Что", "назначение темы"), ("Где", "папки, файлы"), ("Как", "команда запуска"),
             ("Состояние", "что работает сейчас"), ("Дальше", "следующие шаги")]
    pr = "".join(f'<div class="epr"><b>{esc(a)}</b><span>{esc(b)}</span></div>' for a, b in parts)
    el.append(f"""<div class="eps" style="left:1510px;top:{y0}px;width:320px;height:560px">
<div class="eh"><b>Точки входа</b><span>запись темы: расположение, запуск, состояние</span></div>
<div class="eprs">{pr}</div>
<div class="epx"><span>способы входа: страница, команда, папка</span><span>место остановки — после #done</span><span>скриншоты ≤ 12 МБ</span></div></div>""")

    # ---- band 2: hook, server, MCP, agents
    y2 = G2 + 60
    el.append(f"""<div class="box" style="left:330px;top:{y2}px;width:300px;height:280px"><div class="bt">{who('s')}<b>Хук</b></div>
<span>записывает <b>каждое</b> сообщение оператора и ответ агента</span><span>распознаёт теги, передаёт агенту инструкции</span></div>""")
    el.append(f"""<div class="box" style="left:700px;top:{y2}px;width:420px;height:280px"><div class="bt">{who('s')}<b>Сервер</b></div>
<span>хранит текст оператора <b>дословно</b></span><span>меняет статусы задач, считает время и токены</span><span>отдаёт веб-интерфейс; проверяет автора записи</span></div>""")
    el.append(f"""<div class="box" style="left:1190px;top:{y2}px;width:250px;height:280px"><div class="bt">{who('a')}<b>Инструменты</b><span class="tag">MCP</span></div>
<span>агент пишет только через MCP-инструменты</span></div>""")
    el.append(f"""<div class="box" style="left:1510px;top:{y2}px;width:320px;height:280px"><div class="bt">{who('a')}<b>Агенты</b></div>
<span>Claude Code · Codex · OpenCode</span><span>читают AGENTS.md и скиллы; выполняют задачи</span></div>""")
    ym = y2 + 150
    svg.append(arrow([(630, ym), (696, ym)], S))
    svg.append(arrow([(1510, ym), (1444, ym)], A))
    svg.append(arrow([(1190, ym), (1124, ym)], A))
    # terminal → hook, server → pages
    svg.append(arrow([(480, G1 + 600), (480, y2 - 4)], O))
    el.append(f'<div class="pill" style="left:494px;top:{G1 + 640}px;--c:{O}">сообщения</div>')
    svg.append(arrow([(1000, y2), (1000, G1 + 604)], S))
    el.append(f'<div class="pill" style="left:1014px;top:{G1 + 640}px;--c:{S}">данные для страниц</div>')
    svg.append(arrow([(1670, y2), (1670, G1 + 604)], A))
    el.append(f'<div class="pill" style="left:1684px;top:{G1 + 640}px;--c:{A}">запись точек входа</div>')

    # ---- band 3: cores
    cw, ch, gap = 284, 190, 20
    x0, yA, yB = 330, G3 + 40, G3 + 40 + ch + 20
    for i, c in enumerate(L["cores"][:5]):
        t, line = CORE_RU.get(c["name"], (TYPE_RU.get(c.get("type"), c.get("type")), c.get("reason", "")[:70]))
        el.append(f"""<div class="core" style="left:{x0 + i * (cw + gap)}px;top:{yA}px;width:{cw}px;height:{ch}px">
<div class="ct">core · {esc(t)}</div><b>{esc(c['name'])}</b><span>{esc(line)}</span></div>""")
    for i, (name, line, files) in enumerate(UNNAMED):
        el.append(f"""<div class="core un" style="left:{x0 + i * (cw + gap)}px;top:{yB}px;width:{cw}px;height:{ch}px">
<div class="ct">не оформлено как core</div><b>{esc(name)}</b><span>{esc(line)}</span><div class="cf">{esc(files)}</div></div>""")
    el.append(f"""<div class="core note" style="left:{x0 + 4 * (cw + gap)}px;top:{yB}px;width:{cw}px;height:{ch}px">
<div class="ct">обозначения</div><span>сплошная рамка — core проекта (создаётся <code>#core-new</code>)</span><span>пунктир — подсистема в коде, не оформлена как core</span></div>""")

    # ---- band 4: data root, git + CI, AGENTS.md
    y4 = G4 + 50
    el.append(f"""<div class="box" style="left:330px;top:{y4}px;width:400px;height:330px"><div class="bt"><b>Data root</b></div>
<span>CSV-файлы: одна запись — одна строка</span><span>DuckDB: чтение для страниц</span><span class="mono">00-agents-dashboard/</span></div>""")
    stages = [("master", "коммиты агентов, строка Task: tk_…"), ("ci-*", "ветка для CI"), ("Linux, macOS, Windows", "GitHub Actions"), ("release", "ветка релиза")]
    st = "".join(f'<div class="stg"><b>{esc(a)}</b><span>{esc(b)}</span></div>' + ('<i class="sa">→</i>' if j < 3 else '') for j, (a, b) in enumerate(stages))
    el.append(f"""<div class="box" style="left:760px;top:{y4}px;width:720px;height:330px"><div class="bt"><b>Git и CI</b></div>
<div class="stgs">{st}</div><span>тесты: pytest · vitest · e2e</span></div>""")
    el.append(f"""<div class="box dash" style="left:1510px;top:{y4}px;width:320px;height:330px"><div class="bt"><b>AGENTS.md · скиллы</b></div>
<span>активные правила — в AGENTS.md всех проектов</span><span>скиллы устанавливаются в проекты</span><span>читаются <b>каждым</b> агентом</span></div>""")
    # AGENTS.md → agents (dashed up)
    svg.append(arrow([(1536, y4), (1536, G2 + 344)], S, dashed=True))
    el.append(f'<div class="pill" style="left:1550px;top:{G3 - 16}px;--c:{S}">загрузка в агентов</div>')

    # ---- command columns: per band a column of numbered steps
    n = len(SHAFTS)
    sw = (W1 - 40 - SH_X0) / n
    pw = sw - 20
    el.append(f'<div class="shh" style="left:{SH_X0}px;top:{G1 + 24}px;width:{W1 - 40 - SH_X0}px"><b>Обработка команд: шаги</b> · столбец — команда, номер — порядок шага</div>')
    band_top = {1: G1 + 130, 2: G2 + 40, 3: G3 + 50, 4: G4 + 50}
    for i, (cid, label, stops) in enumerate(SHAFTS):
        cx = SH_X0 + sw * i + sw / 2
        per = {1: [], 2: [], 3: [], 4: []}
        for k2, (band, w, text) in enumerate(stops, 1):
            if w == "x":
                c, cls, badge = INK2, "sp sv", "◉"
            elif w == "u":
                c, cls, badge = MUTED, "sp un", LETTER["s"]
            elif w == "l":
                c, cls, badge = S, "sp loop", "↑"
            else:
                c, cls, badge = WHO[w], "sp", LETTER[w]
            per[band].append(f'<div class="{cls}" style="--c:{c}"><span class="sn">{k2}</span>'
                             f'<span class="sb" style="background:{c}">{badge}</span><span class="st">{esc(text)}</span></div>')
        deepest = max(b for b, _w, _t in stops)
        bottom = band_top[deepest] + 70 * len(per[deepest]) + 40
        svg.append(f'<line x1="{cx:.1f}" y1="{G1 + 92}" x2="{cx:.1f}" y2="{bottom - 4}" stroke="{AXIS}" stroke-width="2"/>')
        svg.append(f'<path d="M{cx - 12:.1f},{bottom - 6} L{cx:.1f},{bottom + 12} L{cx + 12:.1f},{bottom - 6} Z" fill="{MUTED}"/>')
        el.append(f'<div class="rig" style="left:{cx - pw / 2:.0f}px;top:{G1 + 64}px;width:{pw:.0f}px"><b>{esc(label)}</b></div>')
        seen = [x for x in per[1] if "sp sv" in x]
        per[1] = [x for x in per[1] if "sp sv" not in x]
        if seen:
            el.append(f'<div class="spc" style="left:{cx - pw / 2:.0f}px;top:{G2 - 150}px;width:{pw:.0f}px">{"".join(seen)}</div>')
        for band, items in per.items():
            if items:
                el.append(f'<div class="spc" style="left:{cx - pw / 2:.0f}px;top:{band_top[band]}px;width:{pw:.0f}px">{"".join(items)}</div>')
    head = header(1, "Архитектура Slightly Parallel", "Четыре уровня сверху вниз: интерфейсы, сервис SP, подсистемы, хранилище и CI. Справа — шаги обработки пяти команд по уровням.", today)
    defs = f"""<defs>{markers()}</defs>"""
    svg_html = f'<svg class="wires" width="{W1}" height="{H}">{defs}{"".join(svg)}</svg>'
    foot = f'<div class="foot" style="left:40px;top:{G5 + 50}px">Пример: проект shopfront, задача «частичные возвраты». Cores — данные SP на {esc(today)}.</div>'
    return f'<section class="sheet" id="s1" style="width:{W1}px"><div class="canvas" style="width:{W1}px;height:{H}px">{svg_html}{head}{"".join(el)}{foot}</div></section>'


def markers() -> str:
    out = []
    for c in (O, S, A, INK2):
        out.append(f'<marker id="h{c[1:]}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0.6 L9.4,5 L0,9.4 z" fill="{c}"/></marker>')
    return "".join(out)


def arrow(pts, color, dashed=False, width=3, r=12) -> str:
    from sysmap import rounded_path
    d = rounded_path([tuple(p) for p in pts], r)
    dash = ' stroke-dasharray="10 7"' if dashed else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round"{dash} marker-end="url(#h{color[1:]})"/>'


# ---------------------------------------------------------------------------
# sheets 2-5

def panel(p: dict) -> str:
    count = '' if p["cmds"] else '<span class="n30">синтаксис, не команда</span>'
    alias = f'<span class="alias">{esc(p["alias"])}</span>' if p.get("alias") else ""
    typed = re.sub(r"^(#{1,3}[\w\-]+(?: solved)?)", r"<b>\1</b>", esc(p["typed"]))
    prog = "".join(f"<li>{rich(s)}</li>" for s in p["prog"])
    if p.get("agent"):
        ag = "".join(f'<div class="lim"><span>{esc(a)}</span><b>{esc(b)}</b></div>' for a, b in p["agent"])
    else:
        ag = '<div class="none">не пишет</div>'
    if p.get("agent_note"):
        ag += f'<div class="anote">{rich(p["agent_note"])}</div>'
    can, how = p["edit"]
    cls = {"да": "yes", "нет": "no", "частично": "part", "только добавить": "part"}.get(can, "part" if can.startswith("да") else "na")
    rec = ""
    if p.get("rec"):
        name, rows = p["rec"]
        rr = "".join(f'<div class="rr"><i style="background:{WHO[w]}"></i><span class="rk">{esc(k)}</span><span class="rv">{esc(v)}</span></div>' for k, w, v in rows)
        rec = f'<div class="rec"><div class="rech">запись · {esc(name)}</div>{rr}</div>'
    else:
        rec = '<div class="rec empty"><div class="rech">записи нет</div><span>ответ — в чате</span></div>'
    links = "".join(f'<span class="lk">{esc(x)}</span>' for x in p.get("links") or [])
    badges = ""
    if p.get("loop"):
        badges += '<div class="loopb"><i class="dsh"></i>в инструкции агентов</div>'
    return f"""<div class="cmd">
<div class="ch"><span class="cn">{esc(p['show'])}</span>{alias}{count}</div>
<div class="does">{esc(p['does'])}</div>
<div class="t1"><span class="pr">›</span>{typed}</div>
<div class="cb"><div class="flow">
<div class="row">{who('o')}<div><div class="rl">оператор пишет</div><div class="rv1">{rich(p['you'])}</div><div class="kept">хранится: {rich(p['kept'])}</div></div></div>
<div class="row">{who('s')}<div><div class="rl">программа</div><ul>{prog}</ul></div></div>
<div class="row">{who('a')}<div><div class="rl">агент пишет · лимит</div>{ag}</div></div>
<div class="row"><span class="eg {cls}">✎</span><div><div class="rl">правка агентом: <b class="{cls}">{esc(can)}</b></div><div class="how">{rich(how)}</div></div></div>
</div><div class="side">{rec}<div class="seen"><span>видно</span><b>{esc(p['seen'])}</b></div>{badges}</div></div>
{f'<div class="links"><span class="lt">связано</span>{links}</div>' if links else ''}
</div>"""


def extra(sid: str, L: dict) -> str:
    if sid == "s2":
        cols = [("агент", "#task"), ("бэклог", "-backlog"), ("к выполнению", "-todo"), ("следующие", "-next"),
                ("в работе", "#now"), ("на проверке", "-review"), ("отложено", "-parked"), ("готово", "#done · -done")]
        cc = "".join(f'<div class="bcol{" hot" if c == "в работе" else ""}"><div class="bch">{esc(c)}</div><div class="bcm">{esc(m)}</div></div>' for c, m in cols)
        return f"""<div class="cmd xtra"><div class="ch"><span class="cn plain">Колонки доски</span></div>
<div class="does">Колонка и команда, которая создаёт в ней карточку. Карточки двигает оператор; агент — только свою из «агент» в архив.</div>
<div class="board">{cc}</div>
<div class="flowline"><span>{who('o')} <b>#now</b> — начало работы</span><span>→ коммиты с Task: tk_…</span><span>→ {who('o')} <b>#done</b> — участок чата к задаче</span><span>→ {who('a')} отчёт · {who('a')} <b>#evidence</b></span></div></div>"""
    if sid == "s3":
        return f"""<div class="cmd xtra"><div class="ch"><span class="cn plain">Правила и скиллы → агенты</span></div>
<div class="does">Правила и скиллы попадают в инструкции всех агентов во всех проектах.</div>
<div class="loopd">
<div class="ln1"><span class="nd o">#vision</span><i>→</i><span class="nd o">#rule</span><i>→</i><span class="nd s">AGENTS.md всех проектов</span></div>
<div class="ln1"><span class="nd o">#skill</span><i>→ агент пишет</i><span class="nd a">SKILL.md</span><i>→ оператор ставит</i><span class="nd s">скилл в проектах</span></div>
<div class="ln1 end"><i class="dsh"></i><span class="nd a">каждый агент читает их при старте чата</span></div>
<div class="ln1"><span class="nd o">#problem</span><i>→</i><span class="nd a">толкование</span><i>→</i><span class="nd o">#problem solved</span></div>
<div class="ln1"><span class="nd o">#prompt</span><i>→ библиотека →</i><span class="nd o">отправить снова</span></div>
</div></div>"""
    if sid == "s4":
        cores = "".join(f'<span class="nd s">{esc(c["name"])}</span>' for c in L["cores"])
        return f"""<div class="cmd xtra"><div class="ch"><span class="cn plain">Связи команд</span></div>
<div class="does">Коммиты → скан → архитектура. День → стендап. Core: файлы, задачи, лента заметок.</div>
<div class="loopd">
<div class="ln1"><span class="nd a">коммиты</span><i>→</i><span class="nd o">#scan</span><i>→</i><span class="nd a">файловая запись</span><i>→</i><span class="nd a">форма</span><i>→</i><span class="nd o">#page</span><i>→</i><span class="nd o">#map</span></div>
<div class="ln1"><span class="nd s">первый чат дня</span><i>→</i><span class="nd o">#standup</span><i>→ помощник: все чаты дня →</i><span class="nd a">стендап</span><i>→</i><span class="nd s">предложить #map</span></div>
<div class="ln1"><span class="nd o">#decision</span><i>→</i><span class="nd a">к задаче и к архитектуре</span></div>
<div class="ln1"><i>cores проекта:</i>{cores}</div>
</div></div>"""
    return ""


def family_sheet(sid: str, n: int, title: str, lede: str, cols: int, panels: list, model: dict, L: dict) -> str:
    body = "".join(panel(p) for p in panels) + extra(sid, L)
    return f"""<section class="sheet fam" id="{sid}" style="--cols:{cols}">{header(n, title, esc(lede) + " Пример: проект shopfront, задача «частичные возвраты».", model.get('today', ''))}
<div class="grid">{body}</div>
<div class="ffoot">Лимиты: код SP на {esc(model.get('today', ''))} (limits.py, corelib.py, описания MCP-инструментов, контракт, скиллы).</div></section>"""


def render(model: dict) -> str:
    L = live(model)
    sheets = [sheet1(model, L)]
    for k, (sid, title, lede, cols, panels) in enumerate(FAMILIES, 2):
        sheets.append(family_sheet(sid, k, title, lede, cols, panels, model, L))
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={W}">
<title>Архитектура SP</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>{''.join(sheets)}</body></html>"""


CSS = """
/* tokens: the article's infographics (scripts/feature_map/ARTICLE_STYLE.md); sizes x1.28 for the 2800-3000 px sheets */
:root{--page:#eef0f2;--surface:#fbfbf9;--tint:#f1f1ee;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e6e5df;--axis:#c3c2b7;--shot:#0e1013;--o:#eb6834;--s:#1baf7a;--a:#2a78d6}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--page);color:var(--ink)}
body{width:3000px;font-family:"Manrope",system-ui,sans-serif}
.sheet{width:2800px;background:var(--page);position:relative}
.canvas{position:relative}
.canvas>div,.canvas>header{position:absolute}
.wires{position:absolute;left:0;top:0;pointer-events:none}
code,.mono{font-family:"IBM Plex Mono",monospace;font-size:.92em}
code{font-weight:500;background:#eceae3;border-radius:5px;padding:0 5px}
header{left:40px;top:40px;width:2920px;display:grid;grid-template-columns:1fr 1000px;gap:60px;align-items:end}
.fam header{position:relative;left:auto;top:auto;width:auto;margin:0 40px;padding-top:40px}
.kicker{font:500 18px "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--ink2);display:flex;gap:13px;align-items:center}
.tag{display:inline-flex;align-items:center;border:2px solid var(--ink);border-radius:8px;padding:5px 12px;color:var(--ink);font:600 18px "IBM Plex Mono",monospace;letter-spacing:.02em}
h1{font:800 64px/1.06 "Manrope",sans-serif;letter-spacing:-.03em;margin:22px 0 14px}
.lede{font-size:23px;line-height:1.5;color:var(--ink2);max-width:1600px}
.lede b{color:var(--ink)}
.key{background:var(--surface);border-radius:18px;padding:20px 24px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px 22px;font-size:17px;color:var(--ink2)}
.kr{display:flex;gap:10px;align-items:center;white-space:nowrap}
.kr b{color:var(--ink);font-weight:700}
.who{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:var(--c);color:#fff;font:700 15px "IBM Plex Mono",monospace;flex:none}
.dsh{display:inline-block;width:44px;height:0;border-top:3px dashed var(--s);flex:none}
.eg{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:7px;background:var(--tint);color:var(--ink);font-size:16px;flex:none}

/* sheet 1 */
.lay{display:flex;flex-direction:column;gap:8px}
.lay .ln{display:inline-flex;width:38px;height:38px;border-radius:50%;border:2px solid var(--ink);align-items:center;justify-content:center;font:700 18px "IBM Plex Mono",monospace}
.lay b{font:700 26px/1.15 "Manrope";letter-spacing:-.01em}
.lay span:last-child{font-size:16px;line-height:1.45;color:var(--ink2)}
.altname{font-size:15px;line-height:1.5;color:var(--muted)}
.term{background:var(--shot);border-radius:13px;box-shadow:0 8px 26px rgba(0,0,0,.14)}
.tbar{height:46px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid rgba(255,255,255,.08)}
.tbar span{font:500 15px "IBM Plex Mono",monospace;color:#8a9099}
.tls{padding:22px 24px;display:flex;flex-direction:column;gap:20px}
.tl{font:400 18.5px "IBM Plex Mono",monospace;color:#d6dae0;white-space:nowrap}
.tl .pr{color:#6f7680;margin-right:10px}
.tl b{color:var(--o);font-weight:600}
.tl.ag{color:var(--a)}
.tfoot{position:absolute;left:24px;bottom:20px;font:400 15px "IBM Plex Mono",monospace;color:#8a9099}
.tfoot b{color:var(--o)}
.brw{background:var(--surface);border-radius:18px;overflow:hidden}
.bbar{height:50px;display:flex;align-items:center;padding:12px 18px 0}
.url{background:var(--tint);border-radius:8px;padding:5px 14px;font:500 14px "IBM Plex Mono",monospace;color:var(--ink2);flex:1}
.pgs{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:16px 18px 18px}
.pg{background:var(--tint);border-radius:13px;padding:16px 16px;height:132px;display:flex;flex-direction:column;justify-content:flex-end;gap:6px}
.pg b{font:700 17px/1.2 "Manrope"}
.pg span{font-size:14px;color:var(--ink2);line-height:1.35}
.bfoot{padding:0 20px;font-size:15px;color:var(--muted)}
.eps{background:var(--surface);border-radius:18px;padding:22px 22px}
.eh b{display:block;font:700 22px "Manrope";letter-spacing:-.01em}
.eh span{display:block;font-size:15px;line-height:1.4;color:var(--ink2);margin-top:4px}
.eprs{display:flex;flex-direction:column;gap:8px;margin:16px 0 14px}
.epr{display:grid;grid-template-columns:96px 1fr;gap:10px;align-items:baseline;border-top:1px solid var(--grid);padding-top:7px}
.epr b{font:600 16px "IBM Plex Mono",monospace}
.epr span{font-size:15px;color:var(--ink2)}
.epx{display:flex;flex-direction:column;gap:6px;font-size:15px;color:var(--ink2);background:var(--tint);border-radius:13px;padding:12px 14px}
.box{background:var(--surface);border-radius:18px;padding:22px 24px;display:flex;flex-direction:column;gap:8px}
.box.dash{background:transparent;border:2.5px dashed var(--s)}
.bt{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.bt b{font:700 25px "Manrope";letter-spacing:-.01em}
.bt .tag{font-size:15px;padding:2px 9px;border-width:1.5px;border-radius:7px}
.box>span{font-size:16.5px;line-height:1.42;color:var(--ink2)}
.box>span b{color:var(--ink)}
.stgs{display:flex;align-items:stretch;gap:6px;margin:10px 0 8px}
.stg{background:var(--tint);border-radius:13px;padding:13px 13px;flex:1;display:flex;flex-direction:column;gap:4px}
.stg b{font:700 16.5px/1.2 "Manrope"}
.stg span{font-size:13.5px;line-height:1.35;color:var(--ink2)}
.sa{font-style:normal;align-self:center;color:var(--muted);font-size:20px}
.core{background:var(--surface);border-radius:18px;padding:16px 18px;display:flex;flex-direction:column;gap:6px}
.core .ct{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.core b{font:700 22px/1.15 "Manrope";letter-spacing:-.01em}
.core span{font-size:15.5px;line-height:1.4;color:var(--ink2)}
.core .cn{margin-top:auto;font:500 14px "IBM Plex Mono",monospace;color:var(--ink2)}
.core .cf{margin-top:auto;font:400 13.5px "IBM Plex Mono",monospace;color:var(--muted)}
.core.un{background:transparent;border:2px dashed var(--axis)}
.core.note{background:transparent;padding-top:24px;gap:10px}
.core.note span{font-size:15.5px}
.pill{position:absolute;white-space:nowrap;font:500 14.5px "IBM Plex Mono",monospace;color:var(--ink2);background:var(--surface);border:2px solid var(--c);border-radius:8px;padding:2px 10px;z-index:4}
.shh{font-size:18px;color:var(--ink2)}
.shh b{color:var(--ink);font-weight:700}
.rig{display:flex;justify-content:space-between;align-items:center;background:var(--surface);border:2px solid var(--ink);border-radius:8px;padding:5px 10px;z-index:3}
.rig b{font:600 17px "IBM Plex Mono",monospace;color:var(--ink)}
.spc{display:flex;flex-direction:column;gap:10px;z-index:3}
.sp{position:relative;display:grid;grid-template-columns:20px 24px 1fr;gap:6px;align-items:start;background:var(--surface);border:2px solid var(--surface);border-radius:10px;padding:7px 8px;z-index:3}
.sp .sn{font:600 13px "IBM Plex Mono",monospace;color:var(--muted);padding-top:3px;text-align:center}
.sp .sb{display:inline-flex;width:22px;height:22px;border-radius:50%;color:#fff;font:700 12px "IBM Plex Mono",monospace;align-items:center;justify-content:center}
.sp .st{font-size:14.5px;line-height:1.3;color:var(--ink)}
.sp.un{border:2px dashed var(--axis);background:var(--page)}
.sp.sv{background:var(--tint);border-color:var(--tint)}
.sp.sv .sb{font-size:13px}
.sp.loop{border:2px dashed var(--s)}
.foot{font-size:16px;line-height:1.55;color:var(--ink2)}

/* sheets 2-5 */
.fam{padding-bottom:40px}
.grid{display:grid;grid-template-columns:repeat(var(--cols),1fr);gap:20px;margin:34px 40px 0}
.cmd{background:var(--surface);border-radius:18px;padding:24px 26px 20px;display:flex;flex-direction:column;gap:12px}
.ch{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.cn{font:600 32px "IBM Plex Mono",monospace;color:var(--ink);letter-spacing:-.01em}
.cn.plain{font:700 28px "Manrope";letter-spacing:-.01em}
.alias{font:500 16px "IBM Plex Mono",monospace;color:var(--muted)}
.n30{margin-left:auto;font:500 15px "IBM Plex Mono",monospace;color:var(--muted);display:flex;align-items:center;gap:8px;white-space:nowrap}
.does{font-size:18.5px;line-height:1.45;color:var(--ink2);font-weight:500}
.t1{background:var(--shot);border-radius:10px;padding:11px 16px;font:400 16px/1.4 "IBM Plex Mono",monospace;color:#d6dae0}
.t1 .pr{color:#6f7680;margin-right:10px}
.t1 b{color:var(--o);font-weight:600}
.cb{display:grid;grid-template-columns:1fr 290px;gap:18px}
.fam[style*="--cols:4"] .cb{grid-template-columns:1fr}
.flow{display:flex;flex-direction:column;gap:12px}
.row{display:grid;grid-template-columns:28px 1fr;gap:12px;align-items:start}
.rl{font:600 14px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:5px 0 4px}
.rl b{font:700 15.5px "Manrope";letter-spacing:0;text-transform:none;color:var(--ink)}
.rv1{font-size:16.5px;line-height:1.4}
.kept{font-size:14.5px;color:var(--muted);margin-top:3px}
.row ul{list-style:none;display:flex;flex-direction:column;gap:3px}
.row li{font-size:15.5px;line-height:1.4;color:var(--ink);padding-left:14px;position:relative}
.row li:before{content:"";position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--s)}
.lim{display:grid;grid-template-columns:170px 1fr;gap:12px;align-items:baseline;border-bottom:1px solid var(--grid);padding:4px 0}
.lim span{font-size:15.5px;color:var(--ink2)}
.lim b{font:600 15px/1.35 "IBM Plex Mono",monospace;color:var(--ink)}
.none{font-size:15.5px;color:var(--muted)}
.anote{font-size:14.5px;color:var(--muted);margin-top:4px}
.how{font-size:15px;line-height:1.4;color:var(--ink2)}
b.yes,b.no,b.part,b.na{color:var(--ink)}
.side{display:flex;flex-direction:column;gap:10px}
.rec{background:var(--tint);border-radius:13px;padding:12px 14px}
.rec.empty{background:transparent;border:2px dashed var(--axis);color:var(--muted);font-size:14.5px}
.rech{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.rr{display:grid;grid-template-columns:10px 92px 1fr;gap:8px;align-items:baseline;padding:4px 0;border-top:1px solid var(--grid)}
.rr i{width:10px;height:10px;border-radius:3px;display:inline-block}
.rk{font-size:13.5px;color:var(--ink2)}
.rv{font-size:14px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.seen{display:flex;flex-direction:column;gap:2px;background:var(--tint);border-radius:13px;padding:10px 14px}
.seen span{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.seen b{font-size:16px;font-weight:700}
.loopb{display:flex;align-items:center;gap:8px;font-size:14.5px;font-weight:600;color:var(--ink2)}
.loopb .dsh{width:30px}
.links{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-top:1px solid var(--grid);padding-top:12px;margin-top:auto}
.lt{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-right:4px}
.lk{font-size:14.5px;font-weight:600;color:var(--ink2);border:1.5px solid var(--axis);border-radius:7px;padding:2px 9px}
.xtra .board{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.bcol{background:var(--tint);border:2px solid var(--tint);border-radius:13px;padding:10px 12px;min-height:84px}
.bcol.hot{border-color:var(--ink);background:var(--surface)}
.bch{font:600 13px "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.bcm{font:600 17px "IBM Plex Mono",monospace;color:var(--ink);margin-top:8px}
.flowline{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:16px;align-items:center;color:var(--ink2)}
.flowline b{color:var(--ink)}
.flowline span{display:inline-flex;align-items:center;gap:6px}
.flowline .who{width:22px;height:22px;font-size:12px}
.loopd{display:flex;flex-direction:column;gap:14px;margin-top:6px}
.ln1{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ln1 i{font-style:normal;font-size:15px;color:var(--ink2)}
.nd{display:inline-flex;align-items:center;gap:6px;font-size:15.5px;font-weight:700;border-radius:10px;padding:5px 10px 5px 6px;background:var(--tint)}
.nd:before{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:50%;background:var(--c);color:#fff;font:700 10.5px "IBM Plex Mono",monospace;flex:none}
.nd.o{--c:var(--o);font-family:"IBM Plex Mono",monospace;font-weight:600}
.nd.o:before{content:"О"}
.nd.s{--c:var(--s)}.nd.s:before{content:"П"}
.nd.a{--c:var(--a)}.nd.a:before{content:"А"}
.ln1.end{padding-left:6px}
.ffoot{margin:24px 40px 0;font-size:16px;color:var(--ink2)}
"""
