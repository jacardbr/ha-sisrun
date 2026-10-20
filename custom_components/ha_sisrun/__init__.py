"""Integração SisRUN para o Home Assistant (não oficial, somente leitura)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ALL,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_WEEKS,
    DEFAULT_HISTORY_WEEKS,
    DOMAIN,
    HISTORY_ALL,
    MAX_HISTORY_WEEKS,
    PLATFORMS,
    RETIRED_ENTITIES,
    SERVICE_LOAD_HISTORY,
    STORAGE_VERSION,
)
from .data import week_bounds, week_payload, with_registration
from .coordinator import SisrunConfigEntry, SisrunCoordinator, storage_key

CARD_URL = f"/{DOMAIN}/ha-sisrun-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "ha-sisrun-card.js"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

LOAD_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WEEKS, default=DEFAULT_HISTORY_WEEKS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_HISTORY_WEEKS)
        ),
        vol.Optional(ATTR_ALL, default=False): cv.boolean,
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
            if call.data[ATTR_ALL]:
                # Pode levar minutos: roda em segundo plano e avisa por notificação.
                entry.async_create_background_task(
                    hass, entry.runtime_data.async_run_import(HISTORY_ALL), f"{DOMAIN}_import_all"
                )
            else:
                await entry.runtime_data.async_load_history(call.data[ATTR_WEEKS])

    hass.services.async_register(
        DOMAIN, SERVICE_LOAD_HISTORY, _load_history, schema=LOAD_HISTORY_SCHEMA
    )
    await _async_register_card(hass)
    websocket_api.async_register_command(hass, _ws_week)
    websocket_api.async_register_command(hass, _ws_races)
    websocket_api.async_register_command(hass, _ws_set_registration)
    websocket_api.async_register_command(hass, _ws_set_race_name)
    websocket_api.async_register_command(hass, _ws_set_race_time)
    websocket_api.async_register_command(hass, _ws_set_race_hidden)
    return True


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/week",
        vol.Required("start"): cv.date,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
@callback
def _ws_week(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Semana pedida pelo card (navegação entre semanas)."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    coordinator = entries[0].runtime_data
    day: date = msg["start"]
    monday = week_bounds(day)[0]
    payload = week_payload(coordinator.data or [], day, coordinator.has_week(monday.isoformat()))
    first_last = coordinator.week_range()
    payload["first_week"], payload["last_week"] = first_last if first_last else (None, None)
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/races", vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
)
@callback
def _ws_races(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Provas (objetivos/metas) guardadas, para a aba Provas do card."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    coordinator = entries[0].runtime_data
    connection.send_result(
        msg["id"],
        {
            "known": coordinator.races_known,
            "races": with_registration(coordinator.races, coordinator.registrations, coordinator.race_names, coordinator.race_times, coordinator.hidden_races),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_registration",
        vol.Required("key"): vol.All(cv.string, vol.Length(max=300)),
        vol.Optional("registered"): cv.boolean,
        vol.Optional("status"): vol.In(["none", "planned", "registered", "done", "missed"]),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
@websocket_api.async_response
async def _ws_set_registration(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Marca se você já está inscrito numa prova (guardado só no Home Assistant)."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    try:
        status = msg.get("status") or ("registered" if msg.get("registered") else "planned")
        await entries[0].runtime_data.async_set_race_status(msg["key"], status)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"key": msg["key"], "status": status})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_race_name",
        vol.Required("key"): vol.All(cv.string, vol.Length(max=300)),
        vol.Required("name"): vol.All(cv.string, vol.Length(max=120)),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
@websocket_api.async_response
async def _ws_set_race_name(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Renomeia uma prova só no Home Assistant (nome vazio = volta ao nome do SisRUN)."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    try:
        await entries[0].runtime_data.async_set_race_name(msg["key"], msg["name"])
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"key": msg["key"], "name": " ".join(msg["name"].split())})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_race_time",
        vol.Required("key"): vol.All(cv.string, vol.Length(max=300)),
        vol.Required("time"): vol.All(cv.string, vol.Length(max=20)),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
@websocket_api.async_response
async def _ws_set_race_time(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Guarda o tempo de prova (só no Home Assistant; vazio apaga)."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    try:
        await entries[0].runtime_data.async_set_race_time(msg["key"], msg["time"])
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"key": msg["key"], "time": " ".join(msg["time"].split())})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_race_hidden",
        vol.Required("key"): vol.All(cv.string, vol.Length(max=300)),
        vol.Required("hidden"): cv.boolean,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
@websocket_api.async_response
async def _ws_set_race_hidden(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Oculta ou restaura uma prova no card (só no Home Assistant)."""
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if entry_id in (None, e.entry_id)
    ]
    if not entries:
        connection.send_error(msg["id"], "not_found", "Nenhuma conta do SisRUN carregada.")
        return
    try:
        await entries[0].runtime_data.async_set_race_hidden(msg["key"], msg["hidden"])
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"key": msg["key"], "hidden": msg["hidden"]})


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve o card Lovelace e o carrega em todas as telas (sem cadastrar recurso à mão)."""
    manifest = Path(__file__).parent / "manifest.json"
    version = json.loads(await hass.async_add_executor_job(manifest.read_text))["version"]
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")


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
    # Em segundo plano: importar dezenas de semanas leva um tempo e não deve travar o início.
    entry.async_create_background_task(
        hass, coordinator.async_import_initial_history(), f"{DOMAIN}_import_history"
    )
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
