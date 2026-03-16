# Getting Started

## What IRIS Runs

IRIS currently ships as one repository with:

- a FastAPI backend
- PostgreSQL / TimescaleDB storage
- Redis Streams and TaskIQ workers
- a Vue 3 frontend

The backend owns HTTP, scheduler wiring, stream consumers, and worker process startup.

## Quick Start With Docker

Default full-stack launch:

```bash
docker compose up --build
```

Dedicated backend-only modes:

Embedded backend:

```bash
docker compose -f docker-compose.backend-embedded.yml up --build backend
```

External PostgreSQL / Redis:

```bash
DATABASE_URL=postgresql+psycopg://iris:iris@db.example.internal:5432/iris \
REDIS_URL=redis://redis.example.internal:6379/0 \
docker compose -f docker-compose.backend-external.yml up --build backend
```

Development mode with bind mounts and automatic container restart on file changes:

```bash
docker compose -f docker-compose.backend-dev.yml up --build --watch backend
```

Default local endpoints:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000` in the full-stack `docker-compose.yml`
- Postgres: `localhost:55432`
- Redis: `localhost:56379`

Embedded and dev modes start PostgreSQL 17 + TimescaleDB and Redis inside the backend container unless `DATABASE_URL` and/or `REDIS_URL` are explicitly provided.

## Host-Side Backend Development

1. Prepare the backend environment:

```bash
cd backend
cp .env.example .env
uv sync --group dev
```

2. Ensure `DATABASE_URL` and `REDIS_URL` in `.env` point to reachable services.

Notes:

- `.env.example` defaults to `localhost:55432` and `localhost:56379`, which match the ports exposed by the embedded/dev backend compose files.
- TimescaleDB support is required. Plain PostgreSQL is not sufficient for the full migration set.
- Market-data API key setup is documented in [Market Data API Keys](market-data-api-keys.md).

3. Run prestart:

```bash
uv run python -m iris.core.bootstrap.prestart
```

4. Run backend tests:

```bash
uv run pytest
```

5. Run the backend locally:

```bash
uv run python -m iris.main
```

When running the backend outside Docker, migrations are not applied from the app lifespan. You must run `iris.core.bootstrap.prestart` or apply Alembic migrations yourself before starting `iris.main`.

## Frontend Development

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

## Useful Repository Commands

From the repository root:

```bash
make openapi-check
make api-matrix-check
make api-capabilities-check
make lint backend
make lint frontend
```

To build the documentation site locally:

```bash
uvx --with mkdocs-material mkdocs build
```

## Configuration Notes

- `backend/.env.example` is configured for host-side development against the published embedded/dev Docker ports.
- The default local setup does not require production market-data credentials to boot the product.
- Official key acquisition links for credentialed providers live in [Market Data API Keys](market-data-api-keys.md).
- The repository includes mode/profile-aware HTTP exposure, so not every route is available in every runtime profile.
