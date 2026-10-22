"""shopfront chats, 1–11 September: catalog, search, cart, staging, the checkout choice."""

from __future__ import annotations

from common import C
from engine import Chat, D, timedelta

P = "shopfront"


def at(t, minutes):
    return t + timedelta(minutes=minutes)


def setup(sim, w, repo, K):
    """K: dict to hand chats to later modules (kept-message interpretations)."""

    # ------------------------------------------------------------------
    # C1 · 1 Sep · bootstrap
    # ------------------------------------------------------------------
    c = Chat(sim, P, "7f3a91c2-5d1e-4b7a-9c3f-2e8a61d04b11", title="bootstrap the monorepo", repo=repo,
             headline="A storefront skeleton: Next.js, FastAPI, Postgres, one compose file")
    K["c1"] = c
    t = D(1, 9, 12)
    c.turn(t, "Morning. New project: shopfront, a small store — Next.js storefront, FastAPI backend, Postgres, Stripe later. "
              "The skeleton is committed. Read it and tell me what you would change before we build on it. Task is {tk:repo-setup}.",
           "Read all 24 files. Three changes before building on it:\n\n"
           "1. `backend/app/db.py` opens a sync engine; the API will want async for Stripe calls later. Keep sync for now — "
           "SQLAlchemy 2 sync is simpler and FastAPI runs it in a thread pool — but put the session behind `get_db` everywhere so switching is one file.\n"
           "2. There are no migrations. Add alembic now, before the first table exists.\n"
           "3. `Makefile` has no `migrate` target. Adding one.\n\n"
           "Nothing else I would change yet.", minutes=9)
    t = D(1, 9, 30)
    c.turn(t, "Agree on all three. Do them.",
           "Done:\n- alembic initialised under `backend/alembic`, env.py reads `settings.database_url`\n"
           "- first migration creates `products`\n- `make migrate` runs `alembic upgrade head` inside the api container\n\n"
           "`make up && make migrate` works from a clean checkout; `pytest -q`: 1 passed.",
           minutes=22, commits=[C(8, "Add alembic with the products table", "mig:create products table", "backend/app/models.py", "Makefile"),
                                C(18, "make migrate runs alembic in the api container", "Makefile", "README.md")],
           helpers=[(3, 6)])
    t = D(1, 10, 5)
    c.turn(t, "#rule Money is integer minor units everywhere — database, API, frontend. Never a float, never a Decimal in JSON.",
           "Kept as a rule. Applied it to what exists: `Product` has no price yet, so I added `price_amount: BigInteger` and "
           "`currency: CHAR(3)` to the variant table in the next migration, and `frontend/lib/money.ts` with one `formatMoney(amount, currency)` "
           "that divides by 100 only at display time. Task {tk:money-minor}.",
           minutes=14, commits=[C(11, "Variants with integer prices and a single money formatter", "mig:variants with integer prices",
                                  "backend/app/models.py", "frontend/lib/money.ts", "frontend/lib/types.ts")])
    t = D(1, 10, 40)
    c.turn(t, "#rule Never commit secrets. .env stays local, settings come from the environment, and a key pasted in a chat gets rotated.",
           "Kept. Checked the repo: `.env` is in `.gitignore`, `settings.py` reads everything from the environment, no key in history. "
           "Added `.env.example` with the variable names and empty values so the next person knows what to set.",
           minutes=6, commits=[C(4, "Add .env.example", "=backend/.env.example::DATABASE_URL=\nSTRIPE_SECRET_KEY=\nSTRIPE_WEBHOOK_SECRET=\nCART_COOKIE_SECRET=\n")])
    K["rule_secrets"] = (c, c.last_n)
    t = D(1, 11, 5)
    c.turn(t, "Good. Skeleton is done then. #done {tk:repo-setup}",
           "Moved {tk:repo-setup} to done. The skeleton: two apps, one compose file, alembic, `.env.example`, a money formatter. "
           "Next on the board is {tk:products-schema}.", minutes=2)
    K["rule_money"] = (c, 3)

    # ------------------------------------------------------------------
    # C2 · 1–3 Sep · catalog API, CI and the seed
    # ------------------------------------------------------------------
    c = Chat(sim, P, "2b8e4d17-a0c2-4f65-8e19-7d3b5c90a2e4", title="catalog api", repo=repo,
             headline="The catalog API: products, variants, categories, cursor pagination")
    K["c2"] = c
    t = D(1, 13, 15)
    c.turn(t, "Next: {tk:products-schema}. Products with variants (size, colour), each variant priced. Categories are just a string for now.",
           "Plan, before code:\n- `products`: id (ULID), slug, title, description, category, created_at\n"
           "- `variants`: id, product_id, sku (unique), size, colour, price_amount, currency, stock\n"
           "- index on `products.category`, unique on `variants.sku`\n\nULIDs so ids sort by creation and do not leak counts. Go?",
           minutes=5)
    t = D(1, 13, 25)
    c.turn(t, "Go.",
           "Migration `0003` adds `variants` and the indexes; models updated; `tests/test_models.py` checks the unique SKU. `pytest -q`: 4 passed.",
           minutes=26, commits=[C(15, "Products and variants schema with ULID ids", "mig:variants sku index", "backend/app/models.py"),
                                C(23, "Model tests for unique SKU", "backend/tests/test_models.py")])
    t = D(1, 16, 20)
    c.turn(t, "#rule Run the tests before you say a task is done, and say how many passed.",
           "Kept. I have been doing it; from now on the count goes in every report, and a skipped suite is said out loud.", minutes=2)
    K["rule_tests"] = (c, c.last_n)
    t = D(2, 9, 25)
    c.turn(t, "Morning. {tk:ci-pipeline} first — a push should fail on a broken test. Then {tk:products-api}.",
           "CI is in `.github/workflows/ci.yml`: two jobs, `api` (ruff, pytest against a Postgres service) and `web` (tsc, next lint). "
           "Both run on every push and pull request. First run green in 2 min 40 s.",
           minutes=18, commits=[C(12, "CI: ruff, pytest with Postgres, tsc and next lint", "=.github/workflows/ci.yml::name: ci\non: [push, pull_request]\njobs:\n  api:\n    runs-on: ubuntu-latest\n    services:\n      postgres:\n        image: postgres:16\n        env: { POSTGRES_PASSWORD: shop }\n    steps:\n      - uses: actions/checkout@v4\n      - run: pip install -e backend[dev]\n      - run: cd backend && ruff check . && pytest -q\n  web:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: cd frontend && npm ci && npm run typecheck && npm run lint\n")])
    t = D(2, 9, 50)
    c.turn(t, "Now {tk:products-api}. Cursor pagination, not offsets.",
           "Done:\n- `GET /api/products?category=&cursor=&limit=` — cursor is the last ULID, limit capped at 48\n"
           "- `GET /api/products/{slug}` with variants\n- 404 with a plain message for an unknown slug\n\n"
           "`pytest -q`: 11 passed. Reported it on the task.",
           minutes=34, commits=[C(14, "Products router: list with cursor, detail by slug", "backend/app/routers/products.py", "backend/app/main.py"),
                                C(28, "Tests for product listing and detail", "backend/tests/test_products.py")],
           helpers=[(10, 14)])
    w.report("products-api", D(2, 10, 26), c.agent_id, "List with cursor pagination and detail by slug; 11 tests pass.")
    w.decision(D(2, 10, 20), P, c.agent_id,
               "Product lists paginate by cursor (the last ULID), not by offset",
               "An offset shifts when a product is added mid-browse and gets slower with depth. A ULID cursor is stable and "
               "uses the primary key index. Settled; revisit only if we need 'jump to page 7'.",
               ["Offset and limit — rejected: pages shift when the catalog changes, and deep pages scan",
                "Keyset on (created_at, id) — rejected: the ULID already orders by creation"], weight="normal", tags="api,catalog")
    t = D(2, 11, 10)
    c.turn(t, "Looks right. #done {tk:products-api}",
           "{tk:products-api} is done. {tk:seed-catalog} next — do you have the CSV?", minutes=1)
    t = D(3, 9, 55)
    c.turn(t, "The CSV is in content/catalog.csv now: 48 products. Do {tk:seed-catalog}. It must be safe to run twice.",
           "`scripts/seed_catalog.py` upserts by SKU: a second run changes nothing and prints `48 products, 0 changed`. "
           "Prices in the CSV were in euros with a comma; the script converts to cents and refuses a row it cannot parse, with the line number. "
           "Found 2 such rows (lines 17 and 33, a dot instead of a comma) and fixed them in the CSV.",
           minutes=31, commits=[C(9, "Catalog CSV with 48 products", "=content/catalog.csv::sku,title,category,size,colour,price_eur\nTEE-BLK-S,Heavy cotton tee,apparel,S,black,\"29,00\"\nTEE-BLK-M,Heavy cotton tee,apparel,M,black,\"29,00\"\nMUG-WHT,Stoneware mug,home,,white,\"18,00\"\n"),
                                C(24, "Seed script: idempotent upsert by SKU", "scripts/seed_catalog.py", "Makefile", "backend/tests/test_seed.py")])

    # ------------------------------------------------------------------
    # C3 · 3–7 Sep · product grid and product page (Codex)
    # ------------------------------------------------------------------
    c = Chat(sim, P, "5c0a9e33-1f7d-4a28-b6e5-90c4d2a8f731", tool="codex", title="storefront pages", repo=repo,
             headline="The storefront's first pages: the grid and the product page")
    K["c3"] = c
    t = D(3, 11, 5)
    c.turn(t, "You're on the frontend. {tk:product-grid}: responsive grid on the home page, 2 columns on phones, 4 on desktop. "
              "Prices through lib/money.ts, nothing else.",
           "Understood. Reading `frontend/lib/api.ts` and `money.ts` first; the grid will be a server component that fetches "
           "`/api/products` and renders `ProductCard`s.", minutes=4)
    t = D(3, 11, 15)
    c.turn(t, "Go ahead.",
           "Added `components/ProductCard.tsx` and `components/ProductGrid.tsx`; `app/page.tsx` renders the first 24 products. "
           "Images use `next/image` with fixed aspect 4:5 so the grid does not jump. `npm run typecheck` clean.",
           minutes=38, commits=[C(20, "Product card and grid on the home page", "frontend/components/ProductCard.tsx", "frontend/components/ProductGrid.tsx", "frontend/app/page.tsx"),
                                C(33, "Grid styles: 2 columns on phones, 4 on desktop", "frontend/app/globals.css")])
    t = D(3, 14, 5)
    c.turn(t, "Now {tk:product-page}. Variant picker for size and colour; price and button follow the variant.",
           "`app/products/[slug]/page.tsx` fetches the product; `VariantPicker` keeps the choice in the URL (`?size=M&colour=black`) "
           "so a shared link opens the same variant. Sold-out variants are shown and disabled, not hidden.",
           minutes=46, commits=[C(25, "Product page with a variant picker kept in the URL", "frontend/app/products/[slug]/page.tsx", "frontend/components/VariantPicker.tsx"),
                                C(41, "Disable sold-out variants instead of hiding them", "frontend/components/VariantPicker.tsx")])
    t = D(4, 11, 40)
    c.turn(t, "On a phone the grid cards are too tall — two rows fill the screen. Tighten it.",
           "Aspect ratio 4:5 → 1:1 on screens under 640 px, title clamped to two lines, price on the same line as the colour dots. "
           "Four rows now fit on a 390 px screen. Moved {tk:product-grid} to review.", minutes=19,
           commits=[C(12, "Tighter product cards on small screens", "frontend/components/ProductCard.tsx", "frontend/app/globals.css")])
    t = D(7, 10, 5)
    c.turn(t, "PDP is approved. Anything left over from it?",
           "One thing: the product page fetches the product twice (metadata and page). Added `cache()` around the fetch so it is one request. "
           "Nothing else open.", minutes=11, commits=[C(7, "Fetch the product once per request on the product page", "frontend/app/products/[slug]/page.tsx", "frontend/lib/api.ts")])

    # ------------------------------------------------------------------
    # C4 · 7–9 Sep · search
    # ------------------------------------------------------------------
    c = Chat(sim, P, "91d4f6a0-3b8c-4e17-a5d2-6f0e9b1c7a38", title="search", repo=repo,
             headline="Search: Postgres full-text on the catalog, instant results in the header")
    K["c4"] = c
    t = D(7, 9, 15)
    c.turn(t, "Search. {tk:search-api} then {tk:search-box}. Postgres full-text is enough for 48 products, and probably for 4,800.",
           "Agreed — no search service. Plan: a generated `tsvector` column (title weight A, description B), a GIN index, "
           "`/api/search?q=` returning the top 20 by `ts_rank`. Prefix matching so 'lin' finds 'linen'.", minutes=6)
    t = D(7, 9, 25)
    c.turn(t, "Go.",
           "Migration adds `products.search` as a generated column with the index; `routers/search.py` answers in 3–6 ms on the seed data. "
           "`pytest -q`: 19 passed, including prefix and accent cases ('cafe' finds 'Café').",
           minutes=48, commits=[C(20, "Full-text search column and GIN index", "mig:products search vector"),
                                C(38, "Search endpoint with prefix matching and unaccent", "backend/app/routers/search.py", "backend/app/main.py", "backend/tests/test_search.py")],
           helpers=[(15, 20)])
    t = D(7, 14, 30)
    c.turn(t, "#vision Merchants edit the catalog in a spreadsheet and the store follows within minutes — no admin screens for products, ever.",
           "Kept as a vision. It fits what exists: the seed script already upserts by SKU from a CSV, so a sheet exported on a schedule is most of it. "
           "The missing parts are a scheduled pull and a way to see what changed.", minutes=3)
    K["vision_sheet"] = (c, c.last_n)
    t = D(8, 13, 5)
    c.turn(t, "{tk:search-box}: debounce, first five results under the box, Enter goes to the results page.",
           "`SearchBox` in the header: 200 ms debounce, aborts the previous request, arrow keys move through the five results, "
           "Enter opens `/search?q=`. Results page reuses `ProductGrid`.", minutes=41,
           commits=[C(22, "Header search box with instant results", "frontend/components/SearchBox.tsx", "frontend/app/layout.tsx"),
                    C(35, "Search results page", "frontend/app/search/page.tsx")])
    t = D(9, 11, 30)
    c.turn(t, "Search box: results flash when typing fast. Fix, then it's ready for review.",
           "Stale responses were landing after newer ones. Each request now carries a sequence number and older answers are dropped. "
           "Typing 'heavy cotton' quickly shows one update at the end. Moved {tk:search-box} to review.", minutes=14,
           commits=[C(9, "Drop stale search responses", "frontend/components/SearchBox.tsx")])

    # ------------------------------------------------------------------
    # C5 · 8–10 Sep · the cart
    # ------------------------------------------------------------------
    c = Chat(sim, P, "3e7b20c5-8a4f-4d91-b2c6-1e5f7a9d3b60", title="cart", repo=repo,
             headline="Carts live on the server; the browser only holds a signed id")
    K["c5"] = c
    t = D(8, 10, 5)
    c.turn(t, "{tk:cart-api}. Server-side cart, browser holds a signed id. Why not localStorage — convince me or don't.",
           "Server-side, because the total must be computed where the prices are: a cart in localStorage is a price list the customer can edit, "
           "and the checkout would have to re-check every line anyway. The cost is one table and a cookie. "
           "Also: a server cart survives a device switch once accounts exist.", minutes=5)
    w.decision(D(8, 10, 9), P, c.agent_id, "Carts are stored server-side; the browser holds only a signed cart id",
               "Totals are computed where the prices live, so a tampered client cannot change what is charged. "
               "Costs one table and a cookie; settled.",
               ["Cart in localStorage — rejected: the client would hold prices, and checkout would re-validate every line",
                "Cart in a JWT — rejected: grows with every line and cannot be invalidated"], weight="major",
               excerpt="Operator: Why not localStorage — convince me or don't.\nAgent: Server-side, because the total must be computed where the prices are.",
               tags="cart,security")
    t = D(8, 10, 20)
    c.turn(t, "Convinced. Build it.",
           "Done:\n- `carts` and `cart_lines` tables; the cookie `sf_cart` is the cart ULID signed with `cart_cookie_secret`, HttpOnly, SameSite=Lax\n"
           "- `GET /api/cart`, `POST /api/cart/items`, `PATCH /api/cart/items/{sku}`, `DELETE …`\n- quantities clamp to stock; totals in cents\n\n`pytest -q`: 27 passed.",
           minutes=55, commits=[C(18, "Cart tables and the signed cart cookie", "mig:carts and cart lines", "backend/app/models.py", "backend/app/cart_cookie.py"),
                                C(40, "Cart API: add, change, remove, totals in cents", "backend/app/routers/cart.py", "backend/app/main.py"),
                                C(50, "Cart API tests", "backend/tests/test_cart.py")],
           helpers=[(20, 25)])
    t = D(9, 9, 35)
    c.turn(t, "{tk:cart-drawer} and {tk:add-to-cart}. The drawer opens after add-to-cart too.",
           "`CartDrawer` slides in from the right; steppers call `PATCH` and the total shown is the server's. `AddToCartButton` bumps the badge "
           "immediately and rolls back with a message if the call fails (tested by stopping the API).", minutes=52,
           commits=[C(20, "Cart drawer with quantity steppers", "frontend/components/CartDrawer.tsx", "frontend/lib/cart.ts"),
                    C(38, "Add-to-cart button with optimistic badge", "frontend/components/AddToCartButton.tsx", "frontend/app/products/[slug]/page.tsx")])
    w.task("cart-cookie-rotate", D(9, 16, 40), P, "Cart cookie is not rotated after sign-in", status="agent", lane="checkout",
           tags="ag_followup", agent=c.agent_id,
           desc="The signed cart id survives sign-in unchanged. Rotate it when the cart is attached to an account.")
    t = D(9, 16, 30)
    c.turn(t, "Drawer works. One thing: stepping to 0 should remove the line, not leave a zero.",
           "Zero now removes the line, with an 'Undo' for five seconds. Also noted a follow-up on the board: the cart cookie is not rotated at sign-in.",
           minutes=13, commits=[C(9, "Stepper at zero removes the line, with undo", "frontend/components/CartDrawer.tsx")])
    w.round("cart-drawer", D(9, 17, 0), "Steppers clamp at the stock level and say so ('only 3 left') instead of failing silently.")
    t = D(10, 9, 40)
    c.turn(t, "Added a round to {tk:cart-drawer.2}: clamp at stock and say so.",
           "Done: the '+' disables at the stock level and the line shows 'only 3 left'. The API already clamped; the drawer now reads `max` from it. "
           "Evidence posted on the task.", minutes=21,
           commits=[C(14, "Cart drawer clamps at stock and says so", "frontend/components/CartDrawer.tsx", "backend/app/routers/cart.py")])
    w.evidence("cart-drawer", D(10, 10, 0), c.agent_id, [
        {"kind": "image", "title": "Drawer at stock limit, 390 px wide", "mock": "cards"},
        {"kind": "text", "title": "What was checked",
         "body": "- stepper disables at stock (3) and shows 'only 3 left'\n- zero removes the line, Undo restores it\n- total shown equals `GET /api/cart` total\n- `pytest -q`: 29 passed"},
    ])
    t = D(10, 10, 5)
    c.turn(t, "Perfect. #done", "{tk:cart-drawer} is done.", minutes=1)

    # ------------------------------------------------------------------
    # C6 · 10 Sep · staging, and the first scan
    # ------------------------------------------------------------------
    c = Chat(sim, P, "a41f8c3d-6e92-4b0a-8d57-3c1b9f2e6a74", title="staging", repo=repo,
             headline="Staging on one VM: compose, Caddy, a deploy script")
    K["c6"] = c
    t = D(10, 10, 35)
    c.turn(t, "{tk:staging-deploy}. One VM, compose, Caddy for TLS. No Kubernetes.",
           "`infra/Caddyfile` terminates TLS for staging.shopfront.dev and proxies `/api` to the API and the rest to Next. "
           "`infra/deploy.sh` pulls, builds, migrates, restarts, and prints the health check. First deploy took 3 min 10 s; "
           "`https://staging.shopfront.dev/api/health` answers `{\"ok\": true, \"env\": \"staging\"}`.", minutes=64,
           commits=[C(25, "Caddy in front of the API and the web app", "=infra/Caddyfile::staging.shopfront.dev {\n  handle /api/* {\n    reverse_proxy api:8000\n  }\n  handle {\n    reverse_proxy web:3000\n  }\n}\n", "infra/docker-compose.yml"),
                    C(50, "Deploy script: pull, build, migrate, restart, check", "=infra/deploy.sh::#!/bin/sh\nset -eu\ngit pull --ff-only\ndocker compose -f infra/docker-compose.yml build\ndocker compose -f infra/docker-compose.yml run --rm api alembic upgrade head\ndocker compose -f infra/docker-compose.yml up -d\ncurl -fsS https://staging.shopfront.dev/api/health\n", "docs/runbook.md")],
           helpers=[(30, 20)])
    w.decision(D(10, 11, 30), P, c.agent_id, "Staging and production run on single VMs with docker compose, not Kubernetes",
               "One store, two apps and a database fit on one machine; compose is a file anyone can read. "
               "Revisit when one VM cannot hold the peak, not before.",
               ["Managed Kubernetes — rejected: a cluster to run for three containers",
                "A PaaS per app — rejected: the database and the webhook path split across providers"],
               weight="major", tags="infra,deploy")
    t = D(10, 17, 10)
    c.turn(t, "Staging works. #scan",
           "Scan written: the catalog, search and the cart are on staging. File entry and the architecture form are in, and the first version of the architecture page.",
           minutes=16, skills=["make-a-scan"])
    K["scan_s1_chat"] = c

    # ------------------------------------------------------------------
    # C7 · 11 Sep · the checkout decision
    # ------------------------------------------------------------------
    c = Chat(sim, P, "6d02b9e8-c4a1-4f3e-9b72-8e0d5a6c1f29", title="checkout: hosted or embedded", repo=repo,
             headline="Checkout decided: the Payment Element, on our own page")
    K["c7"] = c
    t = D(11, 9, 25)
    c.turn(t, "{tk:checkout-choice}. Stripe Checkout (hosted) or the Payment Element on our page? Give me the trade-off in five lines.",
           "1. Hosted Checkout ships in a day; the Payment Element in about four.\n"
           "2. Hosted leaves our domain; conversion data says a redirect costs a few percent on mobile.\n"
           "3. The Payment Element keeps our cart, shipping and totals on one page we control.\n"
           "4. Both give Apple Pay, Google Pay, SEPA and 3DS with no extra work.\n"
           "5. Hosted Checkout owns tax and shipping UI; with the Element we build shipping choice ourselves.\n\n"
           "My pick: the Payment Element — the cart is already server-side, so the extra work is the page.", minutes=7)
    t = D(11, 9, 45)
    c.turn(t, "#decision Payment Element. We keep the customer on our page. Log it as major.",
           "Logged as major, with both rejected options and what would make us revisit it.", minutes=4)
    w.decision(D(11, 9, 47), P, c.agent_id, "Checkout uses Stripe's Payment Element on our own page, not hosted Checkout",
               "The customer stays on shopfront.dev; the server-side cart and totals stay ours. About three more days of work. "
               "Revisit if mobile conversion on our page is below hosted Checkout's in the first month.",
               ["Stripe Checkout (hosted) — rejected: a redirect off our domain and a second place that owns totals",
                "Our own card form with Stripe.js elements — rejected: we would own PCI scope and every wallet button"],
               weight="major",
               excerpt="Operator: Stripe Checkout (hosted) or the Payment Element on our page?\nAgent: My pick: the Payment Element — the cart is already server-side, so the extra work is the page.\nOperator: #decision Payment Element. We keep the customer on our page.",
               tags="checkout,stripe")
    t = D(11, 11, 0)
    c.turn(t, "#vision Guest checkout in under 60 seconds, measured end to end on a mid-range phone.",
           "Kept. For that to be measurable we need the funnel timed: first checkout render to the confirmation page. "
           "I'll make it an acceptance line on {tk:guest-checkout} rather than a task of its own.", minutes=3)
    K["vision_60s"] = (c, c.last_n)
    t = D(11, 12, 25)
    c.turn(t, "I put the four checkout tasks on the board: guest checkout, shipping rates, the confirmation page and the email. "
              "Anything missing? And #done {tk:checkout-choice}.",
           "One gap: nothing covers what happens when the webhook arrives before the customer is back on our page — {tk:webhooks} does, "
           "if the confirmation page reads the order by the intent id and waits for it. Adding that as a line on {tk:order-confirm-page}. "
           "{tk:checkout-choice} is done.", minutes=6)
