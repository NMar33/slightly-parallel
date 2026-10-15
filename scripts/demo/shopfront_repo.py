"""The shopfront repository as it starts on 1 September: a skeleton."""

SKELETON: dict[str, str] = {
    "README.md": """# shopfront

A small online store: a Next.js storefront, a FastAPI service, Postgres, and
Stripe for payments.

```
frontend/   Next.js 14 app router storefront
backend/    FastAPI service: catalog, cart, checkout, webhooks
infra/      docker compose, Dockerfiles, Caddy
docs/       runbook and decisions that outgrew the log
```

## Run it

    make up        # postgres + api + web on :3000
    make test      # backend tests, then frontend type-check

Money is stored and passed as integer minor units (cents). Never floats.
""",
    ".gitignore": "node_modules/\n.next/\n__pycache__/\n.venv/\n.env\n*.pyc\n",
    "Makefile": """up:
\tdocker compose -f infra/docker-compose.yml up --build

test:
\tcd backend && pytest -q
\tcd frontend && npm run typecheck

lint:
\tcd backend && ruff check .
\tcd frontend && npm run lint
""",
    "AGENTS.md": """# Working on shopfront

- Backend: `backend/` (FastAPI, SQLAlchemy 2, alembic). Tests: `cd backend && pytest -q`.
- Frontend: `frontend/` (Next.js 14, app router, Tailwind). Check: `npm run typecheck`.
- Money is integer minor units everywhere.
- Every Stripe call carries an idempotency key.
""",
    "CLAUDE.md": "@AGENTS.md\n",
    "frontend/package.json": """{
  "name": "shopfront-web",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.13",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "@stripe/react-stripe-js": "2.8.0",
    "@stripe/stripe-js": "4.5.0"
  },
  "devDependencies": {
    "typescript": "5.6.2",
    "tailwindcss": "3.4.13",
    "@types/react": "18.3.9"
  }
}
""",
    "frontend/next.config.mjs": """/** @type {import('next').NextConfig} */
const nextConfig = {
  images: { remotePatterns: [{ protocol: 'https', hostname: 'img.shopfront.dev' }] },
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.API_URL}/api/:path*` }]
  },
}
export default nextConfig
""",
    "frontend/tsconfig.json": """{
  "compilerOptions": { "target": "ES2022", "strict": true, "jsx": "preserve", "module": "esnext",
    "moduleResolution": "bundler", "paths": { "@/*": ["./*"] }, "noEmit": true },
  "include": ["**/*.ts", "**/*.tsx"]
}
""",
    "frontend/app/layout.tsx": """import './globals.css'
import type { ReactNode } from 'react'

export const metadata = { title: 'Shopfront', description: 'Everyday goods, shipped across the EU.' }

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-neutral-900">{children}</body>
    </html>
  )
}
""",
    "frontend/app/page.tsx": """import { getProducts } from '@/lib/api'

export default async function Home() {
  const products = await getProducts()
  return <main className="mx-auto max-w-6xl p-6">{products.length} products</main>
}
""",
    "frontend/app/globals.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
    "frontend/lib/api.ts": """const BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export const api = {
  get: (path: string) => fetch(`${BASE}${path}`, { credentials: 'include' }),
  post: (path: string, body: unknown) =>
    fetch(`${BASE}${path}`, { method: 'POST', credentials: 'include',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
}

export async function getProducts(): Promise<Product[]> {
  const res = await api.get('/api/products')
  if (!res.ok) throw new ApiError(res.status, 'products')
  return res.json()
}
""",
    "frontend/lib/types.ts": """export type Money = number // minor units

export interface Product {
  id: string
  slug: string
  title: string
  price: Money
  currency: string
  image: string
}
""",
    "backend/pyproject.toml": """[project]
name = "shopfront-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi==0.115.0",
  "uvicorn[standard]==0.30.6",
  "sqlalchemy==2.0.35",
  "alembic==1.13.3",
  "psycopg[binary]==3.2.3",
  "pydantic-settings==2.5.2",
  "stripe==10.12.0",
]

[project.optional-dependencies]
dev = ["pytest==8.3.3", "httpx==0.27.2", "ruff==0.6.8"]
""",
    "backend/app/__init__.py": "",
    "backend/app/main.py": """from fastapi import FastAPI

from .settings import settings

app = FastAPI(title="shopfront-api")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "env": settings.env}
""",
    "backend/app/settings.py": """from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "dev"
    database_url: str = "postgresql+psycopg://shop:shop@localhost:5432/shop"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    cart_cookie_secret: str = "change-me"


settings = Settings()
""",
    "backend/app/db.py": """from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .settings import settings

engine = create_engine(settings.database_url, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
""",
    "backend/app/models.py": """from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(60), index=True)
""",
    "backend/tests/__init__.py": "",
    "backend/tests/conftest.py": """import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
""",
    "infra/docker-compose.yml": """services:
  db:
    image: postgres:16
    environment: { POSTGRES_USER: shop, POSTGRES_PASSWORD: shop, POSTGRES_DB: shop }
    ports: ["5432:5432"]
  api:
    build: { context: ../backend, dockerfile: ../infra/Dockerfile.api }
    environment: { DATABASE_URL: "postgresql+psycopg://shop:shop@db:5432/shop" }
    depends_on: [db]
    ports: ["8000:8000"]
  web:
    build: { context: ../frontend, dockerfile: ../infra/Dockerfile.web }
    environment: { API_URL: "http://api:8000" }
    ports: ["3000:3000"]
""",
    "infra/Dockerfile.api": """FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "infra/Dockerfile.web": """FROM node:20-alpine
WORKDIR /web
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
""",
}
