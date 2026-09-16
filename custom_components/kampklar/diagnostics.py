"""Diagnostics support for KampKlar."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import KampKlarConfigEntry
from .const import CONF_PERSONS

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "user_id", CONF_PERSONS}

# Personal fields left out of activities and live matches. A match venue keeps its name and field,
# which the match already shows, but not its street address or coordinates: next to a child's
# schedule they would place the child on a map.
_DROP = {"person_contact_id", "person_contact_name", "player", "address", "zip", "city", "latitude", "longitude"}


def _plain(value: Any) -> Any:
    """Make coordinator data JSON-friendly, dropping personal fields."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value) if f.name not in _DROP}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if k not in _DROP}
    return value


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: KampKlarConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry with credentials and personal data removed."""
    coordinator = entry.runtime_data
    # Coordinator data is keyed by person id, so export a list with neutral labels
    # instead of the dict itself: the redactor only masks values, never keys.
    persons = [
        {
            "person": f"person_{index}",
            "activity_count": len(activities),
            "activities": _plain(activities),
            "live_match": _plain(coordinator.live_matches.get(person_id)),
        }
        for index, (person_id, activities) in enumerate((coordinator.data or {}).items(), start=1)
    ]
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
        "persons": persons,
    }
