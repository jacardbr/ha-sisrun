"""Constantes da integração SisRUN."""

from homeassistant.const import Platform

DOMAIN = "ha_sisrun"

CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
CONF_WEEKS_AHEAD = "weeks_ahead"

DEFAULT_SCAN_INTERVAL_HOURS = 3
DEFAULT_WEEKS_AHEAD = 1

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]
