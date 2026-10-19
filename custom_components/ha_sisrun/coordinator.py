"""Coordenador de dados do SisRUN."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_IMPORT_ALL_HISTORY,
    CONF_IMPORT_HISTORY_WEEKS,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_WEEKS_AHEAD,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_WEEKS_AHEAD,
    DOMAIN,
    EVENT_NEW_TEST,
    EVENT_PLAN_CHANGED,
    HISTORY_ALL,
    MAX_EVENTS_PER_REFRESH,
    MAX_STORED_RACES,
    MAX_STORED_TESTS,
    MAX_STORED_WEEKS,
    REFRESH_WEEKS_BACK,
    STORAGE_VERSION,
)
from .data import (
    Race,
    Test,
    Workout,
    flatten_weeks,
    merge_races,
    merge_tests,
    race_key,
    merge_weeks,
    prune_weeks,
    test_message,
    week_bounds,
)
from .sisrun_api import SisrunError, fetch_all_parsed, fetch_parsed

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
        # Quantas semanas de histórico já foram importadas na configuração/opções.
        self._history_done = 0
        # Provas (objetivos/metas), da mais nova à mais antiga.
        self._races: list[Race] = []
        self._races_known = False
        # Inscrição nas provas: dado só do Home Assistant (o SisRUN não informa), por chave da prova.
        self._registrations: dict[str, bool] = {}
        # Nomes dados por você às provas (só locais), por chave da prova.
        self._race_names: dict[str, str] = {}
        # Tempo de prova que você cadastra (só local), por chave da prova.
        self._race_times: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def has_week(self, monday_iso: str) -> bool:
        """A semana (pela segunda-feira) já foi lida e guardada alguma vez?"""
        return monday_iso in self._weeks

    def week_range(self) -> tuple[str, str] | None:
        """Primeira e última semana guardadas (segundas-feiras, AAAA-MM-DD)."""
        return (min(self._weeks), max(self._weeks)) if self._weeks else None

    @property
    def races(self) -> list[Race]:
        return self._races

    @property
    def registrations(self) -> dict[str, bool]:
        return self._registrations

    @property
    def race_names(self) -> dict[str, str]:
        return self._race_names

    @property
    def race_times(self) -> dict[str, str]:
        return self._race_times

    async def async_set_race_time(self, key: str, value: str) -> None:
        """Guarda o tempo de prova só no Home Assistant (vazio apaga)."""
        if key not in {race_key(r) for r in self._races}:
            raise HomeAssistantError("Prova não encontrada.")
        value = " ".join(value.split())[:20]
        async with self._lock:
            if value:
                self._race_times[key] = value
            else:
                self._race_times.pop(key, None)
            await self._store.async_save(self._payload())

    async def async_set_race_name(self, key: str, name: str) -> None:
        """Renomeia a prova só no Home Assistant (nome vazio volta ao do SisRUN)."""
        if key not in {race_key(r) for r in self._races}:
            raise HomeAssistantError("Prova não encontrada.")
        name = " ".join(name.split())[:120]
        async with self._lock:
            if name:
                self._race_names[key] = name
            else:
                self._race_names.pop(key, None)
            await self._store.async_save(self._payload())

    async def async_set_registration(self, key: str, registered: bool) -> None:
        """Marca/desmarca a inscrição numa prova guardada. Só vive no Home Assistant."""
        if key not in {race_key(r) for r in self._races}:
            raise HomeAssistantError("Prova não encontrada.")
        async with self._lock:
            if registered:
                self._registrations[key] = True
            else:
                self._registrations.pop(key, None)
            await self._store.async_save(self._payload())

    @property
    def races_known(self) -> bool:
        return self._races_known

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
        if isinstance(stored.get("history_weeks"), int):
            self._history_done = stored["history_weeks"]
        if isinstance(stored.get("registrations"), dict):
            self._registrations = {k: True for k, v in stored["registrations"].items() if v}
        if isinstance(stored.get("race_names"), dict):
            self._race_names = {
                k: v for k, v in stored["race_names"].items() if isinstance(v, str) and v
            }
        if isinstance(stored.get("race_times"), dict):
            self._race_times = {
                k: v for k, v in stored["race_times"].items() if isinstance(v, str) and v
            }
        if isinstance(stored.get("races"), list):
            self._races = stored["races"]
            self._races_known = True
        if isinstance(stored.get("tests"), list):
            self._tests = stored["tests"]
            self._tests_known = True

    # ---------- atualização periódica ----------

    async def _async_update_data(self) -> list[Workout]:
        async with self._lock:
            parsed, missing, tests, races = await self._async_fetch(
                REFRESH_WEEKS_BACK, self._weeks_ahead, with_extras=True
            )
            await self._async_merge_and_save(parsed, missing, tests, races)
            return flatten_weeks(self._weeks)

    # ---------- histórico sob demanda ----------

    async def async_load_history(self, weeks: int) -> int:
        """Busca `weeks` semanas passadas e guarda. Devolve quantas semanas foram lidas."""
        async with self._lock:
            try:
                parsed, missing, _, _ = await self._async_fetch(weeks, 0, with_extras=False)
            except UpdateFailed as err:
                raise HomeAssistantError(str(err)) from err
            await self._async_merge_and_save(parsed, missing, None, None)
            self.async_set_updated_data(flatten_weeks(self._weeks))
            return len(parsed)

    # ---------- internos ----------

    async def _async_fetch(
        self, back: int, ahead: int, with_extras: bool
    ) -> tuple[dict[str, list[Workout]], set[str], list[Test] | None, list[Race] | None]:
        try:
            if back >= HISTORY_ALL:
                return await self.hass.async_add_executor_job(
                    fetch_all_parsed, self._email, self._password
                )
            return await self.hass.async_add_executor_job(
                fetch_parsed, self._email, self._password, back, ahead, with_extras
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
        races: list[Race] | None,
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

        if races is not None:
            self._races = merge_races(self._races, races)[:MAX_STORED_RACES]
            self._races_known = True

        await self._store.async_save(self._payload())

        self._fire_changes(changes)
        if announce_tests:
            self._fire_new_tests(new_tests)

    def _payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"weeks": self._weeks, "history_weeks": self._history_done}
        if self._tests_known:
            payload["tests"] = self._tests
        if self._races_known:
            payload["races"] = self._races
        if self._registrations:
            payload["registrations"] = self._registrations
        if self._race_names:
            payload["race_names"] = self._race_names
        if self._race_times:
            payload["race_times"] = self._race_times
        return payload

    async def async_import_initial_history(self) -> None:
        """Importa o histórico pedido na configuração (ou nas opções), uma vez por pedido."""
        entry = self.config_entry
        def setting(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        want = HISTORY_ALL if setting(CONF_IMPORT_ALL_HISTORY, False) else int(
            setting(CONF_IMPORT_HISTORY_WEEKS, 0)
        )
        if want <= self._history_done:
            return
        await self.async_run_import(want)

    async def async_run_import(self, want: int) -> None:
        """Importa `want` semanas (HISTORY_ALL = tudo), guarda que foi feito e avisa o resultado."""
        try:
            weeks = await self.async_load_history(want)
        except Exception as err:  # noqa: BLE001 - tenta de novo na próxima inicialização
            _LOGGER.warning("SisRUN: não consegui importar o histórico (%s)", err)
            self._notify_import(f"Não consegui importar o histórico: {err}\nNova tentativa na próxima inicialização.")
            return
        async with self._lock:
            self._history_done = want
            await self._store.async_save(self._payload())
        _LOGGER.info("SisRUN: histórico importado (%d semanas lidas)", weeks)
        with_work = sorted(start for start, rows in self._weeks.items() if rows)
        if with_work:
            workouts = sum(len(self._weeks[start]) for start in with_work)
            self._notify_import(
                f"Histórico importado: {weeks} semanas lidas, {len(with_work)} com treinos "
                f"({workouts} treinos no total). Semana mais antiga com treino: {with_work[0]}. "
                "Se esperava dados mais antigos, o SisRUN pode não ter registros anteriores a essa data."
            )
        else:
            self._notify_import(f"Histórico importado: {weeks} semanas lidas, nenhuma com treino.")

    def _notify_import(self, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            message,
            title="SisRUN",
            notification_id=f"{DOMAIN}_import_{self.config_entry.entry_id}",
        )

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
