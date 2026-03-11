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
- embedded TaskIQ broker and receiver

TaskIQ uses a ZeroMQ broker and an in-process `Receiver` started from the FastAPI lifespan hook. This keeps the worker inside the backend runtime so the same container or `systemd` unit owns the API and background task execution.

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
