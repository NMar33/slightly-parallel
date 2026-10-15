"""The vocabulary of the architecture ledger: the one table the whole
contract hangs on.

A group is a question the ledger answers; a type is a kind of thing that
answers it; an op is what happened to one. The ledger router checks a form
against this, `/api/schema` publishes it to agents, and task evidence reads
it so "what landed" means the same on a card as in a scan. It is a table,
not a router, so nothing has to import a router to read it.
"""

from __future__ import annotations


GROUPS: dict[str, tuple[str, ...]] = {
    "does": ("feature", "fix"),
    "owes": ("debt", "action-needed"),
    "runs": ("service", "runtime", "config", "deploy"),
    "stores": ("database", "files", "cache", "queue"),
    "talks": ("endpoint", "integration", "hook", "command"),
    "built with": ("framework", "library", "module"),
    "faces": ("surface", "auth", "job"),
    "holds": ("rule", "tests"),
}

TYPE_GROUP: dict[str, str] = {t: g for g, types in GROUPS.items() for t in types}

OPS = ("add", "change", "remove")
