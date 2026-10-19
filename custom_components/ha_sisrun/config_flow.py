"""Fluxo de configuração do SisRUN."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_WEEKS_AHEAD,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_WEEKS_AHEAD,
    DOMAIN,
)
from .coordinator import is_login_failure
from .sisrun_api import SisrunClient, SisrunError

_LOGGER = logging.getLogger(__name__)

_EMAIL = TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username"))
_PASSWORD = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


def _try_login(email: str, password: str) -> None:
    """Login + leitura da semana atual. Bloqueante."""
    SisrunClient(email, password).current_week_html()


class SisrunConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pede o login do SisRUN (o mesmo que o treinador te passou)."""

    VERSION = 1

    async def _validate(self, email: str, password: str) -> str | None:
        """Devolve a chave de erro, ou None se o login funcionou."""
        try:
            await self.hass.async_add_executor_job(_try_login, email, password)
        except SisrunError as err:
            _LOGGER.debug("Falha ao validar login do SisRUN: %s", err)
            return "invalid_auth" if is_login_failure(err) else "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Erro inesperado ao validar login do SisRUN")
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            if (error := await self._validate(email, password)) is None:
                return self.async_create_entry(
                    title=f"SisRUN ({email})",
                    data={CONF_EMAIL: email, CONF_PASSWORD: password},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_EMAIL): _EMAIL, vol.Required(CONF_PASSWORD): _PASSWORD}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            if (error := await self._validate(entry.data[CONF_EMAIL], password)) is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SisrunOptionsFlow:
        return SisrunOptionsFlow()


class SisrunOptionsFlow(OptionsFlow):
    """Frequência de consulta e quantas semanas à frente buscar."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_HOURS: int(user_input[CONF_SCAN_INTERVAL_HOURS]),
                    CONF_WEEKS_AHEAD: int(user_input[CONF_WEEKS_AHEAD]),
                }
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_HOURS,
                        default=options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=24,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                    vol.Required(
                        CONF_WEEKS_AHEAD,
                        default=options.get(CONF_WEEKS_AHEAD, DEFAULT_WEEKS_AHEAD),
                    ): NumberSelector(
                        NumberSelectorConfig(min=0, max=4, step=1, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
