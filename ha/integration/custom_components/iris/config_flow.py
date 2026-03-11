from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_API_URL, DEFAULT_NAME, DOMAIN
from .coordinator import async_validate_connection


class CannotConnect(Exception):
    """Raised when the integration cannot reach the IRIS backend."""


class IrisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[CONF_API_URL].rstrip("/")
            await self.async_set_unique_id(api_url)
            self._abort_if_unique_id_configured()

            try:
                await async_validate_connection(self.hass, api_url)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={CONF_API_URL: api_url},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_URL, default="http://localhost:8000"): str,
            },
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
