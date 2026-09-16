"""Calendar platform for KampKlar."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Activity, MatchVenue
from .const import (
    ACTIVITY_TYPE_MATCH,
    ACTIVITY_TYPE_PRACTICE_MATCH,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_START_AT_MEETING_TIME,
    DEFAULT_START_AT_MEETING_TIME,
    DOMAIN,
    is_udtaget,
)
from .coordinator import KampKlarCoordinator

type KampKlarConfigEntry = ConfigEntry[KampKlarCoordinator]

# Default event duration when end_time is missing
_DEFAULT_DURATION = timedelta(hours=1, minutes=30)

_MATCH_TYPES = (ACTIVITY_TYPE_MATCH, ACTIVITY_TYPE_PRACTICE_MATCH)


def _end_time(act: Activity) -> datetime:
    """Return the end time for an activity, with fallback default duration."""
    if act.end_time:
        return dt_util.as_local(act.end_time)
    return dt_util.as_local(act.start_time) + _DEFAULT_DURATION


def _start_time(act: Activity, start_at_meeting: bool) -> datetime:
    """Return the event start: the meeting time when start_at_meeting is set and one is known."""
    meeting = act.effective_meeting_time if start_at_meeting else None
    return dt_util.as_local(meeting or act.start_time)


def _clock(value: datetime) -> str:
    """Format a time of day as HH:MM in local time."""
    return dt_util.as_local(value).strftime("%H:%M")


def _map_link(venue: MatchVenue) -> str:
    """Return an Apple Maps link that pins the venue: tappable on phones and parseable by other tools."""
    return f"https://maps.apple.com/?ll={venue.latitude},{venue.longitude}&q={quote(venue.name, safe='')}"


def _activity_to_event(act: Activity, start_at_meeting: bool = False) -> CalendarEvent:
    """Convert an Activity to a CalendarEvent.

    When the person is udtaget (selected/called up) for a match, the event title is
    marked so it stands out in the calendar. An activity with a known venue uses its address
    as the location. With start_at_meeting the event starts at the meeting time (when
    known) and the description names the real start.
    """
    start = _start_time(act, start_at_meeting)
    end = _end_time(act)

    summary = act.name
    if is_udtaget(act.signup_status_id):
        summary = f"⭐ Udtaget: {act.name}"

    venue = act.venue
    venue_address = venue.formatted_address if venue else ""
    description_parts: list[str] = []
    if (meeting := act.effective_meeting_time) is not None:
        description_parts.append(f"Mødetid: {_clock(meeting)}")
        if start_at_meeting:
            label = "Kampstart" if act.match is not None or act.type_id in _MATCH_TYPES else "Start"
            description_parts.append(f"{label}: {_clock(act.start_time)}")
    # The venue takes the location, so a meeting place elsewhere (the clubhouse before an away match) goes here.
    place = act.meeting_place
    if venue and venue_address and place and place.casefold() not in (venue.name.casefold(), venue_address.casefold()):
        description_parts.append(f"Mødested: {place}")
    description_parts.append(f"Type: {act.type_name}")
    if act.team_name:
        description_parts.append(f"Hold: {act.team_name}")
    if act.signup_status_name:
        description_parts.append(f"Status: {act.signup_status_name}")
    if act.subscribed:
        description_parts.append(f"Tilmeldte: {act.subscribed}")
    if act.match:
        stadium = venue_address or act.match.stadium_name
        if stadium:
            description_parts.append(f"Stadion: {stadium}")
        field = act.match.field_name or (venue.field_name if venue else "")
        if field:
            description_parts.append(f"Bane: {field}")
    if venue is not None and venue.has_coordinates:
        description_parts.append(f"Kort: {_map_link(venue)}")

    # A stævne whose stadium the register does not place still names it, which beats no location at all.
    location = (venue.location_text if venue else "") or act.meeting_place or act.stadium_name or None

    return CalendarEvent(
        summary=summary,
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
        self._attr_translation_key = "calendar"
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
    def _start_at_meeting(self) -> bool:
        """Return whether events start at the meeting time (an entry option)."""
        options = self.coordinator.config_entry.options
        return bool(options.get(CONF_START_AT_MEETING_TIME, DEFAULT_START_AT_MEETING_TIME))

    def _current_activity(self, upcoming: list[Activity]) -> Activity | None:
        """Return the upcoming activity whose event starts first: the one running now, or else the next.

        Events can start at the meeting time, so the feed's order (by real start) is not the event order.
        """
        start_at_meeting = self._start_at_meeting
        return min(upcoming, key=lambda act: _start_time(act, start_at_meeting), default=None)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        act = self._current_activity([a for a in self._activities if _end_time(a) > now])
        return _activity_to_event(act, self._start_at_meeting) if act is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None]:
        """Expose signup status of the current event plus the next call-up, for automations."""
        now = dt_util.now()
        upcoming = [a for a in self._activities if _end_time(a) > now]
        attrs: dict[str, str | int | bool | None] = {}
        if (act := self._current_activity(upcoming)) is not None:
            attrs = {
                "signup_status": act.signup_status_name,
                "signup_status_id": act.signup_status_id,
                "activity_type": act.type_name,
                "team": act.team_name,
                "is_udtaget": is_udtaget(act.signup_status_id),
            }
        # Next activity the person is udtaget (called up) for, so an automation can notify.
        next_udtaget = next((a for a in upcoming if is_udtaget(a.signup_status_id)), None)
        attrs["next_udtaget"] = next_udtaget.name if next_udtaget else None
        attrs["next_udtaget_start"] = dt_util.as_local(next_udtaget.start_time).isoformat() if next_udtaget else None
        return attrs

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a date range."""
        start_at_meeting = self._start_at_meeting
        events = []
        for act in self._activities:
            start = _start_time(act, start_at_meeting)
            end = _end_time(act)
            if end >= start_date and start < end_date:
                events.append(_activity_to_event(act, start_at_meeting))
        return events
