"""Base das entidades do SisRUN."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .data import Workout


class SisrunEntity(CoordinatorEntity[SisrunCoordinator]):
    """Entidade ligada ao coordenador; todas compartilham um dispositivo."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SisrunCoordinator, entry: SisrunConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SisRUN",
            manufacturer="SisRUN (não oficial)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def workouts(self) -> list[Workout]:
        return self.coordinator.data or []
