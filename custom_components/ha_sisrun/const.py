"""Constantes da integração SisRUN."""

from homeassistant.const import Platform

DOMAIN = "ha_sisrun"

CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
CONF_WEEKS_AHEAD = "weeks_ahead"
CONF_IMPORT_HISTORY_WEEKS = "import_history_weeks"
CONF_IMPORT_ALL_HISTORY = "import_all_history"

DEFAULT_SCAN_INTERVAL_HOURS = 3
DEFAULT_WEEKS_AHEAD = 1

# Em toda consulta lemos também a semana anterior: o SisRUN importa atividades
# do Garmin/Strava com atraso e o status de ontem pode mudar.
REFRESH_WEEKS_BACK = 1

STORAGE_VERSION = 1
MAX_STORED_WEEKS = 520  # 10 anos: igual ao teto da importação de todo o histórico
MAX_EVENTS_PER_REFRESH = 20

EVENT_PLAN_CHANGED = "ha_sisrun_plan_changed"
EVENT_NEW_TEST = "ha_sisrun_new_test"
MAX_STORED_TESTS = 200
MAX_STORED_RACES = 1000

SERVICE_LOAD_HISTORY = "load_history"
ATTR_WEEKS = "weeks"
ATTR_ALL = "all"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
DEFAULT_HISTORY_WEEKS = 12
MAX_HISTORY_WEEKS = 52
# Valor interno de "semanas" que significa "todo o histórico".
HISTORY_ALL = 9999

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SENSOR,
]

# Entidades que já existiram e foram retiradas: (plataforma, chave). A integração
# as apaga do registro ao iniciar, para não ficarem "indisponíveis" para sempre.
RETIRED_ENTITIES: tuple[tuple[str, str], ...] = (
    ("binary_sensor", "pending_today"),
    ("sensor", "today_status"),
    ("sensor", "today_hr_min"),
    ("sensor", "today_hr_max"),
    ("sensor", "today_structure"),
)

# Situação local de uma prova (só no Home Assistant); sem entrada = planejada (padrão).
RACE_STATUSES = ("planned", "registered", "done", "missed")
