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
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .data import (
    Workout,
    day_attrs,
    day_summary,
    describe,
    done_km_week,
    first_today,
    latest_test,
    next_pending,
    planned_km_week,
    prescribed,
    test_attrs,
    week_adherence,
    weekday_date,
    workouts_on,
)
from .entity import SisrunEntity


def _next_date(rows: list[Workout], today: date) -> date | None:
    row = next_pending(rows, today)
    return date.fromisoformat(row["date"]) if row else None


def _next_attrs(rows: list[Workout], today: date) -> dict[str, Any]:
    row = next_pending(rows, today)
    return {"workout": row, "summary": describe(row)} if row else {}


def _today_field(
    field: str, convert: Callable[[Any], Any] | None = None
) -> Callable[[list[Workout], date], Any]:
    """Valor de um campo do treino de hoje; None se não há treino ou o campo está vazio."""

    def value_fn(rows: list[Workout], today: date) -> Any:
        row = first_today(rows, today)
        value = row.get(field) if row else None
        if value in ("", None):
            return None
        return convert(value) if convert else value

    return value_fn


def _adherence_value(rows: list[Workout], today: date) -> int | None:
    result = week_adherence(rows, today)
    return result["percent"] if result else None


def _adherence_attrs(rows: list[Workout], today: date) -> dict[str, Any]:
    return week_adherence(rows, today) or {}


@dataclass(frozen=True, kw_only=True)
class SisrunSensorDescription(SensorEntityDescription):
    """Descrição de um sensor calculado a partir da lista de treinos."""

    value_fn: Callable[[list[Workout], date], Any]
    attrs_fn: Callable[[list[Workout], date], dict[str, Any]] | None = None


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _weekday_description(index: int, name: str) -> SisrunSensorDescription:
    """Sensor de um dia fixo da semana atual (segunda a domingo).

    O estado é o mesmo resumo do sensor "Treino de hoje" (ou `Sem treino`); os
    detalhes completos ficam nos atributos. Na virada da semana passa a mostrar a nova.
    """
    return SisrunSensorDescription(
        key=f"weekday_{name}",
        translation_key=f"weekday_{name}",
        value_fn=lambda rows, today: day_summary(rows, weekday_date(today, index)),
        attrs_fn=lambda rows, today: day_attrs(rows, weekday_date(today, index)),
    )


SENSORS: tuple[SisrunSensorDescription, ...] = (
    SisrunSensorDescription(
        key="today",
        translation_key="today",
        value_fn=day_summary,
        attrs_fn=lambda rows, today: {"workouts": prescribed(workouts_on(rows, today))},
    ),
    SisrunSensorDescription(
        key="today_km",
        translation_key="today_km",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=_today_field("planned_km", lambda v: round(float(v), 1)),
    ),
    SisrunSensorDescription(
        key="today_intensity",
        translation_key="today_intensity",
        value_fn=_today_field("intensity"),
    ),
    SisrunSensorDescription(
        key="today_note",
        translation_key="today_note",
        value_fn=_today_field("coach_note", lambda v: str(v)[:255]),
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
    SisrunSensorDescription(
        key="week_adherence",
        translation_key="week_adherence",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_adherence_value,
        attrs_fn=_adherence_attrs,
    ),
    *(_weekday_description(index, name) for index, name in enumerate(WEEKDAYS)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SisrunConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(SisrunSensor(coordinator, entry, desc) for desc in SENSORS),
            SisrunPerformanceSensor(coordinator, entry),
        ]
    )


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


class SisrunPerformanceSensor(SisrunEntity, SensorEntity):
    """Último teste de desempenho: o estado é o VO2 máx; o histórico fica nos atributos."""

    _attr_translation_key = "performance_test"
    _attr_native_unit_of_measurement = "mL/(kg·min)"
    _attr_suggested_display_precision = 2
    # O histórico completo engorda o banco do recorder sem utilidade.
    _unrecorded_attributes = frozenset({"history"})

    def __init__(self, coordinator: SisrunCoordinator, entry: SisrunConfigEntry) -> None:
        super().__init__(coordinator, entry, "performance_test")

    @property
    def native_value(self) -> float | None:
        latest = latest_test(self.coordinator.tests)
        return latest.get("vo2max") if latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return test_attrs(self.coordinator.tests)
