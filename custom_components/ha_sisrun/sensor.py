"""Sensores do SisRUN."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .data import (
    Workout,
    day_summary,
    describe,
    done_km_week,
    next_pending,
    planned_km_week,
    prescribed,
    workouts_on,
)
from .entity import SisrunEntity


def _next_date(rows: list[Workout], today: date) -> date | None:
    row = next_pending(rows, today)
    return date.fromisoformat(row["date"]) if row else None


def _next_attrs(rows: list[Workout], today: date) -> dict[str, Any]:
    row = next_pending(rows, today)
    return {"workout": row, "summary": describe(row)} if row else {}


@dataclass(frozen=True, kw_only=True)
class SisrunSensorDescription(SensorEntityDescription):
    """Descrição de um sensor calculado a partir da lista de treinos."""

    value_fn: Callable[[list[Workout], date], Any]
    attrs_fn: Callable[[list[Workout], date], dict[str, Any]] | None = None


SENSORS: tuple[SisrunSensorDescription, ...] = (
    SisrunSensorDescription(
        key="today",
        translation_key="today",
        value_fn=day_summary,
        attrs_fn=lambda rows, today: {"workouts": prescribed(workouts_on(rows, today))},
    ),
    SisrunSensorDescription(
        key="next",
        translation_key="next",
        device_class=SensorDeviceClass.DATE,
        value_fn=_next_date,
        attrs_fn=_next_attrs,
    ),
    SisrunSensorDescription(
        key="week_planned_km",
        translation_key="week_planned_km",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=planned_km_week,
    ),
    SisrunSensorDescription(
        key="week_done_km",
        translation_key="week_done_km",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=done_km_week,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SisrunConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SisrunSensor(coordinator, entry, desc) for desc in SENSORS)


class SisrunSensor(SisrunEntity, SensorEntity):
    entity_description: SisrunSensorDescription

    # A lista completa de treinos engorda o banco do recorder sem utilidade.
    _unrecorded_attributes = frozenset({"workouts", "workout"})

    def __init__(
        self,
        coordinator: SisrunCoordinator,
        entry: SisrunConfigEntry,
        description: SisrunSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.workouts, dt_util.now().date())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.workouts, dt_util.now().date())
