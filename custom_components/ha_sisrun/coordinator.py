"""Coordenador de dados do SisRUN."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_WEEKS_AHEAD,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_WEEKS_AHEAD,
    DOMAIN,
    EVENT_PLAN_CHANGED,
    MAX_EVENTS_PER_REFRESH,
    MAX_STORED_WEEKS,
    REFRESH_WEEKS_BACK,
    STORAGE_VERSION,
)
from .data import Workout, flatten_weeks, merge_weeks, prune_weeks, week_bounds
from .sisrun_api import SisrunError, fetch_parsed

_LOGGER = logging.getLogger(__name__)

type SisrunConfigEntry = ConfigEntry[SisrunCoordinator]


def is_auth_error(err: SisrunError) -> bool:
    """Login recusado de forma explícita (o cliente só sinaliza pela mensagem)."""
    return "rejected the credentials" in str(err)


def is_login_failure(err: SisrunError) -> bool:
    """Qualquer falha de login, inclusive sem aviso claro de senha errada.

    Usado só ao configurar: lá, "login não completou" quase sempre é senha errada.
    Em execução usamos `is_auth_error`, para uma mudança no site não disparar
    pedidos de reautenticação à toa.
    """
    return is_auth_error(err) or "login did not succeed" in str(err)


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}"


class SisrunCoordinator(DataUpdateCoordinator[list[Workout]]):
    """Busca os treinos do SisRUN, guarda o histórico e avisa quando a planilha muda."""

    config_entry: SisrunConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SisrunConfigEntry) -> None:
        hours = int(entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        self._email: str = entry.data[CONF_EMAIL]
        self._password: str = entry.data[CONF_PASSWORD]
        self._weeks_ahead = int(entry.options.get(CONF_WEEKS_AHEAD, DEFAULT_WEEKS_AHEAD))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        self._weeks: dict[str, list[Workout]] = {}
        self._lock = asyncio.Lock()

    async def _async_setup(self) -> None:
        """Carrega o que já foi guardado (histórico e última planilha conhecida)."""
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("weeks"), dict):
            self._weeks = stored["weeks"]

    # ---------- atualização periódica ----------

    async def _async_update_data(self) -> list[Workout]:
        async with self._lock:
            parsed, missing = await self._async_fetch(REFRESH_WEEKS_BACK, self._weeks_ahead)
            await self._async_merge_and_save(parsed, missing)
            return flatten_weeks(self._weeks)

    # ---------- histórico sob demanda ----------

    async def async_load_history(self, weeks: int) -> int:
        """Busca `weeks` semanas passadas e guarda. Devolve quantas semanas foram lidas."""
        async with self._lock:
            try:
                parsed, missing = await self._async_fetch(weeks, 0)
            except UpdateFailed as err:
                raise HomeAssistantError(str(err)) from err
            await self._async_merge_and_save(parsed, missing)
            self.async_set_updated_data(flatten_weeks(self._weeks))
            return len(parsed)

    # ---------- internos ----------

    async def _async_fetch(
        self, back: int, ahead: int
    ) -> tuple[dict[str, list[Workout]], set[str]]:
        try:
            return await self.hass.async_add_executor_job(
                fetch_parsed, self._email, self._password, back, ahead
            )
        except SisrunError as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

    async def _async_merge_and_save(
        self, parsed: dict[str, list[Workout]], missing: set[str]
    ) -> None:
        current_monday = week_bounds(dt_util.now().date())[0].isoformat()
        weeks, changes, kept = merge_weeks(self._weeks, parsed, missing, current_monday)
        for start in kept:
            _LOGGER.warning(
                "SisRUN: mantive a leitura anterior da semana %s porque a nova veio incompleta",
                start,
            )
        self._weeks = prune_weeks(weeks, MAX_STORED_WEEKS)
        await self._store.async_save({"weeks": self._weeks})
        self._fire_changes(changes)

    def _fire_changes(self, changes: list[dict[str, Any]]) -> None:
        if not changes:
            return
        _LOGGER.info("SisRUN: %d mudança(s) na planilha", len(changes))
        for change in changes[:MAX_EVENTS_PER_REFRESH]:
            self.hass.bus.async_fire(
                EVENT_PLAN_CHANGED,
                {"config_entry_id": self.config_entry.entry_id, **change},
            )
        if len(changes) > MAX_EVENTS_PER_REFRESH:
            _LOGGER.warning(
                "SisRUN: %d mudanças; só as primeiras %d geraram evento",
                len(changes),
                MAX_EVENTS_PER_REFRESH,
            )
