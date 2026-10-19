"""Integração SisRUN para o Home Assistant (não oficial, somente leitura)."""

from __future__ import annotations

from datetime import datetime

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_WEEKS,
    DEFAULT_HISTORY_WEEKS,
    DOMAIN,
    MAX_HISTORY_WEEKS,
    PLATFORMS,
    RETIRED_ENTITIES,
    SERVICE_LOAD_HISTORY,
    STORAGE_VERSION,
)
from .coordinator import SisrunConfigEntry, SisrunCoordinator, storage_key

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

LOAD_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WEEKS, default=DEFAULT_HISTORY_WEEKS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_HISTORY_WEEKS)
        ),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registra a ação `ha_sisrun.load_history` (uma vez por Home Assistant)."""

    async def _load_history(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        entries = [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if entry_id in (None, entry.entry_id)
        ]
        if not entries:
            raise ServiceValidationError("Nenhuma conta do SisRUN carregada para esta chamada.")
        for entry in entries:
            await entry.runtime_data.async_load_history(call.data[ATTR_WEEKS])

    hass.services.async_register(
        DOMAIN, SERVICE_LOAD_HISTORY, _load_history, schema=LOAD_HISTORY_SCHEMA
    )
    return True


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

    _remove_retired_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


@callback
def _remove_retired_entities(hass: HomeAssistant, entry: SisrunConfigEntry) -> None:
    """Apaga do registro as entidades de versões anteriores que não existem mais."""
    registry = er.async_get(hass)
    for platform, key in RETIRED_ENTITIES:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        if entity_id:
            registry.async_remove(entity_id)


async def _async_reload(hass: HomeAssistant, entry: SisrunConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SisrunConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: SisrunConfigEntry) -> None:
    """Ao remover a conta, apaga também o histórico guardado."""
    await Store(hass, STORAGE_VERSION, storage_key(entry.entry_id)).async_remove()
