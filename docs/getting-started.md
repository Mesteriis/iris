# Getting Started

## What IRIS Runs

IRIS currently ships as one repository with:

- a FastAPI backend
- PostgreSQL / TimescaleDB storage
- Redis Streams and TaskIQ workers
- a Vue 3 frontend

The backend owns HTTP, scheduler wiring, stream consumers, and worker process startup.

## Quick Start With Docker

```bash
docker compose up --build
```

Default local endpoints:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- Postgres: `localhost:55432`
- Redis: `localhost:56379`

## Host-Side Backend Development

1. Start infra only:

```bash
docker compose up -d db redis
```

2. Prepare the backend environment:

```bash
cd backend
cp .env.example .env
uv sync --group dev
```

3. Apply migrations:

```bash
uv run alembic upgrade head
```

4. Run backend tests:

```bash
uv run pytest
```

5. Run the backend locally:

```bash
uv run python -m src.main
```

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

- `backend/.env.example` is configured for host-side development against the published Docker ports.
- The default local setup does not require production market-data credentials to boot the product.
- The repository includes mode/profile-aware HTTP exposure, so not every route is available in every runtime profile.
