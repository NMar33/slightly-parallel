"""shopfront's entry points, cores, #publish cards and pins.

Entry points: the operator types #entrypoint in a chat; the agent asks the
server which topic it means (MCP entrypoint_ask) and shows its offer; the
operator answers with the number; the agent writes the record, the ways
in, where it stopped, screenshots of the ways that are up, and the topic
of the tasks it named — the order the contract gives. Other chats add a
stop later. Cores: #core-new in two chats, #core-note from two later ones. Publish: the operator's #publish keeps a message as a card,
the agent writes it (publish_write): the context under the operator's text,
the task, a screenshot, a file, a link; one card's text the agent writes
from "#publish about …"; a later chat adds to a card with #publish pu_…;
the operator places two cards in a document. Pins: #pin, #carry and #fork-later in the operator's
messages, adopted from the chat log like #important.

Played after the chats (build_example.py): every turn here comes after the
chat's last turn in shopfront_chats_*.py.
"""

from __future__ import annotations

import base64
import zlib
from typing import Any

from engine import D, mock_screen

P = "shopfront"


def _png(kind: str, key: str) -> str:
    return base64.b64encode(mock_screen(kind, seed=zlib.crc32(key.encode()) % 97)).decode()


def ask(sim, chat, key: str, name: str) -> Any:
    """entrypoint_ask right after the operator's #entrypoint in this turn.
    Keeps the offer to show (``<key>_show``) and the number of the new-topic
    line the operator will answer with (``<key>_n``). Made as the turn is
    scheduled: the turn it runs in is the chat's next."""
    turn = chat.turns + 1

    def run() -> None:
        sim.adopt()
        cmd = sim.capture.keep_id("entrypoint", chat.project, chat.agent_id, turn)
        r = sim.post("/api/entrypoints/ask", {"agent_id": chat.agent_id, "id": cmd, "name": name}, agent=True)
        sim.ids[f"{key}_show"] = r["show"].strip()
        sim.ids[f"{key}_n"] = str(next(ln["n"] for ln in r["lines"] if ln.get("kind") == "new"))
    return run


def record(sim, chat, key: str, text: str, ways: list[dict], stop: tuple[str, str],
           shots: list[tuple[int, str, str]], tasks: list[str]) -> Any:
    """After the operator's number: entrypoint_answer, the record
    (interpret), each way in, the topic of the tasks, one stop and a shot
    of the ways that are up — ``shots``: (way index, caption, mock kind)."""
    def run() -> None:
        r = sim.post("/api/entrypoints/answer", {"agent_id": chat.agent_id, "number": int(sim.ids[f"{key}_n"])},
                     agent=True)
        ep = r["id"]
        sim.ids[key] = ep
        sim.adopt()
        sim.post(f"/api/entrypoints/{ep}/interpretation",
                 {"text": sim.fill(text), "note": "first version, from this chat", "agent_id": chat.agent_id}, agent=True)
        way_ids = []
        for way in ways:
            got = sim.post(f"/api/entrypoints/{ep}/ways", {"agent_id": chat.agent_id, "way": way}, agent=True)
            way_ids.append(got["way"]["id"])
        for t in tasks:
            sim.post(f"/api/tasks/{sim.tasks[t]}/topic", {"agent_id": chat.agent_id, "entrypoint_id": ep}, agent=True)
        text_, task = stop
        sim.post(f"/api/entrypoints/{ep}/stops",
                 {"agent_id": chat.agent_id, "text": sim.fill(text_), "task_id": sim.tasks[task] if task else ""}, agent=True)
        for i, caption, mock in shots:
            sim.post(f"/api/entrypoints/{ep}/shots", {"agent_id": chat.agent_id, "way_id": way_ids[i], "caption": caption,
                                                      "data_base64": _png(mock, f"{key}{i}{caption}")}, agent=True)
        sim.store.rebuild()
    return run


def stop(sim, chat, key: str, text: str, task: str = "") -> Any:
    """entrypoint_stop from a later chat, e.g. at #done for a task of the topic."""
    def run() -> None:
        sim.post(f"/api/entrypoints/{sim.ids[key]}/stops",
                 {"agent_id": chat.agent_id, "text": sim.fill(text), "task_id": sim.tasks[task] if task else ""}, agent=True)
        sim.store.rebuild()
    return run


def card_of(sim, chat, turn: int) -> str:
    """The card the operator's #publish in this turn keeps (the hook's keep id)."""
    return sim.capture.keep_id("publish", chat.project, chat.agent_id, turn)


def write(sim, chat, context: str, *, text: str = "", tasks: list[str] = (), card: str = "",
          images: list[tuple[str, str]] = (), files: list[tuple[str, str, str]] = (),
          links: list[tuple[str, str]] = ()) -> Any:
    """publish_write right after the operator's #publish in this turn (the
    chat's next, as the turn is scheduled): the context, the text when the
    operator asked for it, and what belongs to the card. ``card`` names the
    card a #publish pu_… adds to; else the card this turn keeps."""
    turn = chat.turns + 1
    cid = card or card_of(sim, chat, turn)
    sim.ids[f"card_{chat.agent_id}_{turn}"] = cid

    def run() -> None:
        sim.adopt()
        body: dict[str, Any] = {
            "agent_id": chat.agent_id, "context": sim.fill(context),
            "tasks": [sim.tasks[t] for t in tasks],
            "images": [{"title": title, "ext": "png", "data_base64": _png(mock, cid + title)} for title, mock in images],
            "files": [{"name": name, "title": title, "source": f"/home/op/shopfront/{name}",
                       "data_base64": base64.b64encode(body_text.encode()).decode()} for name, title, body_text in files],
            "links": [{"title": title, "url": url} for title, url in links]}
        if text:
            body["text"] = text
        sim.post(f"/api/publishing/cards/{cid}/write", {k: v for k, v in body.items() if v not in ([], "")}, agent=True)
    return run


def core_new(sim, chat, key: str, name: str, kind: str, reason: str, anchors: list[str], task: str = "") -> Any:
    """core_new after the operator's #core-new in this turn: the message as
    typed (``<key>_text``) is the core's first note."""
    def run() -> None:
        r = sim.post("/api/cores", {
            "project": P, "agent_id": chat.agent_id, "name": name, "type": kind, "reason": reason,
            "text": sim.ids[f"{key}_text"], "anchors": anchors,
            "task_id": sim.tasks[task] if task else ""}, agent=True)
        sim.ids[key] = r["core"]["id"]
    return run


def core_note(sim, chat, key: str, text: str, comment: str, task: str = "") -> Any:
    def run() -> None:
        sim.post(f"/api/cores/{sim.ids[key]}/notes", {
            "agent_id": chat.agent_id, "text": sim.fill(text), "comment": comment, "kind": "note",
            "task_id": sim.tasks[task] if task else ""}, agent=True)
    return run


CHECKOUT_RECORD = """## What
Taking money on shopfront.dev: the checkout page, the PaymentIntent from the server cart, the Stripe webhook that creates the order, and refunds from the admin order page.

## Where
- frontend/app/checkout/page.tsx, frontend/components/PaymentStep.tsx, frontend/lib/declines.ts
- backend/app/routers/checkout.py, backend/app/routers/webhooks.py, backend/app/routers/admin_orders.py
- backend/app/order_events.py, backend/app/stripe_client.py
- https://staging.shopfront.dev/checkout
- https://dashboard.stripe.com/test/payments

## How
- `make up` starts Postgres, the API and the web app; the admin order page is its way in below.
- Pay with Stripe's test card 4242 4242 4242 4242 on staging; the webhook arrives through the Stripe CLI (`stripe listen --forward-to localhost:8000/webhooks/stripe`).
- Every Stripe call goes through `stripe_client.py` with an idempotency key.

## State
Full refunds work from the admin order page and the order keeps an event for every change. A partial refund marks the whole order refunded; that is the next round of {tk:refunds}.

## Next
- Partial refunds by line ({tk:refunds}).
- Plain decline messages ({tk:payment-failed-ux}).
- The 3-D Secure test matrix ({tk:3ds-tests}).
- Nightly reconciliation against the Stripe balance ({tk:reconcile}).
"""

LAUNCH_RECORD = """## What
What a visitor reads before and around buying: the legal pages, the FAQ, the decline messages, and the checklist for letting the waitlist in.

## Where
- content/legal/terms.md, content/legal/privacy.md, content/legal/imprint.md
- content/faq.md, frontend/app/faq/page.tsx, frontend/components/Footer.tsx
- docs/runbook.md
- https://staging.shopfront.dev/faq
- the artifact beta-launch-checklist

## How
- The legal pages and the FAQ render from Markdown at build time; edit the .md file and deploy staging with `./infra/deploy.sh staging`.
- UI copy is sentence case, plain, without exclamation marks (the rule kept on {dm:24}).

## State
Legal pages and the FAQ are live on staging. The imprint still has the placeholder phone number, and the lawyer has not read the terms; both are on the operator's list.

## Next
- SEO metadata and Open Graph images ({tk:seo-meta}).
- The cookie banner, only if analytics sets cookies ({tk:cookie-banner}).
- The copy for the twelve best sellers ({tk:product-copy}).
"""


def setup(sim, w, repo, K) -> None:
    # -------------------------------------------------------- entry points
    # Day 24 · the refunds chat keeps the checkout as a topic.
    c = K["c14"]
    c.turn(D(24, 10, 20), "#entrypoint checkout and payments — I keep coming back to it from every chat.",
           "Nothing is made yet: which topic do you mean?\n\n{id:ep_checkout_show}", minutes=2,
           actions=[(1, ask(sim, c, "ep_checkout", "Checkout and payments"))])
    c.turn(D(24, 10, 25), "{id:ep_checkout_n}",
           "The new topic «Checkout and payments» ({id:ep_checkout}) is made: its record, three ways in, where it stopped, "
           "two screenshots and four tasks.", minutes=4,
           actions=[(3, record(sim, c, "ep_checkout", CHECKOUT_RECORD,
                               ways=[{"name": "Checkout on staging", "kind": "site", "url": "https://staging.shopfront.dev/checkout",
                                      "note": "test card 4242 4242 4242 4242"},
                                     {"name": "Admin order page", "kind": "page", "url": "http://localhost:3000/admin/orders",
                                      "command": "make up", "folder": str(repo.path), "port": 3000,
                                      "note": "refunds and the order timeline"},
                                     {"name": "Stripe dashboard, test mode", "kind": "site",
                                      "url": "https://dashboard.stripe.com/test/payments"}],
                               stop=("Full refunds work from the admin order page and every order change is an event. "
                                     "Partial refunds are the next round; the customer email for a refund is not written.", "refunds"),
                               shots=[(0, "The checkout on staging with the test card entered", "form"),
                                      (1, "The admin order page with the refund button and the timeline", "cards")],
                               tasks=["refunds", "payment-failed-ux", "3ds-tests", "reconcile"]))])

    # Day 25 · the launch pages chat keeps its own topic; the checkout is offered too.
    c = K["c16"]
    c.turn(D(25, 16, 50), "#entrypoint the launch pages",
           "Nothing is made yet: which topic do you mean?\n\n{id:ep_launch_show}", minutes=2,
           actions=[(1, ask(sim, c, "ep_launch", "Launch pages and the beta"))])
    c.turn(D(25, 16, 55), "{id:ep_launch_n}",
           "The new topic «Launch pages and the beta» ({id:ep_launch}) is made: the record, two ways in, where it stopped, "
           "a screenshot and four tasks.", minutes=4,
           actions=[(3, record(sim, c, "ep_launch", LAUNCH_RECORD,
                               ways=[{"name": "FAQ on staging", "kind": "site", "url": "https://staging.shopfront.dev/faq"},
                                     {"name": "Legal pages", "kind": "folder", "path": str(repo.path / "content" / "legal"),
                                      "note": "Markdown, rendered at build time"}],
                               stop=("Legal pages and the FAQ are live on staging. The imprint's phone number and the lawyer's "
                                     "read wait for the operator.", "legal-pages"),
                               shots=[(0, "The FAQ page on staging", "cards")],
                               tasks=["legal-pages", "faq-page", "seo-meta", "cookie-banner"]))])

    # Later stops from other chats.
    c = K["c20"]
    c.turn(D(30, 10, 19), "And a line on the checkout topic.",
           "Written on «Checkout and payments»; the details are in the note.", minutes=1,
           actions=[(1, stop(sim, c, "ep_checkout", "Partial refunds by line work; the customer email for them is not written. "
                                                     "The note on {tk:refunds} says where it stopped.", "refunds"))])

    # ------------------------------------------------------------- publish
    c = K["c12"]
    c.turn(D(22, 17, 10), "#publish shopfront took its first real payment today: a €22.90 mug, paid with a real card. "
                          "The order existed 0.4 seconds after the payment.",
           "Wrote the card: the context, the task, the confirmation page and the link to the store.", minutes=2,
           actions=[(1, write(sim, c, "First live order SF-10001 on production, a €22.90 mug paid by card through the "
                                      "Payment Element. Before: only test-mode payments on staging. The webhook created "
                                      "the order 0.4 s after payment_intent.succeeded; the confirmation email followed.",
                              tasks=["first-payment"],
                              images=[("The confirmation page for SF-10001", "cards")],
                              links=[("shopfront.dev", "https://shopfront.dev")]))])
    first = (c.agent_id, c.last_n)
    c = K["c17"]
    c.turn(D(28, 16, 20), "#publish Product pages show their main image in 1.7 s on a phone, down from 4.8 s: "
                          "images are served at the size they are shown, as AVIF.",
           "Wrote the card: the numbers, the task, the Lighthouse run and the report.", minutes=2,
           actions=[(1, write(sim, c, "Largest Contentful Paint on a product page, mid-range phone on 4G: 4.8 s before, "
                                      "1.7 s after. Hero images were 2400 px JPEGs shown at 600 px; now the image "
                                      "optimizer serves AVIF at the shown width, 38 KB instead of 410 KB.",
                              tasks=["lcp-images"],
                              images=[("Lighthouse, product page, before and after", "chart")],
                              files=[("lighthouse-product-page.txt", "Lighthouse report, product page",
                                      "LCP 4.8 s -> 1.7 s\nTotal blocking time 210 ms -> 90 ms\n")]))])
    speed = (c.agent_id, c.last_n)
    c = K["c18"]
    c.turn(D(29, 17, 30), "#publish about the order notifications in Telegram, for the beta post",
           "Wrote the card's text from what was done, with the context and the bot's page.", minutes=2,
           actions=[(1, write(sim, c, "Paid orders go to tg-notify as order.paid the moment the webhook confirms them; "
                                      "the bot posts in 1.6 s on average over 40 test orders, the email takes 4 to 9 s.",
                              text="Paid orders now reach the Telegram bot in under two seconds, before the email does.",
                              tasks=["order-webhook-out"],
                              links=[("The order bot", "https://t.me/shopfront_orders_bot")]))])
    c.turn(D(29, 17, 34), "Put a line on the checkout topic: the 3DS matrix is in CI.",
           "Written on «Checkout and payments».", minutes=1,
           actions=[(1, stop(sim, c, "ep_checkout", "The 3-D Secure matrix runs in CI on main, the four cases one after "
                                                     "another (Stripe's test-mode rate limit).", "3ds-tests"))])

    c.turn(D(29, 17, 37), f"#publish {card_of(sim, K['c17'], speed[1])} add how it looks on a phone",
           "Added the phone screenshot to the card.", minutes=1,
           actions=[(1, write(sim, c, "Largest Contentful Paint on a product page, mid-range phone on 4G: 4.8 s before, "
                                      "1.7 s after. Hero images were 2400 px JPEGs shown at 600 px; now the image "
                                      "optimizer serves AVIF at the shown width, 38 KB instead of 410 KB.\n\n"
                                      "On a phone the hero image fills the first screen before the price shows.",
                              card=card_of(sim, K["c17"], speed[1]),
                              images=[("Product page on a phone", "form")]))])

    def announcement() -> None:
        """The operator shortens one card and places two in the beta announcement."""
        sim.post(f"/api/publishing/cards/{sim.ids[f'card_{speed[0]}_{speed[1]}']}/text", {
            "text": "Product pages now show their main image in under two seconds on a phone.",
            "note": "shorter for the post", "actor": "operator"})
        doc = sim.post("/api/publishing/docs", {"project": P, "name": "Public beta announcement", "actor": "operator"})["doc"]
        for agent, turn in (first, speed):
            sim.post(f"/api/publishing/docs/{doc['id']}/items",
                     {"card_id": sim.ids[f"card_{agent}_{turn}"], "actor": "operator"})
    sim.at(D(29, 17, 40), announcement)

    # ---------------------------------------------------------------- pins
    c = K["c19"]
    c.turn(D(29, 16, 45), "#fork-later The email search in the admin list needs an index before there are real volumes — "
                          "another chat can take it after the beta.",
           "Kept for later. It is `ILIKE 'x%'` on `orders.email`; a `text_pattern_ops` index makes it an index scan.", minutes=2)
    c = K["c20"]
    c.turn(D(30, 10, 21), "#carry The beta cannot open until the partial refund email is sent. Keep this in view after a compaction.",
           "Carried: it comes back to this chat after a compaction.", minutes=1)

    # --------------------------------------------------------------- cores
    c = K["c9"]
    said = ("#core-new The Stripe webhook: every payment becomes exactly one order through it, "
            "and it is the first thing to check when an order is missing.")
    sim.ids["core_webhook_text"] = said
    c.turn(D(16, 18, 40), said, "{id:core_webhook} · Stripe webhook · integration — files: backend/app/routers/webhooks.py, backend/app/orders.py.",
           minutes=1, actions=[(0.5, core_new(sim, c, "core_webhook", "Stripe webhook", "integration",
                                               "every payment becomes one order through it",
                                               ["backend/app/routers/webhooks.py", "backend/app/orders.py"], task="webhooks"))])
    c = K["c14"]
    said = "#core-new The order event log: every change to an order, with its cause and time. Support reads it instead of the database."
    sim.ids["core_events_text"] = said
    c.turn(D(24, 10, 40), said, "{id:core_events} · Order event log · store — files: backend/app/order_events.py, frontend/components/OrderTimeline.tsx.",
           minutes=1, actions=[(0.5, core_new(sim, c, "core_events", "Order event log", "store",
                                               "support explains any order from it",
                                               ["backend/app/order_events.py", "frontend/components/OrderTimeline.tsx"],
                                               task="order-events"))])
    c = K["c15"]
    said = "#core-note Webhook events are stored first now, and a worker processes them with backoff; five failures make a dead event."
    c.turn(D(25, 15, 50), said, "added → Stripe webhook ({id:core_webhook}).", minutes=1,
           actions=[(0.5, core_note(sim, c, "core_webhook", said,
                                    "The core's files now include backend/app/worker.py.", task="webhook-retries"))])
    c = K["c20"]
    said = "#core-note A partial refund writes one event with the lines it refunded."
    c.turn(D(30, 10, 23), said, "added → Order event log ({id:core_events}).", minutes=1,
           actions=[(0.5, core_note(sim, c, "core_events", said, "One row per refund, the lines in its value.",
                                    task="refunds"))])
