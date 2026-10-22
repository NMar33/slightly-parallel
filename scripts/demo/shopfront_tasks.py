"""The shopfront board: ~75 tasks and the path each one took.

Each row: key, created (day, hour, minute), title, lane (the assignee lane
is the task's type: ui · checkout · api · infra · content), priority,
impact, effort, tags, due date, sprint key, description, and the moves it
made after it was created — (day, hour, minute, status). A move that a
chat makes (a #done, an agent's report) lives with that chat instead.
"""

from __future__ import annotations

from engine import D

P = "shopfront"

# key, created, title, lane, prio, impact, effort, tags, due, sprint, first status, desc, moves, extra
TASKS = [
    # ---------------- Sprint 1: catalog foundations (1–10 Sep) ----------------
    ("repo-setup", (1, 8, 40), "Monorepo skeleton: Next.js app, FastAPI service, compose file", "infra",
     "high", "4", "2", "setup", "", "s1", "todo",
     "One repository, two apps. `make up` starts Postgres, the API and the web app; `make test` runs both suites.",
     [(1, 9, 5, "doing")], {}),
    ("products-schema", (1, 8, 45), "Postgres schema for products, variants and prices", "api",
     "high", "5", "3", "catalog,db", "", "s1", "todo",
     "Products have variants (size, colour); each variant has its own price in minor units and its own stock.",
     [(1, 13, 10, "doing"), (2, 10, 30, "done")], {}),
    ("money-minor", (1, 8, 50), "Money as integer minor units end to end", "api",
     "high", "5", "2", "catalog,money", "", "s1", "todo",
     "No floats anywhere: the database, the API and the frontend pass cents. One formatter in the frontend.",
     [(1, 14, 0, "doing"), (2, 11, 15, "review"), (2, 16, 40, "done")], {}),
    ("ci-pipeline", (1, 8, 55), "CI: lint, type-check and tests on every push", "infra",
     "med", "3", "2", "ci", "", "s1", "todo",
     "GitHub Actions: ruff and pytest for the API, tsc and next lint for the web app. Fail the push, not the deploy.",
     [(2, 9, 20, "doing"), (2, 15, 5, "done")], {}),
    ("products-api", (1, 9, 0), "Products API: list, detail, filter by category", "api",
     "high", "5", "3", "catalog,api", "", "s1", "todo",
     "GET /api/products with ?category= and cursor pagination; GET /api/products/{slug} with variants.",
     [(2, 9, 30, "doing")], {"auto": True}),
    ("seed-catalog", (1, 9, 5), "Seed script: 48 demo products from a CSV", "content",
     "med", "3", "1", "catalog,content", "", "s1", "todo",
     "scripts/seed_catalog.py reads content/catalog.csv. Idempotent: running it twice changes nothing.",
     [(3, 10, 0, "doing"), (3, 15, 30, "done")], {}),
    ("product-grid", (1, 9, 10), "Product grid on the home page", "ui",
     "high", "4", "2", "catalog,ui", "", "s1", "todo",
     "Responsive grid, 2 columns on phones, 4 on desktop. Price formatted from minor units.",
     [(3, 11, 0, "doing"), (4, 12, 10, "review"), (4, 17, 30, "done")], {}),
    ("product-page", (1, 9, 15), "Product detail page with variant picker", "ui",
     "high", "5", "3", "catalog,ui", "", "s1", "todo",
     "Size and colour pickers; the price and the add-to-cart button follow the chosen variant.",
     [(3, 14, 0, "doing"), (4, 16, 0, "review"), (7, 10, 20, "done")], {}),
    ("image-cdn", (2, 11, 0), "Serve product images through the image optimizer", "infra",
     "med", "4", "2", "perf,images", "", "s1", "backlog",
     "next/image with a remote pattern for img.shopfront.dev; widths 320/640/1024.",
     [(3, 9, 0, "todo"), (7, 14, 0, "doing"), (7, 18, 0, "done")], {}),
    ("category-nav", (2, 11, 5), "Category navigation and breadcrumbs", "ui",
     "low", "2", "1", "catalog,ui", "", "s1", "backlog",
     "Top navigation from the category list; breadcrumbs on the product page.",
     [(7, 11, 0, "todo"), (8, 9, 30, "doing"), (8, 15, 0, "done"), (21, 9, 0, "done-archived")], {}),
    ("search-api", (3, 16, 0), "Postgres full-text search over title and description", "api",
     "med", "4", "3", "search,api", "", "s1", "backlog",
     "tsvector column with a GIN index; weights title A, description B. /api/search?q=",
     [(7, 9, 10, "todo"), (7, 9, 40, "doing"), (8, 12, 0, "done")], {}),
    ("search-box", (3, 16, 5), "Search box with instant results", "ui",
     "med", "4", "2", "search,ui", "", "s1", "backlog",
     "Debounced 200 ms; the first five results under the box, Enter opens the full results page.",
     [(7, 9, 12, "todo"), (8, 13, 0, "doing"), (9, 11, 40, "review"), (9, 16, 0, "done")], {}),
    ("cart-api", (4, 10, 0), "Server-side cart keyed by a signed cookie", "checkout",
     "high", "5", "3", "cart,api", "", "s1", "todo",
     "Carts live in Postgres; the browser holds a signed cart id. Totals are computed on the server only.",
     [(8, 10, 0, "doing"), (8, 17, 20, "done")], {}),
    ("cart-drawer", (4, 10, 5), "Cart drawer with quantity steppers", "ui",
     "high", "5", "2", "cart,ui", "", "s1", "todo",
     "Opens from the header and after add-to-cart. Steppers call the cart API; the total comes from the server.",
     [(9, 9, 30, "doing")], {"evidence": True}),
    ("add-to-cart", (4, 10, 10), "Add-to-cart button with optimistic update", "ui",
     "med", "3", "1", "cart,ui", "", "s1", "todo",
     "The badge moves immediately; a failed call rolls it back and says why.",
     [(9, 10, 0, "doing"), (9, 15, 0, "done"), (21, 9, 0, "done-archived")], {}),
    ("empty-states", (7, 15, 0), "Empty states for cart and search", "ui",
     "low", "2", "1", "ui", "", "s1", "backlog",
     "An empty cart links to the best sellers; a search with no results suggests categories.",
     [(9, 9, 0, "todo"), (10, 10, 0, "doing"), (10, 12, 0, "done"), (21, 9, 1, "done-archived")], {}),
    ("staging-deploy", (7, 15, 5), "Staging on one VM with docker compose", "infra",
     "high", "4", "3", "deploy,infra", "", "s1", "todo",
     "staging.shopfront.dev on a single VM: compose, Caddy for TLS, a deploy script that pulls and restarts.",
     [(10, 10, 30, "doing"), (10, 17, 0, "done")], {}),

    # ---------------- Sprint 2: checkout v1 (11–22 Sep) ----------------
    ("checkout-choice", (9, 17, 0), "Choose Stripe Checkout or the Payment Element", "checkout",
     "high", "5", "1", "checkout,stripe", "", "s2", "todo",
     "Hosted Checkout is faster to ship; the Payment Element keeps the customer on our page. Decide before building.",
     [(11, 9, 20, "doing")], {}),
    ("payment-intent", (10, 16, 0), "Create the PaymentIntent from the server-side cart", "checkout",
     "high", "5", "3", "checkout,stripe", "", "s2", "todo",
     "POST /api/checkout/intent reads the cart, computes the amount on the server and returns a client secret.",
     [(14, 9, 10, "doing"), (14, 17, 0, "done")], {}),
    ("idempotency", (10, 16, 5), "Idempotency keys on every Stripe call", "api",
     "high", "5", "2", "stripe,reliability", "", "s2", "todo",
     "Derived from the cart id and its version, so a retried request cannot create a second intent.",
     [(14, 11, 0, "doing"), (14, 16, 30, "done")], {}),
    ("checkout-page", (10, 16, 10), "Checkout page with the Payment Element", "checkout",
     "high", "5", "3", "checkout,ui,stripe", "{ymd:16}", "s2", "todo",
     "Address, shipping method and the Payment Element on one page. The pay button shows the total the server computed.",
     [(14, 14, 0, "doing"), (15, 10, 5, "review"), (16, 9, 0, "done")], {"evidence": True, "remember": True}),
    ("orders-table", (10, 16, 15), "Orders table and human order numbers", "api",
     "high", "4", "2", "orders,db", "", "s2", "todo",
     "Orders keep a copy of the lines and prices at purchase time. Numbers look like SF-10421.",
     [(15, 10, 0, "doing"), (15, 17, 30, "done")], {}),
    ("webhooks", (10, 16, 20), "Stripe webhook: payment_intent.succeeded creates the order", "checkout",
     "high", "5", "3", "checkout,stripe,webhooks", "{ymd:17}", "s2", "todo",
     "Verify the signature, look up the event id, create the order once. Everything else is logged and ignored.",
     [(15, 11, 0, "doing")], {"evidence": True}),
    ("guest-checkout", (11, 10, 50), "Guest checkout without an account", "checkout",
     "high", "5", "2", "checkout", "", "s2", "todo",
     "Email is the only required identity. An account can be created from the confirmation page.",
     [(16, 9, 40, "doing")], {}),
    ("shipping-rates", (11, 10, 52), "Shipping rates: flat EU rate, free over €60", "checkout",
     "med", "3", "1", "checkout,shipping", "", "s2", "todo",
     "€4.90 inside the EU, free from €60. Rates are server-side and part of the intent amount.",
     [(16, 14, 0, "doing"), (17, 11, 20, "done")], {}),
    ("order-confirm-page", (11, 10, 54), "Order confirmation page", "ui",
     "med", "4", "1", "checkout,ui", "", "s2", "todo",
     "Shows the order number, the lines and what happens next. Reloading it never charges twice.",
     [(16, 15, 0, "doing"), (17, 12, 0, "review"), (17, 16, 30, "done")], {}),
    ("confirm-email", (11, 10, 56), "Order confirmation email", "content",
     "med", "4", "2", "email,content", "{ymd:19}", "s2", "todo",
     "Sent from the webhook handler after the order exists. Plain layout, the order lines, the shipping address.",
     [(18, 9, 30, "doing")], {"evidence": True}),
    ("stripe-tax", (14, 9, 0), "Stripe Tax for EU VAT", "checkout",
     "high", "4", "3", "checkout,tax,stripe", "{ymd:25}", "s2", "backlog",
     "Prices are VAT-inclusive; Stripe Tax computes the split per country for the invoice.",
     [(18, 10, 0, "todo"), (22, 10, 0, "doing")], {"auto": True, "evidence": True}),
    ("address-autocomplete", (14, 9, 5), "Address autocomplete on checkout", "ui",
     "low", "2", "2", "checkout,ui", "", "", "backlog",
     "Nice to have. The Payment Element's address field may be enough.",
     [(18, 12, 0, "parked")], {"resurface_on": "{iso:36}", "resurface_to": "next"}),
    ("webhook-proxy-fix", (16, 11, 30), "Webhook signature fails behind the proxy", "api",
     "high", "5", "1", "stripe,webhooks,bug", "", "s2", "doing",
     "Caddy re-encodes the body; the signature is computed over the raw bytes. Read the raw body before any parsing.",
     [(17, 10, 0, "done")], {}),
    ("prod-deploy", (17, 17, 0), "Production deploy behind Caddy with TLS", "infra",
     "high", "5", "3", "deploy,infra", "{ymd:21}", "s2", "todo",
     "shopfront.dev: the same compose file as staging, secrets from the host, a rollback script that is tested.",
     [(21, 10, 0, "doing"), (21, 17, 40, "done")], {}),
    ("first-payment", (17, 17, 5), "First real payment on production", "infra",
     "high", "5", "1", "launch,stripe", "{ymd:22}", "s2", "todo",
     "A real card, a real order, the webhook, the email, and a refund of it. Done means all five seen.",
     [(22, 9, 0, "doing")], {"remember": True}),

    # ---------------- Sprint 3: payments hardening (23 Sep – 6 Oct) ----------------
    ("refunds", (21, 17, 0), "Refunds from the admin order page", "checkout",
     "high", "5", "3", "checkout,admin,stripe", "{ymd:32}", "s3", "todo",
     "Full refund first. The order keeps the refund id and the reason; the customer gets an email.",
     [(23, 10, 0, "doing")], {"today": True}),
    ("webhook-retries", (21, 17, 5), "Webhook events processed through a retry queue", "api",
     "high", "5", "3", "webhooks,reliability", "{ymd:31}", "s3", "todo",
     "Store every event first, answer 200, then process from the table with backoff. A failed handler retries, never drops.",
     [(24, 10, 0, "doing"), (24, 17, 0, "review"), (25, 12, 0, "done")], {}),
    ("dispute-alerts", (21, 17, 10), "Alert on disputes within five minutes", "api",
     "med", "4", "1", "stripe,alerts", "{ymd:33}", "s3", "todo", "charge.dispute.created posts to the ops channel with the order and the amount.",
     [], {}),
    ("3ds-tests", (21, 17, 15), "3-D Secure test matrix in CI", "checkout",
     "high", "4", "2", "checkout,tests,stripe", "{ymd:30}", "s3", "todo",
     "The Stripe test cards for 3DS required, 3DS failed, and insufficient funds after 3DS, run against staging.",
     [(28, 10, 0, "doing")], {"auto": True, "evidence": True}),
    ("payment-failed-ux", (22, 18, 0), "A clear message when a card is declined", "ui",
     "med", "3", "1", "checkout,ui,copy", "", "s3", "todo",
     "Map Stripe decline codes to three plain messages. Never show the raw code.",
     [(24, 15, 0, "doing"), (25, 12, 0, "review"), (25, 17, 0, "review-later")], {}),
    ("reconcile", (22, 18, 5), "Nightly reconciliation: Stripe balance against orders", "api",
     "med", "4", "3", "stripe,ops", "{ymd:35}", "s3", "backlog",
     "A job that lists yesterday's balance transactions and flags any without an order, or an order without one.",
     [(25, 9, 0, "next")], {"stack": "ops-stack", "position": 10}),
    ("order-events", (22, 18, 10), "Order event log: every state change with its cause", "api",
     "high", "5", "3", "orders,audit", "{ymd:32}", "s3", "todo",
     "order_events table: created, paid, refunded, shipped — each row with the webhook event or the admin who caused it.",
     [(24, 11, 0, "doing"), (29, 11, 0, "review"), (29, 17, 0, "done")], {}),
    ("db-connections", (25, 15, 0), "Connection pool exhausted under the load test", "infra",
     "high", "4", "2", "db,perf", "{ymd:31}", "s3", "todo",
     "At 50 checkouts a minute the API waits on the pool. Size the pool per worker and add pgbouncer if needed.",
     [], {"today": True}),
    ("load-test", (22, 18, 15), "Load test: 50 checkouts a minute on staging", "infra",
     "high", "4", "2", "perf,tests", "", "s3", "todo",
     "k6 script: browse, add to cart, pay with a test card. Report p95 per step.",
     [(25, 10, 0, "doing")], {"auto": True, "evidence": True}),
    ("stripe-sdk-upgrade", (22, 18, 20), "Upgrade stripe-python to v11", "api",
     "low", "2", "1", "deps,stripe", "", "", "backlog", "v11 changes the error classes. Read the changelog before bumping.",
     [], {}),

    # ---------------- Order notifications (with tg-notify) ----------------
    ("order-webhook-out", (24, 10, 0), "Send order.paid to tg-notify", "api",
     "high", "4", "2", "notifications,integration", "{ymd:31}", "s4", "todo",
     "Signed POST to tg-notify after an order is paid. At-least-once; tg-notify dedupes on the order id.",
     [(28, 14, 0, "doing"), (29, 12, 0, "review"), (29, 17, 30, "done")], {"projects": "shopfront,tg-notify"}),
    ("notify-optin", (24, 10, 5), "Telegram opt-in on the order confirmation page", "ui",
     "med", "4", "2", "notifications,ui", "{ymd:36}", "s4", "backlog",
     "A 'Get updates in Telegram' button that deep-links to the bot with a one-time token for the order.",
     [(25, 9, 30, "next")], {"projects": "shopfront,tg-notify"}),

    # ---------------- Storefront polish and launch content ----------------
    ("lcp-images", (25, 16, 0), "LCP is 4.8 s on product pages: resize hero images", "ui",
     "high", "5", "2", "perf,images", "{ymd:31}", "", "todo",
     "Hero images are 3 MB originals. Serve AVIF at the displayed width and preload the first one.",
     [(28, 9, 20, "doing")], {"today": True, "remember": True}),
    ("seo-meta", (21, 10, 0), "SEO metadata and Open Graph images", "content",
     "med", "4", "2", "seo,content", "{ymd:35}", "", "backlog",
     "Title, description and an OG image per product; generated OG images for categories.",
     [(25, 9, 40, "todo")], {"stack": "launch-copy", "position": 20}),
    ("sitemap", (21, 10, 5), "sitemap.xml and robots.txt", "content",
     "med", "3", "1", "seo", "", "", "backlog", "Generated from the catalog at build time; excludes cart and checkout.",
     [(28, 9, 0, "todo"), (28, 11, 0, "doing")], {}),
    ("product-copy", (21, 10, 10), "Rewrite the copy for the 12 best sellers", "content",
     "high", "4", "3", "content,copy", "{ymd:32}", "", "backlog",
     "Plain, concrete, what it is made of and how it fits. No superlatives.",
     [(25, 9, 35, "todo")], {"stack": "launch-copy", "position": 10, "today": True}),
    ("size-guide", (21, 10, 15), "Size guide modal for apparel", "ui",
     "low", "3", "1", "ui,apparel", "", "", "backlog", "One table per garment type, opened from the size picker.",
     [], {"stack": "pdp-extras", "position": 10}),
    ("reviews", (21, 10, 20), "Product reviews (read-only import)", "ui",
     "low", "3", "3", "ui", "", "", "backlog", "Import from the old shop's CSV; show the average and the newest five.",
     [], {"stack": "pdp-extras", "position": 20}),
    ("wishlist", (21, 10, 25), "Wishlist for signed-in customers", "ui",
     "low", "2", "3", "ui,accounts", "", "", "backlog", "", [], {"stack": "pdp-extras", "position": 30}),
    ("i18n", (21, 10, 30), "German translation of the storefront", "content",
     "med", "4", "5", "i18n,content", "", "", "backlog", "Germany is a third of the waitlist. Start with checkout and emails.", [], {}),
    ("analytics", (21, 10, 35), "Privacy-friendly analytics (Plausible)", "infra",
     "med", "3", "1", "analytics", "", "", "backlog", "No cookies, so no banner. Track the checkout funnel steps as events.",
     [(25, 9, 45, "next")], {"stack": "ops-stack", "position": 20}),
    ("backup", (21, 10, 40), "Nightly Postgres backups to object storage", "infra",
     "high", "5", "2", "db,ops", "{ymd:30}", "s3", "backlog",
     "pg_dump at 03:00, 14 daily and 8 weekly kept, and a restore tested once a week.",
     [(23, 12, 0, "todo")], {"today": True}),
    ("uptime", (21, 10, 45), "Uptime checks for / and /api/health", "infra",
     "med", "3", "1", "ops", "", "s3", "todo", "One-minute checks from two regions; alert after two failures.",
     [(25, 10, 0, "doing"), (25, 11, 30, "done")], {}),
    ("admin-orders", (21, 17, 20), "Admin: order list with filters", "ui",
     "high", "4", "3", "admin,ui", "{ymd:32}", "s3", "todo",
     "Filter by status and date; search by order number or email. Opens the order page with the refund button.",
     [(29, 10, 0, "doing")], {}),
    ("admin-auth", (21, 17, 25), "Admin behind SSO", "infra",
     "high", "5", "2", "admin,security", "", "", "backlog", "Put /admin behind the identity provider; no passwords of our own.",
     [(25, 9, 50, "next")], {}),
    ("returns", (22, 18, 30), "Returns started from the order page", "checkout",
     "med", "4", "5", "returns,checkout", "", "", "backlog",
     "The customer picks the items and a reason; we email a label. Depends on refunds.", [], {}),
    ("gift-cards", (15, 12, 0), "Gift cards", "checkout",
     "low", "3", "5", "checkout", "", "", "backlog", "Stripe has no gift cards; this is our own ledger. Not before launch.",
     [(18, 12, 5, "parked")], {"resurface_on": "{iso:63}", "resurface_to": "backlog"}),
    ("discount-codes", (22, 18, 35), "Discount codes at checkout", "checkout",
     "med", "4", "3", "checkout,promo", "{ymd:37}", "", "backlog", "Percentage and fixed codes, one per order, applied before tax.",
     [(28, 17, 0, "todo")], {}),
    ("inventory", (15, 12, 5), "Stock levels and 'only 3 left'", "api",
     "med", "3", "3", "catalog,stock", "", "", "backlog", "Reserve stock when the intent is created, release it after 30 minutes.", [], {}),
    ("price-feed", (24, 11, 0), "Prices from the price-etl feed", "api",
     "med", "4", "2", "catalog,integration", "{ymd:36}", "", "backlog",
     "Read the published price file from price-etl every 15 minutes; a price change never touches an open cart.",
     [(28, 17, 5, "next")], {"projects": "shopfront,price-etl"}),
    ("accessibility", (22, 18, 40), "Accessibility pass: keyboard and contrast", "ui",
     "med", "4", "2", "a11y,ui", "{ymd:35}", "", "backlog", "Checkout must be usable with the keyboard alone.",
     [(28, 17, 10, "todo")], {"stack": "launch-copy", "position": 30}),
    ("cookie-banner", (21, 10, 50), "Cookie banner, only if analytics sets cookies", "content",
     "low", "1", "1", "legal", "", "", "backlog", "Plausible sets none; park until something does.",
     [(25, 10, 5, "parked")], {}),
    ("faq-page", (22, 18, 45), "FAQ page: shipping, returns, payment", "content",
     "med", "3", "1", "content", "", "", "todo", "Twelve questions, answered in two sentences each.",
     [(25, 14, 0, "doing")], {"auto": True}),
    ("legal-pages", (21, 10, 55), "Terms, privacy and imprint pages", "content",
     "high", "4", "1", "legal,content", "{ymd:25}", "", "todo", "From the lawyer's text; rendered from Markdown.",
     [(24, 14, 0, "doing"), (25, 11, 0, "review"), (25, 16, 0, "done")], {}),
    ("perf-budget", (25, 16, 10), "Performance budget in CI (Lighthouse)", "infra",
     "low", "3", "2", "perf,ci", "", "", "backlog", "Fail the build when LCP on the product page goes over 2.5 s.", [], {}),
    ("dark-mode", (28, 18, 0), "Dark mode", "ui", "", "", "", "", "", "", "unclassified", "", [], {}),
    ("apple-pay", (28, 18, 2), "Apple Pay domain verification", "checkout", "", "", "", "", "", "", "unclassified",
     "The Payment Element shows Apple Pay once the domain file is served.", [], {}),
    ("email-templates", (29, 19, 0), "Email templates in MJML", "content", "", "", "", "", "", "", "unclassified", "", [], {}),
    ("order-tracking", (29, 19, 5), "Tracking link in the shipped email", "content", "", "", "", "", "", "", "unclassified",
     "The carrier API returns a URL; put it in the email and on the order page.", [], {}),
]

# Tasks agents wrote themselves (#task): status `agent`, one of the ag_ tags.
AGENT_TASKS = [
    ("two-formatters", (18, 15, 20), "Two places format money: lib/money.ts and emails.py", "content", "ag_debt",
     "The email renders prices with its own helper. They agree today; a currency with three decimals would split them."),
    ("webhook-unknown", (24, 16, 10), "Webhook handler swallows unknown event types silently", "api", "ag_bug",
     "An event type we do not handle is answered 200 and dropped without a log line. Log it at info with the type."),
    ("slug-collide", (29, 15, 30), "Product slugs collide when titles repeat", "api", "ag_bug,ag_followup",
     "Two products named 'Linen shirt' get the same slug; the second import fails. Append the variant SKU."),
]


def setup(sim, w) -> None:
    for key, (d, h, m), title, lane, prio, impact, effort, tags, due, sprint, first, desc, moves, extra in TASKS:
        extra = dict(extra)
        today = extra.pop("today", False)
        stack = extra.pop("stack", None)
        pos = extra.pop("position", None)
        res_on = extra.pop("resurface_on", None)
        res_to = extra.pop("resurface_to", None)
        w.task(key, D(d, h, m), P, title, status=first, lane=lane, priority=prio, impact=impact,
               effort=effort, tags=tags, due=due, desc=desc, sprint=sprint,
               evidence=extra.pop("evidence", False), auto=extra.pop("auto", False),
               remember=extra.pop("remember", False), projects=extra.pop("projects", ""),
               position=pos)
        for md, mh, mm, st in moves:
            w.move(key, D(md, mh, mm), st)
        if res_on:
            w.update(key, D(18, 12, 10) if d < 18 else D(d, h, m + 2), resurface_on=res_on, resurface_to=res_to)
        if today:
            w.update(key, D(30, 8, 50), today_on="{iso:30}")
        if stack:
            _stacks.setdefault(stack, []).append((pos or 0, key))
    # Stacks: the first step's id names the stack; the rest queue behind it.
    for name, members in _stacks.items():
        members.sort()
        head = members[0][1]
        for _, key in members:
            w_stack(sim, key, head, D(28, 17, 30))
    for key, (d, h, m), title, lane, tags, desc in AGENT_TASKS:
        who = {"two-formatters": "oc-4e6c1b9f", "webhook-unknown": "codex-e3b9107f",
               "slug-collide": "cc-e0d7a4b6"}[key]
        w.task(key, D(d, h, m), P, title, status="agent", lane=lane, tags=tags, desc=desc, agent=who)


_stacks: dict[str, list] = {}


def w_stack(sim, key: str, head: str, when) -> None:
    def run() -> None:
        sim.post(f"/api/tasks/{sim.tasks[key]}/update", {"stack_id": sim.tasks[head], "actor": "operator"})
    sim.at(when, run)
