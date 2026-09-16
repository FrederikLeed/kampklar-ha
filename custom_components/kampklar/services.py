"""KampKlar services: tilmeld / afmeld an activity."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import KampKlarApiError
from .const import (
    ATTR_ACTIVITY_ID,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DOMAIN,
    SERVICE_SIGN_OFF,
    SERVICE_SIGN_UP,
    SIGNUP_SIGNED_OFF,
    SIGNUP_SIGNED_UP,
)

# Target the child as a device (or any of its entities). person_id stays accepted for
# existing automations; activity_id defaults to the child's next activity.
_SERVICE_SCHEMA = vol.Schema(
    {
        **cv.TARGET_SERVICE_FIELDS,
        vol.Optional(CONF_PERSON_ID): vol.Coerce(int),
        vol.Optional(ATTR_ACTIVITY_ID): vol.Coerce(int),
    }
)

_STATUS_TEXT = {SIGNUP_SIGNED_UP: "tilmeldt", SIGNUP_SIGNED_OFF: "afmeldt"}


def _as_list(value: Any, what: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # "all" / "none" style targets are not meaningful for signing a child up.
        raise ServiceValidationError(f"Choose specific KampKlar children as {what}")
    return list(value)


def _person_ids(hass: HomeAssistant, call: ServiceCall) -> list[int]:
    """Resolve the targeted children from devices, their entities, or a raw person_id."""
    person_ids: list[int] = []
    if CONF_PERSON_ID in call.data:
        person_ids.append(call.data[CONF_PERSON_ID])

    device_ids = _as_list(call.data.get(ATTR_DEVICE_ID), "devices")
    entity_registry = er.async_get(hass)
    for value in _as_list(call.data.get(ATTR_ENTITY_ID), "entities"):
        entity_id = er.async_resolve_entity_id(entity_registry, value)
        entry = entity_registry.async_get(entity_id) if entity_id else None
        if entry is None or entry.platform != DOMAIN or entry.device_id is None:
            raise ServiceValidationError(f"{value} is not a KampKlar entity")
        device_ids.append(entry.device_id)

    device_registry = dr.async_get(hass)
    for device_id in device_ids:
        device = device_registry.async_get(device_id)
        ids = [int(ident) for domain, ident in (device.identifiers if device else ()) if domain == DOMAIN]
        if not ids:
            raise ServiceValidationError(f"Device {device_id} is not a KampKlar child")
        person_ids.extend(ids)

    return list(dict.fromkeys(person_ids))


def _find_entry(hass: HomeAssistant, person_id: int):
    """Return (coordinator, user_id, name) for the config entry tracking this person."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        for person in entry.data.get(CONF_PERSONS, []):
            if int(person[CONF_PERSON_ID]) == person_id:
                return entry.runtime_data, entry.data.get("user_id"), person.get(CONF_PERSON_NAME) or None
    return None, None, None


async def _async_set_status(hass: HomeAssistant, call: ServiceCall, status_id: int) -> dict[str, Any]:
    person_ids = _person_ids(hass, call)
    if not person_ids:
        raise ServiceValidationError("Choose the KampKlar child to sign up or off")

    results: list[dict[str, Any]] = []
    coordinators = {}
    for person_id in person_ids:
        coordinator, user_id, name = _find_entry(hass, person_id)
        if coordinator is None or user_id is None:
            raise ServiceValidationError(f"No KampKlar person configured with id {person_id}")

        activities = (coordinator.data or {}).get(person_id, [])
        activity_id = call.data.get(ATTR_ACTIVITY_ID)
        if activity_id is None:
            if not activities:
                raise ServiceValidationError(f"{name or person_id} has no upcoming activity")
            activity = activities[0]
            activity_id = activity.activity_id
        else:
            activity = next((a for a in activities if a.activity_id == activity_id), None)

        try:
            await coordinator.client.set_signup_status(activity_id, person_id, status_id, int(user_id))
        except KampKlarApiError as err:
            raise HomeAssistantError(f"KampKlar rejected the change: {err}") from err

        results.append(
            {
                "person": name,
                "activity_id": activity_id,
                "activity": activity.name.strip() if activity else None,
                "start_time": activity.start_time.isoformat() if activity else None,
                "status": _STATUS_TEXT[status_id],
            }
        )
        coordinators[id(coordinator)] = coordinator

    for coordinator in coordinators.values():
        await coordinator.async_request_refresh()
    return {"results": results}


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the KampKlar services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SIGN_UP):
        return

    async def _tilmeld(call: ServiceCall) -> ServiceResponse:
        result = await _async_set_status(hass, call, SIGNUP_SIGNED_UP)
        return result if call.return_response else None

    async def _afmeld(call: ServiceCall) -> ServiceResponse:
        result = await _async_set_status(hass, call, SIGNUP_SIGNED_OFF)
        return result if call.return_response else None

    for service, handler in ((SERVICE_SIGN_UP, _tilmeld), (SERVICE_SIGN_OFF, _afmeld)):
        hass.services.async_register(
            DOMAIN, service, handler, schema=_SERVICE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
        )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry is unloaded."""
    if any(hass.config_entries.async_entries(DOMAIN)):
        return
    hass.services.async_remove(DOMAIN, SERVICE_SIGN_UP)
    hass.services.async_remove(DOMAIN, SERVICE_SIGN_OFF)
