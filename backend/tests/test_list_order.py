"""Every lens list sorts by columns its table has — or the list answers 500."""

from __future__ import annotations

import re

from backend.entities import ENTITIES
from backend.routers.lenses import _DEFAULT_ORDER, ORDER_BY


def test_every_list_orders_by_its_own_columns() -> None:
    for ent in ENTITIES.values():
        order = ORDER_BY.get(ent.name, _DEFAULT_ORDER)
        cols = set(re.findall(r"([a-z_]+)\s+(?:ASC|DESC)", order))
        missing = cols - set(ent.columns)
        assert not missing, f"{ent.name} sorts by {sorted(missing)}, which its table does not have"
