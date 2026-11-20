"""shopfront's notes: the long texts agents wrote for the operator.

Six notes over the month, each written in a chat turn the way an agent
writes one (MCP note_write: the markdown, its kind, the task, the pictures
it names), the reply saying one line and the note's id. The operator's
ticks, answers and copies go through the page's own route; the plan's
question is left open, so one note waits on an answer. One note gets a
second version; the ticks of the items it left alone stay.

Played after the chats (build_example.py): every turn here comes after the
chat's last turn in shopfront_chats_*.py.
"""

from __future__ import annotations

import base64
from typing import Any

from engine import D, mock_screen

P = "shopfront"


def write(sim, chat, key: str, kind: str, text: str, *, task: str = "", ep: str = "",
          images: list[tuple[str, str, str, int]] = (), version_of: str = "") -> Any:
    """An action for ``Chat.turn``: note_write from this chat. ``images``:
    (file name the text uses, caption, mock kind, seed)."""
    def run() -> None:
        body: dict[str, Any] = {
            "agent_id": chat.agent_id, "project": P, "kind": kind, "text": sim.fill(text),
            "images": [{"name": name, "caption": caption,
                        "data_base64": base64.b64encode(mock_screen(mock, seed=seed)).decode()}
                       for name, caption, mock, seed in images]}
        if task:
            body["task_id"] = sim.tasks[task]
        if ep:
            body["entrypoint_id"] = sim.ids[ep]
        if version_of:
            body["id"] = sim.ids[version_of]
        r = sim.post("/api/notes/write", body, agent=True)
        sim.ids[key] = r["id"]
        sim.store.rebuild()  # what the server's watcher does on the next change
    return run


def mark(sim, when, key: str, kind: str, match: str, value: Any = 1) -> None:
    """The operator ticks a step, answers a choice (value: the option's
    index) or copies a block on the Notes page. ``match``: the start of the
    item's text, question or title."""
    def run() -> None:
        from backend import notelib
        nid = sim.ids[key]
        text = notelib.text_of(sim.store, notelib.row_of(sim.store, nid))
        want = {"tick": "check", "answer": "choice", "copy": "copy"}[kind]
        item = next(it for it in notelib.parse(nid, text)["items"] if it["type"] == want
                    and str(it.get("text") or it.get("question") or it.get("title") or "").startswith(match))
        sim.post(f"/api/notes/{nid}/marks", {"item": item["id"], "kind": kind, "value": value, "actor": "operator"})
    sim.at(when, run)


CHECKOUT_REVIEW = """# Checkout layouts: one page or two steps

Three ways to lay out {tk:checkout-page}, built on staging with the same cart (two items, €41.80 with shipping). The server's total sits above the pay button in all three.

```gallery
![One page: address, shipping and payment together](one-page.png)
![Two steps: the address first, then payment](two-steps.png)
![One page with the summary on top on phones](summary-top.png)
```

## What differs

| layout | fields before paying | screens on a phone | the back button |
|---|---|---|---|
| One page | 9 | 3 | leaves the checkout |
| Two steps | 9 | 2 + 1 | returns to the address |
| Summary on top | 9 | 3½ | leaves the checkout |

## Recommendation

One page. Two steps reloads the Payment Element on the way back, about 600 ms each time; the summary on top pushes the pay button below the fold on a 667 px screen.

```choice Which layout ships?
1. One page
2. Two steps
3. One page, summary on top on phones
```
"""

EMAIL_PASTE = """# Confirmation email: the texts for the email provider

The provider keeps the subject and the plain-text part in its own template editor, not in our repository. Paste these two into the template `order-confirmation` (live and test). The HTML part is ours and goes out from `emails.py` for {tk:confirm-email}.

```copy Subject
Your shopfront order {{order_number}} is confirmed
```

```copy Plain-text part
Hello {{first_name}},

thank you for your order {{order_number}}.

{{#lines}}
{{quantity}} × {{title}} — {{price}}
{{/lines}}
Shipping: {{shipping}}
Total paid: {{total}} (incl. VAT)

It ships to:
{{shipping_address}}

You get a tracking link when it leaves the warehouse, usually within two working days.
Questions? Answer this email.

shopfront
```

## Checked

- The placeholders are the ones `emails.py` sends: `order_number`, `first_name`, `lines`, `shipping`, `total`, `shipping_address`.
- Sentence case, no exclamation marks.
- The test template gets the same text; the provider sends test emails only to the team's addresses.
"""

LOAD_REPORT = """# Load test at 50 checkouts a minute: where the pool runs out

What the k6 run on staging found for {tk:load-test}: ten minutes at 50 checkouts a minute, the steps timed one by one. Everything is fast until minute seven; then the API waits for database connections, and the intent step takes over five seconds for one checkout in seven.

## Numbers

| step | p95, minutes 1–6 | p95, minutes 7–10 |
|---|---|---|
| products | 38 ms | 41 ms |
| add to cart | 61 ms | 70 ms |
| intent | 420 ms | 5.2 s |
| confirm | 1.9 s | 2.3 s |

```gallery
![Intent latency over the ten minutes; the step at minute seven](intent-latency.png)
```

## Where the connections go

```mermaid
flowchart LR
  A[4 API workers] -->|5 + 5 overflow each| P[(Postgres, 100 allowed)]
  W[webhook worker] -->|5| P
  I[intent call] -->|held while Stripe answers, 300–400 ms| A
```

Forty connections for the API is enough for the reads. The intent handler opens its transaction before it calls Stripe and keeps it open while Stripe answers; at 50 a minute those idle transactions fill the pool.

## What it means

:::fold Two fixes, either is enough for the beta
1. Shorter transactions: read the cart, close the transaction, call Stripe, open a new one to store the intent id. One file, `routers/checkout.py`; the idempotency key keeps a retried call safe.
2. pgbouncer in transaction mode in front of Postgres. A service to run and watch.
:::

The problem is filed as a problem entry; the task stays in review until one of the fixes is measured.
"""

LAUNCH_ACTIONS = """# Before the beta: what only you can do

The pages are live on staging; these steps need your accounts, your signature or your decision. Everything else for {tk:legal-pages} and the launch is done or on the board.

## Accounts and contracts

- [ ] Sign the data processing agreement with the email provider
- [ ] Stripe live mode: confirm the business details and the statement descriptor `SHOPFRONT`
- [ ] Add your phone to the uptime alerts as the second contact

## The texts

- [ ] Replace the placeholder phone number in the imprint (`content/legal/imprint.md`)
- [ ] Send the terms and privacy pages to the lawyer for a last read
- [ ] Approve the twelve FAQ answers on staging, /faq

## The waitlist

- [ ] Write the invitation email to the waitlist
- [ ] Pick the day the waitlist is let in

The record line for the provider's DNS check, if it asks again:

```copy DNS record for the email provider
shopfront.dev.  TXT  "v=spf1 include:mail.provider.example ~all"
```
"""

LAUNCH_ACTIONS_V2 = LAUNCH_ACTIONS.replace(
    "- [ ] Pick the day the waitlist is let in",
    "- [ ] Pick the day the waitlist is let in\n- [ ] Decide whether returns open with the beta or a week later ({tk:returns})")

SSO_PLAN = """# Admin behind SSO: a plan for two helpers

How {tk:admin-auth} gets built by two helper agents in parallel. Today the admin pages sit behind one shared password in Caddy; after this, every admin request carries a signed-in person, and the order events name who refunded what.

```mermaid
flowchart LR
  B[Browser, /admin] --> C[Caddy]
  C --> W[Next.js admin pages]
  W -->|session cookie| A[API /api/admin/*]
  A -->|checks the session| S[(sessions table)]
  W -->|sign in| I[Identity provider]
  I -->|callback| A
```

```choice Which identity provider?
1. The team's Google Workspace accounts
2. GitHub, members of the shopfront organisation
3. A magic link by email, no provider
```

## Helper 1: the API

- `GET /api/auth/login` and `/api/auth/callback` with the chosen provider; an allow-list of emails in the settings.
- A `sessions` table, a signed cookie, 12 hours, renewed on use.
- Every `/api/admin/*` route depends on `admin_user()`; the refund endpoint writes the user's email into `order_events.cause`.
- Tests: no cookie → 401, a cookie of a removed user → 401, a refund names its admin.

## Helper 2: the pages

- A sign-in page and a sign-out link in the admin header.
- The admin layout redirects to sign-in on 401.
- The order timeline shows who caused each admin event.

## Rules for both

- Additive migrations only; the shared password stays in Caddy until both are merged and deployed.
- No change to the storefront or the checkout.
- Each helper reports what it changed, the test count and what it did not do.
"""

REFUNDS_CONTEXT = """# Partial refunds: where it stopped

For whoever picks up {tk:refunds} next, this chat or another. Full and partial refunds work from the admin order page; the customer is not told about a partial refund yet.

## Done

- `POST /api/admin/orders/{number}/refund` takes lines, quantities and `shipping: true|false`; one Stripe refund for the sum, idempotency key `refund:{order}:{n}`.
- One `order_events` row per refund, with the lines in it.
- The order is `partially_refunded` until every line and the shipping are refunded, then `refunded`.
- The refund dialog on the admin order page: steppers per line, a switch for shipping, the sum before you confirm.
- `pytest -q`: 84 passed.

## Not done

- The customer email for a partial refund: `send_partial_refund()` in `backend/app/emails.py` raises `NotImplementedError` and is not committed.
- A partial refund of a discounted line: discounts do not exist yet ({tk:discount-codes}).

## How to try it

```copy Staging, a partial refund from the shell
curl -X POST https://staging.shopfront.dev/api/admin/orders/SF-10012/refund \\
  -H 'Content-Type: application/json' \\
  -d '{"lines": [{"line": 1, "quantity": 1}], "shipping": false, "reason": "damaged"}'
```

## Next

1. Write `send_partial_refund()` from the confirmation template: the refunded lines and the amount.
2. Send it from the `charge.refunded` handler, like the full refund.
3. Then {tk:returns} can build on it.
"""


def setup(sim, w, repo, K) -> None:
    # Day 15 · the checkout page chat: three layouts to choose from.
    c = K["c8"]
    c.turn(D(15, 10, 10), "Before I look at the layouts: put them side by side somewhere I can come back to. #pin",
           "The three layouts with screenshots, what differs and the one question are in a note: {id:note_checkout}.", minutes=9,
           actions=[(7, write(sim, c, "note_checkout", "review", CHECKOUT_REVIEW, task="checkout-page",
                              images=[("one-page.png", "One page: address, shipping and payment together", "form", 11),
                                      ("two-steps.png", "Two steps: the address first, then payment", "form", 12),
                                      ("summary-top.png", "One page with the summary on top on phones", "cards", 13)]))])
    mark(sim, D(15, 10, 40), "note_checkout", "answer", "Which layout", 0)

    # Day 18 · the confirmation email: two texts for the provider's editor.
    c = K["c11"]
    c.turn(D(18, 16, 0), "The provider wants the subject and the plain-text part in its own editor. Give me both to paste.",
           "Both are in a note with a copy button each, and the placeholders checked against `emails.py`: {id:note_email}.", minutes=6,
           actions=[(5, write(sim, c, "note_email", "paste", EMAIL_PASTE, task="confirm-email"))])
    mark(sim, D(18, 16, 20), "note_email", "copy", "Subject")
    mark(sim, D(18, 16, 21), "note_email", "copy", "Plain-text part")

    # Day 25 · the load test: the findings as a report.
    c = K["c15"]
    c.turn(D(25, 15, 30), "Write the load test up so I can read it again after the pool fix. #pin",
           "Report written as a note, with the numbers, the connection budget and the two fixes: {id:note_load}.", minutes=11,
           actions=[(9, write(sim, c, "note_load", "report", LOAD_REPORT, task="load-test", ep="ep_checkout",
                              images=[("intent-latency.png", "Intent latency over the ten minutes; the step at minute seven", "chart", 21)]))])

    # Day 25 · the launch pages: what only the operator can do.
    c = K["c16"]
    c.turn(D(25, 16, 40), "What is left for the beta that you can't do?",
           "Eight steps that need your accounts, signature or decision, as a checklist: {id:note_launch}.", minutes=7,
           actions=[(6, write(sim, c, "note_launch", "actions", LAUNCH_ACTIONS, task="legal-pages"))])
    for when, item in [(D(26, 9, 10), "Replace the placeholder phone"), (D(26, 9, 30), "Add your phone to the uptime"),
                       (D(26, 15, 0), "Send the terms and privacy"), (D(28, 11, 0), "Stripe live mode"),
                       (D(28, 11, 5), "Approve the twelve FAQ")]:
        mark(sim, when, "note_launch", "tick", item)
    mark(sim, D(26, 9, 12), "note_launch", "copy", "DNS record")

    # Day 29 · the admin list chat: SSO planned for two helpers.
    c = K["c19"]
    c.turn(D(29, 16, 20), "Plan the SSO work for two helpers — but don't start. I'll pick the provider.",
           "The plan for two helpers, with the provider as the one open question: {id:note_sso}. Nothing started.", minutes=12,
           actions=[(10, write(sim, c, "note_sso", "plan", SSO_PLAN, task="admin-auth"))])
    # The provider is left open: the note waits on the operator's answer.
    # The same day, the launch steps gain one: written by another chat of the project.
    c = K["c18"]
    c.turn(D(29, 17, 20), "Add the returns question to the launch checklist note.",
           "Added as a ninth step; your five ticks are kept: {id:note_launch}, version 2.", minutes=3,
           actions=[(2, write(sim, c, "note_launch_v2", "actions", LAUNCH_ACTIONS_V2, version_of="note_launch"))])

    # Day 30 · partial refunds: where it stopped, for the next chat.
    c = K["c20"]
    c.turn(D(30, 10, 15), "The email is not done and I stop here today. Leave the context for whoever picks it up.",
           "Context for the next chat: {id:note_refunds}. The uncommitted stub in `emails.py` is mentioned there.", minutes=3,
           actions=[(2, write(sim, c, "note_refunds", "context", REFUNDS_CONTEXT, task="refunds", ep="ep_checkout"))])
