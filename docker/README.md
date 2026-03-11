# Docker Notes

- `docker-compose.yml` starts PostgreSQL, the backend API, and the frontend dashboard.
- The backend container is the only runtime that owns TaskIQ execution.
- No separate worker container is defined by design.
