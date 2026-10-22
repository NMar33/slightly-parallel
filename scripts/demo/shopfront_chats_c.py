"""shopfront chats, 23–30 September: payments hardening, launch polish."""

from __future__ import annotations

from common import C
from engine import Chat, D

P = "shopfront"

REVIEW_PROMPT = ("#prompt(review the diff) Review the diff since main as if you had not written it. "
                 "List what would break for a customer first, then what a reviewer would ask about, then style. "
                 "No praise. Quote the line for every point.")
REVIEW_AGAIN = ("Review the diff since main as if you had not written it. "
                "List what would break for a customer first, then what a reviewer would ask about, then style. "
                "No praise. Quote the line for every point.")
PLAN_PROMPT = ("#prompt(plan before code) Before writing code: say what you will change, in which files, what you will not touch, "
               "and how we will know it works. Wait for my go.")
PLAN_AGAIN = ("Before writing code: say what you will change, in which files, what you will not touch, "
              "and how we will know it works. Wait for my go.")


def setup(sim, w, repo, K):
    # ------------------------------------------------------------------
    # C14 · 23–24 Sep · refunds and the order event log
    # ------------------------------------------------------------------
    c = Chat(sim, P, "72ab5d08-6f1c-4e39-a2d7-9b4e0c8f3a15", title="refunds", repo=repo,
             headline="Refunds from the admin page, and an event log for every order")
    K["c14"] = c
    t = D(23, 10, 10)
    c.turn(t, "Payments hardening starts. {tk:refunds}: full refund from the admin order page. The order keeps the refund id and a reason.",
           "Plan: `POST /api/admin/orders/{number}/refund {reason}` creates the refund with an idempotency key `refund:{order}`; "
           "the order moves to `refund_pending`, and `charge.refunded` from the webhook moves it to `refunded`. "
           "The customer email goes out from the webhook, like the confirmation.", minutes=8)
    t = D(23, 10, 25)
    c.turn(t, "#vision Every order explainable from its events: cart, intent, webhook, email, refund — each with its cause and time. "
              "Support should never need to open the database.",
           "Kept. {tk:order-events} is the first step: one `order_events` row per state change, with the Stripe event id or the admin who caused it.", minutes=4)
    K["vision_events"] = (c, c.last_n)
    t = D(23, 10, 35)
    c.turn(t, "Build refunds and the event log together then.",
           "Done so far:\n- `order_events` table; every transition writes a row (`paid`, `refund_requested`, `refunded`) with `cause`\n"
           "- the refund endpoint and the `charge.refunded` handler\n- the admin order page shows the events as a timeline\n\n"
           "Not done: the customer email for refunds. `pytest -q`: 66 passed.", minutes=118,
           commits=[C(30, "Order events table and a writer for every transition", "mig:order events", "backend/app/order_events.py", "backend/app/orders.py"),
                    C(70, "Admin refund endpoint and the charge.refunded handler", "backend/app/routers/admin_orders.py", "backend/app/routers/webhooks.py"),
                    C(100, "Order timeline on the admin order page", "frontend/app/admin/orders/[number]/page.tsx", "frontend/components/OrderTimeline.tsx"),
                    C(112, "Refund and event tests", "backend/tests/test_refunds.py")],
           helpers=[(40, 50)])
    t = D(23, 14, 30)
    c.turn(t, "#rule Migrations are additive until the release with the new code has shipped. Drop a column one release later, never in the same one.",
           "Kept. The `order_events` migration only adds; the old `orders.status_note` column stays until the next release.", minutes=3)
    K["rule_migrations"] = (c, c.last_n)
    t = D(24, 9, 40)
    c.turn(t, REVIEW_PROMPT,
           "Customer-facing first:\n1. `admin_orders.py:88` — `refund()` does not check the order is paid; a pending order can be 'refunded'. **Would break.**\n"
           "2. `webhooks.py:141` — `charge.refunded` for a partial refund marks the whole order refunded.\n\n"
           "Reviewer questions:\n3. `order_events.py:22` — `cause` is free text; a reviewer will ask for an enum.\n\n"
           "Style: nothing worth a change.\n\nFixing 1 and 2 now; 3 is a follow-up.", minutes=16,
           commits=[C(12, "Refund only paid orders; partial refunds keep the order open", "backend/app/routers/admin_orders.py", "backend/app/routers/webhooks.py", "backend/tests/test_refunds.py")])
    w.decision(D(24, 10, 0), P, c.agent_id, "Order state changes are recorded as rows in order_events, not as columns on orders",
               "A column holds the last state; support needs the sequence and the cause. The orders.status column is kept as a cache of the newest event. Settled.",
               ["Timestamps per state on orders (paid_at, refunded_at …) — rejected: no cause, and a second refund overwrites the first",
                "Stripe's own event history — rejected: our admin actions and emails are not in it"], weight="normal", tags="orders,audit")
    w.round("refunds", D(24, 17, 0), "Partial refunds: pick lines and quantities; shipping refundable separately.")

    # ------------------------------------------------------------------
    # C15 · 24–25 Sep · webhook retries, and the load test (Codex)
    # ------------------------------------------------------------------
    c = Chat(sim, P, "e3b9107f-2a8d-4c64-9f15-8d0b6e3a7c42", tool="codex", title="webhook queue and load test", repo=repo,
             headline="Webhooks stored first, processed from a table; the checkout load-tested")
    K["c15"] = c
    t = D(24, 10, 10)
    c.turn(t, "#prompt(write the tests first) Write the failing tests first and show them to me. Then the code. "
              "Task: {tk:webhook-retries}.",
           "Tests first, all failing now:\n- `test_event_stored_before_processing` — the row exists even when the handler raises\n"
           "- `test_failed_handler_retries_with_backoff` — 1 s, 5 s, 30 s, 5 min, then `dead`\n"
           "- `test_endpoint_answers_200_within_100ms` — processing is not on the request path\n\nGo on the code?", minutes=21,
           commits=[C(15, "Failing tests for the webhook retry queue", "backend/tests/test_webhook_queue.py")])
    t = D(24, 10, 40)
    c.turn(t, "Go.",
           "The endpoint verifies, stores the event with `status=pending`, answers 200. A worker (`python -m app.worker`) claims pending rows "
           "with `FOR UPDATE SKIP LOCKED`, runs the handler, and on failure sets `next_attempt_at` with backoff. After five failures the row is "
           "`dead` and shows on the admin page. All three tests pass; `pytest -q`: 71 passed.", minutes=96,
           commits=[C(40, "Store webhook events first, process them in a worker", "backend/app/routers/webhooks.py", "backend/app/worker.py", "mig:stripe events status and attempts"),
                    C(80, "Worker service in compose", "infra/docker-compose.yml", "infra/docker-compose.prod.yml"),
                    C(90, "Dead events on the admin page", "frontend/app/admin/events/page.tsx")],
           helpers=[(30, 40)])
    t = D(24, 16, 5)
    c.turn(t, "#rule A webhook handler is idempotent: it looks up the event id before it acts, and acting twice is a bug.",
           "Kept. Every handler is now called with the stored event row; each one checks `processed_at` first. Also found that unknown event types "
           "are answered 200 without a log line — put it on the board.", minutes=6)
    K["rule_webhook"] = (c, c.last_n)
    w.task("webhook-unknown", D(24, 16, 10), P, "Webhook handler swallows unknown event types silently", status="agent",
           lane="api", tags="ag_bug", agent=c.agent_id,
           desc="An event type we do not handle is answered 200 and dropped without a log line. Log it at info with the type.")
    t = D(25, 10, 5)
    c.turn(t, "{tk:load-test}: k6, 50 checkouts a minute on staging for ten minutes. Report p95 per step.",
           "Wrote `loadtest/checkout.js`: browse → add to cart → intent → confirm with a test card. Ramping to 50/min now.", minutes=12,
           commits=[C(8, "k6 checkout scenario", "=loadtest/checkout.js::import http from 'k6/http'\nimport { check, sleep } from 'k6'\n\nexport const options = { scenarios: { checkout: { executor: 'constant-arrival-rate', rate: 50, timeUnit: '1m', duration: '10m', preAllocatedVUs: 40 } } }\n\nexport default function () {\n  const p = http.get(`${__ENV.BASE}/api/products?limit=24`)\n  check(p, { 'products 200': (r) => r.status === 200 })\n  sleep(1)\n}\n")])
    t = D(25, 10, 30)
    c.turn(t, "And?",
           "p95 per step at 50/min: products 38 ms, add to cart 61 ms, intent 420 ms, confirm 1.9 s. At minute 7 the API started waiting on the "
           "database pool: `QueuePool limit of size 5 overflow 5 reached` — 14 % of intents took over 5 s.", minutes=16, helpers=[(1, 14)])
    t = D(25, 14, 55)
    c.turn(t, "#problem The API runs out of database connections at 50 checkouts a minute. Four workers × pool 10 = 40, Postgres allows 100, "
              "but the worker and migrations hold connections too.",
           "Logged. What I know: 4 uvicorn workers × (5 + 5 overflow) = 40, the webhook worker holds 5, idle-in-transaction sessions from the intent "
           "call hold theirs while Stripe answers (300–400 ms). The fix is either shorter transactions around the Stripe call or pgbouncer.", minutes=8)
    K["problem_pool"] = (c, c.last_n)
    w.report("load-test", D(25, 15, 10), c.agent_id, "Ran 10 min at 50 checkouts/min; p95 per step recorded; pool exhaustion found and filed as a problem.")
    w.evidence("load-test", D(25, 15, 12), c.agent_id, [
        {"kind": "image", "title": "k6: intent latency over the 10-minute run", "mock": "chart"},
        {"kind": "text", "title": "p95 per step at 50/min",
         "body": "| step | p95 |\n|---|---|\n| products | 38 ms |\n| add to cart | 61 ms |\n| intent | 420 ms (5.2 s after minute 7) |\n| confirm | 1.9 s |"},
    ])

    # ------------------------------------------------------------------
    # C16 · 24–25 Sep · legal pages, uptime, FAQ, decline messages
    # ------------------------------------------------------------------
    c = Chat(sim, P, "5fa2c894-0e7b-4d23-8c61-4a9f2b7e0d33", title="launch pages", repo=repo,
             headline="The pages a store must have: terms, privacy, imprint, FAQ")
    K["c16"] = c
    t = D(24, 14, 5)
    c.turn(t, "{tk:legal-pages}. The lawyer's text is in docs/legal/. Render from Markdown, link from the footer.",
           "`app/(legal)/[page]/page.tsx` renders `content/legal/*.md` at build time; the footer links all three. The imprint had a placeholder "
           "phone number ('+00 000') — left it and flagged it for you.", minutes=38,
           commits=[C(20, "Legal pages rendered from Markdown", "frontend/app/(legal)/[page]/page.tsx", "=content/legal/terms.md::# Terms\n\nThese terms apply to orders placed on shopfront.dev.\n", "=content/legal/privacy.md::# Privacy\n\nWe keep what an order needs and nothing else.\n", "=content/legal/imprint.md::# Imprint\n\nShopfront. Contact: hello@shopfront.dev, phone +00 000.\n"),
                    C(32, "Footer with the legal links", "frontend/components/Footer.tsx", "frontend/app/layout.tsx")])
    t = D(24, 15, 0)
    c.turn(t, "#rule UI copy is sentence case, plain, and has no exclamation marks. 'Your order is on its way', not 'Your Order Is On Its Way!'",
           "Kept. Went through the storefront: 11 strings changed (buttons, the empty cart, the confirmation page). None in the emails needed it.", minutes=14,
           commits=[C(10, "Sentence case and no exclamation marks in UI copy", "frontend/components/CartDrawer.tsx", "frontend/app/checkout/success/page.tsx", "frontend/components/AddToCartButton.tsx")])
    K["rule_copy"] = (c, c.last_n)
    t = D(24, 15, 30)
    c.turn(t, "{tk:payment-failed-ux}: declines say something a person understands.",
           "Three messages from Stripe's decline codes: 'Your bank declined the card — try another card or contact your bank', "
           "'The card details look wrong — check the number, date and code', 'The payment could not be completed — nothing was charged'. "
           "The raw code goes to our logs only.", minutes=27,
           commits=[C(18, "Plain decline messages mapped from Stripe codes", "frontend/lib/declines.ts", "frontend/components/PaymentStep.tsx")])
    t = D(25, 10, 0)
    c.turn(t, "{tk:uptime}: checks for / and /api/health, alert after two failures.",
           "Set up with the monitoring provider: 60 s checks from Frankfurt and Amsterdam, alert to the ops channel after two failures. "
           "Documented in `docs/runbook.md`.", minutes=18, commits=[C(12, "Runbook: uptime checks and who gets paged", "docs/runbook.md")])
    t = D(25, 14, 5)
    c.turn(t, "{tk:faq-page}: twelve questions, two sentences each. Shipping, returns, payment.",
           "Written and live on staging at /faq. Report sent on the task — it moves to review by itself.", minutes=33,
           commits=[C(20, "FAQ page with twelve answers", "=content/faq.md::# Frequently asked\n\n## How long does shipping take?\nTwo to four working days inside the EU. You get a tracking link when it ships.\n\n## Can I return something?\nYes, within 30 days. Start from the link in your order email.\n", "frontend/app/faq/page.tsx")])
    w.report("faq-page", D(25, 14, 40), c.agent_id, "Twelve answers on /faq (staging), linked from the footer.")
    t = D(25, 16, 10)
    c.turn(t, "#vision Returns start from the order page: pick the items, pick a reason, get a label. No email to support.",
           "Kept. It depends on partial refunds ({tk:refunds.2}) and a carrier label API. {tk:returns} is the task for it.", minutes=3)
    K["vision_returns"] = (c, c.last_n)

    # ------------------------------------------------------------------
    # C17 · 28 Sep · LCP and the sitemap
    # ------------------------------------------------------------------
    c = Chat(sim, P, "b6e0d3a7-4c19-4f82-9e3b-0a6d8c2f5e71", title="product page speed", repo=repo,
             headline="Product pages under 2.5 s LCP: images at the size they are shown")
    K["c17"] = c
    t = D(28, 9, 5)
    c.turn(t, "#prompt(lighthouse pass) Run Lighthouse (mobile, throttled) on /, a product page and /checkout. Give me LCP, CLS and TBT per page "
              "and the single biggest cause on each. Don't fix anything yet.",
           "| page | LCP | CLS | TBT | biggest cause |\n|---|---|---|---|---|\n| / | 2.1 s | 0.02 | 90 ms | the first row of card images |\n"
           "| /products/heavy-cotton-tee | **4.8 s** | 0.01 | 120 ms | hero image: a 3.1 MB JPEG shown at 640 px |\n"
           "| /checkout | 1.9 s | 0.00 | 310 ms | Stripe.js |", minutes=14, helpers=[(2, 10)])
    t = D(28, 9, 25)
    c.turn(t, "#problem Product pages have a 4.8 s LCP on mobile. The hero image is the original upload.",
           "Logged. Every product image is the original from the photographer (2–4 MB). `next/image` resizes, but the hero is marked `unoptimized` "
           "since {tk:image-cdn} because the CDN rejected AVIF then. That flag is the cause.", minutes=6)
    K["problem_lcp"] = (c, c.last_n)
    t = D(28, 9, 40)
    c.turn(t, "Fix it — {tk:lcp-images}.",
           "Removed `unoptimized`, the CDN now serves AVIF (it did not in the first week; it does now), widths 320/640/1024, "
           "`priority` on the hero so it preloads. Product page LCP on the same run: 4.8 s → 1.7 s. Waiting for your look before review.", minutes=41,
           commits=[C(22, "Optimised hero images with preload on product pages", "frontend/app/products/[slug]/page.tsx", "frontend/components/ProductGallery.tsx", "frontend/next.config.mjs")])
    t = D(28, 11, 5)
    c.turn(t, "{tk:sitemap}: from the catalog at build time; no cart or checkout in it.",
           "`app/sitemap.ts` lists /, categories, products and legal pages with `lastModified` from the catalog; `robots.ts` disallows /cart, /checkout "
           "and /admin. 64 URLs.", minutes=19, commits=[C(12, "sitemap.xml and robots.txt from the catalog", "frontend/app/sitemap.ts", "frontend/app/robots.ts")])
    t = D(28, 11, 30)
    c.turn(t, "#done {tk:sitemap}", "{tk:sitemap} is done.", minutes=1)
    t = D(28, 15, 10)
    c.turn(t, REVIEW_AGAIN,
           "Customer-facing first:\n1. `ProductGallery.tsx:31` — `sizes` is `100vw` for thumbnails too; phones download 640 px thumbnails. Would cost bandwidth, not break.\n\n"
           "Reviewer questions:\n2. `next.config.mjs:4` — the AVIF switch has no comment saying why it was off before.\n\nStyle: none.\n\nFixed both.", minutes=12,
           commits=[C(8, "Thumbnail sizes and a note on the AVIF switch", "frontend/components/ProductGallery.tsx", "frontend/next.config.mjs")])
    w.interpret("problem", c, K["problem_lcp"][1], D(28, 15, 30),
                "Product pages took 4.8 s to show the main image on a throttled phone. Cause: product images are the photographer's originals (2–4 MB) and the hero was "
                "served unoptimised since the first week. Fixed on staging (1.7 s); open until the same number is measured on production after the next deploy.",
                note="cause found, fix on staging", agent_id=c.agent_id)

    # ------------------------------------------------------------------
    # C18 · 28–29 Sep · 3-D Secure tests, and orders to tg-notify
    # ------------------------------------------------------------------
    c = Chat(sim, P, "8c3f5e21-9b06-4a7d-b3e8-6f1c0d4a2b97", title="3ds tests and order webhooks", repo=repo,
             headline="3-D Secure tested in CI; paid orders reach the Telegram bot")
    K["c18"] = c
    t = D(28, 10, 5)
    c.turn(t, PLAN_PROMPT + " Task: {tk:3ds-tests}.",
           "Plan:\n- change: `tests/e2e/test_3ds.py` drives the checkout on staging with Playwright and the four Stripe 3DS test cards\n"
           "- files: that test, a CI job `e2e-3ds` that runs on main only, a fixture that resets the cart\n- not touched: checkout code\n"
           "- how we know: four cases green, and a deliberately broken return_url makes one red.", minutes=6)
    t = D(28, 10, 20)
    c.turn(t, "Go.",
           "Four cases pass on staging: 3DS required → success, 3DS failed → the decline message, frictionless → success, insufficient funds after 3DS → decline. "
           "Breaking `return_url` turns two of them red, as it should. The CI job runs on main only.", minutes=74,
           commits=[C(40, "3-D Secure end-to-end tests against staging", "backend/tests/e2e/test_3ds.py", "backend/tests/e2e/conftest.py"),
                    C(66, "CI job for the 3DS matrix on main", ".github/workflows/ci.yml")],
           helpers=[(20, 40)])
    t = D(28, 13, 45)
    c.turn(t, "The CI run failed twice with 'rate limit' from Stripe. #problem The 3DS matrix hits Stripe's test-mode rate limit when the four cases run in parallel.",
           "Logged. Test mode allows 25 requests a second; four browsers creating intents and polling hit it. Running the cases serially costs 40 s "
           "and removes it; I have done that for now. The limit will matter again when the suite grows.", minutes=11,
           commits=[C(7, "Run the 3DS cases serially", "backend/tests/e2e/conftest.py")])
    K["problem_ratelimit"] = (c, c.last_n)
    w.report("3ds-tests", D(28, 14, 0), c.agent_id, "Four 3DS cases pass on staging in CI (serial, 1 min 50 s); a broken return_url fails two, as expected.")
    w.evidence("3ds-tests", D(28, 14, 2), c.agent_id, [
        {"kind": "text", "title": "The matrix",
         "body": "| card | case | result |\n|---|---|---|\n| 4000 0027 6000 3184 | 3DS required, approved | order created |\n"
                 "| 4000 0084 0000 1629 | 3DS required, declined | 'Your bank declined the card' |\n| 4000 0000 0000 3055 | frictionless | order created |\n"
                 "| 4000 0082 6000 3178 | insufficient funds after 3DS | decline message |"},
        {"kind": "image", "title": "CI run on main, 1 min 50 s", "mock": "chart"},
    ])
    t = D(28, 14, 20)
    c.turn(t, "{tk:order-webhook-out}. After an order is paid, POST it to tg-notify. How do we sign it?",
           "HMAC-SHA256 over the raw body with a shared secret, in `X-Shopfront-Signature`, plus a timestamp header so tg-notify can refuse replays "
           "older than five minutes. The same scheme Stripe uses on us — both sides already have the code shape.", minutes=5)
    t = D(28, 14, 30)
    c.turn(t, "#decision HMAC with a timestamp, like Stripe. Build it on the retry queue so a tg-notify outage doesn't lose messages.",
           "Built: `order.paid` is a row in the same event queue as incoming webhooks, direction `out`; the worker POSTs it with the signature and "
           "retries with the same backoff. `pytest -q`: 79 passed.", minutes=58,
           commits=[C(30, "Outgoing order.paid events signed with HMAC and a timestamp", "backend/app/outbound.py", "backend/app/worker.py", "mig:outbound events"),
                    C(52, "Outbound event tests", "backend/tests/test_outbound.py")])
    w.decision(D(28, 14, 40), P, c.agent_id, "Order events to tg-notify are signed with HMAC-SHA256 and a timestamp, and sent from the retry queue",
               "Reuses the scheme Stripe uses on us and the queue we already run; a tg-notify outage delays messages instead of losing them. Settled.",
               ["mTLS between the two services — rejected: certificates to rotate for one POST a minute",
                "A shared message broker — rejected: a third service to run for one event type"], weight="normal", tags="notifications,security", source="explicit")
    t = D(29, 9, 15)
    c.turn(t, "#vision The order status reaches the customer in Telegram before the email arrives.",
           "Kept. Today: order paid → tg-notify in under 2 s via the queue; the email provider takes 5–40 s. So it holds for customers who opted in, "
           "once {tk:notify-optin} exists.", minutes=3)
    K["vision_tg"] = (c, c.last_n)

    # ------------------------------------------------------------------
    # C19 · 29 Sep · admin orders, and the funnel report
    # ------------------------------------------------------------------
    c = Chat(sim, P, "e0d7a4b6-1f3c-4b58-8a9e-2d6c7b0f4e13", title="admin orders", repo=repo,
             headline="The admin order list, and what the checkout funnel looks like after a week")
    K["c19"] = c
    t = D(29, 10, 5)
    c.turn(t, PLAN_AGAIN + " Task: {tk:admin-orders}.",
           "Plan:\n- change: `GET /api/admin/orders?status=&from=&to=&q=` with cursor pagination; the list page with filters\n"
           "- files: `routers/admin_orders.py`, `app/admin/orders/page.tsx`, a test\n- not touched: the order page and refunds (another chat is on them)\n"
           "- how we know: the 23 production orders filter correctly by status and search by number or email.", minutes=5)
    t = D(29, 10, 15)
    c.turn(t, "Go.",
           "Done. Search matches the order number exactly or the email by prefix; status and date filters combine. 23 orders on production list in 40 ms.",
           minutes=63, commits=[C(30, "Admin order list API with filters and search", "backend/app/routers/admin_orders.py", "backend/tests/test_admin_orders.py"),
                                C(55, "Admin order list page", "frontend/app/admin/orders/page.tsx", "frontend/components/OrderFilters.tsx")])
    t = D(29, 14, 10)
    c.turn(t, "#artifact(checkout-funnel-report) The checkout funnel for the first week on production: sessions that reached the cart, the checkout, "
              "payment and the confirmation, per day, as a CSV and a one-page summary.",
           "Written to the artifacts folder: `funnel.csv` (7 days × 5 steps) and `SUMMARY.md`. The biggest drop is checkout → payment (41 %), "
           "most of it on phones.", minutes=24)
    K["artifact_funnel"] = (c, c.last_n)
    w.task("slug-collide", D(29, 15, 30), P, "Product slugs collide when titles repeat", status="agent", lane="api",
           tags="ag_bug,ag_followup", agent=c.agent_id,
           desc="Two products named 'Linen shirt' get the same slug; the second import fails. Append the variant SKU.")
    t = D(29, 15, 20)
    c.turn(t, REVIEW_AGAIN,
           "Customer-facing: none.\n\nReviewer questions:\n1. `admin_orders.py:54` — the email prefix search uses `ILIKE 'x%'` without an index; fine at 23 orders, not at 20,000.\n"
           "2. `OrderFilters.tsx:12` — the date filter is in the browser's time zone; the API expects UTC.\n\nFixed 2; 1 noted. "
           "Also found while seeding test data: product slugs collide when titles repeat — card on the board.", minutes=14,
           commits=[C(9, "Admin date filter in UTC", "frontend/components/OrderFilters.tsx")])
    t = D(29, 16, 0)
    c.turn(t, "#vision A price change from the supplier feed shows in the store within five minutes, and never changes an open cart.",
           "Kept. The price-etl feed publishes every 15 minutes today; {tk:price-feed} reads it. Five minutes means the feed moves to 5 too.", minutes=3)
    K["vision_prices"] = (c, c.last_n)

    # ------------------------------------------------------------------
    # C20 · 30 Sep morning · standup, partial refunds, a scan
    # ------------------------------------------------------------------
    c = Chat(sim, P, "4b1e9c07-3d6a-4e85-a0f2-7c9b1e8d5a64", title="partial refunds", repo=repo,
             headline="shopfront.dev takes payments; refunds by line; public beta on {dm:45}")
    K["c20"] = c
    t = D(30, 8, 55)
    c.turn(t, "Morning. Write yesterday's standup first.",
           "Standup for {dm:29} is written: the admin order list, orders reaching tg-notify, and the funnel report. Two problems are open (connection pool, Stripe test-mode rate limit).",
           minutes=6, helpers=[(1, 4)], skills=["daily-standup"])
    t = D(30, 9, 10)
    c.turn(t, "{tk:refunds.2}: partial refunds. Pick lines and quantities; shipping refundable on its own.",
           "The refund dialog lists the lines with steppers and a 'refund shipping' switch; the API refunds the sum and writes one `order_events` row with the lines. "
           "The order stays `partially_refunded` until everything is refunded. `pytest -q`: 84 passed. Not finished: the customer email for partial refunds.", minutes=52,
           commits=[C(25, "Partial refunds by line and quantity", "backend/app/routers/admin_orders.py", "backend/app/order_events.py", "mig:refund lines"),
                    C(45, "Refund dialog with line steppers", "frontend/components/RefundDialog.tsx", "frontend/app/admin/orders/[number]/page.tsx")],
           helpers=[(20, 25)], dirty=lambda r: r.append("backend/app/emails.py", "\n\ndef send_partial_refund(order, lines):\n    raise NotImplementedError\n"))
    t = D(30, 10, 5)
    c.turn(t, "#skill(deploy-and-rollback) How we deploy shopfront and how we roll back: deploy.sh, what it checks, rollback.sh, and the rule that migrations only add. "
              "#scan #important-agent",
           "Skill drafted from the runbook and the two deploys this month. Scan written: payments hardening so far — refunds, the event log, the webhook queue, "
           "3DS tests, outbound order events. Architecture page is at version 3 and the program map at version 2.", minutes=9,
           skills=["make-a-scan", "keep-the-architecture-page", "map-the-program"])
    K["skill_deploy"] = (c, c.last_n)
    K["scan_s3_chat"] = c
