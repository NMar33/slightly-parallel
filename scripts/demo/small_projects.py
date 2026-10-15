"""The two smaller demo projects: tg-notify (a Telegram notification bot) and
price-etl (a supplier price pipeline). Played through the same engine as
shopfront; ``link_cross`` ties them to shopfront once both are scheduled."""

from __future__ import annotations

from common import C
from engine import Chat, D, Repo, timedelta

TG = "tg-notify"
ETL = "price-etl"

SKELETONS: dict[str, dict[str, str]] = {
    TG: {
        "README.md": """# tg-notify

Sends order updates to customers in Telegram. Shopfront (and anything else
that can sign a request) posts an event to the intake API; a worker turns it
into a message and sends it through the bot, within Telegram's rate limits.

```
notify/api.py        FastAPI intake: POST /events
notify/worker.py     reads the Redis stream, renders, sends
notify/bot.py        aiogram bot: /start, /stop
notify/templates/    one template per event type
```

    docker compose up      # redis, api on :8100, worker, bot
    pytest -q
""",
        ".gitignore": "__pycache__/\n.venv/\n.env\n",
        "AGENTS.md": """# Working on tg-notify

- Python 3.12, aiogram 3, FastAPI, Redis streams. Tests: `pytest -q`.
- Never log a chat id together with an order number.
- The bot token comes from the environment only.
""",
        "CLAUDE.md": "@AGENTS.md\n",
        "pyproject.toml": """[project]
name = "tg-notify"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "aiogram==3.13.1",
  "fastapi==0.115.0",
  "uvicorn[standard]==0.30.6",
  "redis==5.1.0",
  "jinja2==3.1.4",
  "pydantic-settings==2.5.2",
]

[project.optional-dependencies]
dev = ["pytest==8.3.3", "pytest-asyncio==0.24.0", "fakeredis==2.25.0"]
""",
        "notify/__init__.py": "",
        "notify/settings.py": """from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = ""
    redis_url: str = "redis://localhost:6379/0"
    intake_secret: str = ""
    stream: str = "notify:events"


settings = Settings()
""",
        "notify/api.py": """from fastapi import FastAPI

app = FastAPI(title="tg-notify")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
""",
        "notify/bot.py": """from aiogram import Bot, Dispatcher

from .settings import settings

bot = Bot(settings.bot_token)
dp = Dispatcher()
""",
        "tests/__init__.py": "",
        "tests/conftest.py": """import fakeredis
import pytest


@pytest.fixture
def redis():
    return fakeredis.FakeRedis()
""",
        "Dockerfile": """FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY notify ./notify
CMD ["uvicorn", "notify.api:app", "--host", "0.0.0.0", "--port", "8100"]
""",
        "docker-compose.yml": """services:
  redis:
    image: redis:7
  api:
    build: .
    ports: ["8100:8100"]
    env_file: .env
    depends_on: [redis]
""",
    },
    ETL: {
        "README.md": """# price-etl

Turns supplier price drops into the one price file shopfront reads.

    extract   S3 bucket supplier-drops/<supplier>/<date>.csv
    transform DuckDB: validate, normalise to unit prices, apply margins
    publish   prices/latest.json + a manifest with a checksum

Runs from cron every 15 minutes (`etl/run.py`). Tests: `pytest -q`.
""",
        ".gitignore": "__pycache__/\n.venv/\n*.duckdb\ndata/\n",
        "AGENTS.md": """# Working on price-etl

- Python 3.12, DuckDB, boto3. Tests: `pytest -q`.
- Prices are integer cents after the normalise step. Never floats in the published file.
- A drop that fails validation is quarantined, never partially loaded.
""",
        "CLAUDE.md": "@AGENTS.md\n",
        "pyproject.toml": """[project]
name = "price-etl"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "duckdb==1.1.1",
  "boto3==1.35.29",
  "pydantic==2.9.2",
  "charset-normalizer==3.3.2",
]

[project.optional-dependencies]
dev = ["pytest==8.3.3", "moto==5.0.16"]
""",
        "etl/__init__.py": "",
        "etl/config.py": """from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    bucket: str = os.environ.get("DROPS_BUCKET", "supplier-drops")
    publish_bucket: str = os.environ.get("PUBLISH_BUCKET", "shopfront-prices")
    db_path: str = os.environ.get("ETL_DB", "prices.duckdb")


config = Config()
""",
        "etl/run.py": """\"\"\"One pass: extract new drops, transform, publish.\"\"\"

from .config import config


def main() -> int:
    print(f"price-etl: bucket={config.bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        "etl/extract/__init__.py": "",
        "etl/transform/__init__.py": "",
        "etl/publish/__init__.py": "",
        "sql/schema.sql": """CREATE TABLE IF NOT EXISTS raw_prices (
  supplier TEXT, sku TEXT, pack_size INTEGER, price TEXT, currency TEXT, drop_date DATE
);
""",
        "tests/__init__.py": "",
        "tests/test_run.py": """from etl.run import main


def test_main_runs():
    assert main() == 0
""",
        "crontab": "*/15 * * * * cd /srv/price-etl && .venv/bin/python -m etl.run >> /var/log/price-etl.log 2>&1\n",
    },
}


def at(t, minutes):
    return t + timedelta(minutes=minutes)


def _repo(sim, code: str, when) -> Repo:
    repo = Repo(sim.repos_dir / code, email=f"operator@{code}.dev")
    for path, text in SKELETONS[code].items():
        repo.write(path, text)
    repo.commit("Initial skeleton", when)
    sim.repos[code] = repo
    return repo


# key, created, title, lane, prio, impact, effort, tags, due, first status, desc, moves, extra
TG_TASKS = [
    ("tg-intake", (14, 9, 0), "Intake endpoint: POST /events with an HMAC signature", "api", "high", "5", "2",
     "api,security", "", "todo", "Callers sign the body with the shared secret; a bad signature is a 401 and nothing is queued.",
     [(14, 9, 40, "doing"), (15, 11, 30, "done")], {}),
    ("tg-queue", (14, 9, 5), "Redis stream between intake and the sender", "infra", "high", "5", "2",
     "queue,infra", "", "todo", "XADD on intake, a consumer group for the worker, XACK only after Telegram answered.",
     [(14, 14, 0, "doing"), (15, 16, 0, "done")], {}),
    ("tg-start", (14, 9, 10), "Bot /start with a one-time link token", "bot", "high", "5", "2",
     "bot,onboarding", "", "todo", "The deep link carries a token shopfront minted for the order; /start binds the chat to the customer.",
     [(16, 10, 0, "doing")], {}),
    ("tg-templates", (14, 9, 15), "Message templates per event type", "content", "med", "4", "1",
     "content,templates", "", "todo", "Jinja templates: order.paid, order.shipped, order.refunded. Plain text, no emoji.",
     [(17, 10, 0, "doing")], {}),
    ("tg-rate-limit", (16, 17, 0), "Respect Telegram rate limits: 30 messages a second, 1 a second per chat", "bot",
     "high", "4", "2", "bot,reliability", "2609-25", "backlog",
     "A token bucket in Redis for the global limit and one per chat.", [(21, 9, 30, "todo"), (21, 10, 0, "doing")],
     {"auto": True, "evidence": True}),
    ("tg-retries", (16, 17, 5), "Retry with backoff on 429 and 5xx", "bot", "high", "4", "2",
     "bot,reliability", "", "backlog", "Honour retry_after on 429; exponential backoff to five attempts, then the dead-letter stream.",
     [(21, 9, 31, "todo"), (22, 10, 0, "doing"), (22, 15, 0, "done")], {}),
    ("tg-order-paid", (23, 10, 0), "Order paid message to the customer", "bot", "high", "5", "2",
     "bot,orders", "2610-01", "todo", "When shopfront posts order.paid: the order number, the total and the delivery estimate.",
     [(28, 10, 0, "doing")], {"projects": "tg-notify,shopfront"}),
    ("tg-shipped", (23, 10, 5), "Order shipped message with the tracking link", "content", "med", "4", "1",
     "content,orders", "2610-06", "backlog", "Needs the tracking URL from shopfront's shipped event.",
     [(28, 17, 0, "todo")], {}),
    ("tg-unsubscribe", (23, 10, 10), "/stop unsubscribes and deletes the chat id", "bot", "med", "4", "1",
     "bot,privacy", "", "backlog", "Deleting is the point: no chat id kept after /stop.", [(28, 17, 5, "next")], {}),
    ("tg-ops-channel", (22, 16, 0), "Ops channel: disputes and failed jobs", "api", "low", "3", "2",
     "ops", "", "backlog", "A second chat for the operator: disputes from shopfront, dead-lettered messages.", [], {}),
    ("tg-i18n", (22, 16, 5), "German message templates", "content", "low", "3", "1", "content,i18n", "", "backlog",
     "Pick the template by the customer's shop language.", [], {}),
    ("tg-healthcheck", (14, 9, 20), "Health endpoint and a Docker healthcheck", "infra", "low", "2", "1",
     "infra", "", "todo", "", [(15, 9, 50, "doing"), (15, 10, 30, "done"), (22, 9, 0, "done-archived")], {}),
    ("tg-webhook-mode", (17, 16, 0), "Switch the bot from polling to webhook mode", "infra", "low", "2", "2",
     "infra,bot", "", "backlog", "Polling is fine at our volume. Revisit when there is a second bot.",
     [(21, 16, 0, "parked")], {}),
    ("tg-metrics", (29, 16, 0), "Prometheus metrics for sent and failed messages", "infra", "", "", "", "", "",
     "unclassified", "", [], {}),
]

ETL_TASKS = [
    ("etl-s3-ingest", (8, 9, 0), "Pick up supplier CSV drops from S3", "ingest", "high", "5", "2", "ingest,s3", "",
     "todo", "List supplier-drops/<supplier>/ for files newer than the last run; remember what was loaded by ETag.",
     [(8, 9, 30, "doing"), (9, 12, 0, "done")], {}),
    ("etl-schema", (8, 9, 5), "Validate each drop against the supplier schema", "ingest", "high", "5", "2",
     "ingest,quality", "", "todo", "Columns, types and a non-empty SKU. A failing file goes to quarantine/, whole.",
     [(9, 10, 0, "doing"), (9, 16, 0, "done")], {}),
    ("etl-encoding", (10, 11, 12), "Detect and convert Windows-1252 supplier files", "ingest", "high", "4", "1",
     "ingest,bug", "", "doing", "The supplier exports from Excel on Windows; 'Café' arrives as 'CafÃ©'.", [], {}),
    ("etl-normalise", (8, 9, 10), "Normalise currency and pack sizes to unit prices", "transform", "high", "5", "3",
     "transform", "", "todo", "Everything to EUR cents per single unit; the pack size comes from the supplier's column.",
     [(10, 9, 30, "doing"), (11, 15, 0, "done")], {}),
    ("etl-margin", (8, 9, 15), "Apply margin rules per category", "transform", "med", "4", "2", "transform,pricing",
     "2609-26", "backlog", "Margins live in sql/margins.csv; the published price rounds to .90.",
     [(17, 9, 30, "todo"), (24, 10, 0, "doing")], {"auto": True, "evidence": True}),
    ("etl-publish-feed", (11, 16, 0), "Publish the price file shopfront reads", "publish", "high", "5", "2",
     "publish,integration", "2609-30", "todo", "prices/latest.json plus manifest.json with a SHA-256; write the file first, the manifest last.",
     [(17, 10, 0, "doing")], {"projects": "price-etl,shopfront"}),
    ("etl-late-alert", (18, 15, 0), "Alert when a supplier drop is late", "infra", "med", "4", "1", "ops,alerts",
     "2609-29", "backlog", "The supplier drops by 06:00; no file by 07:30 is an alert.", [(24, 9, 0, "todo"), (25, 10, 0, "doing")], {}),
    ("etl-history", (18, 15, 5), "Keep price history for 90 days", "transform", "med", "3", "2", "transform,history",
     "", "backlog", "One row per SKU per change; enough for the price change report.", [(25, 16, 0, "todo")], {}),
    ("etl-second-supplier", (18, 15, 10), "Onboard the second supplier (XML feed)", "ingest", "med", "4", "3",
     "ingest", "2610-09", "backlog", "They send XML over SFTP. Convert to the same raw_prices shape at the edge.",
     [(25, 16, 5, "next")], {}),
    ("etl-backfill", (9, 16, 30), "Backfill August prices from the archive", "ingest", "low", "2", "1", "ingest",
     "", "todo", "", [(11, 10, 0, "doing"), (11, 12, 0, "done"), (22, 9, 0, "done-archived")], {}),
    ("etl-dashboard", (18, 15, 15), "Price change report for the operator", "publish", "low", "3", "2", "publish,report",
     "", "backlog", "Which SKUs moved more than 5% since last week.", [], {}),
    ("etl-prefect", (11, 16, 5), "Move from cron to Prefect", "infra", "low", "2", "3", "infra", "", "backlog",
     "Cron is enough for one pipeline. Park until the second supplier lands.", [(17, 9, 40, "parked")], {}),
    ("etl-dq-tests", (18, 15, 20), "Data quality tests: no negative prices, no tenfold jumps", "transform", "high",
     "4", "2", "quality,tests", "2610-02", "backlog", "", [(25, 16, 10, "todo")], {}),
    ("etl-currency-api", (25, 17, 0), "ECB rates instead of the fixed currency table", "transform", "", "", "", "", "",
     "unclassified", "One supplier started quoting in CHF.", [], {}),
]


def _tasks(sim, w, code: str, rows) -> None:
    for key, (d, h, m), title, lane, prio, impact, effort, tags, due, first, desc, moves, extra in rows:
        w.task(key, D(d, h, m), code, title, status=first, lane=lane, priority=prio, impact=impact,
               effort=effort, tags=tags, due=due, desc=desc, auto=extra.get("auto", False),
               evidence=extra.get("evidence", False), projects=extra.get("projects", ""))
        for md, mh, mm, st in moves:
            w.move(key, D(md, mh, mm), st)


# ---------------------------------------------------------------------------
# tg-notify
# ---------------------------------------------------------------------------

def _p(path, importance, blast, cov, novelty, why, action="modified", security=False):
    return {"path": path, "action": action, "importance": importance, "blast_radius": blast,
            "test_coverage": cov, "novelty": novelty, "security_surface": security, "why": why}


TG_PAGE = """## 1. What it is
tg-notify sends a shop's order updates to its customers in Telegram. Shopfront posts signed events; the bot delivers one plain message per event.
**Kind:** service. **Standing:** active, commits on most working days since 14 September; the last work was the order-paid message for shopfront. **Made how:** by the operator with coding agents; tests run on every change.

## 2. The live work
- **Order paid, end to end** — shopfront's `order.paid` event becomes a message with the order number and total (`notify/templates/order_paid.txt`). Working against a local shopfront; not yet on production.
- **Rate limits** — the token bucket (`notify/ratelimit.py`) is in review; a burst of 200 messages drained in 7 s without a 429.

## 3. What it does or has produced
- Intake — accepts signed events on POST /events · where: `notify/api.py` · seen: ran `pytest tests/test_api.py`, 9 passed · made by: agent run · checked by: automated tests
- Link a chat — /start with a one-time token binds a Telegram chat to a customer · where: `notify/bot.py` · seen: opened, and the start test passes · made by: agent run · checked by: automated tests
- Send with retries — 429 and 5xx retried with backoff, then dead-lettered · where: `notify/worker.py` · seen: ran `pytest tests/test_worker.py` · made by: agent run · checked by: automated tests
- Order paid message — rendered from a template · where: `notify/templates/order_paid.txt` · seen: opened the template · made by: agent run · checked by: person

## 4. How the main thing works
1. Shopfront signs the JSON body with the shared secret and posts it to `/events`.
2. The API checks the HMAC and appends the event to the Redis stream `notify:events`.
3. The worker reads the stream in a consumer group, renders the template, takes a token from the rate limiter and calls `sendMessage`.
4. The event is acknowledged only after Telegram answered; failures retry, then go to the dead-letter stream.

## 5. Ways in and out
- POST /events — signed intake for any sender · where: `notify/api.py` · seen: opened · made by: agent run · checked by: automated tests
- Telegram bot commands /start and /stop · where: `notify/bot.py` · seen: opened · made by: agent run · checked by: nobody

## 6. What it is made of
- Redis stream and consumer group — the queue between intake and sender · where: `notify/queue.py` · seen: opened · made by: agent run · checked by: automated tests
- Rate limiter — a token bucket in Redis, global and per chat · where: `notify/ratelimit.py` · seen: opened · made by: agent run · checked by: automated tests
**Built and run:** Python 3.12, aiogram 3, FastAPI, Redis 7 (`pyproject.toml`); `docker compose up` locally; not deployed yet.
**Old material:** none; the repository is two weeks old.

## 7. Rules the project keeps
- Never log a chat id with an order number · where: `AGENTS.md` · seen: opened · made by: person · checked by: nobody
- The bot token comes from the environment only · where: `notify/settings.py` · seen: opened · made by: person · checked by: nobody

## 8. People
- operator (owner) — asked for the order-paid message (29 Sep) · the message renders locally (29 Sep) · told: in chat.

## 9. What is owed
1. Order paid message for shopfront, due 1 Oct — still true on 29 Sep: the task is in doing.
2. /stop does not delete the chat id yet — `notify/bot.py` has no stop handler; checked by reading it.

## 10. Words, and what was not read
- **Words:** HMAC — the signature on the intake body (`notify/api.py`). Dead-letter stream — `notify:dead` (`notify/worker.py`).
- **Not read:** `docker-compose.yml` beyond the services list.
- **Searched and not found:** a deploy script — searched for deploy, fly, systemd.
"""

TG_MAP = {
    "template": "web-service",
    "rows": [
        {"kind": "runtime", "name": "Python 3.12", "what": "language of the api, worker and bot", "where": "pyproject.toml", "version": "3.12", "evidence": "computed"},
        {"kind": "framework", "name": "FastAPI", "what": "the intake API", "where": "notify/api.py", "version": "0.115.0", "evidence": "computed"},
        {"kind": "framework", "name": "aiogram", "what": "the Telegram bot framework", "where": "notify/bot.py", "version": "3.13.1", "evidence": "computed"},
        {"kind": "entry", "name": "uvicorn notify.api:app", "what": "starts the intake API", "where": "Dockerfile", "evidence": "opened Dockerfile"},
        {"kind": "entry", "name": "python -m notify.worker", "what": "starts the sender", "where": "notify/worker.py", "evidence": "opened notify/worker.py"},
        {"kind": "surface", "name": "Telegram chat", "what": "where the customer reads order updates", "where": "notify/bot.py", "evidence": "opened notify/bot.py"},
        {"kind": "api", "name": "POST /events", "what": "signed intake for order events", "where": "notify/api.py", "evidence": "opened notify/api.py"},
        {"kind": "module", "name": "notify/templates", "what": "one message template per event type", "where": "notify/templates", "evidence": "opened notify/templates/order_paid.txt"},
        {"kind": "module", "name": "notify/queue.py", "what": "stream append and consumer group", "where": "notify/queue.py", "evidence": "opened notify/queue.py"},
        {"kind": "module", "name": "notify/ratelimit.py", "what": "token buckets, global and per chat", "where": "notify/ratelimit.py", "evidence": "opened notify/ratelimit.py"},
        {"kind": "service", "name": "worker", "what": "reads the stream, renders, sends", "where": "notify/worker.py", "evidence": "opened notify/worker.py"},
        {"kind": "store", "name": "Redis streams", "what": "notify:events and notify:dead", "where": "docker-compose.yml", "evidence": "opened docker-compose.yml", "note": "runs outside the repository, in the redis container"},
        {"kind": "external", "name": "Telegram Bot API", "what": "sendMessage, with rate limits", "where": "notify/worker.py", "evidence": "opened notify/worker.py"},
        {"kind": "external", "name": "shopfront", "what": "the sender of order events", "where": "README.md", "evidence": "per README.md, not checked"},
        {"kind": "config", "name": "Settings", "what": "bot token, redis url, intake secret", "where": "notify/settings.py", "evidence": "opened notify/settings.py"},
        {"kind": "build", "name": "Dockerfile", "what": "one image for api and worker", "where": "Dockerfile", "evidence": "opened Dockerfile"},
        {"kind": "deploy", "name": "none", "what": "not deployed yet", "where": "README.md", "evidence": "searched deploy, fly, systemd"},
        {"kind": "test", "name": "pytest", "what": "api, worker and bot tests with fakeredis", "where": "tests", "evidence": "ran pytest -q"},
        {"kind": "auth", "name": "HMAC signature", "what": "the intake checks the body signature", "where": "notify/api.py", "evidence": "opened notify/api.py"},
        {"kind": "job", "name": "none", "what": "no scheduled work", "where": "README.md", "evidence": "searched cron, schedule"},
    ],
    "relations": [
        {"from": "POST /events", "verb": "writes", "to": "Redis streams"},
        {"from": "worker", "verb": "reads", "to": "Redis streams"},
        {"from": "worker", "verb": "uses", "to": "notify/templates"},
        {"from": "worker", "verb": "uses", "to": "notify/ratelimit.py"},
        {"from": "worker", "verb": "calls", "to": "Telegram Bot API"},
        {"from": "shopfront", "verb": "calls", "to": "POST /events"},
        {"from": "uvicorn notify.api:app", "verb": "starts", "to": "POST /events"},
        {"from": "python -m notify.worker", "verb": "starts", "to": "worker"},
        {"from": "pytest", "verb": "tests", "to": "worker"},
    ],
    "notes": {
        "shape": "A signed intake API, a Redis stream and a worker that sends Telegram messages within rate limits.",
        "main_path": "shopfront calls POST /events, which writes the stream; the worker reads it and calls the Telegram Bot API.",
        "runs_on": "docker compose on one machine; not deployed.",
        "not_found": "no deploy and no scheduled job — searched deploy, fly, systemd, cron.",
        "not_read": "tests/ beyond the file names.",
    },
}


def _tg(sim, w) -> None:
    repo = sim.repos[TG]
    P = TG

    # TG1 · 14–15 Sep · intake and the queue
    c = Chat(sim, P, "1d9e4b27-6c3a-4f81-9e52-b07d3a4c8e16", title="intake and queue", repo=repo,
             headline="Order updates in Telegram: a signed intake, a Redis stream, a sender")
    t = D(14, 9, 35)
    c.turn(t, "New project, tg-notify. Shopfront will post order events; customers get a Telegram message. Start with {tk:tg-intake}: "
              "POST /events, signed. Then {tk:tg-queue}.",
           "Plan: `POST /events` takes JSON `{type, order_id, customer_ref, payload}` with an `X-Signature` header, HMAC-SHA256 of the raw body "
           "with `intake_secret`. A bad or missing signature is a 401. Valid events go onto a Redis stream; the API never talks to Telegram. Go?",
           minutes=6)
    t = D(14, 9, 50)
    c.turn(t, "Go. And tell me why a stream and not RQ.",
           "Intake is in `notify/api.py` with `verify_signature` using `hmac.compare_digest`; `pytest -q`: 6 passed, including a body changed by one byte. "
           "Stream over RQ: a consumer group gives us acknowledgement after Telegram answers and a pending list to replay; RQ would need its own "
           "retry bookkeeping for that. Logged the choice.",
           minutes=48, commits=[C(20, "Signed intake endpoint", "notify/api.py", "notify/signing.py"),
                                C(40, "Intake tests: good, bad and missing signatures", "tests/test_api.py")],
           helpers=[(12, 15)])
    w.decision(D(14, 10, 35), P, c.agent_id, "Events travel on a Redis stream with a consumer group, not an RQ job queue",
               "The worker acknowledges an event only after Telegram answered, and the pending list is the replay log. "
               "Revisit if we need scheduled sends, which RQ does out of the box.",
               ["RQ jobs — rejected: retries and acknowledgement would be our own bookkeeping",
                "Celery — rejected: a broker and a result backend for one worker"], weight="normal", tags="queue")
    t = D(14, 14, 5)
    c.turn(t, "{tk:tg-queue} now.",
           "`notify/queue.py`: `append(event)` does XADD with `MAXLEN ~ 100000`; the worker reads with XREADGROUP as `sender`, "
           "XACK after a 200 from Telegram. A crashed worker leaves the event pending; on start it claims pending entries older than 60 s. "
           "`pytest -q`: 11 passed.", minutes=55,
           commits=[C(25, "Redis stream append and consumer group", "notify/queue.py", "notify/worker.py"),
                    C(48, "Worker claims stale pending events on start", "notify/worker.py", "tests/test_worker.py")])
    t = D(15, 9, 45)
    c.turn(t, "Morning. Quick one: {tk:tg-healthcheck}, then close out intake.",
           "`/health` checks Redis with PING; the Dockerfile has a HEALTHCHECK every 30 s. Intake needed one more thing: the body size is capped at 16 KB. "
           "`pytest -q`: 13 passed.", minutes=38,
           commits=[C(15, "Health endpoint pings Redis; Docker healthcheck", "notify/api.py", "Dockerfile"),
                    C(30, "Cap intake bodies at 16 KB", "notify/api.py", "tests/test_api.py")])
    w.standup(at(t, 2), P, c.agent_id, D(14),
              "Shopfront can post signed order events to tg-notify, and they wait on a Redis stream until a worker sends them.",
              ["New: POST /events accepts events signed with the shared secret and refuses anything else (Intake endpoint, {tk:tg-intake}).",
               "New: Events are kept on a Redis stream and acknowledged only after Telegram answered (Redis stream, {tk:tg-queue}).",
               "Decided: a stream with a consumer group rather than an RQ queue — normal."],
              "**Needs an answer:** none.\n**Next:** health check, then the bot's /start.\n**State:** tests pass; nothing deployed.", hours=4.5)
    w.decision(D(15, 10, 20), P, c.agent_id, "Intake is authenticated by an HMAC signature over the raw body, not by an IP allow-list",
               "Shopfront's outbound address changes with its host; a shared secret travels with the request and fails closed. "
               "Revisit if a sender cannot sign, or when a second sender needs its own secret.",
               ["IP allow-list — rejected: shopfront's egress address is not fixed",
                "mTLS — rejected: certificates to rotate for one sender"], weight="major", tags="security,api")
    t = D(15, 11, 25)
    c.turn(t, "Intake is good. #done {tk:tg-intake}", "{tk:tg-intake} is done.", minutes=1)

    # TG2 · 16–17 Sep · the bot and templates (Codex)
    c = Chat(sim, P, "7a3c5e90-2d4b-4e6f-8a19-c5b0e7d2f384", tool="codex", title="bot and templates", repo=repo,
             headline="The bot: linking a chat to a customer, and the message templates")
    t = D(16, 9, 55)
    c.turn(t, "You're on the bot. {tk:tg-start}: shopfront makes a one-time token per order; the customer taps a t.me link; /start binds the chat.",
           "Understood. The token will be 24 random bytes, base64url, stored in Redis with a 7-day TTL and deleted on first use. "
           "I'll read `notify/bot.py` and the settings first.", minutes=5)
    w.standup(at(t, 2), P, c.agent_id, D(15),
              "The sender survives a crash: pending events are claimed again when the worker starts.",
              ["New: The worker takes over events a crashed worker left pending after 60 seconds (Redis stream, {tk:tg-queue}).",
               "Changed: Intake refuses bodies over 16 KB.",
               "Cleanup: health endpoint and Docker healthcheck ({tk:tg-healthcheck})."],
              "**Needs an answer:** none.\n**Next:** /start with a one-time token.\n**State:** 13 tests pass.", hours=3.0)
    t = D(16, 10, 5)
    c.turn(t, "Go.",
           "`/start <token>` looks the token up, stores `chat_id` against `customer_ref`, deletes the token and answers "
           "'You'll get order updates here. Send /stop to end them.' An unknown or used token gets a plain explanation. `pytest -q`: 17 passed.",
           minutes=50, commits=[C(22, "Bot /start binds a chat with a one-time token", "notify/bot.py", "notify/links.py"),
                                C(44, "Tests for used and unknown tokens", "tests/test_bot.py")])
    t = D(16, 15, 10)
    c.turn(t, "#vision A customer never has to open email to know where their order is: every change reaches them in the chat they already use, within a minute.",
           "Kept as a vision. What we have covers 'within a minute' for paid; shipped and refunded need their events from shopfront first.",
           minutes=3)
    vis_turn = c.last_n
    w.interpret("vision", c, vis_turn, D(16, 15, 20),
                "Every order state a customer cares about — paid, shipped, delayed, refunded — arrives as one plain message in Telegram "
                "within a minute of the change in shopfront. Email stays the record; the chat is where they look. "
                "Measure: time from shopfront's event to Telegram's 200, p95 under 60 s.", note="first reading")
    t = D(17, 10, 0)
    c.turn(t, "{tk:tg-templates}: order.paid, order.shipped, order.refunded. Plain text, no emoji.",
           "Three Jinja templates in `notify/templates/`; `render(event)` picks by type and fails loudly on an unknown one. "
           "Amounts arrive in cents and are formatted by one filter. `pytest -q`: 22 passed.", minutes=42,
           commits=[C(20, "Message templates for paid, shipped and refunded", "=notify/templates/order_paid.txt::Order {{ order_number }} is paid: {{ total | money }}.\nWe will tell you here when it ships.\n",
                      "=notify/templates/order_shipped.txt::Order {{ order_number }} has shipped.\nTrack it: {{ tracking_url }}\n",
                      "=notify/templates/order_refunded.txt::Order {{ order_number }}: {{ amount | money }} refunded.\n", "notify/render.py"),
                    C(36, "Render tests and the money filter", "tests/test_render.py", "notify/render.py")])
    w.standup(at(t, 2), P, c.agent_id, D(16),
              "A customer can link their Telegram chat to their orders with the /start link shopfront gives them.",
              ["New: /start with a one-time token links a chat to a customer; a used or unknown token is explained ({tk:tg-start}).",
               "Decided: kept a vision — order updates reach the customer in their chat within a minute."],
              "**Needs an answer:** none.\n**Next:** message templates.\n**State:** 17 tests pass.", hours=2.5)
    t = D(17, 15, 40)
    c.turn(t, "#done {tk:tg-start}", "{tk:tg-start} is done. Templates are in review with you.", minutes=1)

    # TG3 · 21–22 Sep · rate limits and retries, first scan
    c = Chat(sim, P, "c28f6d13-9e1a-4b75-8d03-6a2e4f9b1c57", title="rate limits", repo=repo,
             headline="Sending within Telegram's limits, and retrying what fails")
    t = D(21, 10, 0)
    c.turn(t, "{tk:tg-rate-limit} and {tk:tg-retries}. Telegram allows 30 messages a second overall and about 1 a second per chat.",
           "Plan: two token buckets in Redis (Lua, so take-a-token is atomic): global 30/s, per chat 1/s. A 429 still happens sometimes; "
           "then we sleep `retry_after` and retry, and 5xx backs off 1, 2, 4, 8, 16 s before the dead-letter stream.", minutes=6)
    w.standup(at(t, 2), P, c.agent_id, D(17),
              "Order messages have templates for paid, shipped and refunded, rendered from shopfront's cents.",
              ["New: Templates for order paid, shipped and refunded; an unknown event type fails loudly ({tk:tg-templates})."],
              "**Needs an answer:** review the template wording.\n**Next:** rate limits and retries.\n**State:** 22 tests pass.", hours=1.5)
    t = D(21, 10, 15)
    c.turn(t, "Go.",
           "`notify/ratelimit.py` with the Lua bucket; the worker takes a global and a per-chat token before each send. "
           "A burst of 200 events to 40 chats drained in 7.1 s with no 429 against the test bot. `pytest -q`: 27 passed. Reported on the task with evidence.",
           minutes=70, commits=[C(30, "Token bucket rate limiter in Redis", "notify/ratelimit.py", "notify/worker.py"),
                                C(60, "Rate limiter tests", "tests/test_ratelimit.py")], helpers=[(20, 30)])
    w.report("tg-rate-limit", D(21, 11, 24), c.agent_id, "Global 30/s and per-chat 1/s buckets; 200 messages to 40 chats in 7.1 s, no 429.")
    w.evidence("tg-rate-limit", D(21, 11, 25), c.agent_id, [
        {"kind": "text", "title": "Burst test against the test bot",
         "body": "200 events, 40 chats\ndrained in 7.1 s\n429 responses: 0\nmax per chat per second: 1"},
        {"kind": "image", "title": "Messages sent per second during the burst", "mock": "chart"}])
    t = D(22, 10, 5)
    c.turn(t, "Retries now.",
           "429 honours `retry_after`; 5xx and timeouts back off 1–16 s; after five attempts the event goes to `notify:dead` with the last error. "
           "`pytest -q`: 31 passed.", minutes=58,
           commits=[C(25, "Retry 429 and 5xx with backoff, then dead-letter", "notify/worker.py"),
                    C(50, "Retry and dead-letter tests", "tests/test_worker.py")])
    w.standup(at(t, 2), P, c.agent_id, D(21),
              "Sending stays within Telegram's limits: a burst of 200 messages drained in seven seconds without a refusal.",
              ["New: Token buckets for the global and the per-chat limit; in review ({tk:tg-rate-limit})."],
              "**Needs an answer:** approve the rate limiter.\n**Next:** retries and the dead-letter stream.\n**State:** 27 tests pass.", hours=2.0)
    t = D(22, 15, 10)
    c.turn(t, "#done {tk:tg-retries}. Then #scan.",
           "{tk:tg-retries} is done. Scan written: intake, the stream, /start, templates, rate limits and retries. File entry and architecture form are in.",
           minutes=14, skills=["make-a-scan"])
    w.scan("tg-scan1", at(t, 5), P, c.agent_id,
           "tg-notify sends shopfront's order events to Telegram: signed intake, a Redis stream, and a worker that stays within rate limits",
           "Asked for a notification path from shopfront to customers in Telegram. It exists end to end on a local machine; nothing is deployed.",
           ["Shopfront can post signed events to POST /events.", "A customer links their chat with /start and a one-time token.",
            "Paid, shipped and refunded have templates.", "Sending respects 30/s overall and 1/s per chat.",
            "Failed sends retry with backoff and end in a dead-letter stream."],
           "Signature check — tests/test_api.py — checked.\nRate limits — burst test, 200 messages, no 429 — checked.\nDeployment — not done.", "notify")
    w.file_entry(at(t, 8), P, c.agent_id, "tg-scan1", "8 files · the whole sending path",
                 "The sending path from intake to Telegram, built over two weeks. The worker and the rate limiter carry the risk.",
                 ["notify/api.py — POST /events, verify_signature, body cap", "notify/worker.py — consumer group loop, retries, dead-letter",
                  "notify/ratelimit.py — Lua token bucket", "notify/bot.py — /start handler"],
                 [_p("notify/api.py", 5, 8, "covered", "new", "The only door in; a signature bug is an open relay.", "created", True),
                  _p("notify/worker.py", 5, 7, "covered", "new", "Acknowledges only after Telegram answered; the retry logic lives here.", "created"),
                  _p("notify/ratelimit.py", 4, 6, "covered", "new", "Atomic Lua bucket; a mistake here gets the bot throttled.", "created"),
                  _p("notify/bot.py", 4, 5, "partial", "new", "Binds a chat to a customer; tokens are single use.", "modified", True),
                  _p("notify/render.py", 2, 3, "covered", "pattern-follow", "Templates by event type."),
                  _p("notify/queue.py", 3, 6, "covered", "new", "XADD with a length cap.", "created")])
    w.arch_form(at(t, 11), P, c.agent_id, "tg-scan1", [
        {"op": "add", "type": "endpoint", "name": "POST /events", "path": ["notify/api.py"], "method": "POST", "route": "/events",
         "service": "api", "note": "HMAC-signed intake; 401 on a bad signature."},
        {"op": "add", "type": "queue", "name": "notify:events", "path": ["notify/queue.py"], "producer": "api", "consumer": "worker",
         "note": "Redis stream with the consumer group sender."},
        {"op": "add", "type": "service", "name": "worker", "path": ["notify/worker.py"], "start": "python -m notify.worker",
         "note": "Renders and sends, within rate limits."},
        {"op": "add", "type": "integration", "name": "Telegram Bot API", "path": ["notify/worker.py"], "direction": "outbound",
         "auth": "bot token", "note": "sendMessage; 429 honoured."},
        {"op": "add", "type": "auth", "name": "HMAC intake signature", "path": ["notify/signing.py"], "mechanism": "HMAC-SHA256",
         "checked_in": "notify/api.py", "note": "compare_digest over the raw body."},
        {"op": "add", "type": "tests", "name": "pytest suite", "path": ["tests/test_worker.py"], "command": "pytest -q",
         "covers": "intake, worker, bot, rate limiter", "note": "31 tests."},
    ])

    # TG4 · 28–29 Sep · order paid for shopfront, second scan, page and map (OpenCode)
    c = Chat(sim, P, "9b4e2a71-5f3c-4d8e-a6b1-e2c7094f5d38", tool="opencode", title="order paid message", repo=repo,
             headline="Order paid, end to end from shopfront to the customer's chat")
    t = D(28, 10, 5)
    c.turn(t, "{tk:tg-order-paid}. Shopfront will post order.paid this week. Make sure the message has the order number, total and delivery estimate.",
           "The template has the number and the total; the delivery estimate is missing from the event. I'll accept `delivery_estimate` "
           "as an optional ISO date and print 'Expected by Thursday 2 October' when present.", minutes=6)
    w.standup(at(t, 2), P, c.agent_id, D(22),
              "Failed sends are retried with backoff and end in a dead-letter stream instead of being lost.",
              ["Fixed: A 429 or a Telegram outage no longer drops the message: five attempts, then the dead-letter stream ({tk:tg-retries})."],
              "**Needs an answer:** none.\n**Next:** the order paid message for shopfront.\n**State:** 31 tests pass; not deployed.", hours=2.0)
    t = D(28, 10, 20)
    c.turn(t, "Yes, do that.",
           "Done: `order_paid.txt` prints the estimate when present; the event schema documents the field. Dedupe on `order_id` + type so "
           "shopfront's at-least-once delivery never sends twice. `pytest -q`: 35 passed.", minutes=46,
           commits=[C(18, "Order paid message with the delivery estimate", "notify/templates/order_paid.txt", "notify/render.py"),
                    C(38, "Dedupe events on order id and type", "notify/api.py", "tests/test_api.py")])
    w.task("tg-dedupe", D(28, 11, 10), P, "Dedupe key expires after 24 hours; a late retry would send twice", status="agent",
           lane="api", tags="ag_bug", agent=c.agent_id,
           desc="The dedupe key has a 24 h TTL. Shopfront retries for up to 3 days. Keep keys for 4 days.")
    t = D(28, 15, 30)
    c.turn(t, "Tested against local shopfront: message arrives. {tk:tg-templates} wording is approved. #done {tk:tg-templates}",
           "{tk:tg-templates} is done. {tk:tg-order-paid} stays in doing until shopfront sends from production.", minutes=2)
    t = D(29, 10, 10)
    c.turn(t, "#scan, and bring the architecture page and the map up to date.",
           "Scan, file entry and form written. Architecture page v1 and the first map of the program: 20 rows, 9 relations.",
           minutes=24, skills=["make-a-scan", "keep-the-architecture-page", "map-the-program"], helpers=[(4, 16)])
    w.standup(at(t, 1), P, c.agent_id, D(28),
              "The order paid message now carries the delivery estimate, and a repeated event from shopfront is sent only once.",
              ["New: Order paid message prints the delivery estimate when shopfront sends one ({tk:tg-order-paid}); waits on shopfront's production events.",
               "Fixed: A repeated order.paid from shopfront is sent once, not twice.",
               "Changed: Template wording approved ({tk:tg-templates})."],
              "**Needs an answer:** none.\n**Next:** scan and the architecture page.\n**State:** 35 tests pass.", hours=3.0)
    w.scan("tg-scan2", at(t, 5), P, c.agent_id,
           "The order paid message is ready for shopfront's production events, with the delivery estimate and exactly-once sending",
           "Asked for the order paid message end to end. It works against a local shopfront; production waits on shopfront's webhook.",
           ["Order paid prints the delivery estimate.", "Repeated events are sent once."],
           "Dedupe — tests/test_api.py — checked.\nEnd to end with local shopfront — checked by the operator.", "notify")
    w.file_entry(at(t, 8), P, c.agent_id, "tg-scan2", "4 files · order paid and dedupe",
                 "Two changes: the estimate in the paid message and dedupe at intake.",
                 ["notify/api.py — dedupe key on order_id and type", "notify/templates/order_paid.txt — estimate line"],
                 [_p("notify/api.py", 5, 8, "covered", "pattern-follow", "Dedupe at the door; a wrong key drops real messages.", security=True),
                  _p("notify/templates/order_paid.txt", 2, 2, "untested", "pattern-follow", "Wording only."),
                  _p("notify/render.py", 2, 3, "covered", "pattern-follow", "Date formatting for the estimate."),
                  _p("tests/test_api.py", 2, 1, "covered", "pattern-follow", "Dedupe cases.")])
    w.arch_form(at(t, 11), P, c.agent_id, "tg-scan2", [
        {"op": "add", "type": "feature", "name": "Order paid message", "path": ["notify/templates/order_paid.txt"],
         "note": "Number, total and the delivery estimate."},
        {"op": "change", "type": "endpoint", "name": "POST /events", "path": ["notify/api.py"], "method": "POST",
         "route": "/events", "service": "api", "note": "Dedupes on order id and type."},
        {"op": "add", "type": "debt", "name": "Dedupe keys expire before shopfront stops retrying", "path": ["notify/api.py"],
         "risk": "a retry after 24 h sends a second message", "note": "Keys should live 4 days."},
    ])
    w.arch_page(at(t, 15), P, c.agent_id, TG_PAGE, "First version: the sending path and what is owed to shopfront.")
    w.map(at(t, 20), P, c.agent_id, TG_MAP, "First map: web-service template, 20 rows.")

    # time
    w.timer(D(14, 16, 0), 45, P, task="tg-queue", note="Reading the Redis streams docs")
    w.timer(D(16, 14, 0), 30, P, task="tg-start", note="Testing /start on a phone")
    w.timer(D(21, 14, 30), 50, P, task="tg-rate-limit", note="Burst test against the test bot")
    w.timer(D(28, 16, 0), 40, P, task="tg-order-paid", note="End to end with local shopfront")
    w.auto_time(D(22, 13, 30), 35, P, task="tg-retries", note="auto")
    w.auto_time(D(29, 11, 0), 25, P, note="auto")


# ---------------------------------------------------------------------------
# price-etl
# ---------------------------------------------------------------------------

ETL_PAGE = """## 1. What it is
price-etl turns a supplier's daily price drop into the one price file shopfront reads. It serves the shop's operator, who sets margins, and shopfront, which reads prices.
**Kind:** tool. **Standing:** active since 8 September; the last work was the late-drop alert. **Made how:** by the operator with coding agents.

## 2. The live work
- **Publishing for shopfront** — `prices/latest.json` with a manifest (`etl/publish/feed.py`); in review, shopfront does not read it yet.
- **Late drops** — an alert when the supplier's file is not in by 07:30 (`etl/alerts.py`); in doing.
- **Margins** — per-category margins with .90 rounding (`etl/transform/margins.py`); in review.

## 3. What it does or has produced
- Ingest drops from S3 — new files by ETag, invalid ones quarantined whole · where: `etl/extract/s3.py` · seen: ran `pytest tests/test_extract.py`, passed · made by: agent run · checked by: automated tests
- Encoding repair — Windows-1252 files converted to UTF-8 · where: `etl/extract/encoding.py` · seen: ran against the 10 Sep drop · made by: agent run · checked by: automated tests
- Unit prices in cents — currency and pack size normalised · where: `etl/transform/normalise.py` · seen: opened, and the tests pass · made by: agent run · checked by: automated tests
- The price file — latest.json and manifest.json with a SHA-256 · where: `etl/publish/feed.py` · seen: opened a published file of 24 Sep · made by: agent run · checked by: agent

## 4. How the main thing works
1. Cron runs `etl/run.py` every 15 minutes.
2. New drops are listed in S3 by ETag, decoded to UTF-8 and validated; a failing file goes to `quarantine/`.
3. DuckDB normalises to EUR cents per unit and applies the margins.
4. The feed is written first, the manifest with its checksum last, so a reader never sees half a file.

## 5. Ways in and out
- Supplier drops in S3, `supplier-drops/<supplier>/<date>.csv` · where: `etl/config.py` · seen: opened · made by: person · checked by: nobody
- The published price file for shopfront · where: `etl/publish/feed.py` · seen: opened · made by: agent run · checked by: agent

## 6. What it is made of
- DuckDB database with raw, normalised and published tables · where: `sql/schema.sql` · seen: opened · made by: agent run · checked by: automated tests
**Built and run:** Python 3.12, DuckDB 1.1, boto3 (`pyproject.toml`); cron on one VM (`crontab`).
**Old material:** none.

## 7. Rules the project keeps
- A drop that fails validation is quarantined, never partly loaded · where: `AGENTS.md` · seen: opened · made by: person · checked by: automated tests
- No floats in the published file · where: `AGENTS.md` · seen: opened · made by: person · checked by: automated tests

## 8. People
- operator (owner) — asked for the late-drop alert (24 Sep) · alert in progress · told: in chat.

## 9. What is owed
1. Publish the price file for shopfront, due 30 Sep — still true on 25 Sep: in review.
2. Late-drop alert, due 29 Sep — in doing.
3. Rounding differs between DuckDB and Python for half cents — seen in a test on 25 Sep.

## 10. Words, and what was not read
- **Words:** drop — one supplier CSV for one day (`README.md`). Quarantine — `quarantine/` prefix in the drops bucket (`etl/extract/s3.py`).
- **Not read:** `crontab` beyond its one line.
- **Searched and not found:** a second supplier's parser — searched xml, sftp.
"""


def _etl(sim, w) -> None:
    repo = sim.repos[ETL]
    P = ETL

    # ETL1 · 8–9 Sep · ingest and validation
    c = Chat(sim, P, "58a0e3f6-7b2d-4c19-9f84-d1a6c3e5b702", title="ingest", repo=repo,
             headline="Supplier price drops in, one price file out")
    t = D(8, 9, 25)
    c.turn(t, "price-etl: the supplier drops a CSV in S3 every morning. Shopfront needs one clean price file. Start with {tk:etl-s3-ingest}.",
           "Plan: list `supplier-drops/<supplier>/` for keys newer than the last run, remember loaded files by ETag in DuckDB, and load raw rows "
           "untouched into `raw_prices`. Transforms run on DuckDB SQL rather than pandas. Go?", minutes=6)
    t = D(8, 9, 40)
    c.turn(t, "Go. DuckDB is fine.",
           "`etl/extract/s3.py`: `new_drops()` and `load_raw()`; a loaded ETag is never loaded twice. Tests use moto for S3. `pytest -q`: 7 passed.",
           minutes=62, commits=[C(25, "List and load new supplier drops from S3", "etl/extract/s3.py", "etl/run.py"),
                                C(55, "Extract tests with moto", "tests/test_extract.py")], helpers=[(15, 25)])
    w.decision(D(8, 10, 30), P, c.agent_id, "Transforms run as DuckDB SQL over the raw table, not pandas",
               "The data is one supplier and 40,000 rows; SQL keeps each step readable and testable, and DuckDB reads the CSV directly. "
               "Revisit if a transform needs a library only Python has.",
               ["pandas DataFrames — rejected: steps hidden in method chains, memory for no gain",
                "Postgres staging tables — rejected: a server to run for a batch job"], weight="normal", tags="transform")
    t = D(9, 10, 5)
    c.turn(t, "{tk:etl-schema}: a bad file must not half-load.",
           "Validation runs before any insert: column names, a non-empty SKU, a parseable price. One bad row fails the file; it moves to "
           "`quarantine/<supplier>/<date>.csv` with a `.why.txt` beside it. `pytest -q`: 12 passed.", minutes=54,
           commits=[C(20, "Validate a drop before loading; quarantine failures whole", "etl/extract/validate.py", "etl/extract/s3.py"),
                    C(45, "Validation tests", "tests/test_validate.py")])
    w.standup(at(t, 2), P, c.agent_id, D(8),
              "New supplier drops are picked up from S3 and loaded once each.",
              ["New: Supplier drops are listed and loaded from S3, each file once by its ETag ({tk:etl-s3-ingest}).",
               "Decided: transforms in DuckDB SQL rather than pandas — normal."],
              "**Needs an answer:** none.\n**Next:** validation.\n**State:** 7 tests pass.", hours=3.0)
    t = D(9, 12, 5)
    c.turn(t, "#done {tk:etl-s3-ingest}", "{tk:etl-s3-ingest} is done.", minutes=1)

    # ETL2 · 10–11 Sep · normalise, and the encoding problem
    c = Chat(sim, P, "e71b4c09-3a5f-4e28-b7d6-0c9f2e8a1b43", title="normalise and encoding", repo=repo,
             headline="Unit prices in cents, and files that arrive in the wrong encoding")
    t = D(10, 9, 30)
    c.turn(t, "{tk:etl-normalise}: EUR cents per single unit. Pack size is in the supplier's column.",
           "Reading the first three drops before writing the SQL. The supplier uses a comma as the decimal separator and pack sizes like '6x'. Plan in the next turn.",
           minutes=8)
    w.standup(at(t, 2), P, c.agent_id, D(9),
              "A supplier file with one bad row is now refused whole and set aside with the reason.",
              ["New: Drops are validated before loading; a failing file goes to quarantine with a note saying why ({tk:etl-schema})."],
              "**Needs an answer:** none.\n**Next:** normalise to unit prices.\n**State:** 12 tests pass.", hours=2.5)
    t = D(10, 11, 10)
    c.turn(t, "#problem Today's drop failed validation: product names like 'CafÃ© crème' — the file is Windows-1252, not UTF-8. Every morning this happens we have no prices.",
           "Kept as a problem. Confirmed: the file has no BOM and bytes 0xE9 for 'é'. It was quarantined, so nothing wrong was loaded — but nothing was loaded at all. "
           "Put {tk:etl-encoding} on it.", minutes=9)
    prob_turn = c.last_n
    w.interpret("problem", c, prob_turn, D(10, 11, 25),
                "The supplier exports from Excel on Windows, so some drops arrive in Windows-1252 while we decode UTF-8. The file fails "
                "validation and is quarantined whole: no wrong prices, but that day's prices never arrive. Blocks every morning's update "
                "until decoding detects the encoding. Owner: the ingest step ({tk:etl-encoding}).", note="first reading")
    t = D(10, 13, 30)
    c.turn(t, "Fix it.",
           "`etl/extract/encoding.py` detects with charset-normalizer and converts to UTF-8 before validation; the original bytes are kept in `raw/`. "
           "Re-ran today's drop: 38,412 rows loaded, 'Café crème' correct. `pytest -q`: 15 passed.", minutes=44,
           commits=[C(20, "Detect and convert Windows-1252 drops before validation", "etl/extract/encoding.py", "etl/extract/s3.py"),
                    C(38, "Encoding tests with a real Windows-1252 sample", "tests/test_encoding.py")])
    w.decision(D(10, 14, 10), P, c.agent_id, "Detect the encoding of every drop and convert to UTF-8 at the edge",
               "Asking the supplier to change their export was tried and is not in our control. Detection is one library and keeps the original bytes.",
               ["Ask the supplier to export UTF-8 — rejected: they cannot change their Excel export",
                "Always decode as Windows-1252 — rejected: some drops are UTF-8 and would break the other way"], weight="minor")
    t = D(10, 16, 0)
    c.turn(t, "#done {tk:etl-encoding}", "{tk:etl-encoding} is done. The problem stays open until a week of drops passes.", minutes=1)
    w.kept_update("problem", c, prob_turn, D(18, 9, 0), status="resolved", resolved_date="2609-18")
    t = D(11, 9, 40)
    c.turn(t, "Back to {tk:etl-normalise}.",
           "`sql/normalise.sql`: price text → cents with the comma handled, pack size parsed from '6x', '12 x', 'single'; unit price = pack price / size, "
           "rounded half-up to the cent. 41 SKUs had no pack size and are marked, not guessed. `pytest -q`: 21 passed.", minutes=66,
           commits=[C(30, "Normalise to EUR cents per unit", "=sql/normalise.sql::CREATE OR REPLACE TABLE unit_prices AS\nSELECT supplier, sku,\n       CAST(round(CAST(replace(price, ',', '.') AS DECIMAL(12,2)) * 100 / pack_size) AS BIGINT) AS unit_cents,\n       drop_date\nFROM raw_prices WHERE pack_size > 0;\n", "etl/transform/normalise.py"),
                    C(58, "Normalise tests", "tests/test_normalise.py")])
    w.standup(at(t, 2), P, c.agent_id, D(10),
              "Supplier files in the Windows encoding are read correctly instead of being refused.",
              ["Fixed: Drops in Windows-1252 are converted to UTF-8 before validation; the 10 Sep drop loaded with 38,412 rows ({tk:etl-encoding}).",
               "Decided: detect every drop's encoding at the edge — minor."],
              deviation=["The 10 Sep drop was refused because of its encoding, so that morning had no new prices. Fixed the same day."],
              detail="**Needs an answer:** none.\n**Next:** normalise to unit prices.\n**State:** 15 tests pass.", hours=3.5)
    t = D(11, 15, 5)
    c.turn(t, "Looks right. #done", "{tk:etl-normalise} is done.", minutes=1)

    # ETL3 · 17–18 Sep · publishing the feed
    c = Chat(sim, P, "0f6d9a84-c2e7-4b30-8a5f-7e1d3b9c6a25", title="publish feed", repo=repo,
             headline="The price file shopfront reads: written whole, checked by a manifest")
    t = D(17, 10, 5)
    c.turn(t, "{tk:etl-publish-feed}. Shopfront will poll it every 15 minutes. How do we make sure it never reads half a file?",
           "Write `prices/<run-id>.json` first, then `prices/latest.json`, then `manifest.json` with the run id and a SHA-256 of latest. "
           "Shopfront reads the manifest, then the file, and checks the hash. A reader between the two writes sees the old manifest and the old file.",
           minutes=7)
    w.standup(at(t, 2), P, c.agent_id, D(11),
              "Every supplier price is now a unit price in cents.",
              ["New: Normalised unit prices in EUR cents; 41 SKUs without a pack size are marked, not guessed ({tk:etl-normalise})."],
              "**Needs an answer:** none.\n**Next:** publish the price file for shopfront.\n**State:** 21 tests pass.", hours=3.0)
    t = D(17, 10, 20)
    c.turn(t, "#decision A file with a manifest, not an API. Go.",
           "Logged as major. Built `etl/publish/feed.py`: the run file, latest, then the manifest; integer cents only, sorted by SKU. "
           "`pytest -q`: 26 passed.", minutes=58,
           commits=[C(30, "Publish the price file and its manifest", "etl/publish/feed.py", "etl/run.py"),
                    C(50, "Publish tests: order of writes and checksum", "tests/test_publish.py")])
    w.decision(D(17, 10, 25), P, c.agent_id, "Prices are published as a JSON file with a checksummed manifest on S3, not served by an API",
               "Shopfront polls a file; nothing of ours has to be up when it reads. The manifest is written last, so a reader never sees half a publish. "
               "Revisit if shopfront needs prices changed within a minute.",
               ["A small prices API — rejected: a service to keep up for a file that changes four times an hour",
                "Write straight into shopfront's database — rejected: couples the two schemas"], weight="major",
               excerpt="Operator: #decision A file with a manifest, not an API. Go.", tags="publish,integration")
    t = D(18, 10, 0)
    c.turn(t, "#scan", "Scan, file entry and architecture form written.", minutes=12, skills=["make-a-scan"])
    w.standup(at(t, 1), P, c.agent_id, D(17),
              "Prices are published as one file with a manifest that shopfront can check before trusting it.",
              ["New: latest.json and manifest.json with a SHA-256; in progress for shopfront ({tk:etl-publish-feed}).",
               "Decided: a file with a manifest rather than an API — major."],
              "**Needs an answer:** none.\n**Next:** margins.\n**State:** 26 tests pass.", hours=2.5)
    w.scan("etl-scan1", at(t, 4), P, c.agent_id,
           "Supplier drops become one checksummed price file: ingest, encoding repair, validation, unit prices and publishing",
           "Asked for a pipeline from the supplier's drop to a file shopfront can read. It runs from cron; shopfront does not read it yet.",
           ["Drops are loaded once each from S3.", "Windows-1252 files are converted.", "A bad file is quarantined whole.",
            "Prices are EUR cents per unit.", "latest.json and manifest.json are published."],
           "Order of writes — tests/test_publish.py — checked.\nShopfront reading it — not done.", "etl")
    w.file_entry(at(t, 7), P, c.agent_id, "etl-scan1", "9 files · the pipeline end to end",
                 "The whole pipeline, first pass. Validation and the publish order carry the risk.",
                 ["etl/extract/s3.py — new_drops, load_raw", "etl/extract/validate.py — validate, quarantine",
                  "etl/publish/feed.py — publish, write order"],
                 [_p("etl/extract/s3.py", 4, 6, "covered", "new", "Loads each file once; a wrong ETag check loads twice.", "created"),
                  _p("etl/extract/validate.py", 5, 7, "covered", "new", "The gate: nothing half-loaded.", "created"),
                  _p("etl/extract/encoding.py", 3, 5, "covered", "new", "Converts before validation.", "created"),
                  _p("sql/normalise.sql", 5, 8, "partial", "new", "Every price shopfront shows passes through this.", "created"),
                  _p("etl/publish/feed.py", 5, 9, "covered", "new", "What shopfront reads; write order matters.", "created")])
    w.arch_form(at(t, 10), P, c.agent_id, "etl-scan1", [
        {"op": "add", "type": "job", "name": "price-etl run", "path": ["crontab"], "schedule": "every 15 minutes",
         "note": "cron runs etl/run.py."},
        {"op": "add", "type": "database", "name": "prices.duckdb", "path": ["sql/schema.sql"], "engine": "duckdb 1.1",
         "tables": "raw_prices, unit_prices", "note": "Local file on the VM."},
        {"op": "add", "type": "files", "name": "prices/latest.json", "path": ["etl/publish/feed.py"], "format": "json",
         "writer": "etl/publish/feed.py", "note": "Integer cents; manifest written last."},
        {"op": "add", "type": "integration", "name": "S3 supplier drops", "path": ["etl/extract/s3.py"], "direction": "inbound",
         "auth": "IAM role", "note": "Read-only on supplier-drops."},
        {"op": "add", "type": "rule", "name": "Quarantine a failing drop whole", "path": ["etl/extract/validate.py"],
         "check": "tests/test_validate.py", "enforced_in": "etl/extract/validate.py", "note": "Never partly loaded."},
    ])

    # ETL4 · 24–25 Sep · margins, late alert, second scan and page
    c = Chat(sim, P, "a93c1e52-4d8b-4f06-b2e9-5c7a1d0f3e68", title="margins and alerts", repo=repo,
             headline="Margins per category, and knowing when the supplier is late")
    t = D(24, 10, 10)
    c.turn(t, "{tk:etl-margin}: margins per category from a CSV, published prices end in .90.",
           "Margins in `sql/margins.csv`; `etl/transform/margins.py` joins by category and rounds up to the next .90. A SKU with no category "
           "margin keeps the default 40% and is listed in the run log.", minutes=8)
    w.standup(at(t, 2), P, c.agent_id, D(18),
              "The pipeline was scanned: ingest, encoding repair, validation, unit prices and the published file.",
              ["Architecture: first scan of the pipeline; the published file is the one surface shopfront will depend on."],
              "**Needs an answer:** none.\n**Next:** margins, then the late-drop alert.\n**State:** 26 tests pass.", hours=1.0)
    t = D(24, 10, 25)
    c.turn(t, "Go.",
           "Done, with evidence on the task: 38,412 SKUs priced, 212 on the default margin. One oddity: DuckDB and Python round a half cent "
           "differently; noted on the board. `pytest -q`: 31 passed.", minutes=61,
           commits=[C(25, "Margins per category with .90 rounding", "=sql/margins.csv::category,margin_pct\napparel,55\nhome,45\nkitchen,45\n", "etl/transform/margins.py"),
                    C(52, "Margin tests", "tests/test_margins.py")])
    w.report("etl-margin", D(24, 11, 25), c.agent_id, "Margins per category with .90 rounding; 212 SKUs on the default margin.")
    w.evidence("etl-margin", D(24, 11, 26), c.agent_id, [
        {"kind": "text", "title": "Run of 24 Sep",
         "body": "SKUs priced: 38,412\non default margin: 212\nprices ending .90: 100%\nlargest change vs 23 Sep: +4.1% (kitchen)"}])
    w.task("etl-rounding", D(24, 11, 30), P, "Half-cent rounding differs between DuckDB and Python", status="agent",
           lane="transform", tags="ag_bug", agent=c.agent_id,
           desc="DuckDB rounds 0.5 away from zero, Python's round() to even. Use one rounding function in both places.")
    t = D(25, 10, 5)
    c.turn(t, "{tk:etl-late-alert}: no drop by 07:30 means an alert.",
           "`etl/alerts.py` checks at 07:30 for today's key; if missing it posts to the ops webhook with the last drop's time. "
           "Weekends are skipped — the supplier does not drop then. `pytest -q`: 34 passed.", minutes=44,
           commits=[C(20, "Alert when the supplier drop is late", "etl/alerts.py", "crontab"),
                    C(38, "Late alert tests", "tests/test_alerts.py")])
    w.standup(at(t, 2), P, c.agent_id, D(24),
              "Published prices now include the category margins and end in .90.",
              ["New: Margins per category with .90 rounding; in review ({tk:etl-margin}).",
               "New: Agent note on the board: half-cent rounding differs between DuckDB and Python."],
              "**Needs an answer:** approve the margins.\n**Next:** the late-drop alert.\n**State:** 31 tests pass.", hours=2.0)
    t = D(25, 15, 30)
    c.turn(t, "#scan and write the architecture page.",
           "Scan, file entry and form written; architecture page v1 is up.", minutes=18,
           skills=["make-a-scan", "keep-the-architecture-page"])
    w.scan("etl-scan2", at(t, 4), P, c.agent_id,
           "Published prices carry the category margins, and a late supplier drop now raises an alert at 07:30",
           "Asked for margins and a late-drop alert. Margins are in review; the alert works in tests and is scheduled in cron.",
           ["Margins per category, rounded to .90.", "A missing drop at 07:30 alerts the ops webhook."],
           "Margins — run of 24 Sep, 38,412 SKUs — checked.\nAlert — tests/test_alerts.py — checked; not yet fired for real.", "etl")
    w.file_entry(at(t, 7), P, c.agent_id, "etl-scan2", "6 files · margins and the late alert",
                 "Two features on top of the pipeline.",
                 ["etl/transform/margins.py — apply_margins, round_to_90", "etl/alerts.py — check_late_drop"],
                 [_p("etl/transform/margins.py", 5, 8, "covered", "new", "Every published price passes through the margin.", "created"),
                  _p("sql/margins.csv", 4, 8, "untested", "new", "Data, not code: a typo here reprices a category.", "created"),
                  _p("etl/alerts.py", 3, 3, "covered", "new", "Only fires on a missing file.", "created"),
                  _p("crontab", 3, 5, "untested", "pattern-follow", "Second line for the 07:30 check.")])
    w.arch_form(at(t, 10), P, c.agent_id, "etl-scan2", [
        {"op": "add", "type": "feature", "name": "Category margins", "path": ["etl/transform/margins.py"],
         "note": "Rounded up to .90."},
        {"op": "add", "type": "job", "name": "late drop check", "path": ["etl/alerts.py"], "schedule": "07:30 on weekdays",
         "note": "Posts to the ops webhook."},
        {"op": "add", "type": "debt", "name": "Two rounding rules", "path": ["etl/transform/margins.py"],
         "risk": "a half cent differs between the SQL and Python paths", "note": "One rounding function needed."},
    ])
    w.arch_page(at(t, 14), P, c.agent_id, ETL_PAGE, "First version: the pipeline, the published file and what is owed.")

    # time
    w.timer(D(8, 14, 0), 60, P, task="etl-s3-ingest", note="Setting up the bucket and IAM role")
    w.timer(D(10, 12, 0), 35, P, task="etl-encoding", note="Talking to the supplier about their export")
    w.timer(D(17, 14, 0), 45, P, task="etl-publish-feed", note="Checking the file against shopfront's reader")
    w.timer(D(24, 14, 30), 30, P, task="etl-margin", note="Margin table with the operator's numbers")
    w.auto_time(D(11, 13, 0), 40, P, task="etl-normalise", note="auto")
    w.auto_time(D(25, 11, 0), 30, P, task="etl-late-alert", note="auto")


def setup(sim, w) -> None:
    _repo(sim, ETL, D(8, 8, 45))
    _repo(sim, TG, D(14, 8, 30))
    _tasks(sim, w, TG, TG_TASKS)
    _tasks(sim, w, ETL, ETL_TASKS)
    _tg(sim, w)
    _etl(sim, w)


def link_cross(sim, w) -> None:
    for key in ("tg-order-paid", "tg-shipped", "tg-unsubscribe"):
        w.update(key, D(24, 9, 0), sprint="s4")
    w.link("order-webhook-out", "tg-order-paid", "blocks", D(28, 14, 30))
    w.link("etl-publish-feed", "price-feed", "blocks", D(28, 17, 20))
