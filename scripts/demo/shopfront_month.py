"""The storefront month used by both the demo builder and the shipped example."""

from engine import D, Repo, Sim
from world import World

import shopfront_chats_a
import shopfront_chats_b
import shopfront_chats_c
import shopfront_lenses
import shopfront_desk
import shopfront_notes
import shopfront_standups
import shopfront_story
import shopfront_tasks
from shopfront_repo import SKELETON


def create_shopfront_repo(sim: Sim, code: str) -> Repo:
    repo = Repo(sim.repos_dir / code, email="operator@shopfront.dev")
    for rel, text in SKELETON.items():
        repo.write(rel, text)
    repo.commit("Initial skeleton: Next.js app, FastAPI service, compose", D(1, 8, 20))
    sim.repos[code] = repo
    return repo


def schedule_shopfront(sim: Sim, w: World, repo: Repo) -> dict:
    K: dict = {}
    shopfront_tasks.setup(sim, w)
    shopfront_chats_a.setup(sim, w, repo, K)
    shopfront_chats_b.setup(sim, w, repo, K)
    shopfront_chats_c.setup(sim, w, repo, K)
    shopfront_lenses.setup(sim, w, repo, K)
    shopfront_standups.setup(sim, w, K)
    shopfront_story.setup(sim, w, repo, K)
    shopfront_notes.setup(sim, w, repo, K)
    shopfront_desk.setup(sim, w, repo, K)
    return K


def schedule_links(sim: Sim, K: dict) -> None:
    """Why one chat sits next to another on the timeline."""
    for when, a, b, kind, note in [
        (D(16, 11, 40), "c9", "c10", "handoff", "the signature fix handed over from the webhook chat"),
        (D(22, 14, 45), "c12", "c13", "same-work", "Stripe Tax went live with the first payment"),
        (D(30, 9, 12), "c14", "c20", "branch", "partial refunds continue the refunds chat"),
        (D(28, 14, 35), "c15", "c18", "relates", "outbound events reuse the webhook queue"),
    ]:
        def link(a=a, b=b, kind=kind, note=note) -> None:
            sim.post("/api/agents/links", {"from": K[a].agent_id, "to": K[b].agent_id, "kind": kind,
                                           "note": note, "actor": "operator"})
        sim.at(when, link)
