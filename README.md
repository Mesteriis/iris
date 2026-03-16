# IRIS

IRIS is an event-driven market intelligence platform for market data ingestion, analytical signal generation, routing governance, portfolio automation surfaces, and optional AI-assisted reasoning.

> Disclaimer
> IRIS provides informational and operational tooling for self-directed investors. It is not a broker, investment adviser, execution guarantee, or promise of profitability. Users remain solely responsible for any investment, trading, automation, and risk-management decisions.

The repository is organized as a single product codebase:

- `backend/`: FastAPI, SQLAlchemy, Alembic, Redis Streams, TaskIQ workers
- `frontend/`: Vue 3 dashboard
- `docs/`: architecture, governance, audits, product notes, Home Assistant docs, generated API artifacts

## Current Scope

IRIS currently includes these backend domains:

- `market_data`
- `indicators`
- `patterns`
- `signals`
- `predictions`
- `cross_market`
- `portfolio`
- `anomalies`
- `news`
- `market_structure`
- `control_plane`
- `hypothesis_engine`
- `system`

The runtime model is hybrid:

- market-data ingestion remains polling-driven
- internal analytics, orchestration, and downstream reactions run through Redis Streams and TaskIQ workers
- the HTTP surface is mode/profile-aware and governed through committed snapshots plus generated capability metadata

## Repository Layout

```text
backend/
  iris/        # runtime package: core, apps, api, runtime, main.py
  src/         # Alembic migrations
frontend/
  src/         # Vue 3 application
docs/
  architecture/
  delivery/
  home-assistant/
  product/
  _generated/
```

## Quick Start

### Docker Compose

Default full-stack launch:

```bash
docker compose up --build
```

The repository now also ships dedicated backend-only Compose modes.

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

Development mode with bind mounts and container restart on file changes:

```bash
docker compose -f docker-compose.backend-dev.yml up --build --watch backend
```

In embedded and dev modes the `backend` container is self-contained:

- it starts embedded PostgreSQL 17 with TimescaleDB
- it starts embedded Redis
- it runs `/app/entrypoint.sh`, which waits for DB/Redis, applies Alembic migrations through `iris.core.bootstrap.prestart`, and aborts startup if prestart fails
- only after prestart succeeds does it launch `python -m iris.main`
- HTTP runtime, TaskIQ workers, scheduler, PostgreSQL, and Redis all run in the same backend container

In dev mode:

- `backend/iris`, `backend/src` (migrations), `backend/tests`, and the main backend config files are mounted from the host
- source/config changes restart the whole backend container, so API, scheduler, and workers restart together
- dependency/image changes such as `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env`, or `entrypoint.sh` trigger a container rebuild

Default local ports:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000` in the full-stack `docker-compose.yml`
- PostgreSQL / TimescaleDB: `localhost:55432`
- Redis: `localhost:56379`

Persistent backend state is stored in Docker volumes:

- `backend_runtime_data` in the default full-stack `docker-compose.yml`
- `backend_runtime_data_embedded` / `backend_runtime_data_external` / `backend_runtime_data_dev` in the dedicated backend-only compose files

### External PostgreSQL / Redis Override

The backend can switch per dependency from embedded services to external ones.

- If `DATABASE_URL` is set, the container uses external PostgreSQL / TimescaleDB and does not start the embedded database.
- If `REDIS_URL` is set, the container uses external Redis and does not start the embedded Redis.
- If either variable is unset, the matching embedded service is started inside the backend container.

The dedicated external-mode compose file enforces both variables. The embedded and dev compose files allow mixed mode per dependency.

Example:

```bash
DATABASE_URL=postgresql+psycopg://iris:iris@db.example.internal:5432/iris \
REDIS_URL=redis://redis.example.internal:6379/0 \
docker compose -f docker-compose.backend-external.yml up --build backend
```

### Host-Side Backend With `uv`

1. Create the backend environment:

```bash
cd backend
cp .env.example .env
uv sync --group dev
```

2. Ensure `DATABASE_URL` and `REDIS_URL` in `.env` point to reachable services.

Notes:

- `.env.example` defaults to `localhost:55432` and `localhost:56379`, which match the ports exposed by the Docker Compose backend container.
- TimescaleDB support is required. Plain PostgreSQL is not sufficient for the full migration set.
- Market-data provider key acquisition is documented in [`docs/market-data-api-keys.md`](docs/market-data-api-keys.md).

3. Run prestart and tests:

```bash
uv run python -m iris.core.bootstrap.prestart
uv run pytest
```

4. Run the backend locally:

```bash
uv run python -m iris.main
```

When running the backend outside Docker, migrations are not applied from the app lifespan. You must run `iris.core.bootstrap.prestart` or apply Alembic migrations yourself before starting `iris.main`.

### Frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

## Documentation

Primary documentation entrypoints:

- Documentation site: `https://mesteriis.github.io/iris/`
- Docs landing page: [`docs/index.md`](docs/index.md)
- Architecture overview: [`docs/architecture/index.md`](docs/architecture/index.md)
- ADR index: [`docs/architecture/adr/index.md`](docs/architecture/adr/index.md)
- Market-data key setup: [`docs/market-data-api-keys.md`](docs/market-data-api-keys.md)
- Home Assistant docs: [`docs/home-assistant/index.md`](docs/home-assistant/index.md)
- Generated HTTP governance artifacts:
  - [`docs/_generated/http-availability-matrix.md`](docs/_generated/http-availability-matrix.md)
  - [`docs/_generated/http-capability-catalog.md`](docs/_generated/http-capability-catalog.md)

Documentation classes:

- `docs/architecture/`: accepted architecture and governance documents
- `docs/delivery/`: execution plans, audits, refactor tracking, implementation working docs
- `docs/product/`: product framing and review checklists
- `docs/home-assistant/`: Home Assistant integration and protocol documents
- `docs/_generated/`: generated snapshots exported from the live codebase

When documents disagree, prefer this order:

1. Generated artifacts in `docs/_generated/`
2. Accepted ADRs and governance docs in `docs/architecture/`
3. Section-specific normative specs such as `docs/home-assistant/protocol-specification.md`
4. Current execution and audit docs in `docs/delivery/`

## Home Assistant Integration Repo

The Home Assistant custom integration is maintained as a separate repository rooted at `ha/integration/` in this workspace and mirrored to:

- `git@github.com:Mesteriis/ha-integration-iris.git`

Compatibility metadata lives in [`ha/compatibility.yaml`](ha/compatibility.yaml). The current contract is:

- protocol version `1`
- backend `2026.03.15+`
- integration `0.1.0`
- pinned integration commit `31f5626a18c62c5264fab0c74efafe28c79ae173`

Submodule workflow:

```bash
git clone --recurse-submodules git@github.com:Mesteriis/iris.git
git submodule update --init --recursive
git submodule update --remote ha/integration
```

Release/update workflow:

```bash
python scripts/update_ha_integration_submodule.py --ref main
python scripts/check_ha_integration_contract.py
```

Local integration workflow:

```bash
cd ha/integration
uv sync --group dev
uv run ruff check custom_components tests
uv run pytest tests -q
```

## Governance

The repository already enforces several architecture guardrails in CI:

- committed OpenAPI snapshots
- HTTP availability matrix drift checks
- HTTP capability catalog drift checks
- service-layer scorecard artifact export
- architecture and policy test suites

Relevant docs:

- [`docs/architecture/service-layer-runtime-policies.md`](docs/architecture/service-layer-runtime-policies.md)
- [`docs/architecture/service-layer-performance-budgets.md`](docs/architecture/service-layer-performance-budgets.md)
- [`docs/architecture/complexity-guardrails.md`](docs/architecture/complexity-guardrails.md)
- [`docs/architecture/principal-engineering-checklist.md`](docs/architecture/principal-engineering-checklist.md)

## Open Source

Repository policies:

- License: [`LICENSE`](LICENSE)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## Notes

- The default market-data source remains deterministic enough to let the product boot without external API keys.
- Some implementation plans and reviews remain bilingual. The documentation site groups them by purpose so historical working notes do not masquerade as current architecture contracts.
