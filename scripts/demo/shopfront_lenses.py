"""shopfront around the chats: sprints, milestones, scans and the architecture,
standups, the kept messages' interpretations, time, the calendar."""

from __future__ import annotations

from engine import D, Chat, dated, timedelta
from shopfront_pages import MAP_V1, MAP_V2, PAGE_V1, PAGE_V2, PAGE_V3

P = "shopfront"


def f(path, imp, blast, cov, novelty, why, action="modified", sec=False, conf=80):
    return {"path": path, "action": action, "importance": imp, "blast_radius": blast,
            "test_coverage": cov, "novelty": novelty, "security_surface": sec,
            "agent_confidence": conf, "why": why}


def setup(sim, w, repo, K):
    # ------------------------------------------------------------------ sprints
    w.sprint("s1", D(1, 8, 30), "Catalog foundations", "a catalog a customer can browse, search and put in a cart",
             P, D(1), D(10), budget=45, confidence=70, declared=5)
    w.sprint("s2", D(9, 16, 50), "Checkout v1", "a real customer can pay, and we can prove it",
             P, D(11), D(22), budget=60, confidence=60, declared=6)
    w.sprint("s3", D(21, 9, 30), "Payments hardening", "nothing a customer pays for is lost, doubled or unexplained",
             P, D(23), D(30) + timedelta(days=6), budget=55, confidence=65, declared=6)
    w.sprint("s4", D(23, 17, 0), "Order notifications", "a paid order reaches the customer in Telegram",
             "tg-notify,shopfront", D(24), D(30) + timedelta(days=7), budget=30, confidence=55, declared=3)
    w.end_sprint("s1", D(10, 18, 30),
                 "Shipped what was planned except the image optimizer's AVIF switch: the catalog, search, the cart and staging. "
                 "The cart took a day longer than bet because the server-side decision came mid-sprint. Estimate for checkout raised accordingly.",
                 ["Planned 5 outcomes, shipped 5; 17 of 17 tasks done",
                  "Server-side cart decided on day 8, cost one day",
                  "Staging deploy is one script; first deploy 3 min 10 s",
                  "Carry-over: none"], shipped=5)
    w.end_sprint("s2", D(22, 18, 0),
                 "A real customer paid on day 12 and every step was seen: webhook, order, email, refund caught. "
                 "The webhook signature bug cost most of a day and was ours, not the proxy's. Stripe Tax is in review, not done.",
                 ["Planned 6 outcomes, shipped 5; Stripe Tax carried into review",
                  "First real payment: SF-10001, {dsh:22} 09:12",
                  "One incident on staging: webhook signatures, fixed the same day",
                  "Guest checkout measured at 52 s on a phone"], shipped=5)

    # ------------------------------------------------------------------ milestones
    w.milestone("m-first", D(17, 17, 10), P, "First real payment",
                "A customer can pay with a real card on shopfront.dev and receives the order.",
                "One live-mode payment produces an order, a webhook, an email and a refundable charge, all seen in the logs.",
                "{iso:22}", ["checkout-page", "webhooks", "prod-deploy", "first-payment", "confirm-email"], position=1)
    w.milestone_update("m-first", D(22, 16, 35), status="reached", reached_date="{iso:22}",
                       proof="SF-10001 on {dsh:22} 09:12: webhook 0.4 s after payment, email sent, dashboard refund received.")
    w.milestone("m-beta", D(25, 17, 30), P, "Public beta",
                "The store is open to the waitlist: refunds work, nothing is lost under load, and the pages a store must have exist.",
                "50 checkouts a minute for 10 minutes with no errors; a partial refund end to end; legal pages live; backups restored once.",
                "{iso:45}", ["refunds", "webhook-retries", "db-connections", "load-test", "backup", "admin-auth",
                                "legal-pages", "lcp-images", "product-copy", "seo-meta"], position=2)
    w.milestone("m-telegram", D(24, 10, 10), P, "Order updates in Telegram",
                "A customer who opts in hears about payment and shipping in Telegram.",
                "A test order placed on production produces a Telegram message within 5 seconds.",
                "{iso:37}", ["order-webhook-out", "notify-optin"], position=3)
    w.milestone("m-catalog", D(24, 11, 5), P, "Full catalog from the supplier feed",
                "Prices and stock come from the supplier feed; the store lists every product we sell.",
                "The price-etl file is read every 15 minutes and 200 products are live.",
                "{iso:61}", ["price-feed", "inventory", "i18n"], status="planned", position=4)

    # ------------------------------------------------------------------ links
    w.link("checkout-choice", "checkout-page", "blocks", D(11, 12, 30))
    w.link("payment-intent", "checkout-page", "blocks", D(14, 9, 12))
    w.link("webhooks", "confirm-email", "blocks", D(15, 10, 12))
    w.link("first-payment", "prod-deploy", "parent", D(17, 17, 12))
    w.link("first-payment", "webhooks", "parent", D(17, 17, 13))
    w.link("first-payment", "checkout-page", "parent", D(17, 17, 14))
    w.link("webhook-proxy-fix", "webhooks", "relates", D(16, 11, 40))
    w.link("db-connections", "load-test", "blocks", D(25, 15, 20))
    w.link("order-events", "webhook-retries", "relates", D(24, 10, 12))
    w.link("refunds", "returns", "blocks", D(25, 16, 15))
    w.link("lcp-images", "image-cdn", "relates", D(28, 9, 30))
    w.link("two-formatters", "money-minor", "relates", D(21, 9, 40))
    w.link("cart-api", "cart-drawer", "blocks", D(8, 10, 22))

    # ------------------------------------------------------------------ calendar
    w.calendar(D(8, 9, 0), P, "meeting", "{iso:10}", "Sprint review: Catalog foundations", time="17:30", end_time="18:15",
               body="Demo on staging, then retro. Decide the checkout approach before the next sprint starts.", people="operator")
    w.calendar(D(12, 11, 0), P, "meeting", "{iso:16}", "Call with the payment provider's onboarding", time="15:00", end_time="15:30",
               body="Live-mode activation, payout schedule, Stripe Tax registrations for DE and NL.")
    w.calendar(D(15, 9, 0), P, "deadline", "{iso:21}", "Live-mode keys and webhook secret on the production host",
               task="prod-deploy")
    w.calendar(D(20, 10, 0), P, "meeting", "{iso:22}", "Sprint review: Checkout v1", time="17:30", end_time="18:00")
    w.calendar(D(25, 17, 40), P, "deadline", "{iso:45}", "Public beta opens to the waitlist", milestone="m-beta")
    w.calendar(D(23, 9, 0), P, "reminder", "{iso:26}", "Photographer delivers the autumn product shots",
               body="42 images, 2400 px long edge, sRGB. Upload to img.shopfront.dev/autumn/.")
    w.calendar(D(24, 12, 0), P, "reminder", "{iso:31}", "VAT registration: check the NL number is active in Stripe Tax")
    w.calendar(D(25, 17, 0), P, "meeting", "{iso:32}", "Launch review with the copywriter", time="11:00", end_time="12:00",
               body="Best-seller copy, FAQ, the confirmation email tone.", task="product-copy")
    w.calendar(D(28, 12, 0), P, "note", "{iso:28}", "Staging LCP on product pages down to 1.7 s", task="lcp-images")
    w.calendar(D(29, 9, 0), P, "event", "{iso:36}", "Payments hardening ends", milestone="m-beta")

    # ------------------------------------------------------------------ scans
    scan_turn(sim, w, K["c2"], D(3, 16, 30), "#scan", "Scan written: the catalog API, the seed and the first two storefront pages. File entry and the architecture form are in.")
    w.scan("scan1", D(3, 16, 34), P, K["c2"].agent_id,
           "A customer can browse 48 seeded products on a grid and open any product with its variants and prices",
           "The first three days were to be the catalog end to end, backend to page. It is: data, API and two pages exist and agree on prices.",
           ["Products and variants in Postgres with integer prices",
            "GET /api/products with cursor pagination and GET /api/products/{slug}",
            "48 products seeded from content/catalog.csv, safe to re-run",
            "Home page grid and the product page with a variant picker kept in the URL",
            "CI runs lint, tests and type-check on every push"],
           "Claim: prices agree between API and page — checked: the grid and product page read price_amount through formatMoney only.\n"
           "Claim: seeding is idempotent — checked: second run prints '48 products, 0 changed'.\n"
           "Claim: CI blocks a broken test — checked on a deliberately failing commit, then reverted.",
           "backend, frontend")
    w.file_entry(D(3, 16, 37), P, K["c2"].agent_id, "scan1", "15 files · catalog API, seed and the first pages",
                 "The catalog exists end to end. The riskiest files are the schema and the products router: every later feature reads them. "
                 "The frontend pages are new and untested beyond type-checking.",
                 ["backend/app/routers/products.py — list_products (cursor), get_product (by slug)",
                  "backend/app/models.py — Product, Variant with price_amount/currency",
                  "scripts/seed_catalog.py — upsert by SKU, euro-comma parsing",
                  "frontend/components/ProductGrid.tsx — server component, 24 per page"],
                 [f("backend/app/models.py", 5, 9, "covered", "new", "Every feature reads products and variants; prices live here.", "created"),
                  f("backend/app/routers/products.py", 4, 7, "covered", "new", "The storefront's only data source.", "created"),
                  f("scripts/seed_catalog.py", 3, 3, "covered", "new", "Idempotent upsert; wrong prices here are wrong prices everywhere.", "created"),
                  f("frontend/components/ProductGrid.tsx", 3, 4, "untested", "new", "Home page; renders every product.", "created"),
                  f("frontend/app/products/[slug]/page.tsx", 4, 5, "untested", "new", "Product page and the variant choice that feeds the cart.", "created"),
                  f(".github/workflows/ci.yml", 3, 6, "partial", "new", "Gatekeeper for every push.", "created")],
                 since_first=True)
    w.arch_form(D(3, 16, 42), P, K["c2"].agent_id, "scan1", [
        {"op": "add", "type": "feature", "name": "Product catalog", "path": ["backend/app/routers/products.py"],
         "endpoint": "GET /api/products", "note": "List with cursor pagination, detail by slug."},
        {"op": "add", "type": "database", "name": "Postgres: products and variants", "path": ["backend/app/models.py"],
         "engine": "postgres 16", "tables": "products, variants", "note": "Prices as integer minor units per variant."},
        {"op": "add", "type": "endpoint", "name": "GET /api/products/{slug}", "path": ["backend/app/routers/products.py"],
         "method": "GET", "route": "/api/products/{slug}", "service": "api"},
        {"op": "add", "type": "surface", "name": "Home page grid", "path": ["frontend/app/page.tsx"], "route": "/", "service": "web"},
        {"op": "add", "type": "surface", "name": "Product page", "path": ["frontend/app/products/[slug]/page.tsx"],
         "route": "/products/[slug]", "service": "web"},
        {"op": "add", "type": "command", "name": "seed_catalog", "path": ["scripts/seed_catalog.py"],
         "usage": "python scripts/seed_catalog.py content/catalog.csv"},
        {"op": "add", "type": "rule", "name": "Money is integer minor units", "path": ["frontend/lib/money.ts"],
         "check": "no float or Decimal in API payloads; one formatter in the frontend", "enforced_in": "code review"},
        {"op": "add", "type": "tests", "name": "API tests in CI", "path": [".github/workflows/ci.yml"],
         "command": "cd backend && pytest -q", "covers": "models, products, seed"},
    ])

    w.scan("scan2", D(10, 17, 14), P, K["c6"].agent_id,
           "Search and a server-side cart are on staging: a customer can find a product, fill a cart and see a total the server computed",
           "Sprint 1 asked for browse, search and cart on a real host. Done; the image optimizer change was dropped to the backlog.",
           ["Full-text search in Postgres with prefix and accent matching",
            "Instant results under the header search box; stale answers dropped",
            "Carts stored server-side behind a signed cookie; totals in cents",
            "Cart drawer with steppers that clamp at stock",
            "staging.shopfront.dev behind Caddy, deployed by one script"],
           "Claim: the total cannot be changed from the browser — checked: a PATCH with a price field is ignored (test_cart.py).\n"
           "Claim: staging is reproducible — checked: deploy.sh on a clean VM, 3 min 10 s.\n"
           "Not checked: search quality beyond the 48 seed products.",
           "backend, frontend, infra")
    w.file_entry(D(10, 17, 18), P, K["c6"].agent_id, "scan2", "18 files · search, cart and staging",
                 "The cart is the first place the server refuses to trust the browser; cart.py and cart_cookie.py carry that. "
                 "Search is self-contained. Infra is new and has no tests except the health check after deploy.",
                 ["backend/app/routers/cart.py — add/patch/delete lines, totals, stock clamp",
                  "backend/app/cart_cookie.py — sign/verify the cart id",
                  "backend/app/routers/search.py — ts_rank with prefix tsquery",
                  "infra/deploy.sh — pull, build, migrate, restart, check"],
                 [f("backend/app/routers/cart.py", 5, 8, "covered", "new", "Totals are computed here and nowhere else.", "created"),
                  f("backend/app/cart_cookie.py", 4, 7, "covered", "new", "A forged cookie would read someone else's cart.", "created", sec=True),
                  f("backend/app/routers/search.py", 3, 3, "covered", "new", "Self-contained; slow queries would show in the header box.", "created"),
                  f("frontend/components/CartDrawer.tsx", 4, 5, "untested", "new", "Every purchase passes through it.", "created"),
                  f("frontend/components/SearchBox.tsx", 2, 3, "untested", "new", "Debounce and stale-answer handling.", "created"),
                  f("infra/deploy.sh", 4, 8, "untested", "new", "A bad deploy takes staging down; no rollback yet.", "created")])
    w.arch_form(D(10, 17, 22), P, K["c6"].agent_id, "scan2", [
        {"op": "add", "type": "feature", "name": "Search", "path": ["backend/app/routers/search.py", "frontend/components/SearchBox.tsx"],
         "endpoint": "GET /api/search", "surface": "header search box"},
        {"op": "add", "type": "feature", "name": "Server-side cart", "path": ["backend/app/routers/cart.py"], "endpoint": "/api/cart"},
        {"op": "add", "type": "auth", "name": "Signed cart cookie", "path": ["backend/app/cart_cookie.py"],
         "mechanism": "HMAC-signed cart id in an HttpOnly cookie", "checked_in": "cart router dependency"},
        {"op": "add", "type": "deploy", "name": "Staging VM", "path": ["infra/deploy.sh", "infra/Caddyfile"], "command": "infra/deploy.sh"},
        {"op": "add", "type": "service", "name": "Caddy", "path": ["infra/Caddyfile"], "start": "docker compose up", "port": "443"},
        {"op": "add", "type": "debt", "name": "No rollback for deploys", "path": ["infra/deploy.sh"],
         "risk": "a failed deploy leaves staging down until fixed forward"},
    ])
    w.arch_page(D(10, 17, 26), P, K["c6"].agent_id, PAGE_V1, "First version: catalog, search, cart, staging.")

    scan_turn(sim, w, K["c9"], D(16, 18, 10), "#scan, and map the program while you're at it — the shape changed a lot this week.",
              "Scan written for the checkout week so far, with the file entry and the architecture form. The program map is at version 1: 34 rows, 18 relations.")
    w.scan("scan3", D(16, 18, 14), P, K["c9"].agent_id,
           "A customer can pay on our own checkout page, and the webhook turns the payment into exactly one order",
           "The week asked for a working checkout with orders created reliably. The checkout and orders work on staging; the webhook signature bug was found and fixed the same day.",
           ["Checkout page with address, shipping and the Payment Element",
            "PaymentIntent created from the server cart with an idempotency key per cart version",
            "Orders created only by the payment_intent.succeeded webhook, deduplicated on the event id",
            "Guest checkout: an email is the only identity",
            "Flat EU shipping, free from €60",
            "Fixed: webhook signatures failed on staging because our logger re-serialised the body"],
           "Claim: one intent per cart version — checked: 20 parallel requests, one intent.\n"
           "Claim: a replayed event creates nothing — checked: 12 failed events replayed, 3 orders, 9 no-ops.\n"
           "Not checked: live mode.", "backend, frontend")
    w.file_entry(D(16, 18, 18), P, K["c9"].agent_id, "scan3", "21 files · checkout, orders and the webhook",
                 "Money now moves. The webhook router and stripe_client are the two files where a bug costs real money; both are covered, "
                 "the webhook by replay tests. The checkout page is large and untested in the browser.",
                 ["backend/app/routers/webhooks.py — verify raw body, dedupe event id, create order",
                  "backend/app/stripe_client.py — every call wrapped, idempotency key required",
                  "backend/app/routers/checkout.py — intent from cart, shipping, guest email",
                  "backend/app/logging_mw.py — skip body logging on /webhooks/*"],
                 [f("backend/app/routers/webhooks.py", 5, 10, "covered", "new", "Creates orders from payments; a bug here loses or doubles orders.", "created", sec=True),
                  f("backend/app/stripe_client.py", 5, 9, "covered", "new", "The only door to Stripe; enforces idempotency keys.", "created", sec=True),
                  f("backend/app/routers/checkout.py", 5, 8, "covered", "new", "Computes what the customer is charged.", "created"),
                  f("backend/app/orders.py", 4, 7, "covered", "new", "Order numbers and the copy of prices at purchase time.", "created"),
                  f("backend/app/logging_mw.py", 3, 9, "covered", "pattern-break", "The cause of the signature incident; now skips webhooks.", "created"),
                  f("frontend/components/PaymentStep.tsx", 4, 6, "untested", "new", "Mounts Stripe's element; no card data touches our code.", "created", sec=True),
                  f("backend/app/shipping.py", 3, 4, "covered", "new", "Part of the charged amount.", "created")])
    w.arch_form(D(16, 18, 22), P, K["c9"].agent_id, "scan3", [
        {"op": "add", "type": "integration", "name": "Stripe", "path": ["backend/app/stripe_client.py"],
         "direction": "both", "auth": "secret key; webhook signing secret", "note": "PaymentIntents out, webhooks in."},
        {"op": "add", "type": "hook", "name": "Stripe webhook", "path": ["backend/app/routers/webhooks.py"],
         "host": "Stripe", "event": "payment_intent.succeeded", "note": "Dedupe on event id, create the order once."},
        {"op": "add", "type": "endpoint", "name": "POST /api/checkout/intent", "path": ["backend/app/routers/checkout.py"],
         "method": "POST", "route": "/api/checkout/intent", "service": "api"},
        {"op": "add", "type": "database", "name": "Postgres: orders", "path": ["backend/app/orders.py"],
         "engine": "postgres 16", "tables": "orders, order_lines, stripe_events"},
        {"op": "add", "type": "surface", "name": "Checkout page", "path": ["frontend/app/checkout/page.tsx"], "route": "/checkout", "service": "web"},
        {"op": "add", "type": "rule", "name": "Idempotency key on every Stripe call", "path": ["backend/app/stripe_client.py"],
         "check": "stripe_client refuses a call without a key; ruff flags stripe.* elsewhere", "enforced_in": "stripe_client.py, ruff"},
        {"op": "add", "type": "fix", "name": "Webhook signature over the raw body", "path": ["backend/app/logging_mw.py"],
         "note": "The logger re-serialised JSON before the signature check.", "task": "webhook-proxy-fix"},
    ])
    w.map(D(16, 18, 26), P, K["c9"].agent_id, MAP_V1, "First map: storefront, API, Postgres, Stripe, staging.")

    w.scan("scan4", D(22, 16, 44), P, K["c12"].agent_id,
           "shopfront.dev is live: the first real payment became order SF-10001 with its email, and VAT is split per country",
           "Checkout v1 was to end with a real payment we could prove. It did, on day 12; the refund showed we do not handle refunds yet.",
           ["Production on shopfront.dev with a tested rollback",
            "Order confirmation email, sent once per order",
            "Order confirmation page waits for the webhook",
            "Stripe Tax on VAT-inclusive prices (in review)",
            "First live payment: SF-10001, €22.90"],
           "Claim: rollback works — checked twice, 42 s on staging and 38 s on production.\n"
           "Claim: the email is sent once — checked by replaying the webhook three times.\n"
           "Seen: a dashboard refund is logged and ignored; tracked as refunds.", "infra, backend")
    w.file_entry(D(22, 16, 48), P, K["c12"].agent_id, "scan4", "16 files · production, email, tax",
                 "Production is a second compose file and two scripts. The email and tax code both hang off the order; tax changes what the invoice says, not what is charged.",
                 ["infra/rollback.sh — restart the previous images; no migration down",
                  "backend/app/emails.py — send once, keyed on the order",
                  "backend/app/tax.py — inclusive tax calculation per intent"],
                 [f("infra/docker-compose.prod.yml", 4, 10, "untested", "new", "Production itself.", "created"),
                  f("infra/rollback.sh", 5, 10, "partial", "new", "Run twice by hand; the only way back from a bad deploy.", "created"),
                  f("backend/app/emails.py", 3, 5, "covered", "new", "Customer-visible; must never double-send.", "created"),
                  f("backend/app/tax.py", 4, 6, "covered", "new", "Invoice VAT per country.", "created"),
                  f("backend/app/money.py", 2, 4, "covered", "pattern-break", "Second money formatter, for emails. Known debt.", "created")])
    w.arch_form(D(22, 16, 52), P, K["c12"].agent_id, "scan4", [
        {"op": "add", "type": "deploy", "name": "Production VM", "path": ["infra/docker-compose.prod.yml", "infra/rollback.sh"],
         "command": "infra/deploy.sh (prod env)"},
        {"op": "remove", "type": "debt", "name": "No rollback for deploys", "path": ["infra/deploy.sh"], "note": "rollback.sh, tested twice."},
        {"op": "add", "type": "feature", "name": "Order confirmation email", "path": ["backend/app/emails.py"], "surface": "email"},
        {"op": "add", "type": "integration", "name": "Stripe Tax", "path": ["backend/app/tax.py"], "direction": "outbound", "auth": "secret key"},
        {"op": "add", "type": "debt", "name": "Two money formatters", "path": ["backend/app/money.py", "frontend/lib/money.ts"],
         "risk": "emails and the storefront could show different amounts for a new currency"},
        {"op": "add", "type": "action-needed", "name": "Refunds are not handled", "path": ["backend/app/routers/webhooks.py"],
         "action": "handle charge.refunded and add admin refunds", "by_when": "before the public beta"},
    ])
    w.arch_page(D(22, 16, 56), P, K["c12"].agent_id, PAGE_V2, "Second version: checkout, orders, production, the first payment.")

    scan_turn(sim, w, K["c16"], D(25, 16, 20), "#scan", "Scan written: refunds, the order event log, the webhook queue, the load test and the launch pages.")
    w.scan("scan5", D(25, 16, 24), P, K["c16"].agent_id,
           "Refunds and every order state change are recorded with their cause, and webhooks are stored before they are processed",
           "The week asked that nothing paid for is lost or unexplained. Refunds and the event log do that; the load test found the database pool is the next limit.",
           ["Full refunds from the admin order page",
            "order_events: every state change with its Stripe event or admin",
            "Incoming webhooks stored first, processed by a worker with backoff",
            "Load test at 50 checkouts/min: pool exhaustion after 7 minutes",
            "Terms, privacy, imprint and FAQ pages", "Plain decline messages"],
           "Claim: a failing handler retries — checked by test_failed_handler_retries_with_backoff.\n"
           "Claim: refunds only for paid orders — checked after review found the gap.\n"
           "Open: the pool limit, logged as a problem.", "backend, frontend, loadtest")
    w.file_entry(D(25, 16, 28), P, K["c16"].agent_id, "scan5", "24 files · refunds, events, the webhook queue",
                 "The webhook path changed shape: the request only stores; the worker acts. That moves the risk from the endpoint to worker.py.",
                 ["backend/app/worker.py — claim with SKIP LOCKED, backoff, dead after five",
                  "backend/app/order_events.py — one writer for every transition",
                  "backend/app/routers/admin_orders.py — refund endpoint"],
                 [f("backend/app/worker.py", 5, 9, "covered", "new", "Every order now passes through it.", "created"),
                  f("backend/app/routers/webhooks.py", 4, 10, "covered", "pattern-break", "Now stores and returns; processing moved out.", "modified", sec=True),
                  f("backend/app/order_events.py", 4, 6, "covered", "new", "The audit trail support will read.", "created"),
                  f("backend/app/routers/admin_orders.py", 5, 7, "covered", "new", "Moves money back to customers.", "created", sec=True),
                  f("loadtest/checkout.js", 2, 1, "untested", "new", "Test harness only.", "created"),
                  f("frontend/lib/declines.ts", 2, 3, "untested", "new", "What a declined customer reads.", "created")])
    w.arch_form(D(25, 16, 32), P, K["c16"].agent_id, "scan5", [
        {"op": "add", "type": "service", "name": "webhook worker", "path": ["backend/app/worker.py"], "start": "python -m app.worker"},
        {"op": "add", "type": "queue", "name": "stripe_events table", "path": ["backend/app/worker.py"],
         "producer": "webhook endpoint", "consumer": "worker"},
        {"op": "add", "type": "feature", "name": "Refunds", "path": ["backend/app/routers/admin_orders.py"], "endpoint": "POST /api/admin/orders/{number}/refund"},
        {"op": "add", "type": "database", "name": "Postgres: order_events", "path": ["backend/app/order_events.py"], "engine": "postgres 16", "tables": "order_events"},
        {"op": "add", "type": "surface", "name": "Legal pages", "path": ["frontend/app/(legal)/[page]/page.tsx"], "route": "/terms, /privacy, /imprint"},
        {"op": "add", "type": "action-needed", "name": "Database pool exhausted at 50 checkouts/min", "path": ["backend/app/db.py"],
         "action": "shorten transactions around Stripe calls or add pgbouncer", "by_when": "before the public beta", "task": "db-connections"},
        {"op": "remove", "type": "action-needed", "name": "Refunds are not handled", "path": ["backend/app/routers/webhooks.py"]},
    ])

    scan_turn(sim, w, K["c17"], D(28, 16, 0), "#scan", "Scan written: product pages load in 1.7 s, the sitemap, and the 3DS tests.")
    w.scan("scan6", D(28, 16, 4), P, K["c17"].agent_id,
           "Product pages show their main image in 1.7 s on a throttled phone instead of 4.8 s",
           "The day was for launch polish: page speed and search engines. Both done on staging; production follows the next deploy.",
           ["Hero images served as AVIF at the displayed width and preloaded",
            "sitemap.xml with 64 URLs and robots.txt without cart, checkout or admin",
            "3-D Secure cases run in CI against staging",
            "Paid orders are sent to tg-notify, signed and retried"],
           "Claim: LCP 1.7 s — checked with Lighthouse mobile on staging, same page and settings as the 4.8 s run.\n"
           "Not checked: production LCP.", "frontend, backend")
    w.file_entry(D(28, 16, 8), P, K["c17"].agent_id, "scan6", "14 files · images, sitemap, 3DS, outbound events",
                 "Two independent threads: images and search engines on the frontend, and outbound order events plus 3DS tests on the backend.",
                 ["frontend/components/ProductGallery.tsx — sizes per breakpoint, priority on the hero",
                  "frontend/app/sitemap.ts — catalog-driven sitemap",
                  "backend/app/outbound.py — HMAC-signed order.paid"],
                 [f("frontend/components/ProductGallery.tsx", 4, 5, "untested", "new", "The LCP element of every product page.", "created"),
                  f("frontend/next.config.mjs", 3, 8, "untested", "pattern-follow", "AVIF switched on for every image."),
                  f("frontend/app/sitemap.ts", 2, 2, "untested", "new", "Search engines only.", "created"),
                  f("backend/app/outbound.py", 4, 5, "covered", "new", "Signs what tg-notify trusts.", "created", sec=True),
                  f("backend/tests/e2e/test_3ds.py", 3, 2, "covered", "new", "The only browser test of payment.", "created")])
    w.arch_form(D(28, 16, 12), P, K["c17"].agent_id, "scan6", [
        {"op": "change", "type": "surface", "name": "Product page", "path": ["frontend/app/products/[slug]/page.tsx"],
         "route": "/products/[slug]", "note": "Hero preloaded; AVIF at displayed width."},
        {"op": "add", "type": "surface", "name": "sitemap.xml", "path": ["frontend/app/sitemap.ts"], "route": "/sitemap.xml"},
        {"op": "add", "type": "integration", "name": "tg-notify", "path": ["backend/app/outbound.py"],
         "direction": "outbound", "auth": "HMAC-SHA256 with timestamp"},
        {"op": "add", "type": "tests", "name": "3DS end-to-end matrix", "path": ["backend/tests/e2e/test_3ds.py"],
         "command": "pytest backend/tests/e2e -q", "covers": "3DS required, failed, frictionless, insufficient funds"},
    ])

    w.scan("scan7", D(30, 10, 8), P, K["c20"].agent_id,
           "Refunds work line by line, and support can read every order's history on the admin page",
           "The sprint asks that nothing a customer pays for is lost, doubled or unexplained. Partial refunds and the admin list close most of it; "
           "the refund email and the pool limit are open.",
           ["Partial refunds by line and quantity, shipping on its own",
            "Admin order list with status, date and search",
            "Paid orders reach tg-notify within 2 s",
            "Checkout funnel report for the first week"],
           "Claim: a partial refund leaves the order open — checked in test_refunds.py.\nOpen: the partial-refund email is not written (uncommitted stub).",
           "backend, frontend")
    w.file_entry(D(30, 10, 11), P, K["c20"].agent_id, "scan7", "9 files · partial refunds and the admin list",
                 "Refunds grew from whole orders to lines; the admin list is new. One uncommitted stub in emails.py is the next step.",
                 ["backend/app/routers/admin_orders.py — refund lines, list with filters",
                  "frontend/components/RefundDialog.tsx — steppers per line, shipping switch"],
                 [f("backend/app/routers/admin_orders.py", 5, 7, "covered", "pattern-follow", "Refund amounts are computed here.", "modified", sec=True),
                  f("frontend/components/RefundDialog.tsx", 4, 4, "untested", "new", "What the operator clicks to move money back.", "created"),
                  f("frontend/app/admin/orders/page.tsx", 3, 3, "untested", "new", "Support's starting point.", "created"),
                  f("backend/app/emails.py", 2, 5, "untested", "pattern-follow", "Stub for the partial-refund email, not committed.")])
    w.arch_form(D(30, 10, 13), P, K["c20"].agent_id, "scan7", [
        {"op": "change", "type": "feature", "name": "Refunds", "path": ["backend/app/routers/admin_orders.py", "frontend/components/RefundDialog.tsx"],
         "note": "Partial refunds by line; order stays partially_refunded."},
        {"op": "add", "type": "surface", "name": "Admin order list", "path": ["frontend/app/admin/orders/page.tsx"], "route": "/admin/orders"},
        {"op": "add", "type": "action-needed", "name": "Admin has no sign-in", "path": ["frontend/app/admin/orders/page.tsx"],
         "action": "put /admin behind SSO", "by_when": "before the public beta", "task": "admin-auth"},
    ])
    w.arch_page(D(30, 10, 15), P, K["c20"].agent_id, PAGE_V3, "Third version: payments hardening, outbound events, what the beta still owes.")
    w.map(D(30, 10, 17), P, K["c20"].agent_id, MAP_V2, "Worker, event log, outbound events, admin; 44 rows.")

    # ------------------------------------------------------------------ extra decisions
    w.decision(D(7, 10, 10), P, K["c4"].agent_id, "Search runs on Postgres full-text, not a search service",
               "48 products today and a few thousand at most this year; a GIN index answers in milliseconds and there is nothing else to run.",
               ["Meilisearch — rejected: a second store to keep in sync for a catalog this size",
                "LIKE queries — rejected: no ranking, no stemming"], weight="normal", tags="search")
    w.decision(D(18, 10, 55), P, K["c11"].agent_id, "The confirmation email is sent from the webhook, once per order",
               "The webhook is the one place that knows the order exists; `email_sent_at` guards the resend.",
               weight="minor", tags="email")
    w.decision(D(22, 10, 20), P, K["c13"].agent_id, "Prices are VAT-inclusive; Stripe Tax splits the VAT, it never adds it",
               "Customers in the EU expect the shelf price to be the price. The split per country only changes the invoice. Revisit if we sell to businesses.",
               ["Tax-exclusive prices plus VAT at checkout — rejected: the price changes at the last step",
                "Our own VAT table — rejected: rates and registrations change; Stripe keeps them current"], weight="major", tags="tax,checkout")
    w.decision(D(21, 10, 30), P, K["c12"].agent_id, "Production secrets live in a root-only env file on the host, not in the repository or the image",
               "The image is the same for staging and production; only /etc/shopfront/env differs. Rotating a key is editing one file and restarting.",
               ["Secrets baked into the image at build — rejected: every image would be a secret",
                "A hosted secrets manager — rejected: a service and an SDK for five variables"], weight="normal", tags="security,deploy")
    w.decision(D(25, 10, 8), P, K["c15"].agent_id, "Load tests use k6 against staging, not production",
               "Test cards only work in test mode, and staging is the same compose file.", weight="minor", tags="tests")
    w.decision(D(28, 9, 50), P, K["c17"].agent_id, "Product images are served as AVIF at the displayed width",
               "The CDN supports AVIF now; the hero was 3.1 MB and is 94 KB. JPEG stays as the fallback.", weight="minor", tags="perf,images")

    # ------------------------------------------------------------------ kept messages: interpretations
    c1, t1 = K["rule_money"]
    w.interpret("rule", c1, t1, D(1, 10, 25),
                "Every amount of money is an integer count of the currency's minor unit (cents for EUR): in the database (BIGINT), in the API "
                "(JSON integers), in the frontend until the moment it is shown. Only `formatMoney` divides, and only for display. "
                "A float, a Decimal serialised as a string, or a price with a decimal point in a payload is a bug.",
                note="scope: database, API, frontend", agent_id=c1.agent_id)
    c1, t1 = K["rule_secrets"]
    w.interpret("rule", c1, t1, D(1, 10, 48),
                "No secret is ever committed: keys, passwords and webhook secrets come from the environment (`settings.py`), `.env` stays untracked, "
                "and `.env.example` lists the names with empty values. A secret that appears in a chat, a log or a commit is rotated the same day.",
                agent_id=c1.agent_id)
    w.kept_update("rule", c1, t1, D(1, 11, 30), auto="yes", tags="security")
    c1, t1 = K["rule_tests"]
    w.interpret("rule", c1, t1, D(1, 16, 25),
                "Before saying a task is done, run the project's test suite and state the result as a count ('pytest -q: 41 passed'). "
                "A suite that was not run, or was skipped in part, is said out loud with the reason.", agent_id=c1.agent_id)
    w.kept_update("rule", c1, t1, D(1, 16, 40), auto="yes", tags="process")
    c1, t1 = K["rule_idem"]
    w.interpret("rule", c1, t1, D(14, 11, 12),
                "Every call to Stripe goes through `stripe_client.py` and carries an idempotency key derived from what the call is about "
                "(`cart:{id}:v{version}`, `refund:{order}`). A retry with the same key must be safe. Scripts are not an exception.",
                agent_id=c1.agent_id)
    c1, t1 = K["rule_migrations"]
    w.interpret("rule", c1, t1, D(23, 14, 36),
                "A migration only adds (tables, nullable columns, indexes) until the release that stops using the old shape has shipped. "
                "Dropping or renaming happens in a later release's migration. This keeps rollback.sh safe: old code runs on the new schema.",
                agent_id=c1.agent_id)
    c1, t1 = K["rule_webhook"]
    w.interpret("rule", c1, t1, D(24, 16, 12),
                "A webhook handler checks the stored event's `processed_at` before acting and sets it in the same transaction as its effect. "
                "Running a handler twice for one event must change nothing the second time.", agent_id=c1.agent_id)
    c1, t1 = K["rule_copy"]
    w.interpret("rule", c1, t1, D(24, 15, 16),
                "Interface text is sentence case ('Your order is on its way'), plain, and without exclamation marks. Applies to buttons, headings, "
                "empty states, errors and emails.", agent_id=c1.agent_id)
    w.kept_update("rule", c1, t1, D(24, 15, 20), tags="copy,ui")

    c1, t1 = K["rule_deps"]
    w.interpret("rule", c1, t1, D(22, 14, 32),
                "Adding a package (Python or npm) needs a decision entry naming what it is for and the alternatives considered, "
                "including writing it ourselves. Upgrades of existing packages do not.", agent_id=c1.agent_id)
    w.kept_update("rule", c1, t1, D(22, 14, 33), tags="process,deps")
    c1, t1 = K["vision_sheet"]
    w.interpret("vision", c1, t1, D(7, 14, 40),
                "The catalog's source of truth is a spreadsheet the merchant already uses. Every few minutes the store pulls it, upserts by SKU, "
                "and shows what changed (new, changed price, removed). No product admin screens are built. What exists: the seed script upserts by SKU from CSV.",
                agent_id=c1.agent_id)
    w.kept_update("vision", c1, t1, D(7, 14, 45), category="catalog", impact="high", effort="medium", tags="catalog")
    c1, t1 = K["vision_60s"]
    w.kept_update("vision", c1, t1, D(11, 11, 10), category="checkout", impact="high", effort="medium", tags="checkout,conversion")
    c1, t1 = K["vision_events"]
    w.interpret("vision", c1, t1, D(23, 10, 32),
                "Any order can be explained from its own history: the cart it came from, the intent, each webhook, each email, each refund, "
                "with the time and the cause (a Stripe event id or the admin who acted). Support answers 'what happened to my order' from the "
                "admin order page alone. First step: order_events ({tk:order-events}).", agent_id=c1.agent_id)
    w.kept_update("vision", c1, t1, D(23, 10, 34), category="operations", impact="high", effort="medium", tags="orders,support")
    c1, t1 = K["vision_returns"]
    w.interpret("vision", c1, t1, D(25, 16, 15),
                "A customer starts a return from their order page: chooses items and a reason, receives a prepaid label by email, and is refunded "
                "when the parcel is scanned. Needs partial refunds and a carrier label API.", agent_id=c1.agent_id)
    w.kept_update("vision", c1, t1, D(25, 16, 16), category="post-purchase", impact="medium", effort="large", tags="returns")
    c1, t1 = K["vision_tg"]
    w.interpret("vision", c1, t1, D(29, 9, 20),
                "Customers who opt in get order updates (paid, shipped, delivered) in Telegram, and the first one arrives before the confirmation "
                "email. Today the outbound event reaches tg-notify in under 2 s; the email takes 5–40 s.", agent_id=c1.agent_id)
    w.kept_update("vision", c1, t1, D(29, 9, 22), category="notifications", impact="medium", effort="small", tags="notifications")
    c1, t1 = K["vision_prices"]
    w.interpret("vision", c1, t1, D(29, 16, 5),
                "Supplier price changes reach the storefront within five minutes of the feed, and a price change never alters the total of a cart "
                "that already has an intent. Needs the price-etl publish interval at 5 minutes and cart price locking.", agent_id=c1.agent_id)
    w.kept_update("vision", c1, t1, D(29, 16, 6), category="catalog", impact="medium", effort="medium", tags="catalog,pricing")

    c1, t1 = K["problem_sig"]
    w.interpret("problem", c1, t1, D(16, 11, 5),
                "Every Stripe webhook on staging failed signature verification, so no order was created from a staging payment. "
                "Cause (found 11:15): our request logger parsed and re-serialised the JSON body before the handler read it. Owner: the webhook route.",
                note="cause found", agent_id=c1.agent_id)
    w.interpret("problem", c1, t1, D(17, 10, 5),
                "Every Stripe webhook on staging failed signature verification, so no order was created from a staging payment. "
                "Cause: the request logger re-serialised the JSON body. Fixed {dsh:16} (webhook-proxy-fix): the route reads the raw body first and the logger "
                "skips /webhooks/*. The 12 failed events were replayed: 3 orders, 9 no-ops.", note="fixed and replayed", agent_id=K["c10"].agent_id)
    w.kept_update("problem", c1, t1, D(17, 10, 8), status="resolved", resolved_date="{ymd:17}", severity="high", tags="stripe,webhooks")
    c1, t1 = K["problem_pool"]
    w.interpret("problem", c1, t1, D(25, 15, 5),
                "At 50 checkouts a minute the API waits for database connections after about seven minutes and 14 % of intents take over 5 s. "
                "It blocks the public beta's load criterion. Likely cause: transactions held open during Stripe calls. Owner: {tk:db-connections}.",
                agent_id=c1.agent_id)
    w.kept_update("problem", c1, t1, D(25, 15, 6), severity="high", tags="db,perf")
    c1, t1 = K["problem_lcp"]
    w.kept_update("problem", c1, t1, D(28, 9, 32), severity="medium", tags="perf")
    c1, t1 = K["problem_ratelimit"]
    w.interpret("problem", c1, t1, D(28, 13, 58),
                "The 3DS end-to-end cases fail in CI when run in parallel because Stripe's test mode allows 25 requests a second. "
                "It delays CI, not customers. Workaround: serial runs (+40 s). Owner: whoever grows the e2e suite next.",
                agent_id=c1.agent_id)
    w.kept_update("problem", c1, t1, D(28, 14, 0), severity="low", tags="ci,stripe")

    # ------------------------------------------------------------------ skills and artifacts
    skill_draft(sim, *K["skill_replay"], D(22, 14, 10), "stripe-webhook-replay",
                "Replay Stripe webhooks against local or staging and check the handler stayed idempotent. Use when a webhook failed, "
                "when a handler changed, or when the operator asks to replay events.",
                """Replaying webhooks is how we recover from a failed handler and how we prove a handler is idempotent.

1. List the failed events: Stripe dashboard → Developers → Webhooks → the endpoint → failed, or
   `stripe events list --limit 20 --type payment_intent.succeeded`.
2. Point at the right endpoint. Local: `stripe listen --forward-to localhost:8000/webhooks/stripe`.
   Staging: the dashboard's "Resend" on the staging endpoint.
3. Resend one: `stripe events resend evt_… --webhook-endpoint we_…`.
4. Check it landed once: `select id, status, processed_at from stripe_events where id = 'evt_…'`.
5. Resend it again. Nothing may change: same order count, no second email.
6. If the signature fails: the handler must read `await request.body()` before anything parses it,
   and `logging_mw.py` must skip `/webhooks/*`.

Say how many events were replayed, how many created something, and how many were no-ops.
""")
    skill_draft(sim, *K["skill_deploy"], D(30, 10, 16), "deploy-and-rollback",
                "Deploy shopfront to staging or production and roll back when the health check fails. Use for any deploy or when a deploy went wrong.",
                """1. On main, CI green. Migrations in this release only add (rule: migrations are additive).
2. `ssh shop@<host> 'cd shopfront && infra/deploy.sh'` — it tags the running images as `previous`,
   pulls, builds, runs `alembic upgrade head`, restarts, and curls `/api/health`.
3. Watch for 5 minutes: `docker compose logs -f api worker` and the uptime checks.
4. Health fails or errors climb: `infra/rollback.sh`. It restarts the `previous` images and runs
   no migration down — additive migrations keep old code working.
5. Write in the chat what was deployed (commit), how long it took, and whether rollback was needed.
""")
    artifact(sim, *K["artifact_funnel"], D(29, 14, 30), "checkout-funnel-report", "dataset",
             "Checkout funnel for the first week on production: sessions reaching cart, checkout, payment and confirmation per day, with a one-page summary.",
             {"funnel.csv": "date,sessions,cart,checkout,payment,confirmed\n{iso:22},412,96,41,24,23\n{iso:23},388,88,39,22,21\n"
                            "{iso:24},455,104,47,27,27\n{iso:25},501,117,52,31,30\n{iso:26},610,139,63,37,36\n"
                            "{iso:27},574,131,58,34,33\n{iso:28},523,120,55,33,33\n",
              "SUMMARY.md": "# Checkout funnel, {dm:22} to {dm:28}\n\n- 3,463 sessions, 795 reached the cart (23 %), 355 the checkout (45 % of carts), "
                            "208 paid (59 % of checkouts), 203 confirmed.\n- The largest drop is checkout → payment: 41 %, two thirds of it on phones.\n"
                            "- Five payments did not reach confirmation: the customer closed the tab; all five orders exist (the webhook created them).\n"},
             )
    # The launch checklist is registered on the Artifacts page by the operator.
    launch_checklist(sim, D(30, 9, 8))

    # ------------------------------------------------------------------ time
    tm = [
        (D(1, 9, 5), 150, "repo-setup", "s1", "Skeleton review and alembic"),
        (D(2, 9, 20), 110, "products-api", "s1", "Products API with the agent"),
        (D(3, 10, 0), 95, "seed-catalog", "s1", "Catalog CSV clean-up"),
        (D(7, 9, 10), 120, "search-api", "s1", "Search"),
        (D(8, 10, 0), 170, "cart-api", "s1", "Cart API and the cookie"),
        (D(9, 9, 30), 140, "cart-drawer", "s1", "Cart drawer"),
        (D(10, 10, 30), 125, "staging-deploy", "s1", "Staging VM"),
        (D(11, 9, 20), 75, "checkout-choice", "s2", "Hosted vs embedded checkout"),
        (D(14, 9, 10), 205, "checkout-page", "s2", "Checkout page"),
        (D(15, 10, 10), 160, "webhooks", "s2", "Webhooks and orders"),
        (D(16, 10, 40), 85, "webhook-proxy-fix", "s2", "Signature incident"),
        (D(18, 9, 30), 90, "confirm-email", "s2", "Confirmation email"),
        (D(21, 10, 0), 140, "prod-deploy", "s2", "Production"),
        (D(22, 9, 0), 60, "first-payment", "s2", "First real payment"),
        (D(23, 10, 0), 180, "refunds", "s3", "Refunds and events"),
        (D(24, 10, 10), 130, "webhook-retries", "s3", "Webhook queue"),
        (D(25, 10, 0), 70, "load-test", "s3", "Load test"),
        (D(28, 9, 5), 105, "lcp-images", "", "Lighthouse and images"),
        (D(28, 14, 20), 80, "order-webhook-out", "s4", "Outbound order events"),
        (D(29, 10, 5), 95, "admin-orders", "s3", "Admin order list"),
        (D(30, 9, 10), 55, "refunds", "s3", "Partial refunds"),
    ]
    for start, mins, task, sprint, note in tm:
        w.timer(start - timedelta(minutes=2), mins, P, task=task, sprint=sprint, note=note)
    for start, mins, task, note in [
        (D(4, 14, 0), 45, "product-page", "auto: product page review"),
        (D(17, 14, 30), 40, "order-confirm-page", "auto: confirmation page review"),
        (D(24, 14, 30), 35, "legal-pages", "auto: legal pages"),
        (D(29, 11, 30), 50, "admin-orders", "auto: admin list review"),
        (D(25, 11, 0), 30, "uptime", "auto: monitoring setup"),
    ]:
        w.auto_time(start, mins, P, task=task, note=note)


def scan_turn(sim, w, chat: Chat, when, user: str, agent: str) -> None:
    chat.turn(when, user, agent, minutes=14, skills=["make-a-scan"])


def skill_draft(sim, chat: Chat, turn: int, when, name: str, description: str, body: str) -> None:
    def run() -> None:
        kid = sim.capture.keep_id("skill", chat.project, chat.agent_id, turn)
        sim.adopt()
        md = f'---\nname: {name}\ndescription: "{description}"\n---\n\n{body}'
        sim.post(f"/api/skills/{kid}/draft", {"skill_md": md, "note": "drafted from the chat", "agent_id": chat.agent_id}, agent=True)
    sim.at(when, run)


def artifact(sim, chat: Chat, turn: int, when, name: str, kind: str, description: str, files: dict[str, str]) -> None:
    def run() -> None:
        kid = sim.capture.keep_id("artifact", chat.project, chat.agent_id, turn)
        sim.adopt()
        dest = sim.root / "projects" / chat.project / "artifacts" / name
        dest.mkdir(parents=True, exist_ok=True)
        for rel, text in files.items():
            (dest / rel).write_text(dated(text), encoding="utf-8")
        sim.post(f"/api/artifacts/{kid}/write", {"agent_id": chat.agent_id, "name": name, "kind": kind,
                                                "description": description}, agent=True)
    sim.at(when, run)


def launch_checklist(sim, when) -> None:
    """The operator registers a document on the Artifacts page by hand."""
    def run() -> None:
        dest = sim.root / "projects" / P / "artifacts" / "beta-launch-checklist"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "CHECKLIST.md").write_text(
            "# Public beta checklist\n\n"
            "- [x] Legal pages live (terms, privacy, imprint)\n- [x] First real payment and refund seen\n"
            "- [x] Uptime checks and paging\n- [ ] Partial refund email\n- [ ] Database pool holds 50 checkouts/min\n"
            "- [ ] Admin behind SSO\n- [ ] Backups restored once\n- [ ] Best-seller copy rewritten\n", encoding="utf-8")
        sim.post("/api/artifacts/new", {"project": P, "name": "beta-launch-checklist", "kind": "document",
                                        "description": "What must be true before the waitlist is let in on {dm:45}, checked off as it happens.",
                                        "actor": "operator", "tags": "launch"})
    sim.at(when, run)
