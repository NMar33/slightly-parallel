"""shopfront: a press note from a finished task, and a storyboard document
with two versions (the agent's, then the operator's edit)."""

from __future__ import annotations

from engine import Chat, D

P = "shopfront"
OP = "operator"

NOTE = (
    "# shopfront takes its first real payment\n\n"
    "On {dm:22} shopfront.dev sold its first item to a real customer: a €22.90 mug, paid by card. "
    "The order was in the database 0.4 seconds after the payment, and the confirmation email went out a few seconds later.\n\n"
    "Checkout is one page: address, shipping and the card form together. Card details never reach shopfront's server; "
    "Stripe holds them. A refund made in the Stripe dashboard is recorded on the order.\n\n"
    "Next: refunds from shopfront's own admin, and the public beta on {dm:45}."
)

V1 = (
    "# Public beta: shopfront opens to the waitlist\n\n"
    "From {dm:45}, everyone on the waitlist can buy from shopfront.dev. The shop has sold to real customers since {dm:22}: "
    "208 payments so far, every one recorded as an order within a second.\n\n"
    "## What you can do\n\n"
    "- Browse 48 products and search them by name.\n"
    "- Pay on one page, by card, with 3-D Secure where your bank asks for it.\n"
    "- Get an email when the order is confirmed and when it ships.\n\n"
    "## What is not there yet\n\n"
    "- Accounts: you check out as a guest.\n"
    "- Shipping outside the EU.\n\n"
    "Questions go to hello@shopfront.dev."
)

V2 = (
    "# shopfront opens on {dm:45}\n\n"
    "Everyone on the waitlist can buy from shopfront.dev from {dm:45}. We have sold to real customers since {dm:22}, "
    "and every payment has become an order within a second.\n\n"
    "- 48 products, searchable by name.\n"
    "- One checkout page, by card. Prices include VAT and are shown in euros.\n"
    "- An email when the order is confirmed and when it ships.\n\n"
    "Guest checkout only for now, and shipping inside the EU. Write to hello@shopfront.dev."
)


def setup(sim, w, repo, K: dict) -> None:
    # A note from a finished task: the operator asks for it from the task
    # window (Story), and an agent writes it under that request.
    c = Chat(sim, P, "6c2d8e14-9a3b-4f07-b5e1-2d8c4a9f7e30", title="first payment note", repo=repo)
    K["c21"] = c
    box: dict = {}

    def ask() -> None:
        r = sim.post(f"/api/tasks/{sim.tasks['first-payment']}/story-requests",
                     {"type": "release", "focus": "the first real payment, for the waitlist email", "actor": OP})
        box["request"] = r["request"]["id"]

    sim.at(D(23, 10, 0), ask)

    def write() -> None:
        sim.post(f"/api/tasks/{sim.tasks['first-payment']}/story",
                 {"request_id": box["request"], "agent_id": c.agent_id, "body": NOTE}, agent=True)

    c.turn(D(23, 10, 2),
           "Here is the prompt from the task window: write the press note for {tk:first-payment}.",
           "The note is saved on the task, under your request: the first payment on {dm:22}, what checkout is, "
           "and what comes next. It names no customer.",
           minutes=5, actions=[(4, write)])

    # A storyboard document: the operator collects the material, an agent
    # writes the text with the MCP tool doc_version, the operator pastes an edit.
    d = Chat(sim, P, "9e4a7b21-3c8d-4f56-a0b9-8d2e6c1f4a73", title="beta announcement", repo=repo)
    K["c22"] = d

    def doc() -> None:
        r = sim.post("/api/docs", {"project": P, "kind": "post",
                                   "title": "Public beta: shopfront opens to the waitlist", "actor": OP})
        sim.ids["doc_beta"] = r["doc"]["id"]
        for text in ("Date: {dm:45}, everyone on the waitlist.",
                     "Numbers: 208 payments since {dm:22}; every payment an order within a second.",
                     "Not there yet: accounts, shipping outside the EU."):
            sim.post(f"/api/docs/{r['doc']['id']}/items", {"text": text, "actor": OP})

    sim.at(D(29, 15, 40), doc)

    def first() -> None:
        sim.post(f"/api/docs/{sim.ids['doc_beta']}/versions",
                 {"agent_id": d.agent_id, "body": V1, "note": "first draft from the pack"}, agent=True)

    d.turn(D(29, 16, 0),
           "This is the Storyboard pack for the beta announcement. Write the post and save it as a version.",
           "Version 1 is on the Storyboard: the date, what a customer can do, what is not there yet. "
           "The numbers are the ones in the pack.",
           minutes=8, actions=[(7, first)])

    def second() -> None:
        sim.post(f"/api/docs/{sim.ids['doc_beta']}/versions",
                 {"body": V2, "note": "shorter; prices with VAT, in euros", "actor": OP})

    sim.at(D(29, 17, 30), second)
