"""Integração SisRUN para o Home Assistant (não oficial, somente leitura)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import PLATFORMS
from .coordinator import SisrunConfigEntry, SisrunCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: SisrunConfigEntry) -> bool:
    coordinator = SisrunCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _midnight(_now: datetime) -> None:
        # Os dados vêm de poucas em poucas horas, mas "hoje" muda à meia-noite:
        # reavalia os sensores sem ir à rede.
        coordinator.async_update_listeners()

    entry.async_on_unload(async_track_time_change(hass, _midnight, hour=0, minute=0, second=5))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: SisrunConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SisrunConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
