"""The shopfront architecture page (three versions) and program map (two)."""

PAGE_V1 = """## 1. What it is

shopfront is a small online store for everyday goods shipped inside the EU: a Next.js storefront and a FastAPI service over Postgres. It serves customers browsing and buying, and the operator who runs the shop.
**Kind:** service. **Standing:** active — 38 commits since {dm:1}, the newest today. The last real work was the staging deploy.
**Made how:** by the operator with coding agents (Claude Code, Codex), one chat per piece of work.

## 2. The live work

- **The cart** — carts moved server-side mid-sprint; the drawer, steppers and stock clamp are done (`backend/app/routers/cart.py`). Done means the total cannot be changed from the browser: tested.
- **Staging** — one VM with compose and Caddy (`infra/deploy.sh`). Done: deployed, health check answers.
- **Next: checkout** — the sprint "Checkout v1" starts tomorrow; the choice between hosted and embedded checkout is still open.

## 3. What it does or has produced

- Browse the catalog — 48 products on a grid · where: `frontend/components/ProductGrid.tsx` · seen: opened on staging · made by: agent run · checked by: person
- Product page with variants — size and colour in the URL · where: `frontend/app/products/[slug]/page.tsx` · seen: opened, variant links shared · made by: agent run · checked by: person
- Search — full-text with prefix and accents · where: `backend/app/routers/search.py` · seen: ran tests, 19 passed · made by: agent run · checked by: automated tests
- Cart — server-side, signed cookie, totals in cents · where: `backend/app/routers/cart.py` · seen: ran tests, 29 passed · made by: agent run · checked by: automated tests

## 4. How the main thing works

1. The browser holds only a signed cart id (`sf_cart`).
2. Adding an item posts the SKU and quantity; the API reads the current variant price from Postgres.
3. The API clamps the quantity to stock and recomputes the total in cents.
4. The drawer shows the server's total; it never computes one.

## 5. Ways in and out

- Storefront pages — `/`, `/products/[slug]`, `/search` · where: `frontend/app/page.tsx` · seen: opened on staging · made by: agent run · checked by: person
- JSON API — products, search, cart · where: `backend/app/main.py` · seen: read the router list · made by: agent run · checked by: automated tests
- Seed script — loads the catalog CSV · where: `scripts/seed_catalog.py` · seen: ran twice, second run changed nothing · made by: agent run · checked by: automated tests

## 6. What it is made of

- Postgres schema — products, variants, carts · where: `backend/app/models.py` · seen: read the models and migrations · made by: agent run · checked by: automated tests
- Money formatter — the only place cents become euros · where: `frontend/lib/money.ts` · seen: opened · made by: agent run · checked by: nobody

**Built and run:** Git repository, no remote recorded. Next.js 14, FastAPI, SQLAlchemy 2, Postgres 16. Built by `make up`; tested by `make test` and CI (`.github/workflows/ci.yml`). Runs on staging.shopfront.dev only; not released. Real data: none yet — the catalog is seeded from `content/catalog.csv`.
**Old material:** none; the repository is ten days old.

## 7. Rules the project keeps

- Money is integer minor units everywhere · where: `AGENTS.md` · seen: opened · made by: person · checked by: agent
- Secrets never committed; `.env.example` lists names only · where: `backend/.env.example` · seen: opened · made by: person · checked by: agent

## 8. People

None found — looked in README.md and docs/.

## 9. What is owed

1. Checkout approach not chosen — stated in the board task "Choose Stripe Checkout or the Payment Element"; still true on {iso:10}: checked the board.
2. No rollback for deploys — seen in `infra/deploy.sh`; costs a manual fix-forward if a deploy fails.

## 10. Words, and what was not read

- **Words:** SKU — stock keeping unit, one per variant (`content/catalog.csv`). Minor units — cents (`AGENTS.md`).
- **Not read:** `frontend/app/globals.css`, `infra/Dockerfile.web`.
- **Searched and not found:** a remote URL (searched `.git/config`).
"""

PAGE_V2 = """## 1. What it is

shopfront is a small online store for everyday goods shipped inside the EU: a Next.js storefront, a FastAPI service over Postgres, and Stripe for payments. It serves customers buying and the operator who runs the shop.
**Kind:** service. **Standing:** active — the newest commit is today; production at shopfront.dev took its first real payment this morning.
**Made how:** by the operator with coding agents (Claude Code, Codex, OpenCode), one chat per piece of work.

## 2. The live work

- **Checkout v1** — the Payment Element on our own page, guest checkout, flat EU shipping (`backend/app/routers/checkout.py`). Done: a live payment became order SF-10001.
- **Orders from webhooks** — the order is created only by `payment_intent.succeeded`, deduplicated on the event id (`backend/app/routers/webhooks.py`). Done: replay tested.
- **Production** — shopfront.dev on one VM with a tested rollback (`infra/rollback.sh`).
- **VAT** — Stripe Tax on VAT-inclusive prices; in review.

## 3. What it does or has produced

- Checkout — address, shipping, Payment Element on one page · where: `frontend/app/checkout/page.tsx` · seen: paid with a real card on {dsh:22} · made by: agent run · checked by: person
- Orders — created once per payment · where: `backend/app/routers/webhooks.py` · seen: 12 events replayed, 3 orders, 9 no-ops · made by: agent run · checked by: automated tests
- Confirmation page — waits for the webhook · where: `frontend/app/checkout/success/page.tsx` · seen: SF-10001 shown on first load · made by: agent run · checked by: person
- Confirmation email — once per order · where: `backend/app/emails.py` · seen: replayed three times, one email · made by: agent run · checked by: automated tests
- Catalog, search, cart — as in version 1 · where: `backend/app/routers/products.py` · seen: unchanged since {dsh:10} · made by: agent run · checked by: automated tests

## 4. How the main thing works

1. `POST /api/checkout/intent` loads the cart, recomputes the lines and shipping, and creates one PaymentIntent keyed `cart:{id}:v{version}`.
2. The page mounts the Payment Element with the client secret; the card goes to Stripe, never to us.
3. Stripe calls `/webhooks/stripe`; the route verifies the signature over the raw body and inserts the event id.
4. On `payment_intent.succeeded` the handler copies the cart into `orders` and `order_lines` and sends the email.
5. The confirmation page reads the order by intent id and polls until it exists.

## 5. Ways in and out

- Storefront pages — `/`, `/products/[slug]`, `/search`, `/checkout` · where: `frontend/app/checkout/page.tsx` · seen: opened on production · made by: agent run · checked by: person
- Stripe webhook — `POST /webhooks/stripe` · where: `backend/app/routers/webhooks.py` · seen: live-mode event verified · made by: agent run · checked by: automated tests
- Stripe API — intents, tax · where: `backend/app/stripe_client.py` · seen: read; every call carries a key · made by: agent run · checked by: automated tests
- Email — transactional provider · where: `backend/app/emails.py` · seen: preview route on staging · made by: agent run · checked by: person

## 6. What it is made of

- Postgres — products, variants, carts, orders, stripe_events · where: `backend/app/models.py` · seen: read models and migrations · made by: agent run · checked by: automated tests
- Stripe client wrapper — idempotency required · where: `backend/app/stripe_client.py` · seen: opened · made by: agent run · checked by: automated tests
- Money formatters — one per side · where: `backend/app/money.py` · seen: opened both · made by: agent run · checked by: nobody

**Built and run:** Next.js 14, FastAPI, SQLAlchemy 2, Postgres 16, Stripe. Built with compose; tested by `make test` and CI. Runs on staging.shopfront.dev and shopfront.dev (production, not announced). Real data: the production database on the VM; staging uses test mode.
**Old material:** none.

## 7. Rules the project keeps

- Money is integer minor units everywhere · where: `AGENTS.md` · seen: opened · made by: person · checked by: agent
- Every Stripe call carries an idempotency key · where: `backend/app/stripe_client.py` · seen: wrapper refuses a call without one · made by: person · checked by: automated tests
- Secrets never committed · where: `backend/.env.example` · seen: opened · made by: person · checked by: agent

## 8. People

None found — looked in README.md and docs/.

## 9. What is owed

1. Refunds are not handled — a dashboard refund on {dsh:22} was logged and ignored; still true on {iso:22}: checked `routers/webhooks.py`.
2. Stripe Tax in review — board task; still true on {iso:22}.
3. Two money formatters — `backend/app/money.py` and `frontend/lib/money.ts`; could disagree for a new currency.

## 10. Words, and what was not read

- **Words:** PaymentIntent — Stripe's object for one payment attempt. SF-number — our order number (`backend/app/orders.py`). Intent key — `cart:{id}:v{version}` (`backend/app/idempotency.py`).
- **Not read:** `frontend/app/globals.css`, `infra/Dockerfile.web`.
- **Searched and not found:** a staging-to-production data copy (searched `infra/`).

Corrected in this version: the checkout choice is made; deploys have a rollback.
"""

PAGE_V3 = """## 1. What it is

shopfront is a small online store for everyday goods shipped inside the EU: a Next.js storefront, a FastAPI service with a background worker, Postgres, and Stripe. It serves customers buying, the operator who runs the shop, and support answering order questions.
**Kind:** service. **Standing:** active — commits every working day for a month; production has taken 208 payments since {dsh:22}.
**Made how:** by the operator with coding agents (Claude Code, Codex, OpenCode), one chat per piece of work.

## 2. The live work

- **Payments hardening** — refunds by line, an event log per order, webhooks stored before processing (`backend/app/worker.py`). Target, in the sprint's words: "nothing a customer pays for is lost, doubled or unexplained". Left: the partial-refund email (an uncommitted stub in `backend/app/emails.py`).
- **Order notifications** — paid orders are sent to tg-notify, signed, from the same queue (`backend/app/outbound.py`). Left: the opt-in on the confirmation page.
- **Launch polish** — product images at 1.7 s LCP on staging, sitemap, legal pages, FAQ.

## 3. What it does or has produced

- Checkout — Payment Element on our page, 3DS covered · where: `frontend/app/checkout/page.tsx` · seen: 208 live payments; 3DS matrix green in CI · made by: agent run · checked by: automated tests
- Orders — created once per payment, by the worker · where: `backend/app/worker.py` · seen: ran tests, 84 passed · made by: agent run · checked by: automated tests
- Refunds — whole or by line, shipping separately · where: `backend/app/routers/admin_orders.py` · seen: partial refund in tests · made by: agent run · checked by: automated tests
- Order history — every state change with its cause · where: `backend/app/order_events.py` · seen: timeline on the admin order page · made by: agent run · checked by: person
- Admin order list — filter and search · where: `frontend/app/admin/orders/page.tsx` · seen: 23 orders listed in 40 ms · made by: agent run · checked by: person
- Legal pages and FAQ · where: `frontend/app/faq/page.tsx` · seen: opened on staging · made by: agent run · checked by: person
- Funnel report for week one · where: `backend/app/orders.py` · seen: artifact checkout-funnel-report, {dsh:22} to {dsh:28} · made by: agent run · checked by: nobody

## 4. How the main thing works

1. `POST /api/checkout/intent` recomputes the cart and creates one PaymentIntent per cart version.
2. Stripe's webhook is verified over the raw body and stored in `stripe_events` as pending; the endpoint answers 200.
3. The worker claims pending rows (`FOR UPDATE SKIP LOCKED`), runs the handler, and retries with backoff; five failures make a row dead.
4. `payment_intent.succeeded` creates the order and its first `order_events` row, sends the email and queues `order.paid` for tg-notify.
5. Refunds go out through the same client with `refund:{order}` keys and come back as `charge.refunded` events.

## 5. Ways in and out

- Storefront — `/`, products, search, checkout, FAQ, legal · where: `frontend/app/layout.tsx` · seen: opened on production · made by: agent run · checked by: person
- Admin — `/admin/orders`, `/admin/events` · where: `frontend/app/admin/orders/page.tsx` · seen: opened; no sign-in yet · made by: agent run · checked by: person
- Stripe webhook in, Stripe API out · where: `backend/app/routers/webhooks.py` · seen: live events verified · made by: agent run · checked by: automated tests
- order.paid out to tg-notify, HMAC-signed · where: `backend/app/outbound.py` · seen: ran tests, 79 passed · made by: agent run · checked by: automated tests
- sitemap.xml and robots.txt · where: `frontend/app/sitemap.ts` · seen: 64 URLs · made by: agent run · checked by: nobody

## 6. What it is made of

- Postgres — catalog, carts, orders, order_events, stripe_events · where: `backend/app/models.py` · seen: read migrations · made by: agent run · checked by: automated tests
- Worker — processes stored events · where: `backend/app/worker.py` · seen: runs in compose as `worker` · made by: agent run · checked by: automated tests
- Load test — k6 checkout scenario · where: `loadtest/checkout.js` · seen: ran 10 min at 50/min · made by: agent run · checked by: agent

**Built and run:** Next.js 14, FastAPI, SQLAlchemy 2, Postgres 16, Stripe. Compose on two VMs (staging, production), deployed by `infra/deploy.sh`, rolled back by `infra/rollback.sh`. CI: lint, tests, type-check, 3DS matrix on main. Real data: the production database; no backups yet.
**Old material:** none.

## 7. Rules the project keeps

- Money is integer minor units everywhere · where: `AGENTS.md` · seen: opened · made by: person · checked by: agent
- Every Stripe call carries an idempotency key · where: `backend/app/stripe_client.py` · seen: enforced by the wrapper · made by: person · checked by: automated tests
- Webhook handlers are idempotent · where: `backend/app/worker.py` · seen: `processed_at` checked first · made by: person · checked by: automated tests
- Migrations only add until the release has shipped · where: `infra/rollback.sh` · seen: rollback runs no migration down · made by: person · checked by: agent
- UI copy in sentence case, no exclamation marks · where: `frontend/lib/declines.ts` · seen: opened · made by: person · checked by: agent

## 8. People

- Copywriter (role) — launch copy review booked for {dsh:32} (calendar) · last thing done for them: none · not recorded.

## 9. What is owed

1. Public beta on {iso:45} — milestone; not passed.
2. Database pool exhausted at 50 checkouts/min — load test of {dsh:25}; still true on {iso:30}: no fix committed.
3. Admin has no sign-in — the admin pages (`frontend/app/admin/orders/page.tsx`) open for anyone who knows the path; still true: checked the layout.
4. No backups of the production database — board task due {iso:30}; still true.
5. Partial-refund email — uncommitted stub; still true.

## 10. Words, and what was not read

- **Words:** PaymentIntent — Stripe's object for one payment attempt. SF-number — our order number (`backend/app/orders.py`). Dead event — a webhook that failed five times (`backend/app/worker.py`). LCP — largest contentful paint.
- **Not read:** `frontend/app/globals.css`, `infra/Dockerfile.web`, `content/legal/`.
- **Searched and not found:** a backup job (searched `infra/` and cron files).

Corrected in this version: refunds exist; webhooks are processed by a worker, not in the request.
"""


def _r(kind, name, what, where, evidence, version="", note=""):
    row = {"kind": kind, "name": name, "what": what, "where": where, "evidence": evidence}
    if version:
        row["version"] = version
    if note:
        row["note"] = note
    return row


_BASE_ROWS = [
    _r("runtime", "Python 3.12", "backend language", "backend/pyproject.toml", "computed", "3.12"),
    _r("runtime", "Node 20", "storefront build and server", "infra/Dockerfile.web", "computed", "20"),
    _r("framework", "FastAPI", "the API service", "backend/pyproject.toml", "computed", "0.115.0"),
    _r("framework", "Next.js", "storefront, app router", "frontend/package.json", "computed", "14.2.13"),
    _r("library", "SQLAlchemy", "ORM and migrations with alembic", "backend/pyproject.toml", "computed", "2.0.35"),
    _r("library", "stripe-python", "payments client, wrapped", "backend/app/stripe_client.py", "opened backend/app/stripe_client.py", "10.12.0"),
    _r("library", "@stripe/react-stripe-js", "Payment Element in React", "frontend/package.json", "computed", "2.8.0"),
    _r("entry", "make up", "starts db, api and web with compose", "Makefile", "opened Makefile"),
    _r("entry", "uvicorn app.main:app", "API process", "infra/Dockerfile.api", "opened infra/Dockerfile.api"),
    _r("surface", "Storefront", "home, product, search, cart pages", "frontend/app/page.tsx", "opened frontend/app/page.tsx"),
    _r("surface", "Checkout page", "address, shipping, payment on one page", "frontend/app/checkout/page.tsx", "opened frontend/app/checkout/page.tsx"),
    _r("api", "/api/products, /api/search", "catalog reads", "backend/app/routers/products.py", "opened backend/app/routers/products.py"),
    _r("api", "/api/cart", "server-side cart", "backend/app/routers/cart.py", "opened backend/app/routers/cart.py"),
    _r("api", "/api/checkout/intent", "PaymentIntent from the cart", "backend/app/routers/checkout.py", "opened backend/app/routers/checkout.py"),
    _r("api", "/webhooks/stripe", "Stripe events in", "backend/app/routers/webhooks.py", "opened backend/app/routers/webhooks.py"),
    _r("module", "backend/app/routers", "HTTP routes, one file per area", "backend/app/routers", "opened 6 files"),
    _r("module", "frontend/components", "shared React components", "frontend/components", "opened 8 files"),
    _r("module", "frontend/lib", "API client, money, cart helpers", "frontend/lib", "opened frontend/lib/api.ts"),
    _r("module", "scripts", "seed catalog from CSV", "scripts/seed_catalog.py", "opened scripts/seed_catalog.py"),
    _r("service", "api", "FastAPI on :8000", "infra/docker-compose.yml", "computed"),
    _r("service", "web", "Next.js on :3000", "infra/docker-compose.yml", "computed"),
    _r("service", "Caddy", "TLS and routing /api vs pages", "infra/Caddyfile", "opened infra/Caddyfile"),
    _r("store", "Postgres 16", "catalog, carts, orders, stripe events", "infra/docker-compose.yml", "computed", "16", "runs in compose; data volume on the VM"),
    _r("external", "Stripe", "payments, tax, webhooks", "backend/app/stripe_client.py", "opened backend/app/stripe_client.py"),
    _r("external", "Email provider", "transactional email", "backend/app/emails.py", "per backend/app/emails.py, not checked"),
    _r("config", "Settings from env", "database, Stripe keys, cookie secret", "backend/app/settings.py", "opened backend/app/settings.py"),
    _r("config", ".env.example", "names of every variable, no values", "backend/.env.example", "opened backend/.env.example"),
    _r("build", "Docker images", "api and web images", "infra/Dockerfile.api", "computed"),
    _r("deploy", "deploy.sh", "pull, build, migrate, restart, check", "infra/deploy.sh", "opened infra/deploy.sh"),
    _r("test", "pytest", "API tests incl. webhook replay", "backend/tests", "ran cd backend && pytest -q"),
    _r("test", "CI", "lint, tests, type-check on push", ".github/workflows/ci.yml", "opened .github/workflows/ci.yml"),
    _r("auth", "Signed cart cookie", "the browser holds only a signed cart id", "backend/app/cart_cookie.py", "opened backend/app/cart_cookie.py"),
    _r("job", "none", "no scheduled work", "infra/docker-compose.yml", "searched cron, schedule, worker"),
    _r("store", "Catalog CSV", "source of the seeded products", "content/catalog.csv", "opened content/catalog.csv"),
]

_BASE_RELATIONS = [
    {"from": "Storefront", "verb": "calls", "to": "/api/products, /api/search"},
    {"from": "Storefront", "verb": "calls", "to": "/api/cart"},
    {"from": "Checkout page", "verb": "calls", "to": "/api/checkout/intent"},
    {"from": "/api/checkout/intent", "verb": "calls", "to": "Stripe"},
    {"from": "Stripe", "verb": "triggers", "to": "/webhooks/stripe"},
    {"from": "/webhooks/stripe", "verb": "writes", "to": "Postgres 16"},
    {"from": "/api/cart", "verb": "reads", "to": "Postgres 16"},
    {"from": "/api/products, /api/search", "verb": "reads", "to": "Postgres 16"},
    {"from": "Caddy", "verb": "serves", "to": "Storefront"},
    {"from": "Caddy", "verb": "serves", "to": "api"},
    {"from": "make up", "verb": "starts", "to": "api"},
    {"from": "make up", "verb": "starts", "to": "web"},
    {"from": "deploy.sh", "verb": "deploys-to", "to": "Caddy"},
    {"from": "pytest", "verb": "tests", "to": "/webhooks/stripe"},
    {"from": "CI", "verb": "tests", "to": "pytest"},
    {"from": "scripts", "verb": "writes", "to": "Postgres 16"},
    {"from": "Catalog CSV", "verb": "feeds", "to": "scripts"},
    {"from": "Signed cart cookie", "verb": "uses", "to": "/api/cart"},
]

MAP_V1 = {
    "template": "web-service",
    "rows": _BASE_ROWS,
    "relations": _BASE_RELATIONS,
    "notes": {
        "shape": "A Next.js storefront and a FastAPI API over Postgres, with Stripe for payments; the checkout and the webhook are the core.",
        "main_path": "Storefront → /api/cart → /api/checkout/intent → Stripe → /webhooks/stripe → Postgres (order).",
        "runs_on": "One VM per environment with docker compose behind Caddy; only staging is reachable today.",
        "not_found": "No scheduled jobs; no admin sign-in (no admin yet).",
        "not_read": "frontend/app/globals.css, infra/Dockerfile.web.",
    },
}

_V2_ROWS = [r for r in _BASE_ROWS if r["name"] not in ("none",)] + [
    _r("service", "worker", "processes stored webhook and outbound events", "backend/app/worker.py", "opened backend/app/worker.py"),
    _r("job", "Webhook retry", "backoff 1 s, 5 s, 30 s, 5 min, then dead", "backend/app/worker.py", "opened backend/app/worker.py"),
    _r("surface", "Admin", "order list, order page with refunds, dead events", "frontend/app/admin/orders/page.tsx", "opened frontend/app/admin/orders/page.tsx",
       note="no sign-in yet"),
    _r("api", "/api/admin/orders", "list, refund by line", "backend/app/routers/admin_orders.py", "opened backend/app/routers/admin_orders.py"),
    _r("external", "tg-notify", "Telegram notifications for paid orders", "backend/app/outbound.py", "opened backend/app/outbound.py",
       note="separate repository and service"),
    _r("deploy", "rollback.sh", "restart the previous images", "infra/rollback.sh", "opened infra/rollback.sh"),
    _r("test", "3DS e2e", "four 3-D Secure cases against staging", "backend/tests/e2e/test_3ds.py", "opened backend/tests/e2e/test_3ds.py"),
    _r("test", "k6 load test", "50 checkouts a minute", "loadtest/checkout.js", "opened loadtest/checkout.js"),
    _r("module", "backend/app", "orders, events, emails, tax, outbound", "backend/app", "opened 9 files"),
    _r("data-out", "sitemap.xml", "catalog URLs for search engines", "frontend/app/sitemap.ts", "opened frontend/app/sitemap.ts"),
]

MAP_V2 = {
    "template": "web-service",
    "rows": _V2_ROWS,
    "relations": _BASE_RELATIONS[:9] + [
        {"from": "/webhooks/stripe", "verb": "writes", "to": "worker"},
        {"from": "worker", "verb": "writes", "to": "Postgres 16"},
        {"from": "worker", "verb": "calls", "to": "tg-notify"},
        {"from": "Admin", "verb": "calls", "to": "/api/admin/orders"},
        {"from": "/api/admin/orders", "verb": "calls", "to": "Stripe"},
        {"from": "Webhook retry", "verb": "uses", "to": "worker"},
        {"from": "rollback.sh", "verb": "deploys-to", "to": "Caddy"},
        {"from": "3DS e2e", "verb": "tests", "to": "Checkout page"},
        {"from": "k6 load test", "verb": "tests", "to": "/api/checkout/intent"},
        {"from": "CI", "verb": "tests", "to": "pytest"},
        {"from": "Catalog CSV", "verb": "feeds", "to": "scripts"},
    ],
    "notes": {
        "shape": "Storefront and admin on Next.js, a FastAPI API and a worker over Postgres; Stripe in and out; tg-notify out.",
        "main_path": "Checkout page → /api/checkout/intent → Stripe → /webhooks/stripe → worker → Postgres (order, events) → tg-notify.",
        "runs_on": "Two VMs (staging, production) with compose behind Caddy; production is public at shopfront.dev.",
        "not_found": "No admin sign-in; no backup job (searched infra/ and cron).",
        "not_read": "content/legal/, frontend/app/globals.css.",
    },
}
