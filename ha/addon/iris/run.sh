#!/usr/bin/env sh
set -eu

if [ -f /data/options.json ]; then
  export DATABASE_URL="${DATABASE_URL:-$(python -c "import json; print(json.load(open('/data/options.json')).get('database_url', 'postgresql+psycopg://iris:iris@db:5432/iris'))")}"
  export IRIS_API_PORT="${IRIS_API_PORT:-$(python -c "import json; print(json.load(open('/data/options.json')).get('api_port', 8000))")}"
else
  export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://iris:iris@db:5432/iris}"
  export IRIS_API_PORT="${IRIS_API_PORT:-8000}"
fi

cd /app/backend
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${IRIS_API_PORT}"
