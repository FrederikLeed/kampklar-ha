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
    ACTIVITY_TYPE_MATCH,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DOMAIN,
    SIGNUP_NOT_RESPONDED,
)
from .coordinator import KampKlarCoordinator

type KampKlarConfigEntry = ConfigEntry[KampKlarCoordinator]


def _next_activity(activities: list[Activity]) -> Activity | None:
    """Return the next upcoming activity."""
    return activities[0] if activities else None


def _next_match(activities: list[Activity]) -> Activity | None:
    """Return the next upcoming match."""
    for act in activities:
        if act.type_id == ACTIVITY_TYPE_MATCH:
            return act
    return None


def _pending_signups(activities: list[Activity]) -> list[Activity]:
    """Return activities with unanswered signup."""
    return [a for a in activities if a.signup_status_id == SIGNUP_NOT_RESPONDED]


def _activity_attributes(act: Activity | None) -> dict[str, Any]:
    """Build attribute dict for an activity sensor."""
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
    }
    if act.end_time:
        attrs["end_time"] = act.end_time.isoformat()
    if act.meeting_time:
        attrs["meeting_time"] = act.meeting_time.isoformat()
    if act.meeting_place:
        attrs["meeting_place"] = act.meeting_place
    if act.match:
        attrs["match_id"] = act.match.match_id
        attrs["stadium"] = act.match.stadium_name
        attrs["field"] = act.match.field_name
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
        name="Naeste aktivitet",
        value_fn=lambda acts: a.name if (a := _next_activity(acts)) else None,
        attr_fn=lambda acts: _activity_attributes(_next_activity(acts)),
    ),
    KampKlarSensorDescription(
        key="next_match",
        translation_key="next_match",
        name="Naeste kamp",
        value_fn=lambda acts: (
            f"{a.match.home_team_name} - {a.match.away_team_name}" if (a := _next_match(acts)) and a.match else None
        ),
        attr_fn=lambda acts: _activity_attributes(_next_match(acts)),
    ),
    KampKlarSensorDescription(
        key="pending_signups",
        translation_key="pending_signups",
        name="Afventende tilmeldinger",
        value_fn=lambda acts: len(_pending_signups(acts)),
        attr_fn=lambda acts: {"activities": [a.name for a in _pending_signups(acts)]},
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

    entities: list[KampKlarSensor] = []
    for person in persons:
        person_id = person[CONF_PERSON_ID]
        person_name = person[CONF_PERSON_NAME]
        for desc in SENSOR_DESCRIPTIONS:
            entities.append(KampKlarSensor(coordinator, desc, person_id, person_name))

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
