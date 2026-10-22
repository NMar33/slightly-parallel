"""shopfront chats, 14–22 September: checkout v1 and the first real payment."""

from __future__ import annotations

from common import C
from engine import Chat, D

P = "shopfront"


def setup(sim, w, repo, K):
    # ------------------------------------------------------------------
    # C8 · 14–15 Sep · the intent, idempotency, the checkout page
    # ------------------------------------------------------------------
    c = Chat(sim, P, "c7e513aa-2d64-4b1f-8e3a-5f9c0b7d2e18", title="checkout page", repo=repo,
             headline="Checkout: the intent from the server cart, one page with the Payment Element")
    K["c8"] = c
    t = D(14, 9, 15)
    c.turn(t, "Checkout v1 starts. {tk:payment-intent} first: the amount comes from the server cart, never from the page.",
           "Plan: `POST /api/checkout/intent` loads the cart from the cookie, recomputes the lines from current prices, adds shipping, "
           "and creates or updates one PaymentIntent per cart. The client gets only the client secret and the amount to show.", minutes=6)
    t = D(14, 9, 30)
    c.turn(t, "Yes. And {tk:idempotency} while you're in there — a double click must not make two intents.",
           "Done both:\n- `stripe_client.py` wraps every call and requires an idempotency key\n"
           "- the intent key is `cart:{id}:v{version}` — the cart version bumps on every change, so a retry reuses the intent and a changed cart gets a new amount\n"
           "- the intent id is stored on the cart; a second call updates it instead of creating one\n\n"
           "Tested with 20 parallel requests on one cart: one intent. `pytest -q`: 38 passed.", minutes=58,
           commits=[C(20, "Stripe client wrapper that requires an idempotency key", "backend/app/stripe_client.py", "backend/app/idempotency.py"),
                    C(42, "Checkout intent from the server-side cart", "backend/app/routers/checkout.py", "backend/app/main.py", "mig:cart intent id and version"),
                    C(54, "Checkout intent tests, including parallel requests", "backend/tests/test_checkout.py")],
           helpers=[(25, 22)])
    t = D(14, 11, 0)
    c.turn(t, "#rule Every Stripe call carries an idempotency key. No exceptions, including scripts.",
           "Kept. The wrapper already refuses a call without one; I added a ruff rule that flags `stripe.` used outside `stripe_client.py`, "
           "so a script cannot go around it.", minutes=9,
           commits=[C(6, "Lint: Stripe only through stripe_client", "backend/pyproject.toml")])
    K["rule_idem"] = (c, c.last_n)
    w.decision(D(14, 11, 5), P, c.agent_id, "The PaymentIntent idempotency key is the cart id plus the cart's version",
               "A retry of the same cart reuses its intent; any change to the cart bumps the version and gets a fresh amount. Settled.",
               ["A random key per request — rejected: a double click makes two intents",
                "The cart id alone — rejected: a changed cart would replay the old amount"], weight="normal", tags="stripe,checkout")
    t = D(14, 14, 5)
    c.turn(t, "{tk:checkout-page}. Address, shipping method, Payment Element, one page. The pay button shows the server's total.",
           "Built `app/checkout/page.tsx`: address form, shipping choice (from `/api/checkout/shipping`), then the Payment Element "
           "mounted with the client secret. The pay button label is the server's amount, formatted once. Submitting confirms with "
           "`return_url` set to the confirmation page.", minutes=72,
           commits=[C(25, "Checkout page: address and shipping", "frontend/app/checkout/page.tsx", "frontend/components/CheckoutForm.tsx"),
                    C(55, "Mount the Payment Element with the server's amount", "frontend/components/PaymentStep.tsx", "frontend/lib/api.ts"),
                    C(68, "Order summary beside the payment form", "frontend/components/OrderSummary.tsx")],
           helpers=[(10, 30), (40, 25)])
    w.round("checkout-page", D(15, 9, 0), "Show the total including VAT right above the pay button, and the shipping line in the summary.")
    t = D(15, 9, 20)
    c.turn(t, "Round 2 on {tk:checkout-page.2}: total incl. VAT above the button, shipping in the summary.",
           "Done. The summary lists lines, shipping and 'incl. VAT' with the amount Stripe Tax will split later; the same total sits above the button. "
           "Screenshots and the checks are on the task as evidence.", minutes=28,
           commits=[C(18, "Checkout summary: shipping line and total incl. VAT", "frontend/components/OrderSummary.tsx", "frontend/components/PaymentStep.tsx")])
    w.evidence("checkout-page", D(15, 9, 48), c.agent_id, [
        {"kind": "image", "title": "Checkout on desktop, test card entered", "mock": "form"},
        {"kind": "text", "title": "Checked against the rules",
         "body": "- amount on the button = `PaymentIntent.amount` (checked for 3 carts)\n- changing quantity in another tab updates the intent on reload, no second intent\n"
                 "- the card form is Stripe's iframe; no card data reaches our server\n- `pytest -q`: 41 passed, `npm run typecheck` clean"},
    ])
    w.note("checkout-page", D(15, 10, 0), "release",
           "Checkout is one page now: address, shipping and payment together, with the total shown before you pay. Cards, Apple Pay and Google Pay work out of the box.",
           template="release-line")

    # ------------------------------------------------------------------
    # C9 · 15–16 Sep · webhooks and orders (Codex)
    # ------------------------------------------------------------------
    c = Chat(sim, P, "8f21d6c4-7b3e-4a05-9d18-2c6e4f0a9b57", tool="codex", title="webhooks and orders", repo=repo,
             headline="Orders are created by the webhook, once, whatever Stripe retries")
    K["c9"] = c
    t = D(15, 10, 10)
    c.turn(t, "{tk:orders-table} and {tk:webhooks}. The webhook creates the order, not the confirmation page. Exactly once.",
           "Reading the checkout code first. Plan: `orders` + `order_lines` copy prices at purchase time; `stripe_events` stores every event id; "
           "the handler inserts the event id first and does nothing if it is already there.", minutes=8)
    t = D(15, 10, 25)
    c.turn(t, "Go.",
           "Orders are in: `orders`, `order_lines`, numbers `SF-10001` upwards from a sequence. `POST /webhooks/stripe` verifies the signature, "
           "inserts the event id (unique), and on `payment_intent.succeeded` creates the order from the cart in the same transaction. "
           "A replayed event returns 200 and changes nothing. `pytest -q`: 49 passed.", minutes=95,
           commits=[C(30, "Orders and order lines with human order numbers", "mig:orders and order lines", "backend/app/models.py", "backend/app/orders.py"),
                    C(70, "Stripe webhook: verify, dedupe on event id, create the order", "backend/app/routers/webhooks.py", "backend/app/main.py", "mig:stripe events"),
                    C(88, "Webhook tests: replay and out-of-order events", "backend/tests/test_webhooks.py")],
           helpers=[(35, 40)])
    w.decision(D(15, 12, 5), P, c.agent_id, "Orders are created only by the webhook, never by the confirmation page",
               "The page can be closed, reloaded or never reached; Stripe's event always arrives, and may arrive twice. "
               "Dedupe on the event id makes the handler idempotent. The page waits for the order instead of making one.",
               ["Create the order on the return_url — rejected: a closed tab loses a paid order",
                "Create it in both places and merge — rejected: two writers for one record"], weight="major", tags="orders,webhooks")
    t = D(16, 10, 40)
    c.turn(t, "Staging: every webhook fails with 'No signatures found matching the expected signature'. Local works. #problem Stripe signature check fails on staging, every event.",
           "Looking. Local uses `stripe listen`, staging goes through Caddy. Logged the raw body length on both: local 1,843 bytes, "
           "staging 1,812 for the same replayed event — the body is altered before we read it.", minutes=24)
    K["problem_sig"] = (c, c.last_n)
    t = D(16, 11, 15)
    c.turn(t, "What alters it?",
           "Not Caddy: it forwards bytes unchanged. It is our own middleware — the request logger calls `await request.json()` and FastAPI "
           "re-serialises the body for the handler, so key order and whitespace change. The signature is over the raw bytes. "
           "Fix: the webhook route reads `await request.body()` before anything parses it, and the logger skips `/webhooks/*`. "
           "Handing the fix to the board as {tk:webhook-proxy-fix}.", minutes=18)
    t = D(16, 18, 0)
    c.turn(t, "Proxy fix is merged by the other chat. Replayed the 12 failed events — all 200. #done {tk:webhooks}",
           "{tk:webhooks} is done. The 12 replayed events created 3 orders and 9 no-ops, as expected.", minutes=3)

    # ------------------------------------------------------------------
    # C10 · 16–17 Sep · the proxy fix, guest checkout, shipping, confirmation
    # ------------------------------------------------------------------
    c = Chat(sim, P, "0b9a7e52-4c1d-4f86-a3e9-7d2b8c5f1e06", title="guest checkout", repo=repo,
             headline="Guest checkout: an email is enough; shipping and the confirmation page")
    K["c10"] = c
    t = D(16, 9, 45)
    c.turn(t, "{tk:guest-checkout}: email is the only identity. No account wall.",
           "The checkout form asks for the email first and stores it on the cart; the order copies it. No password anywhere. "
           "An 'create an account' link on the confirmation page pre-fills the email.", minutes=40,
           commits=[C(25, "Guest checkout: email on the cart, copied to the order", "backend/app/routers/checkout.py", "frontend/components/CheckoutForm.tsx")])
    t = D(16, 11, 35)
    c.turn(t, "Take {tk:webhook-proxy-fix} — the other chat found it: the logger re-serialises the body.",
           "Fixed: the webhook route reads the raw body first; the request logger skips `/webhooks/*` and logs only length and event type there. "
           "Added a test that sends a body with unusual whitespace and a valid signature. Deployed to staging; a test event verifies. `pytest -q`: 53 passed.",
           minutes=31, commits=[C(15, "Webhook reads the raw body; logger skips webhook routes", "backend/app/routers/webhooks.py", "backend/app/logging_mw.py"),
                                C(26, "Test: signature over raw bytes with odd whitespace", "backend/tests/test_webhooks.py")])
    w.update("webhook-proxy-fix", D(16, 12, 10), actor="operator", status="review")
    t = D(16, 14, 5)
    c.turn(t, "{tk:shipping-rates}: €4.90 in the EU, free from €60. Server-side.",
           "`shipping.py` returns the rate for the cart and country; it is added to the intent amount and shown as its own line. "
           "Outside the EU the checkout says we do not ship there yet instead of failing at payment.", minutes=34,
           commits=[C(20, "Shipping rates: flat EU, free from 60 euro", "backend/app/shipping.py", "backend/app/routers/checkout.py", "backend/tests/test_shipping.py")])
    t = D(16, 15, 5)
    c.turn(t, "{tk:order-confirm-page}. It has to handle the webhook being late.",
           "The page reads the order by payment intent id. If the webhook has not landed yet it shows 'Payment received, preparing your order' "
           "and polls every 2 s for up to 30 s. Reloading never charges again — the page only reads.", minutes=46,
           commits=[C(30, "Order confirmation page that waits for the webhook", "frontend/app/checkout/success/page.tsx", "backend/app/routers/orders.py")])
    t = D(17, 9, 50)
    c.turn(t, "Guest checkout timed on my phone: 52 seconds from cart to confirmation. #done {tk:guest-checkout}",
           "{tk:guest-checkout} is done. 52 s is under the 60 s in the vision; the slowest step was typing the address.", minutes=2)
    w.interpret("vision", K["c7"], K["vision_60s"][1], D(17, 10, 0),
                "Target: a guest goes from 'Checkout' to the confirmation page in under 60 seconds on a mid-range Android phone over 4G, "
                "typing the address by hand.\n\nFirst measurement ({dsh:17}, staging): 52 s. The address step takes 31 s of it. "
                "Autocomplete ({tk:address-autocomplete}) is the only lever left and is parked.",
                note="first measurement", agent_id=c.agent_id)

    # ------------------------------------------------------------------
    # C11 · 18 Sep · the confirmation email (OpenCode)
    # ------------------------------------------------------------------
    c = Chat(sim, P, "4e6c1b9f-9a27-4e3d-b058-1f7c6d2a8e93", tool="opencode", title="confirmation email", repo=repo,
             headline="The confirmation email: sent once, from the webhook")
    K["c11"] = c
    t = D(18, 9, 35)
    c.turn(t, "{tk:confirm-email}. Sent from the webhook handler after the order exists. Plain layout.",
           "Using the transactional provider's API with a plain HTML template: order number, lines, shipping address, what happens next. "
           "The send is keyed on the order id so a replayed webhook does not send twice.", minutes=7)
    t = D(18, 9, 50)
    c.turn(t, "Go.",
           "`emails.py` renders `order_confirmation.html` and sends it after the order transaction commits. `email_sent_at` on the order guards the resend. "
           "Preview at `/api/dev/emails/order-confirmation?order=SF-10003` on staging only.", minutes=64,
           commits=[C(30, "Order confirmation email, sent once per order", "backend/app/emails.py", "backend/app/templates/order_confirmation.html", "mig:orders email sent at"),
                    C(55, "Email preview route on staging only", "backend/app/routers/dev.py", "backend/tests/test_emails.py")])
    w.task("two-formatters", D(18, 15, 20), P, "Two places format money: lib/money.ts and emails.py", status="agent",
           lane="content", tags="ag_debt", agent=c.agent_id,
           desc="The email renders prices with its own helper. They agree today; a currency with three decimals would split them.")
    t = D(18, 15, 10)
    c.turn(t, "Prices in the email say 29.0 € for one line. Fix it.",
           "The template used Python's float formatting. Now it uses `format_money(cents, currency, locale)` — same rules as the frontend: `€29.00`. "
           "Put a debt card on the board: two formatters exist now. Screenshot on the task.", minutes=16,
           commits=[C(9, "Format money in emails like the storefront", "backend/app/emails.py", "backend/app/money.py")])
    w.evidence("confirm-email", D(18, 15, 30), c.agent_id, [
        {"kind": "image", "title": "Confirmation email as rendered in the preview", "mock": "form"},
        {"kind": "text", "title": "Sent once", "body": "Replayed `payment_intent.succeeded` for SF-10004 three times: one email, `email_sent_at` set once."},
    ])
    t = D(18, 15, 40)
    c.turn(t, "#done", "{tk:confirm-email} is done.", minutes=1)

    # ------------------------------------------------------------------
    # C12 · 21–22 Sep · production and the first real payment
    # ------------------------------------------------------------------
    c = Chat(sim, P, "d58f2a61-3e0b-4c7a-8f95-6b1d2e9c4a70", title="production", repo=repo,
             headline="shopfront.dev is live and has taken its first real payment")
    K["c12"] = c
    t = D(21, 10, 5)
    c.turn(t, "{tk:prod-deploy}. Same compose file as staging. Secrets from the host. And a rollback that we have actually run.",
           "Plan: `infra/docker-compose.prod.yml` overrides only env and volumes; secrets from `/etc/shopfront/env` (root-only); "
           "`deploy.sh` tags the running images before pulling, `rollback.sh` restarts the tagged ones and runs no migration down. "
           "I'll run the rollback on staging first.", minutes=8)
    t = D(21, 10, 20)
    c.turn(t, "Go.",
           "Production is up at https://shopfront.dev. Rollback tested on staging (42 s) and once on production before any traffic (38 s). "
           "Webhook endpoint registered in Stripe live mode with its own secret. Health: `{\"ok\": true, \"env\": \"prod\"}`.",
           minutes=110, commits=[C(35, "Production compose overrides and host secrets", "=infra/docker-compose.prod.yml::services:\n  api:\n    env_file: /etc/shopfront/env\n    restart: always\n  web:\n    restart: always\n  db:\n    volumes: [\"pgdata:/var/lib/postgresql/data\"]\nvolumes:\n  pgdata: {}\n", "infra/deploy.sh"),
                                 C(80, "Rollback script: restart the previous images", "=infra/rollback.sh::#!/bin/sh\nset -eu\ndocker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml down\ndocker tag shopfront-api:previous shopfront-api:latest\ndocker tag shopfront-web:previous shopfront-web:latest\ndocker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d\n", "docs/runbook.md")],
           helpers=[(20, 45), (70, 25)])
    t = D(22, 9, 5)
    c.turn(t, "I'll pay with my own card for the mug now — {tk:first-payment}. Watch the logs. #important",
           "Watching. Intent `pi_…Qz` created for €22.90 (mug €18.00 + shipping €4.90).", minutes=4)
    t = D(22, 9, 12)
    c.turn(t, "Paid.",
           "Seen, in order: `payment_intent.succeeded` verified (0.4 s after payment), order **SF-10001** created, confirmation email sent, "
           "the confirmation page showed the order on first load. Nothing retried.", minutes=5)
    t = D(22, 9, 30)
    c.turn(t, "Now refund it from the Stripe dashboard and check we notice.",
           "`charge.refunded` arrived and was logged — and ignored: we have no refund handling yet, the order still says paid. "
           "That is the gap {tk:refunds} will close. Everything else in the five checks passed.", minutes=9)
    t = D(22, 16, 25)
    c.turn(t, "Five of five, with the refund caveat noted. #done {tk:first-payment} #important-task",
           "{tk:first-payment} is done. The paragraph for the launch post is in the chat above; a note on the task is the operator's to write.", minutes=4)
    w.note("first-payment", D(22, 16, 28), "article",
           "On {dm:22} shopfront took its first real payment: a €22.90 mug, paid with a real card. The order existed 0.4 seconds after the payment, "
           "the email followed, and a refund from the dashboard reached us — and showed us the one thing we had not built yet.",
           template="moment")
    t = D(22, 16, 40)
    c.turn(t, "#scan", "Scan written for the Checkout v1 sprint: the checkout, webhooks, orders, email and production. File entry, architecture form and the page's second version are in.",
           minutes=18, skills=["make-a-scan", "keep-the-architecture-page"])
    K["scan_s2_chat"] = c

    # ------------------------------------------------------------------
    # C13 · 22 Sep · Stripe Tax, and a skill from the webhook work
    # ------------------------------------------------------------------
    c = Chat(sim, P, "19c4e7b3-8d5f-4a12-b6c0-3e7a9f1d5b28", title="stripe tax", repo=repo,
             headline="EU VAT through Stripe Tax on VAT-inclusive prices")
    K["c13"] = c
    t = D(22, 10, 10)
    c.turn(t, "{tk:stripe-tax}. Our prices include VAT. Stripe Tax should split it per country for the invoice, not add it on top.",
           "Right — `tax_behavior: inclusive` on every price, customer address from the checkout form passed as `shipping`, and the "
           "calculation attached to the intent. The amount the customer pays does not change; the invoice shows the VAT line per country.", minutes=9)
    t = D(22, 10, 25)
    c.turn(t, "Go. Report when it's done — the card moves itself.",
           "Implemented and reported on the task:\n- prices created with `tax_behavior=inclusive`\n- a tax calculation per intent update, stored on the order\n"
           "- the invoice PDF shows 'incl. 19 % VAT' for DE, 21 % for NL, 20 % for FR\n\n`pytest -q`: 58 passed.", minutes=85,
           commits=[C(40, "Stripe Tax on VAT-inclusive prices", "backend/app/tax.py", "backend/app/routers/checkout.py", "mig:orders tax amount"),
                    C(75, "Tax tests for DE, NL and FR addresses", "backend/tests/test_tax.py")],
           helpers=[(30, 35)])
    w.report("stripe-tax", D(22, 11, 52), c.agent_id, "VAT split per country on VAT-inclusive prices; invoices show the rate; 58 tests pass.")
    w.evidence("stripe-tax", D(22, 11, 55), c.agent_id, [
        {"kind": "text", "title": "Three countries, one price",
         "body": "| country | paid | VAT | rate |\n|---|---|---|---|\n| DE | €29.00 | €4.63 | 19 % |\n| NL | €29.00 | €5.03 | 21 % |\n| FR | €29.00 | €4.83 | 20 % |\n\nSame amount charged; only the split differs."},
    ])
    t = D(22, 14, 0)
    c.turn(t, "#skill(stripe-webhook-replay) How we replay Stripe webhooks against staging or local: stripe CLI, the event ids from the dashboard, "
              "the expected no-op on a second replay, and where to look when the signature fails.",
           "Kept as a skill and drafted SKILL.md from what we did on the 16th: list failed events, `stripe events resend` to the right endpoint, "
           "check `stripe_events` for the id, and the raw-body check when signatures fail.", minutes=12)
    K["skill_replay"] = (c, c.last_n)
    t = D(22, 14, 25)
    c.turn(t, "#rule No new dependency without a line in the decision log: what it is for and what we considered instead.",
           "Kept. Checked this month's additions against the log: stripe, @stripe/react-stripe-js and the tax client are covered by the checkout "
           "and tax decisions; nothing else was added.", minutes=4)
    K["rule_deps"] = (c, c.last_n)
