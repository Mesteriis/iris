# IRIS Architecture

## Scope

IRIS is intentionally narrow:

- `coins`
- `price_history`

Not included:

- signals
- trading logic
- pattern detection

## Backend runtime

The backend owns three concerns inside one service:

- FastAPI HTTP API
- SQLAlchemy/Alembic database access and migrations
- TaskIQ brokers plus dedicated worker processes

FastAPI only enqueues TaskIQ jobs. Task execution runs in dedicated worker processes started from the backend lifespan hook, so long-running analytics never execute inside the main HTTP event loop.

Background tasks:

- startup bootstrap task: sync watched assets and backfill retention windows from seed data
- periodic refresh task: append newly available bars for enabled, non-deleted assets

The default `source` is an internal deterministic market-data generator for the MVP, so the project runs without external API keys.

## Database

Tables:

- `coins`
- `price_history`

`coins` stores the watched asset catalog metadata:

- `asset_type`
- `theme`
- `source`
- `enabled`
- `sort_order`
- `candles_config`
- `last_history_sync_at`
- `deleted_at`

`price_history` stores interval-based bars and keeps:

- `interval`
- `timestamp`
- `price`
- `volume`

Indexes:

- `(coin_id, timestamp)`
- unique `(coin_id, interval, timestamp)`

## Home Assistant

The custom integration polls `GET /status` and exposes `sensor.iris_status`.

The addon runs the same backend code path as Docker/systemd deployments, so Home Assistant also uses the single-service backend model.

## Deletion

Deleting a coin removes its history immediately and marks the coin as deleted in `coins`, which prevents startup seed sync from recreating it on the next restart.
