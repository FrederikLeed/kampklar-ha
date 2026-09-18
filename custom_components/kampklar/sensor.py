"""Sensor platform for KampKlar."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Activity
from .const import (
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DOMAIN,
    SIGNUP_NOT_RESPONDED,
    is_playing,
)
from .coordinator import KampKlarCoordinator

type KampKlarConfigEntry = ConfigEntry[KampKlarCoordinator]


def _next_activity(activities: list[Activity]) -> Activity | None:
    """Return the next upcoming activity."""
    return activities[0] if activities else None


def _next_match(activities: list[Activity]) -> Activity | None:
    """Return the next upcoming match (league match or practice match, anything with match details)."""
    for act in activities:
        if act.match is not None:
            return act
    return None


def _next_udtaget(activities: list[Activity]) -> Activity | None:
    """Return the next match or tournament the person is expected at.

    That is udtaget where a coach picks the squad, and tilmeldt where people sign up instead, since
    such an activity never reaches udtaget (see const.is_playing).
    """
    for act in activities:
        if is_playing(act):
            return act
    return None


def _mode_name(act: Activity) -> str | None:
    """Name how an activity picks its players, for the attribute: udtagelse, tilmelding or unknown."""
    if act.selection_mode is None:
        return None
    return "udtagelse" if act.selection_mode else "tilmelding"


def _pending_signups(activities: list[Activity]) -> list[Activity]:
    """Return activities with unanswered signup.

    The live API leaves signupStatusId null for activities nobody has answered, so an
    open activity without a status counts as pending too.
    """
    return [
        a
        for a in activities
        if a.signup_status_id == SIGNUP_NOT_RESPONDED or (a.signup_status_id is None and a.is_open_for_signup)
    ]


def _activity_attributes(act: Activity | None, *, with_venue: bool = False) -> dict[str, Any]:
    """Build attribute dict for an activity sensor.

    with_venue is for the next match and next call-up sensors. It adds the venue (stadium_address,
    latitude, longitude) so a map card can show it, and gives meeting_time repaired like the calendar does
    (Activity.effective_meeting_time). Without it meeting_time stays as DBU sent it, as before 0.7.0.
    """
    if act is None:
        return {}
    attrs: dict[str, Any] = {
        "activity_id": act.activity_id,
        "type": act.type_name,
        "start_time": act.start_time.isoformat(),
        "team": act.team_name,
        "club": act.club_name,
        "signup_status": act.signup_status_name,
        "subscribed": act.subscribed,
        "person": act.person_contact_name,
        "is_open_for_signup": act.is_open_for_signup,
        # How this activity picks players, and whether the child is on it, so a dashboard or an
        # automation can tell a match the child plays from one nobody has answered.
        "selection_mode": _mode_name(act),
        "is_playing": is_playing(act),
    }
    if act.end_time:
        attrs["end_time"] = act.end_time.isoformat()
    if (meeting := act.effective_meeting_time if with_venue else act.meeting_time) is not None:
        attrs["meeting_time"] = meeting.isoformat()
    if act.meeting_place:
        attrs["meeting_place"] = act.meeting_place
    if act.subscription_deadline:
        attrs["subscription_deadline"] = act.subscription_deadline.isoformat()
    if act.team_assignment_name:
        attrs["team_assignment"] = act.team_assignment_name
    if act.tasks:
        attrs["tasks"] = act.tasks
    if act.club_logo_url:
        attrs["club_logo"] = act.club_logo_url
    if act.match:
        attrs["match_id"] = act.match.match_id
        attrs["stadium"] = act.match.stadium_name
        attrs["field"] = act.match.field_name
        attrs["home_team"] = act.match.home_team_name
        attrs["away_team"] = act.match.away_team_name
        if act.match.home_team_logo_url:
            attrs["home_logo"] = act.match.home_team_logo_url
        if act.match.away_team_logo_url:
            attrs["away_logo"] = act.match.away_team_logo_url
        if act.match.row_name:
            attrs["row"] = act.match.row_name
    elif act.stadium_name:
        # A stævne has no match object; its round names the stadium.
        attrs["stadium"] = act.stadium_name
    if with_venue and act.venue is not None:
        if act.venue.formatted_address:
            attrs["stadium_address"] = act.venue.formatted_address
        if act.venue.has_coordinates:
            attrs["latitude"] = act.venue.latitude
            attrs["longitude"] = act.venue.longitude
    return attrs


@dataclass(frozen=True, kw_only=True)
class KampKlarSensorDescription(SensorEntityDescription):
    """Sensor entity description for KampKlar."""

    value_fn: Callable[[list[Activity]], str | int | None]
    attr_fn: Callable[[list[Activity]], dict[str, Any]]


SENSOR_DESCRIPTIONS: tuple[KampKlarSensorDescription, ...] = (
    KampKlarSensorDescription(
        key="next_activity",
        translation_key="next_activity",
        value_fn=lambda acts: a.name if (a := _next_activity(acts)) else None,
        attr_fn=lambda acts: _activity_attributes(_next_activity(acts)),
    ),
    KampKlarSensorDescription(
        key="next_match",
        translation_key="next_match",
        value_fn=lambda acts: (
            f"{a.match.home_team_name} - {a.match.away_team_name}" if (a := _next_match(acts)) and a.match else None
        ),
        attr_fn=lambda acts: _activity_attributes(_next_match(acts), with_venue=True),
    ),
    KampKlarSensorDescription(
        key="pending_signups",
        translation_key="pending_signups",
        value_fn=lambda acts: len(_pending_signups(acts)),
        attr_fn=lambda acts: {"activities": [a.name for a in _pending_signups(acts)]},
    ),
    KampKlarSensorDescription(
        key="next_udtagelse",
        translation_key="next_udtagelse",
        value_fn=lambda acts: a.name if (a := _next_udtaget(acts)) else None,
        attr_fn=lambda acts: _activity_attributes(_next_udtaget(acts), with_venue=True),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KampKlarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KampKlar sensors from a config entry."""
    coordinator = entry.runtime_data
    persons: list[dict] = entry.data[CONF_PERSONS]

    entities: list[SensorEntity] = []
    for person in persons:
        person_id = person[CONF_PERSON_ID]
        person_name = person[CONF_PERSON_NAME]
        for desc in SENSOR_DESCRIPTIONS:
            entities.append(KampKlarSensor(coordinator, desc, person_id, person_name))
        entities.append(KampKlarLiveMatchSensor(coordinator, person_id, person_name))

    async_add_entities(entities)


class KampKlarSensor(CoordinatorEntity[KampKlarCoordinator], SensorEntity):
    """A KampKlar sensor entity."""

    entity_description: KampKlarSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KampKlarCoordinator,
        description: KampKlarSensorDescription,
        person_id: int,
        person_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._person_id = person_id
        self._attr_unique_id = f"{person_id}_{description.key}"
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
    def native_value(self) -> str | int | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._activities)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self.entity_description.attr_fn(self._activities)


class KampKlarLiveMatchSensor(CoordinatorEntity[KampKlarCoordinator], SensorEntity):
    """Live score for the tracked person's current match.

    The state is the score line while a match is live (or its result afterwards),
    otherwise unknown. Details (teams, minute, events) are in the attributes.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "live_match"

    def __init__(self, coordinator: KampKlarCoordinator, person_id: int, person_name: str) -> None:
        """Initialize the live-match sensor."""
        super().__init__(coordinator)
        self._person_id = person_id
        self._attr_unique_id = f"{person_id}_live_match"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(person_id))},
            name=person_name or f"Person {person_id}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _match(self):
        return self.coordinator.live_matches.get(self._person_id)

    @property
    def native_value(self) -> str | None:
        """Return the score line, or a status when the match has no score yet."""
        match = self._match
        if match is None:
            return None
        if match.home_score is not None and match.away_score is not None:
            return f"{match.home_score} - {match.away_score}"
        return "Ikke startet"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the live-match details."""
        match = self._match
        if match is None:
            return None
        return {
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_logo": match.home_logo,
            "away_logo": match.away_logo,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "minute": match.current_minute,
            "is_live": match.is_live,
            "status": match.status_text,
            "match_length": match.match_length_text,
            "stadium": match.stadium,
            "kickoff": match.kickoff.isoformat() if match.kickoff else None,
            "events": [
                {
                    "minute": e.minute,
                    "type": e.type_name,
                    "team": "home" if e.is_home else "away",
                    "player": e.player,
                    "is_goal": e.is_goal,
                    "is_card": e.is_card,
                }
                for e in match.events
            ],
        }
