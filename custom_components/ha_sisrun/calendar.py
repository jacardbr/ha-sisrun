"""Calendário com os treinos prescritos no SisRUN."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SisrunConfigEntry, SisrunCoordinator
from .data import event_description, event_summary, prescribed
from .entity import SisrunEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SisrunConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SisrunCalendar(entry.runtime_data, entry)])


class SisrunCalendar(SisrunEntity, CalendarEntity):
    """Um evento de dia inteiro por treino (o SisRUN não informa horário)."""

    _attr_translation_key = "workouts"

    def __init__(self, coordinator: SisrunCoordinator, entry: SisrunConfigEntry) -> None:
        super().__init__(coordinator, entry, "calendar")

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for index, row in enumerate(sorted(prescribed(self.workouts), key=lambda r: r["date"])):
            day = date.fromisoformat(row["date"])
            events.append(
                CalendarEvent(
                    start=day,
                    end=day + timedelta(days=1),
                    summary=event_summary(row),
                    description=event_description(row),
                    uid=f"sisrun-{row['date']}-{index}",
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Treino de hoje, ou o próximo."""
        today = dt_util.now().date()
        return next((ev for ev in self._events() if ev.end > today), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start = dt_util.as_local(start_date).date()
        end = dt_util.as_local(end_date).date()
        return [ev for ev in self._events() if ev.start < end and ev.end > start]
