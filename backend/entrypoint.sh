#!/usr/bin/env sh
set -eu

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

cd /app

if [ "$#" -eq 0 ]; then
  set -- python -m src.main
fi

IRIS_DATA_ROOT="${IRIS_DATA_ROOT:-/var/lib/iris}"
IRIS_RUN_ROOT="${IRIS_RUN_ROOT:-/var/run/iris}"
IRIS_EMBEDDED_POSTGRES_DATA_DIR="${IRIS_EMBEDDED_POSTGRES_DATA_DIR:-$IRIS_DATA_ROOT/postgres}"
IRIS_EMBEDDED_REDIS_DATA_DIR="${IRIS_EMBEDDED_REDIS_DATA_DIR:-$IRIS_DATA_ROOT/redis}"
IRIS_EMBEDDED_POSTGRES_HOST="${IRIS_EMBEDDED_POSTGRES_HOST:-127.0.0.1}"
IRIS_EMBEDDED_POSTGRES_PORT="${IRIS_EMBEDDED_POSTGRES_PORT:-5432}"
IRIS_EMBEDDED_POSTGRES_DB="${IRIS_EMBEDDED_POSTGRES_DB:-iris}"
IRIS_EMBEDDED_POSTGRES_USER="${IRIS_EMBEDDED_POSTGRES_USER:-iris}"
IRIS_EMBEDDED_POSTGRES_PASSWORD="${IRIS_EMBEDDED_POSTGRES_PASSWORD:-iris}"
IRIS_EMBEDDED_REDIS_HOST="${IRIS_EMBEDDED_REDIS_HOST:-127.0.0.1}"
IRIS_EMBEDDED_REDIS_PORT="${IRIS_EMBEDDED_REDIS_PORT:-6379}"
IRIS_EMBEDDED_REDIS_DB="${IRIS_EMBEDDED_REDIS_DB:-0}"
POSTGRES_INITDB_PATH="${POSTGRES_INITDB_PATH:-$(find /usr/lib/postgresql -type f -name initdb 2>/dev/null | sort -V | tail -n 1)}"

if [ -z "${POSTGRES_INITDB_PATH}" ]; then
  log "Embedded PostgreSQL binaries not found."
  exit 1
fi

POSTGRES_BIN_DIR="$(dirname "$POSTGRES_INITDB_PATH")"
export PATH="${POSTGRES_BIN_DIR}:${PATH}"

start_embedded_postgres() {
  log "Starting embedded PostgreSQL."
  mkdir -p "$IRIS_DATA_ROOT" "$IRIS_RUN_ROOT" "$IRIS_EMBEDDED_POSTGRES_DATA_DIR"
  chown -R postgres:postgres "$IRIS_DATA_ROOT" "$IRIS_RUN_ROOT"

  if [ ! -s "$IRIS_EMBEDDED_POSTGRES_DATA_DIR/PG_VERSION" ]; then
    log "Initializing embedded PostgreSQL data directory."
    su postgres -s /bin/sh -c "initdb -D '$IRIS_EMBEDDED_POSTGRES_DATA_DIR' --username=postgres --locale=C.UTF-8 --encoding=UTF8 --auth-local=trust --auth-host=scram-sha-256 >/dev/null"
    if ! grep -q "0.0.0.0/0" "$IRIS_EMBEDDED_POSTGRES_DATA_DIR/pg_hba.conf"; then
      cat >> "$IRIS_EMBEDDED_POSTGRES_DATA_DIR/pg_hba.conf" <<'EOF'
host all all 0.0.0.0/0 scram-sha-256
host all all ::/0 scram-sha-256
EOF
    fi
  fi

  if ! su postgres -s /bin/sh -c "pg_ctl -D '$IRIS_EMBEDDED_POSTGRES_DATA_DIR' status" >/dev/null 2>&1; then
    rm -f "$IRIS_EMBEDDED_POSTGRES_DATA_DIR/postmaster.pid"
    su postgres -s /bin/sh -c "pg_ctl -D '$IRIS_EMBEDDED_POSTGRES_DATA_DIR' -l '$IRIS_EMBEDDED_POSTGRES_DATA_DIR/postgresql.log' -o \"-p $IRIS_EMBEDDED_POSTGRES_PORT -k $IRIS_RUN_ROOT -c listen_addresses='*' -c shared_preload_libraries=timescaledb\" -w start"
  fi

  su postgres -s /bin/sh -c "psql -v ON_ERROR_STOP=1 -h '$IRIS_RUN_ROOT' -p '$IRIS_EMBEDDED_POSTGRES_PORT' -U postgres -d postgres -c \"DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '$IRIS_EMBEDDED_POSTGRES_USER') THEN CREATE ROLE \\\"$IRIS_EMBEDDED_POSTGRES_USER\\\" LOGIN PASSWORD '$IRIS_EMBEDDED_POSTGRES_PASSWORD'; ELSE ALTER ROLE \\\"$IRIS_EMBEDDED_POSTGRES_USER\\\" WITH LOGIN PASSWORD '$IRIS_EMBEDDED_POSTGRES_PASSWORD'; END IF; END \\\$\\\$;\" >/dev/null"

  if ! su postgres -s /bin/sh -c "psql -h '$IRIS_RUN_ROOT' -p '$IRIS_EMBEDDED_POSTGRES_PORT' -U postgres -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname = '$IRIS_EMBEDDED_POSTGRES_DB'\"" | grep -q 1; then
    su postgres -s /bin/sh -c "createdb -h '$IRIS_RUN_ROOT' -p '$IRIS_EMBEDDED_POSTGRES_PORT' -U postgres -O '$IRIS_EMBEDDED_POSTGRES_USER' '$IRIS_EMBEDDED_POSTGRES_DB'"
  fi
}

start_embedded_redis() {
  log "Starting embedded Redis."
  mkdir -p "$IRIS_RUN_ROOT" "$IRIS_EMBEDDED_REDIS_DATA_DIR"
  if ! redis-cli -h "$IRIS_EMBEDDED_REDIS_HOST" -p "$IRIS_EMBEDDED_REDIS_PORT" ping >/dev/null 2>&1; then
    rm -f "$IRIS_RUN_ROOT/redis.pid"
    redis-server \
      --bind 0.0.0.0 \
      --protected-mode no \
      --port "$IRIS_EMBEDDED_REDIS_PORT" \
      --appendonly yes \
      --dir "$IRIS_EMBEDDED_REDIS_DATA_DIR" \
      --daemonize yes \
      --logfile "$IRIS_EMBEDDED_REDIS_DATA_DIR/redis.log" \
      --pidfile "$IRIS_RUN_ROOT/redis.pid"
  fi
}

if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL="postgresql+psycopg://${IRIS_EMBEDDED_POSTGRES_USER}:${IRIS_EMBEDDED_POSTGRES_PASSWORD}@${IRIS_EMBEDDED_POSTGRES_HOST}:${IRIS_EMBEDDED_POSTGRES_PORT}/${IRIS_EMBEDDED_POSTGRES_DB}"
  start_embedded_postgres
else
  log "Using external PostgreSQL."
fi

if [ -z "${REDIS_URL:-}" ]; then
  export REDIS_URL="redis://${IRIS_EMBEDDED_REDIS_HOST}:${IRIS_EMBEDDED_REDIS_PORT}/${IRIS_EMBEDDED_REDIS_DB}"
  start_embedded_redis
else
  log "Using external Redis."
fi

python -m src.core.bootstrap.prestart

exec "$@"
