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
    EVENT_NEW_TEST,
    EVENT_PLAN_CHANGED,
    MAX_EVENTS_PER_REFRESH,
    MAX_STORED_TESTS,
    MAX_STORED_WEEKS,
    REFRESH_WEEKS_BACK,
    STORAGE_VERSION,
)
from .data import (
    Test,
    Workout,
    flatten_weeks,
    merge_tests,
    merge_weeks,
    prune_weeks,
    test_message,
    week_bounds,
)
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
    """Busca os treinos e testes do SisRUN, guarda o histórico e avisa das mudanças."""

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
        # Testes de desempenho, do mais novo ao mais antigo. `_tests_known` diz se já
        # houve uma leitura bem-sucedida: só depois dela um teste novo gera evento.
        self._tests: list[Test] = []
        self._tests_known = False
        self._lock = asyncio.Lock()

    @property
    def tests(self) -> list[Test]:
        return self._tests

    async def _async_setup(self) -> None:
        """Carrega o que já foi guardado (histórico e última planilha conhecida)."""
        stored = await self._store.async_load()
        if not stored:
            return
        if isinstance(stored.get("weeks"), dict):
            self._weeks = stored["weeks"]
        if isinstance(stored.get("tests"), list):
            self._tests = stored["tests"]
            self._tests_known = True

    # ---------- atualização periódica ----------

    async def _async_update_data(self) -> list[Workout]:
        async with self._lock:
            parsed, missing, tests = await self._async_fetch(
                REFRESH_WEEKS_BACK, self._weeks_ahead, with_tests=True
            )
            await self._async_merge_and_save(parsed, missing, tests)
            return flatten_weeks(self._weeks)

    # ---------- histórico sob demanda ----------

    async def async_load_history(self, weeks: int) -> int:
        """Busca `weeks` semanas passadas e guarda. Devolve quantas semanas foram lidas."""
        async with self._lock:
            try:
                parsed, missing, _ = await self._async_fetch(weeks, 0, with_tests=False)
            except UpdateFailed as err:
                raise HomeAssistantError(str(err)) from err
            await self._async_merge_and_save(parsed, missing, None)
            self.async_set_updated_data(flatten_weeks(self._weeks))
            return len(parsed)

    # ---------- internos ----------

    async def _async_fetch(
        self, back: int, ahead: int, with_tests: bool
    ) -> tuple[dict[str, list[Workout]], set[str], list[Test] | None]:
        try:
            return await self.hass.async_add_executor_job(
                fetch_parsed, self._email, self._password, back, ahead, with_tests
            )
        except SisrunError as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

    async def _async_merge_and_save(
        self,
        parsed: dict[str, list[Workout]],
        missing: set[str],
        tests: list[Test] | None,
    ) -> None:
        current_monday = week_bounds(dt_util.now().date())[0].isoformat()
        weeks, changes, kept = merge_weeks(self._weeks, parsed, missing, current_monday)
        for start in kept:
            _LOGGER.warning(
                "SisRUN: mantive a leitura anterior da semana %s porque a nova veio incompleta",
                start,
            )
        self._weeks = prune_weeks(weeks, MAX_STORED_WEEKS)

        new_tests: list[Test] = []
        announce_tests = self._tests_known  # a primeira leitura é só a linha de base
        if tests is not None:
            merged, new_tests = merge_tests(self._tests, tests)
            self._tests = merged[:MAX_STORED_TESTS]
            self._tests_known = True

        payload: dict[str, Any] = {"weeks": self._weeks}
        if self._tests_known:
            payload["tests"] = self._tests
        await self._store.async_save(payload)

        self._fire_changes(changes)
        if announce_tests:
            self._fire_new_tests(new_tests)

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

    def _fire_new_tests(self, new_tests: list[Test]) -> None:
        if not new_tests:
            return
        _LOGGER.info("SisRUN: %d teste(s) de desempenho novo(s)", len(new_tests))
        for test in new_tests[:MAX_EVENTS_PER_REFRESH]:
            self.hass.bus.async_fire(
                EVENT_NEW_TEST,
                {
                    "config_entry_id": self.config_entry.entry_id,
                    "message": test_message(test),
                    **test,
                },
            )
