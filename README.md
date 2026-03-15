# IRIS

IRIS is an event-driven market intelligence platform for market data ingestion, analytical signal generation, routing governance, portfolio automation surfaces, and optional AI-assisted reasoning.

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
backend/src/
  core/        # settings, bootstrap, DB, HTTP primitives
  apps/        # domain apps
  runtime/     # streams, orchestration, scheduler, workers
frontend/
  src/         # Vue 3 application
docs/
  architecture/
  ha/
  iso/
  product/
  reviews/
  _generated/
```

## Quick Start

### Docker Compose

```bash
docker compose up --build
```

Services:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- PostgreSQL / TimescaleDB: `localhost:55432`
- Redis: `localhost:56379`

### Host-Side Backend With `uv`

1. Start infrastructure only:

```bash
docker compose up -d db redis
```

2. Create the backend environment:

```bash
cd backend
cp .env.example .env
uv sync --group dev
```

3. Apply migrations and run tests:

```bash
uv run alembic upgrade head
uv run pytest
```

4. Run the backend locally:

```bash
uv run python -m src.main
```

### Frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

## Documentation

Primary documentation entrypoints:

- Documentation site: `https://mesteriis.github.io/iris/`
- Docs landing page: [`docs/index.md`](docs/index.md)
- Architecture overview: [`docs/architecture.md`](docs/architecture.md)
- ADR index: [`docs/architecture/adr/index.md`](docs/architecture/adr/index.md)
- Home Assistant docs: [`docs/ha/index.md`](docs/ha/index.md)
- Generated HTTP governance artifacts:
  - [`docs/_generated/http-availability-matrix.md`](docs/_generated/http-availability-matrix.md)
  - [`docs/_generated/http-capability-catalog.md`](docs/_generated/http-capability-catalog.md)

Documentation classes:

- `docs/architecture/`: accepted architecture and governance documents
- `docs/iso/`: execution plans, audits, refactor tracking, implementation working docs
- `docs/product/`: product framing and review checklists
- `docs/ha/`: Home Assistant integration and protocol documents
- `docs/_generated/`: generated snapshots exported from the live codebase
- `docs/reviews/`: historical review snapshots that may lag the current implementation

When documents disagree, prefer this order:

1. Generated artifacts in `docs/_generated/`
2. Accepted ADRs and governance docs in `docs/architecture/`
3. Current execution and audit docs in `docs/iso/`
4. Historical reviews in `docs/reviews/`

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
