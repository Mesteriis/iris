from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DECISIONS_PATH, SCAN_INTERVAL, STATUS_PATH

LOGGER = logging.getLogger(__name__)


class IrisDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")
        self._seen_decision_ids: set[int] = set()
        super().__init__(
            hass,
            logger=LOGGER,
            name="IRIS status",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(f"{self.api_url}{STATUS_PATH}", timeout=10) as response:
                response.raise_for_status()
                status_payload = await response.json()
            async with session.get(
                f"{self.api_url}{DECISIONS_PATH}",
                params={"limit": 100},
                timeout=10,
            ) as response:
                response.raise_for_status()
                decision_payload = await response.json()
        except (ClientError, TimeoutError, ValueError) as exc:
            raise UpdateFailed(f"Unable to fetch IRIS status: {exc}") from exc
        self._emit_decision_events(decision_payload if isinstance(decision_payload, list) else [])
        status_payload["decisions"] = decision_payload
        return status_payload

    def _emit_decision_events(self, decisions: list[dict[str, Any]]) -> None:
        decision_ids = {
            int(item["id"])
            for item in decisions
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        if not self._seen_decision_ids:
            self._seen_decision_ids = decision_ids
            return

        new_items = [
            item
            for item in decisions
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and int(item["id"]) not in self._seen_decision_ids
        ]
        self._seen_decision_ids |= decision_ids
        if len(self._seen_decision_ids) > 500:
            self._seen_decision_ids = set(sorted(self._seen_decision_ids, reverse=True)[:500])
        for item in new_items:
            self.hass.bus.async_fire(
                "iris.decision",
                {
                    "coin": item.get("symbol"),
                    "decision": item.get("decision"),
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason"),
                },
            )


async def async_validate_connection(hass: HomeAssistant, api_url: str) -> dict[str, Any]:
    coordinator = IrisDataUpdateCoordinator(hass, api_url)
    return await coordinator._async_update_data()
