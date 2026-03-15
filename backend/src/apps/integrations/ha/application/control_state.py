from __future__ import annotations

from redis.asyncio import Redis as AsyncRedis

from src.core.settings import Settings, get_settings

_CONTROL_STATE_KEY = "iris:ha:control:state"
_NOTIFICATIONS_ENABLED_FIELD = "settings.notifications_enabled"
_DEFAULT_TIMEFRAME_FIELD = "settings.default_timeframe"
HA_TIMEFRAME_OPTIONS = ("15m", "1h", "4h", "1d")


class HAControlStateStore:
    def __init__(
        self,
        client: AsyncRedis | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        effective_settings = settings or get_settings()
        self._client = client or AsyncRedis.from_url(effective_settings.redis_url, decode_responses=True)

    async def get_notifications_enabled(self, *, default: bool) -> bool:
        raw = await self._client.hget(_CONTROL_STATE_KEY, _NOTIFICATIONS_ENABLED_FIELD)
        if raw is None:
            return bool(default)
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}

    async def set_notifications_enabled(self, enabled: bool) -> None:
        await self._client.hset(_CONTROL_STATE_KEY, _NOTIFICATIONS_ENABLED_FIELD, "true" if enabled else "false")

    async def get_default_timeframe(self, *, default: str) -> str:
        raw = await self._client.hget(_CONTROL_STATE_KEY, _DEFAULT_TIMEFRAME_FIELD)
        if raw in HA_TIMEFRAME_OPTIONS:
            return str(raw)
        return default

    async def set_default_timeframe(self, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in HA_TIMEFRAME_OPTIONS:
            allowed = ", ".join(HA_TIMEFRAME_OPTIONS)
            raise ValueError(f"default_timeframe must be one of: {allowed}")
        await self._client.hset(_CONTROL_STATE_KEY, _DEFAULT_TIMEFRAME_FIELD, normalized)
        return normalized


__all__ = ["HAControlStateStore", "HA_TIMEFRAME_OPTIONS"]
