"""Botão para consultar o SisRUN na hora."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .entity import SisrunEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SisrunConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SisrunRefreshButton(entry.runtime_data, entry)])


class SisrunRefreshButton(SisrunEntity, ButtonEntity):
    """Força uma consulta ao SisRUN sem esperar o intervalo."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: SisrunCoordinator, entry: SisrunConfigEntry) -> None:
        super().__init__(coordinator, entry, "refresh")

    @property
    def available(self) -> bool:
        # Fica disponível mesmo após uma falha: é justamente o botão de tentar de novo.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
