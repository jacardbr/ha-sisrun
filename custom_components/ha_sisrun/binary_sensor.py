"""Sensor binário: há treino pendente hoje?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .data import pending_on
from .entity import SisrunEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SisrunConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SisrunPendingToday(entry.runtime_data, entry)])


class SisrunPendingToday(SisrunEntity, BinarySensorEntity):
    """Ligado quando existe treino de hoje ainda não feito (Proposto/Programado)."""

    _attr_translation_key = "pending_today"
    _unrecorded_attributes = frozenset({"workouts"})

    def __init__(self, coordinator: SisrunCoordinator, entry: SisrunConfigEntry) -> None:
        super().__init__(coordinator, entry, "pending_today")

    @property
    def is_on(self) -> bool:
        return bool(pending_on(self.workouts, dt_util.now().date()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"workouts": pending_on(self.workouts, dt_util.now().date())}
