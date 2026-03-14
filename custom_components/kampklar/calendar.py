"""Calendar platform for KampKlar."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Activity
from .const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN
from .coordinator import KampKlarCoordinator

type KampKlarConfigEntry = ConfigEntry[KampKlarCoordinator]

# Default event duration when end_time is missing
_DEFAULT_DURATION = timedelta(hours=1, minutes=30)


def _end_time(act: Activity) -> datetime:
    """Return the end time for an activity, with fallback default duration."""
    if act.end_time:
        return dt_util.as_local(act.end_time)
    return dt_util.as_local(act.start_time) + _DEFAULT_DURATION


def _activity_to_event(act: Activity) -> CalendarEvent:
    """Convert an Activity to a CalendarEvent."""
    start = dt_util.as_local(act.start_time)
    end = _end_time(act)

    description_parts = [f"Type: {act.type_name}"]
    if act.team_name:
        description_parts.append(f"Hold: {act.team_name}")
    if act.signup_status_name:
        description_parts.append(f"Status: {act.signup_status_name}")
    if act.subscribed:
        description_parts.append(f"Tilmeldte: {act.subscribed}")
    if act.match:
        if act.match.stadium_name:
            description_parts.append(f"Stadion: {act.match.stadium_name}")
        if act.match.field_name:
            description_parts.append(f"Bane: {act.match.field_name}")

    location = act.meeting_place or None

    return CalendarEvent(
        summary=act.name,
        start=start,
        end=end,
        description="\n".join(description_parts),
        location=location,
        uid=str(act.activity_id),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KampKlarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KampKlar calendars from a config entry."""
    coordinator = entry.runtime_data
    persons: list[dict] = entry.data[CONF_PERSONS]

    entities = [KampKlarCalendar(coordinator, person[CONF_PERSON_ID], person[CONF_PERSON_NAME]) for person in persons]
    async_add_entities(entities)


class KampKlarCalendar(CoordinatorEntity[KampKlarCoordinator], CalendarEntity):
    """A KampKlar calendar entity for a tracked person."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KampKlarCoordinator, person_id: int, person_name: str) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._person_id = person_id
        self._attr_unique_id = f"{person_id}_calendar"
        self._attr_name = "Kalender"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(person_id))},
            name=person_name or f"Person {person_id}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _activities(self) -> list[Activity]:
        """Return activities for this person."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get(self._person_id, [])

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        now = dt_util.now()
        for act in self._activities:
            end = _end_time(act)
            if end > now:
                return _activity_to_event(act)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Expose signup status of the current event for automations."""
        now = dt_util.now()
        for act in self._activities:
            end = _end_time(act)
            if end > now:
                return {
                    "signup_status": act.signup_status_name,
                    "signup_status_id": act.signup_status_id,
                    "activity_type": act.type_name,
                    "team": act.team_name,
                }
        return {}

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a date range."""
        events = []
        for act in self._activities:
            start = dt_util.as_local(act.start_time)
            end = _end_time(act)
            if end >= start_date and start < end_date:
                events.append(_activity_to_event(act))
        return events
