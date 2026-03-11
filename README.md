# IRIS

IRIS is an MVP cryptocurrency monitoring service focused on two concepts only:

- coins
- price history

The repository includes:

- FastAPI backend with SQLAlchemy, Alembic, and embedded TaskIQ worker runtime
- Vue 3 dashboard with Pinia, Tailwind, Vite, and ECharts
- PostgreSQL via Docker Compose
- Home Assistant addon scaffold
- Home Assistant custom integration scaffold
- embedded watched asset seed and historical sync tasks

## Run

```bash
docker compose up --build
```

Services:

- Backend: http://localhost:8000
- Frontend: http://localhost:3000

## Notes

- TaskIQ workers run inside the backend service lifecycle. There is no separate worker container.
- The backend applies Alembic migrations during startup.
- On startup, a TaskIQ historical sync seeds watched assets into `coins` and backfills `price_history`.
- A periodic TaskIQ task incrementally appends new bars for enabled assets.
- The watched asset seed was embedded into backend code from the provided assignment data; runtime does not depend on `settings.json`.
- The Home Assistant addon Dockerfile expects the repository root as build context so it can reuse `backend/`.
