from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IrisDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrisStatusSensor(entry, coordinator)])


class IrisStatusSensor(CoordinatorEntity[IrisDataUpdateCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:chart-line"

    def __init__(self, entry: ConfigEntry, coordinator: IrisDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "status"
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        return str(self.coordinator.data.get("status", "unknown"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "service": self.coordinator.data.get("service"),
            "taskiq_mode": self.coordinator.data.get("taskiq_mode"),
            "taskiq_running": self.coordinator.data.get("taskiq_running"),
        }
