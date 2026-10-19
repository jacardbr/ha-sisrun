"""Coordenador de dados do SisRUN."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_WEEKS_AHEAD,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_WEEKS_AHEAD,
    DOMAIN,
)
from .data import Workout
from .sisrun_api import SisrunClient, SisrunError, detail_panels_missing, parse_week_html

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


def fetch_workouts(email: str, password: str, weeks_ahead: int) -> list[Workout]:
    """Faz login e lê a semana atual + `weeks_ahead` semanas. Bloqueante."""
    client = SisrunClient(email, password)
    weeks = client.fetch_weeks(back=0, ahead=weeks_ahead)

    rows: list[Workout] = []
    failures: list[str] = []
    for start in sorted(weeks):
        html = weeks[start]
        try:
            rows.extend(parse_week_html(html))
        except Exception as err:  # noqa: BLE001 - layout do site pode mudar de qualquer jeito
            failures.append(f"semana {start}: {err}")
            continue
        if detail_panels_missing(html):
            _LOGGER.warning(
                "SisRUN: semana %s veio sem os detalhes dos treinos (estrutura/observações)",
                start,
            )

    if failures and not rows:
        raise SisrunError("Não consegui interpretar as páginas do SisRUN: " + "; ".join(failures))
    for failure in failures:
        _LOGGER.warning("SisRUN: %s", failure)
    return rows


class SisrunCoordinator(DataUpdateCoordinator[list[Workout]]):
    """Busca os treinos do SisRUN periodicamente."""

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

    async def _async_update_data(self) -> list[Workout]:
        try:
            return await self.hass.async_add_executor_job(
                fetch_workouts, self._email, self._password, self._weeks_ahead
            )
        except SisrunError as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err
