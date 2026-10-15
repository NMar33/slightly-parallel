"""Plausible code for the demo repositories.

A commit in the demo touches real files with real-looking changes: a new
function named after what the commit did, a test for it, a migration, a CI
step. Nobody runs this code; it has to read as a small, ordinary codebase
in a diff and in a file listing.
"""

from __future__ import annotations

import re

_STOP = {"a", "an", "the", "to", "of", "for", "and", "on", "in", "with", "from", "by", "at",
         "is", "as", "into", "when", "so", "it", "its", "no", "not", "be", "only", "per", "all"}


def words(subject: str) -> list[str]:
    ws = re.findall(r"[A-Za-z][A-Za-z0-9]*", subject.lower())
    return [w for w in ws if w not in _STOP][:4] or ["change"]


def snake(subject: str) -> str:
    return "_".join(words(subject))


def camel(subject: str) -> str:
    ws = words(subject)
    return ws[0] + "".join(w.capitalize() for w in ws[1:])


def pascal(subject: str) -> str:
    return "".join(w.capitalize() for w in words(subject))


def py_function(subject: str, n: int) -> str:
    name = snake(subject)
    variants = [
        f'''

def {name}(session: Session, payload: dict) -> dict:
    """{subject}."""
    record = session.get(Model, payload["id"]) if "id" in payload else None
    if record is None:
        raise NotFound("{name.replace('_', ' ')}: no such record")
    for key, value in payload.items():
        setattr(record, key, value)
    session.flush()
    return record.to_dict()
''',
        f'''

async def {name}(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """{subject}."""
    body = await request.json()
    result = await db.execute(select(Order).where(Order.id == body.get("order_id")))
    order = result.scalar_one_or_none()
    if order is None:
        return JSONResponse({{"detail": "order not found"}}, status_code=404)
    log.info("{name}", extra={{"order_id": order.id}})
    return JSONResponse(order.as_public())
''',
        f'''

def {name}(items: list[LineItem], *, currency: str = "EUR") -> int:
    """{subject}. Amounts are integer minor units."""
    total = 0
    for item in items:
        if item.quantity <= 0:
            raise ValueError(f"line {{item.sku}}: quantity must be positive")
        total += item.unit_amount * item.quantity
    return total
''',
        f'''

class {pascal(subject)}Error(Exception):
    """Raised when {subject[0].lower() + subject[1:]} cannot complete."""


def {name}(key: str, ttl_seconds: int = 900) -> bool:
    """{subject}."""
    seen = redis.set(f"idem:{{key}}", "1", nx=True, ex=ttl_seconds)
    return bool(seen)
''',
    ]
    return variants[n % len(variants)]


def py_test(subject: str, n: int) -> str:
    name = snake(subject)
    variants = [
        f'''

def test_{name}(client, seeded_catalog):
    resp = client.post("/api/{name.split('_')[0]}", json={{"sku": "TEE-BLK-M", "quantity": 2}})
    assert resp.status_code == 200
    assert resp.json()["total"] == 5800
''',
        f'''

@pytest.mark.parametrize("quantity", [0, -1])
def test_{name}_rejects_bad_quantity(client, quantity):
    resp = client.post("/api/cart/items", json={{"sku": "MUG-WHT", "quantity": quantity}})
    assert resp.status_code == 422
''',
        f'''

def test_{name}_is_idempotent(client, stripe_event):
    first = client.post("/webhooks/stripe", data=stripe_event.body, headers=stripe_event.headers)
    second = client.post("/webhooks/stripe", data=stripe_event.body, headers=stripe_event.headers)
    assert first.status_code == second.status_code == 200
    assert Order.count_for(stripe_event.payment_intent) == 1
''',
    ]
    return variants[n % len(variants)]


def ts_code(subject: str, n: int, path: str) -> str:
    if path.endswith(".tsx"):
        comp = pascal(subject)
        variants = [
            f'''

export function {comp}({{ product }}: {{ product: Product }}) {{
  const price = formatMoney(product.price, product.currency)
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{{product.title}}</h3>
      <span className="text-sm text-muted">{{price}}</span>
    </section>
  )
}}
''',
            f'''

export function {comp}() {{
  const {{ items, total, isLoading }} = useCart()
  if (isLoading) return <Skeleton lines={{3}} />
  if (!items.length) return <EmptyState title="Your cart is empty" />
  return (
    <ul className="divide-y">
      {{items.map((it) => <CartLine key={{it.sku}} item={{it}} />)}}
      <li className="flex justify-between pt-3 font-medium">Total <span>{{formatMoney(total)}}</span></li>
    </ul>
  )
}}
''',
        ]
        return variants[n % len(variants)]
    fn = camel(subject)
    variants = [
        f'''

export async function {fn}(input: {{ sku: string; quantity: number }}): Promise<Cart> {{
  const res = await api.post('/api/cart/items', input)
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return (await res.json()) as Cart
}}
''',
        f'''

export function {fn}(amount: number, currency = 'EUR', locale = 'en-IE'): string {{
  // amounts arrive in minor units
  return new Intl.NumberFormat(locale, {{ style: 'currency', currency }}).format(amount / 100)
}}
''',
    ]
    return variants[n % len(variants)]


def other_code(subject: str, n: int, path: str) -> str:
    if path.endswith((".yml", ".yaml")):
        return f"""
      - name: {subject}
        run: make {snake(subject).replace('_', '-')}
"""
    if path.endswith(".sql"):
        return f"""
-- {subject}
ALTER TABLE orders ADD COLUMN IF NOT EXISTS {snake(subject)[:40]} text;
"""
    if path.endswith(".md"):
        return f"""
## {subject}

{subject}. See the decision log for why, and the tests for what it guarantees.
"""
    if path.endswith(".css"):
        return f"""
/* {subject} */
.{snake(subject).replace('_', '-')} {{ display: grid; gap: 0.75rem; }}
"""
    if path.endswith((".toml", ".cfg", ".ini", ".env.example")):
        return f"# {subject}\n{snake(subject).upper()[:30]}=\n"
    if path.endswith(".json"):
        return ""
    return f"# {subject}\n"


def migration(subject: str, rev: str, down: str) -> str:
    name = snake(subject)
    return f'''"""{subject}

Revision ID: {rev}
Revises: {down}
"""
from alembic import op
import sqlalchemy as sa

revision = "{rev}"
down_revision = "{down}"


def upgrade() -> None:
    op.add_column("orders", sa.Column("{name[:40]}", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "{name[:40]}")
'''


def snippet(path: str, subject: str, n: int) -> str:
    if path.endswith(".py"):
        return py_test(subject, n) if "/tests/" in f"/{path}" or path.split("/")[-1].startswith("test_") else py_function(subject, n)
    if path.endswith((".ts", ".tsx")):
        return ts_code(subject, n, path)
    return other_code(subject, n, path)
