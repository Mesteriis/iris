from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import SCAN_INTERVAL, STATUS_PATH

LOGGER = logging.getLogger(__name__)


class IrisDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")
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
                payload = await response.json()
        except (ClientError, TimeoutError, ValueError) as exc:
            raise UpdateFailed(f"Unable to fetch IRIS status: {exc}") from exc
        return payload


async def async_validate_connection(hass: HomeAssistant, api_url: str) -> dict[str, Any]:
    coordinator = IrisDataUpdateCoordinator(hass, api_url)
    return await coordinator._async_update_data()
