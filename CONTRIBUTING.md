# Contributing To IRIS

Thanks for contributing.

## Before You Start

- Read [`README.md`](README.md) for repository entrypoints.
- Read [`docs/architecture/index.md`](docs/architecture/index.md) and [`docs/architecture/adr/index.md`](docs/architecture/adr/index.md) before large architecture changes.
- For refactor work, check the active rollout and audit docs under `docs/delivery/`.

## Local Setup

### Backend

```bash
docker compose up -d db redis
cd backend
cp .env.example .env
uv sync --group dev
uv run alembic upgrade head
```

### Frontend

```bash
npm --prefix frontend install
```

## Common Commands

Run backend tests:

```bash
cd backend
uv run pytest
```

Run the backend locally:

```bash
make backend start
```

Run the frontend locally:

```bash
make frontend start
```

Run governed API checks:

```bash
make openapi-check
make api-matrix-check
make api-capabilities-check
```

Run documentation build:

```bash
uvx --with mkdocs-material mkdocs build
```

## Change Expectations

- Keep backend layering aligned with `runtime -> apps -> core`.
- Preserve the service/engine split where it already exists.
- Do not introduce new direct DB access from routes, tasks, or worker adapters when repositories/query services already own the boundary.
- Update docs when changing architecture, repo entrypoints, or governed HTTP contracts.
- Refresh generated API docs when changing governed HTTP surfaces.

## Pull Requests

- Keep PRs focused.
- Include tests or an explicit explanation when tests are not practical.
- Document user-visible or operator-visible behavior changes.
- Update architecture and rollout docs when the change affects accepted boundaries or active refactor campaigns.

## Discussions And Large Changes

Open an issue or design note before making large changes to runtime topology, persistence architecture, HTTP governance, or AI platform direction.
